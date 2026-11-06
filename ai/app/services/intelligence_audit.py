from app.models.audit_log import AuditLog
from app.models.case import Case
from datetime import datetime, timezone


def audit(db, user_id, case_id, action, detail):
    if action in ('EVIDENCE_ACQUIRED', 'FINDING_REVIEWED', 'HYPOTHESIS_REVISED') or action.startswith('PIPELINE_'):
        db.query(Case).filter_by(id=case_id).update({'updated_at': datetime.now(timezone.utc)}, synchronize_session=False)
    db.add(AuditLog(user_id=user_id, action=action, resource_type='Investigation',
        resource_id=str(case_id), detail=detail))
