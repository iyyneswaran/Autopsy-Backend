from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class TimeOfDeathRequest(BaseModel):

    body_temperature: float

    ambient_temperature: float

    rigor_stage: str

    lividity_stage: str


class AnalysisResponse(BaseModel):

    id: int

    evidence_id: int

    analysis_type: str

    result_json: Dict[str, Any]

    confidence_score: Optional[float]

    model_version: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True