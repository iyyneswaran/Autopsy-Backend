from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    autopsy,
    evidence,
    analysis,
    timeline,
    health
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(autopsy.router)
api_router.include_router(evidence.router)
api_router.include_router(analysis.router)
api_router.include_router(timeline.router)
api_router.include_router(health.router)