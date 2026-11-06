"""Durable case orchestration around the eight existing engines.

Stage outputs are immutable snapshots. Retry creates a new run and reuses only
successful, version-matched stages from this case and this evidence item.
"""
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from sqlalchemy import func
from app.models.case import Case
from app.models.intelligence import CasePipelineRun, PipelineStage
from app.models.pipeline import (EvidenceFile, OCRExtractionRecord, ForensicEntityRecord,
    CorrelationRecord, TemporalRecord, TODEstimationRecord, AnomalyDetectionRecord, ExtractionStatus)
from app.pipeline.extraction.engine import ExtractionEngine
from app.pipeline.extraction.schemas import ExtractionEnvelope
from app.pipeline.structuring.engine import StructuringEngine
from app.pipeline.structuring.schemas import ForensicEntityGraph
from app.pipeline.normalization.engine import NormalizationEngine
from app.pipeline.ingestion.ocr.schemas import DocumentOCRResult
from app.pipeline.ingestion.checksum import compute_checksums_from_file
from app.pipeline.correlation.engine import CorrelationEngine
from app.pipeline.correlation.schemas import CorrelationGraph
from app.pipeline.temporal.engine import TemporalEngine
from app.pipeline.temporal.schemas import ForensicTimeline
from app.pipeline.tod_estimation.engine import TODEstimationEngine
from app.pipeline.tod_estimation.schemas import TODEstimationResult
from app.pipeline.anomaly_detection.engine import AnomalyDetectionEngine
from app.services.document_reader import read_document
from app.services.intelligence_audit import audit

VERSION = '2.0.4'
DOCUMENT_STAGES = ('acquisition', 'ocr', 'extraction', 'structuring', 'normalization')
CASE_STAGES = ('correlation', 'temporal', 'tod', 'anomalies')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def utcnow():
    return datetime.now(timezone.utc)


def stage_failures(output):
    reports = output.get('stage_reports', [])
    return [r.get('error') or r.get('stage') or r.get('stage_name') for r in reports
            if r.get('status', '').upper() in ('FAILED', 'PARTIAL')]


