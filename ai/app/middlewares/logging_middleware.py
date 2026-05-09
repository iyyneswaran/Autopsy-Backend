import time

from starlette.middleware.base import (
    BaseHTTPMiddleware
)

from fastapi import Request

from app.core.logger import logger


class LoggingMiddleware(
    BaseHTTPMiddleware
):

    async def dispatch(
        self,
        request: Request,
        call_next
    ):

        start_time = time.time()

        response = await call_next(request)

        process_time = (
            time.time() - start_time
        )

        logger.info(
            f"{request.method} "
            f"{request.url.path} "
            f"Status: {response.status_code} "
            f"Completed in {process_time:.4f}s"
        )

        return response