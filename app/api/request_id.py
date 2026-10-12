import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.log import LogContext, Stage

REQUEST_ID_HEADER = "X-Request-Id"


def logger() -> logging.Logger:
    return logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Takes the caller's request ID (or makes one), returns it in the response, and logs each request with it.

    The log line has the method, path and status only. Paths contain borrower IDs, never names.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        ctx = LogContext(Stage.API, request_id=request_id)
        logger().info(f"{request.method} {request.url.path} {response.status_code}", extra=ctx.extra())
        return response
