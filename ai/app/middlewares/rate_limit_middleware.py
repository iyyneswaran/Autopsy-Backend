from slowapi.middleware import (
    SlowAPIMiddleware
)


class CustomRateLimitMiddleware(
    SlowAPIMiddleware
):
    pass