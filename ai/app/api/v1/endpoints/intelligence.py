import json
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from app.core.database import get_db
from app.api.dependencies.case_access import current_investigator, require_case, allowed_cases
from app.models.intelligence import CasePipelineRun, FindingReview, HypothesisRevision
from app.models.pipeline import EvidenceFile, AcquisitionLog
from app.models.evidence import Evidence
from app.models.audit_log import AuditLog
from app.pipeline.ingestion.engine import IngestionEngine
from app.pipeline.ingestion.checksum import compute_checksums_from_file
from app.services.case_pipeline_orchestrator import CasePipelineOrchestrator
from app.services.case_intelligence import snapshot, row_json, targets, answer_question, hypotheses
from app.services.intelligence_audit import audit
from app.exceptions.pipeline import AtopsyBaseError

router = APIRouter(prefix='/api/v1/intelligence', tags=['Case intelligence'])


def ok(data):
    return {'success': True, 'data': data}


class RunRequest(BaseModel):
    request_key: str | None = Field(None, min_length=1, max_length=128)
    retry_of: uuid.UUID | None = None


class ReviewRequest(BaseModel):
    run_id: uuid.UUID
    target_id: str = Field(min_length=1, max_length=200)
    state: Literal['DETECTED', 'UNDER_REVIEW', 'ACCEPTED', 'DISMISSED', 'CORRECTED', 'RESOLVED']
    note: str = Field(min_length=1, max_length=10000)
    correction: str | None = Field(None, max_length=10000)


class Assessment(BaseModel):
    run_id: uuid.UUID
    target_id: str
    assessment: Literal['CONSISTENT', 'INCONSISTENT', 'NEUTRAL', 'UNKNOWN']
    note: str = Field(default='', max_length=10000)


class HypothesisRequest(BaseModel):
    hypothesis_id: uuid.UUID | None = None
    description: str = Field(min_length=1, max_length=10000)
    notes: str = Field(default='', max_length=10000)
    status: Literal['DRAFT', 'UNDER_REVIEW', 'REVIEWED'] = 'DRAFT'
    assessments: list[Assessment] = Field(default_factory=list, max_length=1000)


