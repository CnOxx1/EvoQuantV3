from __future__ import annotations

import hashlib
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


def compute_etag(body: bytes) -> str:
    """Return a weak ETag from the MD5 hash of the body."""
    return f'W/"{hashlib.md5(body).hexdigest()}"'


class ETagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method != "GET" or "upgrade" in request.headers.get("connection", "").lower():
            return await call_next(request)

        if_none_match = request.headers.get("if-none-match")
        response = await call_next(request)

        if response.status_code != 200:
            return response

        # Skip streaming responses without body attribute
        if not hasattr(response, "body"):
            return response

        body = response.body
        etag = compute_etag(body)
        response.headers["ETag"] = etag

        if if_none_match and if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})

        if_modified_since = request.headers.get("if-modified-since")
        last_modified = response.headers.get("last-modified")
        if if_modified_since and last_modified and if_modified_since == last_modified:
            return Response(status_code=304, headers={"ETag": etag})

        return response


async def etag_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Functional middleware entry point for app.middleware('http') usage."""
    middleware = ETagMiddleware(app=None)
    return await middleware.dispatch(request, call_next)
