from starlette.middleware.base import (
    BaseHTTPMiddleware
)

from fastapi import Request
from jose import jwt, JWTError

from app.core.config import settings


class AuthMiddleware(
    BaseHTTPMiddleware
):

    async def dispatch(
        self,
        request: Request,
        call_next
    ):

        excluded_paths = [
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/ping",
            "/system/status",
            "/auth/login",
            "/health"
        ]

        if request.url.path in excluded_paths:
            return await call_next(request)

        auth_header = request.headers.get(
            "Authorization"
        )

        if auth_header:

            try:

                token = auth_header.replace(
                    "Bearer ",
                    ""
                )

                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[
                        settings.ALGORITHM
                    ]
                )

                request.state.user = payload

            except JWTError:
                request.state.user = None

        response = await call_next(request)

        return response