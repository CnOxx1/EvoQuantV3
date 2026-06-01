"""标准化 API 错误响应。

所有 API 错误统一返回以下 JSON 格式：
{
    "error_code": "NOT_FOUND",
    "detail": "No regime data for BTC/USDT",
    "request_id": "abc-123",
    "timestamp": "2026-06-01T12:00:00Z"
}
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from loguru import logger

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from exceptions import APIError, EvoQuantError


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _build_error_body(
    error_code: str,
    detail: str,
    request_id: str,
) -> dict:
    return {
        "error_code": error_code,
        "detail": detail,
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """处理项目自定义 APIError 及其子类。"""
    request_id = _get_request_id(request)
    logger.warning(
        "[{}] {} {} -> {}: {}",
        request_id, request.method, request.url.path,
        exc.error_code, exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_body(exc.error_code, exc.message, request_id),
    )


async def evoquant_error_handler(request: Request, exc: EvoQuantError) -> JSONResponse:
    """处理非 API 层的 EvoQuantError（视为 500）。"""
    request_id = _get_request_id(request)
    logger.error(
        "[{}] {} {} -> {}: {}",
        request_id, request.method, request.url.path,
        exc.error_code, exc.message,
    )
    return JSONResponse(
        status_code=500,
        content=_build_error_body(exc.error_code, str(exc.message), request_id),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException,
) -> JSONResponse:
    """统一 FastAPI/Starlette HTTPException 的响应格式。"""
    request_id = _get_request_id(request)
    code_map = {400: "BAD_REQUEST", 404: "NOT_FOUND", 422: "VALIDATION_ERROR", 429: "RATE_LIMIT_EXCEEDED"}
    error_code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_body(error_code, str(exc.detail), request_id),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError,
) -> JSONResponse:
    """处理 Pydantic 请求校验错误。"""
    request_id = _get_request_id(request)
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    )
    return JSONResponse(
        status_code=422,
        content=_build_error_body("VALIDATION_ERROR", detail, request_id),
    )


async def fallback_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：未捕获异常返回安全 JSON，不泄露 traceback。"""
    request_id = _get_request_id(request)
    logger.error(
        "unhandled exception [request_id={}] {} {}: {}: {}",
        request_id, request.method, request.url.path,
        type(exc).__name__, exc,
    )
    return JSONResponse(
        status_code=500,
        content=_build_error_body(
            "INTERNAL_ERROR", "Internal server error", request_id,
        ),
    )


def register_error_handlers(app) -> None:
    """将所有异常处理器注册到 FastAPI app。"""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(EvoQuantError, evoquant_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, fallback_exception_handler)
