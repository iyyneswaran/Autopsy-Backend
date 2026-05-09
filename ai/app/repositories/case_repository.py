from sqlalchemy.orm import Session

from app.models.case import Case


def create_case(
    db: Session,
    case_data: dict
):

    case = Case(**case_data)

    db.add(case)

    db.commit()

    db.refresh(case)

    return case


def get_case_by_id(
    db: Session,
    case_id: int
):

    return db.query(Case).filter(
        Case.id == case_id
    ).first()


def get_all_cases(
    db: Session
):

    return db.query(Case).all()


def delete_case(
    db: Session,
    case_id: int
):

    case = get_case_by_id(
        db,
        case_id
    )

    if not case:
        return None

    db.delete(case)

    db.commit()

    return True