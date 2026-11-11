import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException

from app import __version__, db
from app.api import admin, ask, export, feeds, items, search, topics, trends
from app.api.common import ApiError
from app.config import get_settings
from app.logging import request_id_var, setup_logging
from app.schemas import ErrorResponse
from app.security import (
    API_CSP,
    CSRF_HEADER,
    DEFAULT_LIMIT,
    RATE_LIMIT_EXEMPT,
    SECURITY_HEADERS,
    allow,
    client_key,
)
from app.seed import seed

log = logging.getLogger("app.main")
access_log = logging.getLogger("app.access")

API_PREFIX = "/api/v1"
DOCS_PATHS = (f"{API_PREFIX}/docs", f"{API_PREFIX}/openapi.json")
UNCACHED = (f"{API_PREFIX}/health", f"{API_PREFIX}/ready")  # probes must see the live state
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HTTP_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
}

router = APIRouter(prefix=API_PREFIX)


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    version: str


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness: always 200 while the process is up; reports DB state."""
    ok = db.check_db()
    return Health(
        status="ok" if ok else "degraded", db="ok" if ok else "error", version=__version__
    )


@router.get("/ready", response_model=Health)
def ready(response: Response) -> Health:
    """Readiness: 503 when the database is unreachable."""
    h = health()
    if h.db != "ok":
        response.status_code = 503
    return h


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Invalid YAML raises and stops startup on purpose. A DB that is down or not yet migrated
    # only logs: liveness stays up and /ready reports the DB state.
    try:
        seed(db.engine, get_settings().config_dir)
    except SQLAlchemyError as exc:
        log.error("seeding skipped: database error", extra={"error": type(exc).__name__})
    yield


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    """The one error shape (§11.7): {"error": {"code", "message", "request_id"}}."""
    rid = getattr(request.state, "request_id", "") or ""
    body = {"error": {"code": code, "message": message, "request_id": rid}}
    return JSONResponse(body, status_code=status, headers={"X-Request-ID": rid} if rid else None)


def _validation_message(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid request"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "validation_error", _validation_message(exc))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return error_response(request, exc.status_code, code, str(exc.detail))


MAX_BODY_BYTES = 64 * 1024  # the largest valid For You profile is well under this


async def body_limit(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Request bodies must declare their size and stay under MAX_BODY_BYTES (§11.7). Browsers'
    fetch() always sends Content-Length for a JSON body, so chunked uploads are refused (411)."""
    if request.method in ("POST", "PUT", "PATCH"):
        size = request.headers.get("content-length", "")
        if not size.isdigit():
            return error_response(request, 411, "length_required", "Content-Length required")
        if int(size) > MAX_BODY_BYTES:
            msg = f"request body over {MAX_BODY_BYTES} bytes"
            return error_response(request, 413, "payload_too_large", msg)
    return await call_next(request)


async def rate_limit(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Default per-IP limit on every route except the health probes. CORS preflights are answered
    by the CORS middleware before they get here."""
    if request.url.path not in RATE_LIMIT_EXEMPT and not allow(client_key(request)):
        return error_response(request, 429, "rate_limited", f"rate limit exceeded: {DEFAULT_LIMIT}")
    return await call_next(request)


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Request ID, JSON access log, security headers, and a last-resort error envelope."""
    supplied = request.headers.get("x-request-id", "")
    rid = supplied if _CLIENT_REQUEST_ID.match(supplied) else uuid.uuid4().hex
    request.state.request_id = rid
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except OperationalError as exc:  # DB down: degraded, not a code bug
        log.error("database unavailable", extra={"error": type(exc).__name__})
        response = error_response(request, 503, "db_unavailable", "database unavailable")
    except Exception:
        log.exception("unhandled error")
        response = error_response(request, 500, "internal_error", "internal server error")
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    response.headers.update(SECURITY_HEADERS)
    if request.url.path not in DOCS_PATHS:
        response.headers["Content-Security-Policy"] = API_CSP
    if request.method == "GET" and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = (
            "public, max-age=30"
            if response.status_code == 200
            and request.url.path not in UNCACHED
            and not request.url.path.startswith(f"{API_PREFIX}/admin")
            else "no-store"
        )
    access_log.info(
        "request",
        extra={
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,  # no query string: search terms stay out of the logs
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            "client": request.client.host if request.client else None,
        },
    )
    return response


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title="NewsDC API",
        version=__version__,
        docs_url="/api/v1/docs" if settings.api_docs else None,
        openapi_url="/api/v1/openapi.json" if settings.api_docs else None,
        redoc_url=None,
        lifespan=lifespan,
        responses={
            422: {"model": ErrorResponse, "description": "Validation error"},
            429: {"model": ErrorResponse, "description": "Rate limited"},
            500: {"model": ErrorResponse, "description": "Internal error"},
        },
    )
    install_error_handlers(app)
    # Added inner to outer: the rate limiter runs inside CORS (so a 429 is readable by the
    # browser), and request_context wraps everything (so every response gets an ID and a log line).
    app.middleware("http")(body_limit)
    app.middleware("http")(rate_limit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Request-ID", CSRF_HEADER],
        allow_credentials=True,  # the admin session cookie (Phase 8); origins are an allow-list
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(request_context)
    app.include_router(router)
    not_found: dict[int | str, dict[str, Any]] = {
        404: {"model": ErrorResponse, "description": "Not found"}
    }
    app.include_router(items.router, prefix=API_PREFIX, responses=not_found)
    app.include_router(feeds.router, prefix=API_PREFIX)
    app.include_router(topics.router, prefix=API_PREFIX, responses=not_found)
    app.include_router(search.router, prefix=API_PREFIX)
    app.include_router(ask.router, prefix=API_PREFIX)
    app.include_router(trends.router, prefix=API_PREFIX)
    app.include_router(export.router, prefix=API_PREFIX)
    app.include_router(admin.public, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX, responses=not_found)
    return app


app = create_app()
