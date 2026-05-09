from loguru import logger
import sys
import os

LOG_DIR = "logs"

os.makedirs(LOG_DIR, exist_ok=True)

logger.remove()

logger.add(
    sys.stdout,
    level="INFO"
)

logger.add(
    f"{LOG_DIR}/app.log",
    rotation="10 MB",
    retention="10 days",
    level="INFO"
)

logger.add(
    f"{LOG_DIR}/error.log",
    rotation="5 MB",
    retention="15 days",
    level="ERROR"
)