class CasePipelineOrchestrator:
    def __init__(self, db):
        self.db = db

    def enqueue(self, case_id, user_id, request_key=None, retry_of=None):
        case_id = uuid.UUID(str(case_id))
        # Serializes version allocation and evidence snapshots per investigation.
        self.db.query(Case).filter(Case.id == case_id).with_for_update().one()
        files = self.db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id,
            EvidenceFile.is_deleted.is_(False)).order_by(EvidenceFile.id).all()
        if not files:
            raise ValueError('Upload evidence before starting analysis')
        fingerprint = digest([VERSION, [(str(f.id), f.sha256_hash, f.version) for f in files]])
        key = request_key or fingerprint
        existing = self.db.query(CasePipelineRun).filter_by(case_id=case_id, request_key=key).first()
        if existing:
            if existing.fingerprint != fingerprint:
                raise ValueError('Idempotency key belongs to a different evidence snapshot')
            self.db.commit()
            return existing
        if retry_of:
            previous = self.db.query(CasePipelineRun).filter_by(id=retry_of, case_id=case_id).one()
            if previous.status in ('QUEUED', 'PROCESSING'):
                raise ValueError('The previous run is still active')
        version = (self.db.query(func.max(CasePipelineRun.version)).filter_by(case_id=case_id).scalar() or 0) + 1
        run = CasePipelineRun(case_id=case_id, requested_by=user_id, version=version,
            fingerprint=fingerprint, request_key=key, evidence_ids=[str(f.id) for f in files], retry_of=retry_of)
        self.db.add(run)
        self.db.flush()
        for evidence in files:
            for name in DOCUMENT_STAGES:
                self.db.add(PipelineStage(run_id=run.id, scope=str(evidence.id), name=name,
                    cache_key=digest([VERSION, str(case_id), str(evidence.id), evidence.sha256_hash, evidence.version, name])))
        for name in CASE_STAGES:
            self.db.add(PipelineStage(run_id=run.id, scope='case', name=name,
                cache_key=digest([fingerprint, name])))
        audit(self.db, user_id, case_id, 'PIPELINE_QUEUED', {'run_id': str(run.id), 'version': version})
        self.db.commit()
        return run

    def _stage(self, run, scope, name, operation, dependency_ok=True, reuse=True):
        stage = self.db.query(PipelineStage).filter_by(run_id=run.id, scope=scope, name=name).one()
        if not dependency_ok:
            stage.status = 'SKIPPED'
            stage.error = 'Required upstream stage failed or produced partial output; retry after review'
            self.db.commit()
            return None
        if reuse:
            cached = self.db.query(PipelineStage).join(CasePipelineRun, PipelineStage.run_id == CasePipelineRun.id).filter(
                CasePipelineRun.case_id == run.case_id, PipelineStage.cache_key == stage.cache_key,
                PipelineStage.status == 'SUCCEEDED', PipelineStage.run_id != run.id).order_by(PipelineStage.completed_at.desc()).first()
            if cached:
                stage.status, stage.output, stage.record_id = 'SUCCEEDED', cached.output, cached.record_id
                stage.reused_from, stage.completed_at = cached.id, utcnow()
                self.db.commit()
                return stage.output
        stage.status, stage.started_at = 'RUNNING', utcnow()
        self.db.commit()
        started = time.monotonic()
        try:
            output, record_id = operation()
            failures = stage_failures(output)
            stage.status = 'PARTIAL' if failures or output.get('status') in ('PARTIAL', 'FAILED') or output.get('stages_failed') else 'SUCCEEDED'
            stage.output, stage.record_id = output, record_id
            stage.warnings = failures + output.get('warnings', [])
            if stage.status == 'PARTIAL':
                stage.error = 'Engine reported incomplete stages: ' + '; '.join(str(x) for x in failures or output.get('stages_failed', []))
        except Exception as exc:
            self.db.rollback()
            stage = self.db.get(PipelineStage, stage.id)
            stage.status, stage.error = 'FAILED', f'{type(exc).__name__}: {exc}'
        stage.duration_ms = round((time.monotonic() - started) * 1000, 2)
        stage.completed_at = utcnow()
        self.db.commit()
        return stage.output if stage.status == 'SUCCEEDED' else None

    def execute(self, run_id):
        run = self.db.get(CasePipelineRun, run_id)
        if run.status != 'QUEUED':
            return run
        run.status = 'PROCESSING'
        self.db.commit()
        try:
            graphs = []
            for eid in run.evidence_ids:
                evidence = self.db.query(EvidenceFile).filter_by(id=uuid.UUID(eid), case_id=run.case_id).one()
                acquired = self._stage(run, eid, 'acquisition', lambda: self._verify(evidence), reuse=False)
                ocr = self._stage(run, eid, 'ocr', lambda: (read_document(evidence.storage_path, eid, evidence.mime_type).model_dump(mode='json'), None), bool(acquired))
                extracted = self._stage(run, eid, 'extraction', lambda: self._extract(ocr, eid), bool(ocr))
                structured = self._stage(run, eid, 'structuring', lambda: self._structure(extracted, eid), bool(extracted))
                normalized = self._stage(run, eid, 'normalization', lambda: self._normalize(structured, eid), bool(structured))
                if structured and normalized:
                    graphs.append((eid, ForensicEntityGraph.model_validate(structured['entity_graph'])))
            # Partial cases are explicit: case analyses use only fully processed evidence.
            omitted = sorted(set(run.evidence_ids) - {eid for eid, _ in graphs})
            run.warnings = [f'Evidence excluded from case analysis due to failed processing: {eid}' for eid in omitted]
            self.db.commit()
            corr = self._stage(run, 'case', 'correlation', lambda: self._persist(
                CorrelationRecord, 'correlation_graph', CorrelationEngine().correlate(graphs, case_id=str(run.case_id)), run), bool(graphs), reuse=False)
            correlation = CorrelationGraph.model_validate(corr) if corr else None
            temporal = self._stage(run, 'case', 'temporal', lambda: self._persist(
                TemporalRecord, 'forensic_timeline', TemporalEngine().build_timeline(graphs, correlation, str(run.case_id)), run), bool(corr), reuse=False)
            timeline = ForensicTimeline.model_validate(temporal) if temporal else None
            tod = self._stage(run, 'case', 'tod', lambda: self._persist(
                TODEstimationRecord, 'tod_estimation_result', TODEstimationEngine().estimate(graphs, correlation, timeline, str(run.case_id)), run), bool(temporal), reuse=False)
            estimate = TODEstimationResult.model_validate(tod) if tod else None
            self._stage(run, 'case', 'anomalies', lambda: self._persist(
                AnomalyDetectionRecord, 'anomaly_report', AnomalyDetectionEngine().detect(graphs, correlation, timeline, estimate, str(run.case_id)), run), bool(tod), reuse=False)
            stages = self.db.query(PipelineStage).filter_by(run_id=run.id).all()
            run.status = 'COMPLETED' if all(s.status == 'SUCCEEDED' for s in stages) else ('PARTIAL' if graphs else 'FAILED')
            run.changes = self._changes(run)
        except Exception as exc:
            self.db.rollback()
            run.status, run.error = 'FAILED', f'{type(exc).__name__}: {exc}'
        for stage in self.db.query(PipelineStage).filter(PipelineStage.run_id == run.id, PipelineStage.status.in_(['PENDING', 'RUNNING'])):
            stage.status, stage.error = 'SKIPPED', 'Run interrupted: ' + (run.error or 'dependency unavailable')
        run.completed_at = utcnow()
        audit(self.db, run.requested_by, run.case_id, 'PIPELINE_' + run.status, {'run_id': str(run.id), 'version': run.version})
        self.db.commit()
        return run

    def _verify(self, evidence):
        checksum = compute_checksums_from_file(evidence.storage_path)
        if checksum.sha256 != evidence.sha256_hash:
            raise ValueError('SHA-256 mismatch: original evidence integrity check failed')
        return {'evidence_id': str(evidence.id), 'sha256': checksum.sha256, 'verified': True}, evidence.id

    def _extract(self, ocr, eid):
        output = ExtractionEngine(self.db).extract(DocumentOCRResult.model_validate(ocr), eid)
        return output, uuid.UUID(output['extraction_id'])

    def _structure(self, extracted, eid):
        output = StructuringEngine(self.db).structure(ExtractionEnvelope.model_validate(extracted['envelope']), eid)
        record = self.db.get(ForensicEntityRecord, uuid.UUID(output['structuring_id']))
        record.ocr_extraction_id = uuid.UUID(extracted['extraction_id'])
        self.db.commit()
        return output, record.id

    def _normalize(self, structured, eid):
        output = NormalizationEngine(self.db, entity_graph=structured['entity_graph']).normalize(eid)
        return output, uuid.UUID(output['normalization_id'])

    def _persist(self, model, field, output, run):
        data = output.model_dump(mode='json')
        record = model(case_id=run.case_id, evidence_file_ids=data.get('evidence_file_ids', []),
            status=ExtractionStatus.PARTIAL if stage_failures(data) else ExtractionStatus.COMPLETED,
            schema_version=data.get('schema_version', '1.0.0'), completed_at=utcnow(), **{field: data})
        record.stages_failed = stage_failures(data)
        record.stages_completed = [s.get('stage', s.get('stage_name')) for s in data.get('stage_reports', []) if s.get('status') == 'completed']
        record.processing_time_ms = data.get('processing_time_ms', 0)
        for column, stage_name in [('correlation_id', 'correlation'), ('temporal_id', 'temporal'), ('tod_estimation_id', 'tod')]:
            if hasattr(model, column):
                parent = self.db.query(PipelineStage).filter_by(run_id=run.id, scope='case', name=stage_name).one()
                setattr(record, column, parent.record_id)
        counts = {'cluster_count':'entity_clusters', 'edge_count':'relationship_edges',
            'contradiction_count':'contradictions', 'evidence_group_count':'evidence_groups',
            'event_count':'temporal_events', 'relation_count':'temporal_relations',
            'tod_candidate_count':'tod_candidates', 'candidate_count':'tod_candidates',
            'signal_count':'supporting_signals', 'anomaly_count':'anomalies'}
        for column, key in counts.items():
            if hasattr(model, column):
                setattr(record, column, len(data.get(key, [])))
        if hasattr(model, 'conflict_count'):
            record.conflict_count = len(data.get('temporal_conflicts', data.get('signal_conflicts', [])))
        severity = data.get('severity_summary', {})
        for level in ('critical', 'high'):
            if hasattr(model, level + '_count'):
                setattr(record, level + '_count', severity.get(level, 0))
        record.overall_confidence = data.get('confidence_summary', data.get('confidence_scores', {})).get('overall_confidence', 0)
        self.db.add(record)
        self.db.commit()
        return data, record.id

    def _changes(self, run):
        previous = self.db.query(CasePipelineRun).filter(CasePipelineRun.case_id == run.case_id,
            CasePipelineRun.version < run.version).order_by(CasePipelineRun.version.desc()).first()
        def signatures(rid):
            stage = self.db.query(PipelineStage).filter_by(run_id=rid, name='anomalies', scope='case').first()
            output = stage.output or {} if stage else {}
            return {digest([f.get('description'), f.get('rule_id'), f.get('category')]): f.get('description', '')
                for key in ('anomalies', 'contradictions') for f in output.get(key, [])}
        before = signatures(previous.id) if previous else {}
        after = signatures(run.id)
        return {'previous_run_id': str(previous.id) if previous else None,
            'new_evidence_ids': sorted(set(run.evidence_ids) - set(previous.evidence_ids if previous else [])),
            'added_findings': [after[k] for k in after.keys() - before.keys()],
            'removed_findings': [before[k] for k in before.keys() - after.keys()]}
