from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.api.v1.router import api_router

from app.core.rate_limiter import limiter
from app.core.database import Base, engine
from app.core.logger import logger

from app.middlewares.logging_middleware import (
    LoggingMiddleware
)

from app.middlewares.auth_middleware import (
    AuthMiddleware
)

from app.workers.analysis_worker import (
    start_worker
)

from app.workers.cleanup_worker import (
    cleanup_temp_files
)

from app.workers.ingestion_worker import (
    start_ingestion_worker
)

from app.exceptions.pipeline import AtopsyBaseError

import threading
import app.models


# =========================
# DATABASE INITIALIZATION
# =========================

Base.metadata.create_all(bind=engine)


# =========================
# FASTAPI APP
# =========================

app = FastAPI(
    title="Atopsy AI Service",
    description="""
AI-powered forensic investigation backend.

Features:
- Autopsy report analysis
- Evidence management
- CCTV processing
- Object detection
- Time-of-death estimation
- Metadata correlation
- Role-based authentication
- Rate limiting
""",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# =========================
# RATE LIMITER SETUP
# =========================

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler
)

app.add_middleware(
    SlowAPIMiddleware
)


# =========================
# CUSTOM MIDDLEWARES
# =========================

app.add_middleware(
    LoggingMiddleware
)

app.add_middleware(
    AuthMiddleware
)


# =========================
# ROUTERS
# =========================

app.include_router(api_router)


# =========================
# STARTUP EVENTS
# =========================

@app.on_event("startup")
async def startup_event():

    logger.info(
        "Starting Atopsy AI Backend..."
    )

    # Start AI Analysis Worker
    start_worker()

    logger.info(
        "Analysis worker initialized"
    )

    # Start Cleanup Worker
    cleanup_thread = threading.Thread(
        target=cleanup_temp_files,
        daemon=True
    )

    cleanup_thread.start()

    logger.info(
        "Cleanup worker initialized"
    )

    # Start Pipeline Ingestion Worker
    start_ingestion_worker()

    logger.info(
        "Pipeline ingestion worker initialized"
    )

    logger.info(
        "Application startup completed"
    )


# =========================
# SHUTDOWN EVENTS
# =========================

@app.on_event("shutdown")
async def shutdown_event():

    logger.info(
        "Shutting down Atopsy AI Backend..."
    )


# =========================
# GLOBAL EXCEPTION HANDLER
# =========================

@app.exception_handler(AtopsyBaseError)
async def pipeline_exception_handler(
    request: Request,
    exc: AtopsyBaseError
):
    logger.error(
        f"Pipeline Error [{exc.error_code}]: {exc.message}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            **exc.to_dict()
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception
):

    logger.error(
        f"Unhandled Exception: {str(exc)}"
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message":
                "Internal server error",
            "error": str(exc)
        }
    )


# =========================
# ROOT ROUTE
# =========================

@app.get("/")
def root():

    return {
        "success": True,
        "message":
            "Atopsy AI Backend Running",
        "version": "1.0.0"
    }


# =========================
# HEALTH CHECK
# =========================

@app.get("/ping")
def ping():

    return {
        "success": True,
        "status": "alive"
    }


# =========================
# SYSTEM STATUS
# =========================

@app.get("/system/status")
def system_status():

    return {
        "success": True,
        "service": "Atopsy AI Service",
        "database": "connected",
        "workers": {
            "analysis_worker": "running",
            "cleanup_worker": "running"
        },
        "ai_modules": {
            "ocr": "active",
            "nlp": "active",
            "object_detection": "active",
            "tod_estimation": "active",
            "correlation_engine": "active"
        }
    }