class Question(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    run_id: uuid.UUID | None = None


@router.get('/dashboard')
def dashboard(db=Depends(get_db), user=Depends(current_investigator)):
    cases = allowed_cases(db, user).all()
    ids = [c.id for c in cases]
    runs = db.query(CasePipelineRun).filter(CasePipelineRun.case_id.in_(ids)).all()
    latest = {}
    for run in sorted(runs, key=lambda r: r.version, reverse=True):
        latest.setdefault(run.case_id, run)
    unresolved = pending = 0
    for cid, run in latest.items():
        data = snapshot(db, cid, run.id)
        reviews = {r['target_id']: r['state'] for r in data['reviews']}
        pending += sum(1 for e in data['entities'] if reviews.get(e['entity_id'], 'DETECTED') in ('DETECTED', 'UNDER_REVIEW'))
        anomaly = data.get('anomalies') or {}
        unresolved += sum(1 for k in ('anomalies', 'contradictions') for f in anomaly.get(k, [])
            if reviews.get(f['finding_id'], 'DETECTED') not in ('RESOLVED', 'DISMISSED', 'CORRECTED'))
    activity = db.query(AuditLog).filter(AuditLog.resource_type == 'Investigation',
        AuditLog.resource_id.in_([str(i) for i in ids])).order_by(AuditLog.created_at.desc()).limit(20).all()
    return ok({'total_investigations': len(cases), 'active_investigations': sum(c.status not in ('CLOSED', 'ARCHIVED') for c in cases),
        'total_evidence': db.query(EvidenceFile).filter(EvidenceFile.case_id.in_(ids), EvidenceFile.is_deleted.is_(False)).count(),
        'processing': sum(r.status in ('QUEUED', 'PROCESSING') for r in runs), 'pending_reviews': pending,
        'unresolved_anomalies': unresolved, 'failed_jobs': [row_json(r) for r in runs if r.status in ('FAILED', 'PARTIAL')],
        'recent_cases': [row_json(c) for c in sorted(cases, key=lambda c: c.updated_at, reverse=True)[:10]],
        'activity': [row_json(a) for a in activity]})


@router.get('/cases/{case_id}')
def workspace(case_id: uuid.UUID, run_id: uuid.UUID | None = None, db=Depends(get_db), user=Depends(current_investigator)):
    case = require_case(db, user, case_id)
    data = snapshot(db, case_id, run_id)
    if run_id and not data['run']:
        raise HTTPException(404, 'Analysis version not found')
    return ok({**data, 'case': row_json(case), 'hypotheses': hypotheses(db, case_id)})


@router.post('/cases/{case_id}/evidence', status_code=201)
def upload(case_id: uuid.UUID, files: list[UploadFile] = File(...), category: str = Form('DOCUMENT'),
           db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    if not 1 <= len(files) <= 20:
        raise HTTPException(422, 'Upload between 1 and 20 files')
    if category not in ('DOCUMENT', 'AUTOPSY_REPORT', 'TOXICOLOGY', 'WITNESS', 'INQUEST', 'CCTV', 'SCENE'):
        raise HTTPException(422, 'Unknown evidence category')
    results = []
    for file in files:
        try:
            result = IngestionEngine(db, user_id=str(user.id)).ingest_file(file.file, file.filename or 'evidence',
                file.content_type, str(case_id), tags=[category], commit=False)
            evidence = db.get(EvidenceFile, uuid.UUID(result['evidence_file_id']))
            # Same UUID joins the application's evidence registry to the pipeline source.
            db.add(Evidence(id=evidence.id, case_id=case_id, file_name=evidence.original_filename,
                file_path=evidence.storage_path, file_hash=evidence.sha256_hash, file_type='DOCUMENT',
                file_size=evidence.file_size, uploaded_by=user.id))
            audit(db, user.id, case_id, 'EVIDENCE_ACQUIRED', {'evidence_id': str(evidence.id), 'sha256': evidence.sha256_hash})
            db.commit()
            results.append(result)
        except Exception as exc:
            db.rollback()
            # Do not expose another case's checksum match or internal storage paths.
            detail = exc.message if isinstance(exc, AtopsyBaseError) else 'Evidence acquisition failed; inspect server logs'
            results.append({'filename': file.filename, 'status': 'FAILED', 'error': detail})
    run = CasePipelineOrchestrator(db).enqueue(case_id, user.id) if any(r.get('status') == 'COMPLETED' for r in results) else None
    return ok({'results': results, 'run': row_json(run) if run else None})


@router.get('/cases/{case_id}/evidence/{evidence_id}/original')
def original(case_id: uuid.UUID, evidence_id: uuid.UUID, db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    evidence = db.query(EvidenceFile).filter_by(id=evidence_id, case_id=case_id, is_deleted=False).first()
    if not evidence:
        raise HTTPException(404, 'Evidence not found')
    checksum = compute_checksums_from_file(evidence.storage_path)
    if checksum.sha256 != evidence.sha256_hash:
        raise HTTPException(409, 'Original evidence failed SHA-256 verification')
    audit(db, user.id, case_id, 'EVIDENCE_VERIFIED_VIEWED', {'evidence_id': str(evidence_id), 'sha256': checksum.sha256})
    db.commit()
    return FileResponse(evidence.storage_path, media_type=evidence.mime_type, filename=evidence.original_filename,
        content_disposition_type='inline', headers={'X-Evidence-SHA256': checksum.sha256})


@router.get('/cases/{case_id}/runs')
def runs(case_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    query = db.query(CasePipelineRun).filter_by(case_id=case_id)
    return ok({'items': [row_json(r) for r in query.order_by(CasePipelineRun.version.desc()).offset(offset).limit(limit)], 'total': query.count()})


@router.post('/cases/{case_id}/runs', status_code=202)
def start_run(case_id: uuid.UUID, body: RunRequest, db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    if body.retry_of and not db.query(CasePipelineRun).filter_by(id=body.retry_of, case_id=case_id).first():
        raise HTTPException(404, 'Run not found')
    try:
        return ok(row_json(CasePipelineOrchestrator(db).enqueue(case_id, user.id, body.request_key, body.retry_of)))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.post('/cases/{case_id}/reviews', status_code=201)
def review(case_id: uuid.UUID, body: ReviewRequest, db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    data = snapshot(db, case_id, body.run_id)
    if body.target_id not in targets(data):
        raise HTTPException(404, 'Finding or entity not found in this case version')
    if body.state == 'CORRECTED' and not (body.correction or '').strip():
        raise HTTPException(422, 'A correction must contain the revised assertion')
    revision = FindingReview(case_id=case_id, user_id=user.id, **body.model_dump())
    db.add(revision)
    audit(db, user.id, case_id, 'FINDING_REVIEWED', body.model_dump(mode='json'))
    db.commit()
    return ok(row_json(revision))


@router.post('/cases/{case_id}/hypotheses', status_code=201)
def save_hypothesis(case_id: uuid.UUID, body: HypothesisRequest, db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    # Lock the case to serialize hypothesis revision allocation.
    from app.models.case import Case
    db.query(Case).filter_by(id=case_id).with_for_update().one()
    hid = body.hypothesis_id or uuid.uuid4()
    previous = db.query(HypothesisRevision).filter_by(hypothesis_id=hid, case_id=case_id).order_by(HypothesisRevision.version.desc()).first()
    if body.hypothesis_id and not previous:
        raise HTTPException(404, 'Hypothesis not found')
    for assessment in body.assessments:
        if assessment.target_id not in targets(snapshot(db, case_id, assessment.run_id)):
            raise HTTPException(404, 'Observation does not belong to this case version')
    revision = HypothesisRevision(hypothesis_id=hid, case_id=case_id, user_id=user.id,
        version=previous.version + 1 if previous else 1, description=body.description, notes=body.notes,
        status=body.status, assessments=[a.model_dump(mode='json') for a in body.assessments])
    db.add(revision)
    audit(db, user.id, case_id, 'HYPOTHESIS_REVISED', {'hypothesis_id': str(hid), 'version': revision.version})
    db.commit()
    return ok(row_json(revision))


@router.post('/cases/{case_id}/assistant')
def assistant(case_id: uuid.UUID, body: Question, db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    data = snapshot(db, case_id, body.run_id)
    if body.run_id and not data['run']:
        raise HTTPException(404, 'Run not found')
    answer = answer_question(data, body.query)
    audit(db, user.id, case_id, 'ASSISTANT_RETRIEVAL', {'run_id': answer['run_id'], 'citations': [c['entity_id'] for c in answer['citations']]})
    db.commit()
    return ok(answer)


@router.get('/cases/{case_id}/audit')
def history(case_id: uuid.UUID, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(current_investigator)):
    require_case(db, user, case_id)
    query = db.query(AuditLog).filter_by(resource_type='Investigation', resource_id=str(case_id))
    return ok({'items': [row_json(r) for r in query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)], 'total': query.count()})


@router.get('/cases/{case_id}/report')
def report(case_id: uuid.UUID, run_id: uuid.UUID | None = None, format: Literal['json', 'markdown'] = 'json', db=Depends(get_db), user=Depends(current_investigator)):
    case = require_case(db, user, case_id)
    data = snapshot(db, case_id, run_id)
    if not data['run']:
        raise HTTPException(409, 'No analysis version available')
    data['case'] = row_json(case)
    data['hypotheses'] = hypotheses(db, case_id)
    data['audit'] = [row_json(r) for r in db.query(AuditLog).filter_by(resource_type='Investigation', resource_id=str(case_id)).order_by(AuditLog.created_at)]
    audit(db, user.id, case_id, 'REPORT_GENERATED', {'run_id': data['run']['id']})
    db.commit()
    if format == 'markdown':
        from app.services.investigation_report import markdown_report
        return Response(markdown_report(data), media_type='text/markdown',
            headers={'Content-Disposition': f'attachment; filename="atopsy-{case_id}-v{data["run"]["version"]}.md"'})
    return Response(json.dumps(data, indent=2, default=str), media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="atopsy-{case_id}-v{data["run"]["version"]}.json"'})
