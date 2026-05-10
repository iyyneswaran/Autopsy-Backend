"""
Atopsy — Ingestion Background Worker.

Processes pending normalizations in the background.
Runs as a daemon thread alongside the main application.

Future: Can be replaced with Celery workers for
horizontal scaling and Redis-backed queues.
"""

from __future__ import annotations

import time
import threading
import traceback

from app.core.database import SessionLocal
from app.core.logger import logger
from app.pipeline.normalization.engine import NormalizationEngine
from app.repositories.pipeline_repository import PipelineRepository


# Worker configuration
WORKER_POLL_INTERVAL = 10  # seconds
WORKER_BATCH_SIZE = 5
_WORKER_READY = False


def process_pending_normalizations() -> int:
    """
    Process all pending normalizations.

    Returns the number of files processed.
    """
    db = SessionLocal()
    processed = 0

    try:
        repo = PipelineRepository(db)
        pending = repo.list_pending_normalizations(
            limit=WORKER_BATCH_SIZE
        )

        if not pending:
            return 0

        logger.info(
            f"Ingestion worker: found {len(pending)} pending normalizations"
        )

        engine = NormalizationEngine(db)

        for evidence in pending:
            try:
                engine.normalize(str(evidence.id))
                processed += 1
                logger.info(
                    f"Worker normalized: {evidence.original_filename}"
                )
            except Exception as e:
                logger.error(
                    f"Worker normalization failed for "
                    f"{evidence.id}: {e}"
                )

    except Exception as e:
        logger.warning(
            f"Ingestion worker query error (will retry): "
            f"{type(e).__name__}: {e}"
        )

    finally:
        try:
            db.close()
        except Exception:
            pass

    return processed


def ingestion_worker_loop() -> None:
    """
    Main worker loop — polls for pending normalizations
    and processes them in batches.

    Fully fault-tolerant: catches ALL exceptions to prevent
    the daemon thread from dying.
    """
    global _WORKER_READY

    logger.info(
        "Ingestion worker started "
        f"(poll={WORKER_POLL_INTERVAL}s, batch={WORKER_BATCH_SIZE})"
    )

    # Allow tables to be created before first poll
    time.sleep(5)
    _WORKER_READY = True

    while True:
        try:
            processed = process_pending_normalizations()

            if processed > 0:
                logger.info(
                    f"Ingestion worker: processed {processed} files"
                )

        except Exception as e:
            logger.warning(
                f"Ingestion worker loop error (non-fatal): "
                f"{type(e).__name__}: {e}"
            )

        try:
            time.sleep(WORKER_POLL_INTERVAL)
        except Exception:
            break


def start_ingestion_worker() -> threading.Thread:
    """Start the ingestion worker as a daemon thread."""
    thread = threading.Thread(
        target=ingestion_worker_loop,
        daemon=True,
        name="ingestion-worker",
    )
    thread.start()
    logger.info("Ingestion worker thread started")
    return thread
