import time
import threading

from app.core.logger import logger

from app.services.ai_service import (
    analyze_autopsy_report
)

from app.ml.cv.object_detection import (
    detect_objects
)

from app.ml.cv.cctv_processing import (
    process_cctv_video
)

analysis_queue = []


def add_analysis_job(job: dict):

    analysis_queue.append(job)

    logger.info(
        f"Job added to queue: {job}"
    )


def process_analysis_job(job: dict):

    analysis_type = job.get(
        "analysis_type"
    )

    file_path = job.get(
        "file_path"
    )

    logger.info(
        f"Processing job: {analysis_type}"
    )

    result = None

    try:

        if analysis_type == "autopsy":

            result = analyze_autopsy_report(
                file_path
            )

        elif analysis_type == "object_detection":

            result = detect_objects(
                file_path
            )

        elif analysis_type == "cctv":

            result = process_cctv_video(
                file_path
            )

        else:

            result = {
                "success": False,
                "message":
                    "Unknown analysis type"
            }

        logger.info(
            f"Job completed successfully"
        )

        logger.info(result)

    except Exception as e:

        logger.error(
            f"Worker failed: {str(e)}"
        )


def worker_loop():

    logger.info(
        "Analysis worker started"
    )

    while True:

        if len(analysis_queue) > 0:

            job = analysis_queue.pop(0)

            process_analysis_job(job)

        time.sleep(2)


def start_worker():

    worker_thread = threading.Thread(
        target=worker_loop,
        daemon=True
    )

    worker_thread.start()