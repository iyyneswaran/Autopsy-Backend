"""Database queue with PostgreSQL advisory locks; no Redis/service dependency."""
import threading
import uuid
from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.core.logger import logger
from app.models.intelligence import CasePipelineRun, PipelineStage
from app.services.case_pipeline_orchestrator import CasePipelineOrchestrator, utcnow
from app.services.intelligence_audit import audit

stop_event = threading.Event()


def process_next():
    with SessionLocal() as db:
        ids = [r.id for r in db.query(CasePipelineRun).filter(CasePipelineRun.status.in_(['QUEUED', 'PROCESSING']))
            .order_by(CasePipelineRun.created_at).limit(20)]
    for rid in ids:
        key = rid.int % (2**63 - 1)
        with engine.connect() as lock:
            if not lock.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}).scalar():
                continue
            try:
                with SessionLocal() as db:
                    run = db.get(CasePipelineRun, rid)
                    if run.status == 'PROCESSING':
                        run.status, run.error = 'FAILED', 'Worker stopped during processing. Successful outputs preserved; retry is available.'
                        run.completed_at = utcnow()
                        for stage in db.query(PipelineStage).filter(PipelineStage.run_id == rid, PipelineStage.status.in_(['PENDING', 'RUNNING'])):
                            stage.status, stage.error = 'FAILED' if stage.status == 'RUNNING' else 'SKIPPED', run.error
                        audit(db, run.requested_by, run.case_id, 'PIPELINE_INTERRUPTED', {'run_id': str(rid), 'reason': run.error})
                        db.commit()
                    elif run.status == 'QUEUED':
                        CasePipelineOrchestrator(db).execute(rid)
                return True
            finally:
                lock.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})
    return False


def start_case_worker():
    stop_event.clear()
    def loop():
        while not stop_event.is_set():
            try:
                if process_next():
                    continue
            except Exception:
                logger.exception('Case pipeline worker failed; queue remains persisted')
            stop_event.wait(2)
    thread = threading.Thread(target=loop, name='case-pipeline', daemon=True)
    thread.start()
    return thread
