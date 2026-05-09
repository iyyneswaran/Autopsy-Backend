from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    user_id: int,
    action: str,
    resource_type: str = None,
    resource_id: int = None,
    ip_address: str = None
):

    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address
    )

    db.add(log)
    db.commit()

    return log