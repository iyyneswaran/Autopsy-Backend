from pydantic import BaseModel
from datetime import datetime


class CaseCreate(BaseModel):

    title: str

    description: str


class CaseResponse(BaseModel):

    id: int

    title: str

    description: str

    status: str

    created_by: int

    created_at: datetime

    class Config:
        from_attributes = True