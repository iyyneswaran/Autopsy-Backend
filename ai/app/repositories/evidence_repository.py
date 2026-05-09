from sqlalchemy.orm import Session

from app.models.evidence import Evidence


def create_evidence(
    db: Session,
    evidence_data: dict
):

    evidence = Evidence(**evidence_data)

    db.add(evidence)

    db.commit()

    db.refresh(evidence)

    return evidence


def get_evidence_by_id(
    db: Session,
    evidence_id: int
):

    return db.query(Evidence).filter(
        Evidence.id == evidence_id
    ).first()


def get_case_evidence(
    db: Session,
    case_id: int
):

    return db.query(Evidence).filter(
        Evidence.case_id == case_id
    ).all()