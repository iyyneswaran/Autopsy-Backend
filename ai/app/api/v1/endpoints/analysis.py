from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies.auth_dependency import get_current_user
from app.services.ai_service import (
    estimate_time_of_death,
    correlate_metadata
)

router = APIRouter(prefix="/analysis", tags=["AI Analysis"])


@router.post("/time-of-death")
def time_of_death_analysis(
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = estimate_time_of_death(payload)

    return {
        "analysis_type": "time_of_death",
        "result": result
    }


@router.post("/correlation")
def metadata_correlation(
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = correlate_metadata(payload)

    return {
        "analysis_type": "correlation",
        "result": result
    }

from app.ml.intelligence.multi_hypothesis import hypothesis_engine

@router.post("/hypotheses")
async def generate_hypotheses(
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await hypothesis_engine.generate_hypotheses(payload)

    return {
        "analysis_type": "hypotheses",
        "result": result
    }

from app.ml.intelligence.copilot import copilot_engine

@router.post("/chat")
async def copilot_chat(
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    case_id = payload.get("case_id", "default")
    query = payload.get("query", "")
    conversation_history = payload.get("history", [])
    
    result = await copilot_engine.answer_question(case_id, query, conversation_history)
    
    return result