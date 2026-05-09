import os
import time

from datetime import datetime, timedelta

from app.core.logger import logger

TEMP_DIR = "app/storage/temp"

MAX_FILE_AGE_HOURS = 24


def cleanup_temp_files():

    logger.info(
        "Cleanup worker started"
    )

    while True:

        try:

            now = datetime.utcnow()

            for filename in os.listdir(TEMP_DIR):

                file_path = os.path.join(
                    TEMP_DIR,
                    filename
                )

                if os.path.isfile(file_path):

                    file_modified_time = datetime.utcfromtimestamp(
                        os.path.getmtime(file_path)
                    )

                    age = (
                        now - file_modified_time
                    )

                    if age > timedelta(
                        hours=MAX_FILE_AGE_HOURS
                    ):

                        os.remove(file_path)

                        logger.info(
                            f"Deleted temp file: {filename}"
                        )

        except Exception as e:

            logger.error(
                f"Cleanup worker error: {str(e)}"
            )

        time.sleep(3600)