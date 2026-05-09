from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import shutil
import uuid
import os

from app.core.database import get_db
from app.services.ai_service import analyze_autopsy_report
from app.api.dependencies.auth_dependency import get_current_user

router = APIRouter(prefix="/autopsy", tags=["Autopsy Analysis"])

UPLOAD_DIR = "app/storage/reports"


@router.post("/analyze")
async def analyze_autopsy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    allowed_types = ["application/pdf"]

    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    filename = f"{uuid.uuid4()}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = analyze_autopsy_report(file_path)

    return {
        "message": "Autopsy report analyzed successfully",
        "result": result
    }