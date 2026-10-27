import json
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.advanced_risk import router as advanced_router
from app.api.agent import router as agent_router
from app.api.documents import router as documents_router
from app.api.governance import router as governance_router
from app.api.ml import router as ml_router
from app.api.optimization import router as optimization_router
from app.api.routes import router
from app.core.config import settings
from app.core.errors import AppError

app = FastAPI(
    title="VANTAGE",
    version="0.4.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(router)
app.include_router(advanced_router)
app.include_router(ml_router)
app.include_router(optimization_router)
app.include_router(governance_router)
app.include_router(agent_router)
app.include_router(documents_router)
logger = logging.getLogger("vantage")
logging.basicConfig(level=logging.INFO, format="%(message)s")
# httpx's INFO logger includes URLs and therefore API keys. Disable it.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def error_response(request: Request, code: str, message: str, status: int, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    request.state.request_id = str(uuid4())
    if request.method == "POST" and request.url.path == "/api/v1/research/documents":
        # Bound the complete multipart stream before FastAPI can spool an oversized file.
        upload_limit = 6 * 1024 * 1024
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > upload_limit:
                return error_response(
                    request,
                    "DOCUMENT_SIZE",
                    "Multipart PDF upload exceeds 6 MB including metadata.",
                    413,
                )
            body.extend(chunk)
        request._body = bytes(body)
    started = time.monotonic()
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if (
            origin and origin.rstrip("/") != settings().frontend_url.rstrip("/")
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            return error_response(
                request, "ORIGIN_REJECTED", "Cross-origin changes are not allowed.", 403
            )
    try:
        response = await call_next(request)
    except Exception:
        # Log only a generated ID, never exception messages or private payloads.
        logger.error(json.dumps({"event": "request_error", "request_id": request.state.request_id}))
        response = error_response(
            request,
            "INTERNAL_ERROR",
            "Request failed. Check database readiness and server configuration.",
            500,
        )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info(
        json.dumps(
            {
                "event": "request",
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
    )
    return response


@app.exception_handler(AppError)
async def app_error(request: Request, error: AppError):
    return error_response(request, error.code, error.message, error.status, error.details)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    # Pydantic's default error includes input values, possibly callback tokens. Omit them.
    details = [
        {"field": ".".join(str(p) for p in e["loc"]), "type": e["type"]} for e in error.errors()
    ]
    return error_response(
        request, "VALIDATION_ERROR", "Request parameters failed validation.", 422, details
    )
