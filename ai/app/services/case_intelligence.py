"""Case-scoped reads and evidence-grounded explanations from persisted outputs."""
import re
import uuid
from sqlalchemy import inspect
from app.models.intelligence import CasePipelineRun, PipelineStage, FindingReview, HypothesisRevision
from app.models.pipeline import EvidenceFile
from app.models.audit_log import AuditLog

LIMITATIONS = ['Automated outputs are investigative leads requiring qualified review.',
    'Extraction is rule-based and may miss or misinterpret observations.',
    'TOD estimates are experimental, not scientifically validated; alternative windows and assumptions must be reviewed.',
    'No assessment of criminal responsibility or guilt is made.']


def row_json(row):
    result = {}
    for column in inspect(row).mapper.column_attrs:
        value = getattr(row, column.key)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif hasattr(value, 'isoformat'):
            value = value.isoformat()
        result[column.key] = value
    return result


def snapshot(db, case_id, run_id=None):
    query = db.query(CasePipelineRun).filter_by(case_id=case_id)
    run = query.filter_by(id=run_id).first() if run_id else query.order_by(CasePipelineRun.version.desc()).first()
    files = db.query(EvidenceFile).filter_by(case_id=case_id, is_deleted=False).order_by(EvidenceFile.created_at).all()
    if run_id and run:
        files = [f for f in files if str(f.id) in run.evidence_ids]
    evidence = [{k: row_json(f)[k] for k in ('id', 'original_filename', 'mime_type', 'file_size', 'sha256_hash', 'category', 'tags', 'created_at', 'status')} for f in files]
    result = {'run': row_json(run) if run else None, 'evidence': evidence, 'stages': [], 'entities': [],
        'reviews': [], 'limitations': LIMITATIONS}
    if not run:
        return result
    stages = db.query(PipelineStage).filter_by(run_id=run.id).order_by(PipelineStage.started_at, PipelineStage.id).all()
    result['stages'] = [row_json(s) for s in stages]
    names = {str(f.id): f.original_filename for f in files}
    for stage in stages:
        if stage.name == 'structuring' and stage.output:
            for entities in stage.output.get('entity_graph', {}).get('entities', {}).values():
                for entity in entities:
                    result['entities'].append({**entity, 'evidence_id': stage.scope, 'document_name': names.get(stage.scope, stage.scope)})
        if stage.scope == 'case':
            result[stage.name] = stage.output
    # Cached entities keep their IDs. Carry their review history forward, but never
    # import a decision on a recomputed finding with a different identity.
    valid_targets = targets(result)
    reviews = db.query(FindingReview).join(CasePipelineRun, FindingReview.run_id == CasePipelineRun.id).filter(
        FindingReview.case_id == case_id, CasePipelineRun.version <= run.version,
        FindingReview.target_id.in_(valid_targets)).order_by(FindingReview.created_at).all()
    result['reviews'] = [row_json(r) for r in reviews]
    return result


def targets(data):
    ids = {e['entity_id'] for e in data['entities']}
    ids.update(e['edge_id'] for e in (data.get('correlation') or {}).get('relationship_edges', []))
    anomaly = data.get('anomalies') or {}
    for key in ('anomalies', 'contradictions'):
        ids.update(f['finding_id'] for f in anomaly.get(key, []) if f.get('finding_id'))
    return ids


def answer_question(data, question):
    """Deterministic retrieval: uploaded text is data, never executable instructions.

    Citations are validated against the persisted OCR/extraction page before return.
    A local language model is deliberately optional; no runtime AI API is required.
    """
    terms = set(re.findall(r'[a-z]{3,}', question.lower())) - {'the', 'all', 'show', 'what', 'which', 'summarize', 'are', 'this', 'case', 'documented'}
    aliases = {'injuries': 'injury', 'toxicology': 'toxicology_finding', 'death': 'time_of_death',
        'movements': 'scene_reference', 'timeline': 'time_of_death'}
    terms |= {aliases[t] for t in terms if t in aliases}
    documents = {}
    for stage in data['stages']:
        if stage['name'] == 'extraction' and stage['output']:
            documents[stage['scope']] = stage['output']['envelope']['assembled_document']['pages']
    citations = []
    unsupported_action = bool(re.search(r'other (?:cases|investigations)|mark .*verif|ignore .*instructions|reveal .*secret', question, re.I))
    reviews = {r['target_id']: r['state'] for r in data.get('reviews', [])}
    unverified = bool(re.search(r'unverified|unreviewed', question, re.I))
    uncertain = bool(re.search(r'uncertain|unresolved', question, re.I))
    requested_types = set()
    if re.search(r'\binjur(?:y|ies)\b', question, re.I):
        requested_types.add('INJURY')
    if re.search(r'\btoxicology\b', question, re.I):
        requested_types.add('TOXICOLOGY_FINDING')
    for entity in data['entities']:
        searchable = ' '.join([entity['entity_type'], entity['raw_value'], str(entity.get('metadata', {}))]).lower()
        if unsupported_action:
            continue
        if requested_types and entity['entity_type'] not in requested_types:
            continue
        if unverified:
            relevant = reviews.get(entity['entity_id'], 'DETECTED') in ('DETECTED', 'UNDER_REVIEW')
        elif uncertain:
            relevant = entity.get('metadata', {}).get('assertion_status') == 'UNCERTAIN'
        else:
            relevant = any(t in searchable for t in terms)
        if not relevant:
            continue
        for span in entity['provenance'].get('source_spans', []):
            page = next((p for p in documents.get(entity['evidence_id'], []) if p['page_number'] == span['page']), None)
            if not page:
                continue
            excerpt = page['text'][span['start_char']:span['end_char']]
            if not excerpt or excerpt != span['raw_text']:
                continue
            citations.append({'evidence_id': entity['evidence_id'], 'document_name': entity['document_name'],
                'page': span['page'] + 1, 'start_char': span['start_char'], 'end_char': span['end_char'],
                'original_text': excerpt, 'entity_id': entity['entity_id'],
                'relationship': f"Source assertion for {entity['entity_type']}: {entity['canonical_value']}",
                'uncertainty': entity.get('metadata', {}).get('assertion_status', 'EXTRACTED_ASSERTION'),
                'confidence': entity['confidence']})
            break
        if len(citations) >= 20:
            break
    return {'answer': 'Relevant documented assertions are listed below. They require source review.' if citations else
        'Insufficient evidence in the processed case data to answer this question.', 'citations': citations,
        'limitations': data['limitations'] + ['Extractive retrieval does not infer missing facts or assess hypotheses automatically.'],
        'mode': 'deterministic_evidence_retrieval', 'run_id': data['run']['id'] if data['run'] else None}


def hypotheses(db, case_id):
    rows = db.query(HypothesisRevision).filter_by(case_id=case_id).order_by(HypothesisRevision.version.desc()).all()
    latest = {}
    for row in rows:
        latest.setdefault(str(row.hypothesis_id), row_json(row))
    return list(latest.values())
