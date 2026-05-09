from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies.auth_dependency import get_current_user

router = APIRouter(prefix="/timeline", tags=["Timeline"])


@router.get("/{case_id}")
def get_case_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    mock_timeline = [
        {
            "timestamp": "2026-05-09T10:00:00",
            "event": "Victim last seen"
        },
        {
            "timestamp": "2026-05-09T12:30:00",
            "event": "CCTV footage recorded"
        },
        {
            "timestamp": "2026-05-09T15:00:00",
            "event": "Body discovered"
        }
    ]

    return {
        "case_id": case_id,
        "timeline": mock_timeline
    }