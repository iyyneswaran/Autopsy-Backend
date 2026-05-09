from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": "Atopsy AI Service",
        "timestamp": datetime.utcnow()
    }