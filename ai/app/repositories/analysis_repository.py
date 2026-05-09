from sqlalchemy.orm import Session

from app.models.analysis import Analysis


def create_analysis(
    db: Session,
    analysis_data: dict
):

    analysis = Analysis(**analysis_data)

    db.add(analysis)

    db.commit()

    db.refresh(analysis)

    return analysis


def get_analysis_by_id(
    db: Session,
    analysis_id: int
):

    return db.query(Analysis).filter(
        Analysis.id == analysis_id
    ).first()


def get_evidence_analyses(
    db: Session,
    evidence_id: int
):

    return db.query(Analysis).filter(
        Analysis.evidence_id == evidence_id
    ).all()