from sqlalchemy.orm import Session

from app.models.case import Case
from app.schemas.case_schema import CaseCreate


def create_case(
    db: Session,
    payload: CaseCreate,
    user_id: int
):

    new_case = Case(
        title=payload.title,
        description=payload.description,
        created_by=user_id
    )

    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    return new_case


def get_case_by_id(
    db: Session,
    case_id: int
):

    return db.query(Case).filter(
        Case.id == case_id
    ).first()


def get_all_cases(db: Session):

    return db.query(Case).all()