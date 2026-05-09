from pydantic import BaseModel
from datetime import datetime


class EvidenceResponse(BaseModel):

    id: int

    case_id: int

    file_name: str

    file_path: str

    file_hash: str

    file_type: str

    uploaded_by: int

    created_at: datetime

    class Config:
        from_attributes = True