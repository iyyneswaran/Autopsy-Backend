"""
Atopsy — Pipeline API Endpoints.

REST API for the forensic data acquisition and normalization layers.
All endpoints are prefixed with /pipeline.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logger import logger
from app.exceptions.pipeline import (
    AtopsyBaseError,
    DuplicateEvidenceError,
    FileValidationError,
    FileSizeLimitError,
    UnsupportedFileTypeError,
)
from app.schemas.pipeline.ingestion import (
    StructuredEvidencePayload,
)
from app.services.pipeline_service import PipelineService

router = APIRouter(
    prefix="/pipeline",
    tags=["Pipeline — Forensic Intelligence"],
)


def _get_user_id(request: Request) -> str | None:
    """Extract user ID from auth middleware state."""
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        return user.get("sub") or user.get("user_id")
    return None


def _get_correlation_id(request: Request) -> str:
    """Get or generate a correlation ID for tracing."""
    return request.headers.get(
        "X-Correlation-ID", str(uuid.uuid4())
    )


# ─────────────────────────────────────────────
# Upload Endpoints
# ─────────────────────────────────────────────


@router.post("/upload", status_code=201)
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    case_id: str | None = Form(None),
    tags: str | None = Form(None),
    source_attribution: str | None = Form(None),
    auto_normalize: bool = Form(True),
    db: Session = Depends(get_db),
):
    """
    Upload a single evidence file.

    Supports: PDF, DOCX, TXT, CSV, XLSX, JPG, PNG, TIFF, BMP, MP4, AVI, MOV, JSON.

    The file is automatically:
    - Validated (MIME, size, integrity)
    - Fingerprinted (SHA-256 + MD5)
    - Checked for duplicates
    - Stored securely (UUID-based naming)
    - Metadata extracted
    - Normalized into canonical forensic schema (if auto_normalize=true)
    """
    user_id = _get_user_id(request)
    correlation_id = _get_correlation_id(request)

    tag_list = (
        [t.strip() for t in tags.split(",") if t.strip()]
        if tags
        else []
    )

    service = PipelineService(
        db=db,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    try:
        result = service.ingest_file(
            file_stream=file.file,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            case_id=case_id,
            tags=tag_list,
            source_attribution=source_attribution,
            auto_normalize=auto_normalize,
        )

        return {
            "success": True,
            "message": "Evidence uploaded and processed successfully",
            "data": result,
        }

    except DuplicateEvidenceError as e:
        raise HTTPException(status_code=409, detail=e.to_dict())
    except (UnsupportedFileTypeError, FileSizeLimitError, FileValidationError) as e:
        raise HTTPException(status_code=400, detail=e.to_dict())
    except AtopsyBaseError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/batch", status_code=201)
async def upload_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    case_id: str | None = Form(None),
    tags: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload multiple evidence files in a single batch.

    Each file is processed independently — partial failures
    don't affect other files in the batch.
    """
    user_id = _get_user_id(request)
    correlation_id = _get_correlation_id(request)

    tag_list = (
        [t.strip() for t in tags.split(",") if t.strip()]
        if tags
        else []
    )

    service = PipelineService(
        db=db,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    file_tuples = [
        (f.file, f.filename or "unknown", f.content_type)
        for f in files
    ]

    result = service.ingest_batch(
        files=file_tuples,
        case_id=case_id,
        tags=tag_list,
    )

    return {
        "success": True,
        "message": f"Batch upload completed: {result['completed']}/{result['total_files']} succeeded",
        "data": result,
    }


@router.post("/upload/structured", status_code=201)
async def upload_structured(
    request: Request,
    payload: StructuredEvidencePayload,
    db: Session = Depends(get_db),
):
    """
    Ingest structured JSON evidence via API payload.

    Used for forensic metadata feeds, GPS data, IoT sensor data, etc.
    """
    user_id = _get_user_id(request)
    correlation_id = _get_correlation_id(request)

    service = PipelineService(
        db=db,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    try:
        result = service.ingest_structured(
            data=payload.data,
            evidence_type=payload.evidence_type,
            case_id=str(payload.case_id) if payload.case_id else None,
            tags=payload.tags,
            source_attribution=payload.source_attribution,
        )

        return {
            "success": True,
            "message": "Structured evidence ingested",
            "data": result,
        }

    except AtopsyBaseError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())


# ─────────────────────────────────────────────
# Query Endpoints
# ─────────────────────────────────────────────


@router.get("/evidence")
async def list_evidence(
    case_id: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List ingested evidence files with filtering and pagination."""
    service = PipelineService(db=db)
    result = service.list_evidence(
        case_id=case_id,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"success": True, "data": result}


@router.get("/evidence/{evidence_id}")
async def get_evidence_detail(
    evidence_id: str,
    db: Session = Depends(get_db),
):
    """Get full detail for an evidence file including metadata and normalization."""
    service = PipelineService(db=db)
    result = service.get_evidence_detail(evidence_id)

    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")

    return {"success": True, "data": result}


@router.get("/evidence/{evidence_id}/download")
async def download_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
):
    """Get the download path or signed URL for an evidence file."""
    service = PipelineService(db=db)
    path = service.get_download_path(evidence_id)

    if not path:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # If local path, return file directly
    if not path.startswith("http"):
        from pathlib import Path

        file_path = Path(path)
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                filename=file_path.name,
            )
        raise HTTPException(status_code=404, detail="File not found on disk")

    # S3 signed URL
    return {"success": True, "download_url": path}


# ─────────────────────────────────────────────
# Normalization Endpoints
# ─────────────────────────────────────────────


@router.post("/normalize/{evidence_id}")
async def normalize_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
):
    """Trigger normalization for a specific evidence file."""
    service = PipelineService(db=db)

    try:
        result = service.normalize_evidence(evidence_id)
        return {"success": True, "data": result}
    except AtopsyBaseError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())


@router.post("/normalize/pending")
async def normalize_all_pending(
    db: Session = Depends(get_db),
):
    """Normalize all evidence files that are pending normalization."""
    service = PipelineService(db=db)
    result = service.normalize_pending()
    return {"success": True, "data": result}


# ─────────────────────────────────────────────
# Audit & Monitoring
# ─────────────────────────────────────────────


@router.get("/logs")
async def get_acquisition_logs(
    evidence_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get immutable acquisition audit logs."""
    service = PipelineService(db=db)
    logs = service.get_acquisition_logs(
        evidence_file_id=evidence_id,
        limit=limit,
        offset=offset,
    )
    return {"success": True, "data": logs}


@router.get("/health")
async def pipeline_health(
    db: Session = Depends(get_db),
):
    """Pipeline subsystem health check."""
    service = PipelineService(db=db)
    return {"success": True, "data": service.get_pipeline_health()}


# ─────────────────────────────────────────────
# Evidence Management
# ─────────────────────────────────────────────


@router.delete("/evidence/{evidence_id}")
async def delete_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
):
    """Soft-delete an evidence file (forensic: data is preserved)."""
    repo = __import__(
        "app.repositories.pipeline_repository",
        fromlist=["PipelineRepository"],
    ).PipelineRepository(db)

    deleted = repo.soft_delete_evidence(evidence_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Evidence not found")

    return {"success": True, "message": "Evidence marked as deleted"}
