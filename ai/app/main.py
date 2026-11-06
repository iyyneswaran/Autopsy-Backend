"""Integrated API. Legacy prototype endpoints remain in source, but are not exposed."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.api.v1.endpoints.intelligence import router
from app.core.database import engine
from app.core.logger import logger
from app.workers.case_pipeline_worker import start_case_worker, stop_event
import app.models

@asynccontextmanager
async def lifespan(app):
    with engine.connect() as connection:
        connection.execute(text('SELECT id FROM case_pipeline_runs LIMIT 0'))
    worker = start_case_worker()
    yield
    stop_event.set()
    worker.join(timeout=5)

app = FastAPI(title='Atopsy Forensic Intelligence', version='2.0.0', lifespan=lifespan)
app.include_router(router)

@app.get('/health')
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'success': True, 'data': {'database': 'connected'}}

@app.exception_handler(Exception)
async def error_handler(request: Request, exc: Exception):
    logger.exception('Request failed: {}', request.url.path)
    return JSONResponse(status_code=500, content={'success': False, 'message': 'Internal processing error; see server logs'})
