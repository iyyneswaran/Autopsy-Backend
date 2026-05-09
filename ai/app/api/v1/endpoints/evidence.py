from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import hashlib
import uuid
import os
import shutil

from app.core.database import get_db
from app.api.dependencies.auth_dependency import get_current_user

router = APIRouter(prefix="/evidence", tags=["Evidence"])

UPLOAD_DIR = "app/storage/evidence"


@router.post("/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    allowed_types = [
        "image/jpeg",
        "image/png",
        "application/pdf",
        "video/mp4"
    ]

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type"
        )

    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)

    return {
        "message": "Evidence uploaded successfully",
        "filename": unique_filename,
        "file_hash": sha256_hash.hexdigest()
    }