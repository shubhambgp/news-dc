"""Admin (PLAN Phase 8, §11.9): token login to a short signed session cookie, then actions.

- `POST /admin/login` compares ADMIN_TOKEN in constant time, is rate limited per IP and globally,
  and sets an httpOnly, Secure, SameSite=Strict cookie scoped to `/api/v1/admin`.
- Every other `/admin/*` route needs that cookie (401 otherwise). Requests that change state also
  need the session's CSRF token in `X-CSRF-Token` and, from a browser, an allowed Origin/Referer.
- Heavy work (ingest, pipeline, trend brief) is queued as a durable job for the worker.
- With ADMIN_TOKEN or SESSION_SECRET unset (or too short), every admin route returns 503.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from limits import parse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import db as app_db
from app import jobs
from app.api.common import ApiError, Pagination, get_db, pagination
from app.config import get_settings
from app.models import AIAnnotation, Category, Item, Job, PipelineRun, Source
from app.pipeline.graph import reprocess_item, reprocess_outdated
from app.schemas import (
    AdminCategory,
    AdminJob,
    AdminLogin,
    AdminRun,
    AdminSessionInfo,
    AdminSource,
    CategoryPatch,
    ErrorResponse,
    IngestRequest,
    JobQueued,
    Page,
    RejectedItem,
    Reprocessed,
    SourcePatch,
)
from app.security import (
    CSRF_HEADER,
    SESSION_COOKIE,
    AdminSession,
    allow,
    check_admin_token,
    client_key,
    new_session,
    origin_allowed,
    read_session,
    revoke,
)

log = logging.getLogger(__name__)
COOKIE_PATH = "/api/v1/admin"
LOGIN_LIMIT = parse(get_settings().rate_limit_admin_login)
LOGIN_LIMIT_GLOBAL = parse(get_settings().rate_limit_admin_login_global)
_AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "No valid admin session"},
    403: {"model": ErrorResponse, "description": "CSRF token or origin check failed"},
    503: {"model": ErrorResponse, "description": "Admin is disabled"},
}


def _enabled() -> None:
    if not get_settings().admin_enabled:
        raise ApiError(503, "admin_disabled", "admin is disabled")


def _check_origin(request: Request) -> None:
    own = f"{request.url.scheme}://{request.url.netloc}"
    h = request.headers
    if not origin_allowed(h.get("origin"), h.get("referer"), own, get_settings().cors_origin_list):
        raise ApiError(403, "forbidden_origin", "request origin not allowed")


def require_admin(request: Request) -> AdminSession:
    """A valid session; for state-changing methods also the origin and CSRF checks (§11.9)."""
    _enabled()
    sess = read_session(request.cookies.get(SESSION_COOKIE, ""), get_settings().session_secret)
    if sess is None:
        raise ApiError(401, "unauthorized", "admin login required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        _check_origin(request)
        if not check_admin_token(request.headers.get(CSRF_HEADER, ""), sess.csrf):
            raise ApiError(403, "csrf_failed", f"missing or invalid {CSRF_HEADER}")
    return sess


public = APIRouter(prefix="/admin", tags=["admin"], responses=_AUTH_ERRORS)
router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)], responses=_AUTH_ERRORS
)
Admin = Annotated[AdminSession, Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]


def _info(sess: AdminSession) -> AdminSessionInfo:
    return AdminSessionInfo(csrf_token=sess.csrf, expires_at=datetime.fromtimestamp(sess.exp, UTC))


@public.post(
    "/login",
    response_model=AdminSessionInfo,
    responses={429: {"model": ErrorResponse, "description": "Too many login attempts"}},
)
def login(body: AdminLogin, request: Request, response: Response) -> AdminSessionInfo:
    """Exchange ADMIN_TOKEN for a session cookie. Rate limited per IP
    (`RATE_LIMIT_ADMIN_LOGIN`, 5/minute) and for all clients together (30/minute)."""
    _enabled()
    _check_origin(request)
    client = client_key(request)
    # Per IP first, so one noisy client doesn't use up the global budget for everyone.
    if not allow(client, LOGIN_LIMIT, "admin_login") or not allow(
        "all", LOGIN_LIMIT_GLOBAL, "admin_login_global"
    ):
        raise ApiError(429, "rate_limited", "too many login attempts")
    s = get_settings()
    if not check_admin_token(body.token, s.admin_token):
        log.warning("admin login failed", extra={"client": client})
        raise ApiError(401, "unauthorized", "invalid admin token")
    sess, cookie = new_session(s.session_secret, s.admin_session_minutes)
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        max_age=s.admin_session_minutes * 60,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
    log.info("admin login", extra={"client": client})
    return _info(sess)


@router.get("/session", response_model=AdminSessionInfo)
def session(sess: Admin) -> AdminSessionInfo:
    """The current session's CSRF token and expiry (the cookie itself is httpOnly)."""
    return _info(sess)


@router.post("/logout", status_code=204)
def logout(sess: Admin, response: Response) -> Response:
    revoke(sess)
    response.status_code = 204
    response.delete_cookie(
        SESSION_COOKIE, path=COOKIE_PATH, secure=True, httponly=True, samesite="strict"
    )
    return response


# --- Actions ------------------------------------------------------------------------------------


def _enqueue(kind: str, **payload: Any) -> JobQueued:
    return JobQueued(job_id=jobs.enqueue(app_db.engine, kind, {"trigger": "admin", **payload}))


@router.post("/ingest", response_model=JobQueued, status_code=202)
def ingest(body: IngestRequest, db: DB) -> JobQueued:
    """Queue ingestion of one source, or of every active source when `source` is omitted. The
    worker queues a pipeline run when it finishes."""
    if body.source:
        src = db.scalars(select(Source).where(Source.key == body.source)).one_or_none()
        if src is None:
            raise ApiError(404, "not_found", f"source {body.source!r} not found")
        if not src.enabled or src.admin_disabled:
            raise ApiError(409, "source_inactive", f"source {body.source!r} is not active")
        return _enqueue("ingest_all", source=body.source)
    return _enqueue("ingest_all")


@router.post("/pipeline", response_model=JobQueued, status_code=202)
def pipeline() -> JobQueued:
    """Queue an AI pipeline run over `new` items (paid LLM calls, within the spend limits)."""
    return _enqueue("pipeline")


@router.post("/trend-brief", response_model=JobQueued, status_code=202)
def trend_brief() -> JobQueued:
    """Queue a new weekly trend brief (one paid call to ASSISTANT_MODEL)."""
    s = get_settings()
    if not (s.anthropic_api_key and s.assistant_model):
        raise ApiError(409, "assistant_unavailable", "ASSISTANT_MODEL is not configured")
    return _enqueue("trend_brief")


@router.post("/reprocess-outdated", response_model=Reprocessed, status_code=202)
def reprocess_all_outdated() -> Reprocessed:
    """Send items classified with an older prompt (version, or categories since edited) back to
    `new` and queue a pipeline run. Paid: every one is classified again."""
    n = reprocess_outdated(app_db.engine)
    return Reprocessed(items=n, job_id=_enqueue("pipeline").job_id if n else None)


@router.post("/items/{item_id}/reprocess", response_model=Reprocessed, status_code=202)
def reprocess_one(item_id: Annotated[int, Path(ge=1, le=2**63 - 1)]) -> Reprocessed:
    """Send one item back to `new` (any status) and queue a pipeline run."""
    if not reprocess_item(app_db.engine, item_id):
        raise ApiError(404, "not_found", f"item {item_id} not found")
    return Reprocessed(items=1, job_id=_enqueue("pipeline").job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobQueued)
def retry_job(job_id: Annotated[int, Path(ge=1, le=2**63 - 1)]) -> JobQueued:
    """Give a dead-lettered job a fresh set of attempts (§11.4)."""
    if not jobs.retry_dead(app_db.engine, job_id):
        raise ApiError(409, "not_dead_letter", f"job {job_id} is not in dead_letter")
    return JobQueued(job_id=job_id)


# --- Views --------------------------------------------------------------------------------------


@router.get("/runs", response_model=list[AdminRun])
def runs(db: DB) -> list[Any]:
    """The last 50 ingest and pipeline runs with counts, errors and spend-limit stop reasons."""
    return list(db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(50)))


@router.get("/jobs", response_model=list[AdminJob])
def list_jobs(db: DB) -> list[Any]:
    """The last 50 durable jobs, including dead letters and their last error."""
    return list(db.scalars(select(Job).order_by(Job.id.desc()).limit(50)))


def _source(s: Source) -> AdminSource:
    return AdminSource(
        key=s.key,
        name=s.name,
        type=s.type,
        url=s.url,
        enabled=s.enabled,
        admin_disabled=s.admin_disabled,
        active=s.enabled and not s.admin_disabled,
        terms_url=s.settings.get("terms_url"),
        last_fetched_at=s.last_fetched_at,
        last_success_at=s.last_success_at,
        last_status=s.last_status,
        last_error=s.last_error,
    )


@router.get("/sources", response_model=list[AdminSource])
def sources(db: DB) -> list[AdminSource]:
    return [_source(s) for s in db.scalars(select(Source).order_by(Source.id))]


@router.patch("/sources/{key}", response_model=AdminSource)
def patch_source(
    key: Annotated[str, Path(max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")],
    body: SourcePatch,
    db: DB,
) -> AdminSource:
    """Pause or resume a source. A source disabled in config/sources.yaml (terms not reviewed)
    can't be turned on here."""
    src = db.scalars(select(Source).where(Source.key == key)).one_or_none()
    if src is None:
        raise ApiError(404, "not_found", f"source {key!r} not found")
    if body.active and not src.enabled:
        raise ApiError(409, "disabled_in_config", f"source {key!r} is disabled in sources.yaml")
    src.admin_disabled = not body.active
    db.commit()
    log.info("admin source change", extra={"source_key": key, "active": body.active})
    return _source(src)


@router.get("/categories", response_model=list[AdminCategory])
def categories(db: DB) -> list[Any]:
    rows = db.scalars(select(Category).order_by(Category.sort_order, Category.slug))
    return [AdminCategory.model_validate(c, from_attributes=True) for c in rows]


@router.patch("/categories/{slug}", response_model=AdminCategory)
def patch_category(
    slug: Annotated[str, Path(max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")],
    body: CategoryPatch,
    db: DB,
) -> AdminCategory:
    """Edit a category. The next classification run uses it; seeding keeps the edit (D-035)."""
    cat = db.get(Category, slug)
    if cat is None:
        raise ApiError(404, "not_found", f"category {slug!r} not found")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if changes.get("enabled") is False and cat.enabled:
        others = db.scalar(select(func.count()).where(Category.enabled, Category.slug != slug))
        if not others:
            raise ApiError(409, "last_category", "at least one category must stay enabled")
    db.execute(
        update(Category)
        .where(Category.slug == slug)
        .values(**changes, admin_edited_at=func.now(), updated_at=func.now())
    )
    db.commit()
    db.refresh(cat)
    log.info("admin category change", extra={"category": slug, "fields": sorted(changes)})
    return AdminCategory.model_validate(cat, from_attributes=True)


REJECTED = ("rejected_prefilter", "rejected_ai", "duplicate")


@router.get("/rejected", response_model=Page[RejectedItem])
def rejected(
    pg: Annotated[Pagination, Depends(pagination)],
    db: DB,
    status: Annotated[
        Literal["rejected_prefilter", "rejected_ai", "duplicate"] | None, Query()
    ] = None,
) -> Page[RejectedItem]:
    """Items kept out of the feed, newest decision first, with the reason (the AI filter demo)."""
    where = Item.status == status if status else Item.status.in_(REJECTED)
    total = db.scalar(select(func.count()).select_from(Item).where(where)) or 0
    rows = db.execute(
        select(
            Item.id,
            Item.title,
            Item.original_url,
            Item.publisher,
            Item.published_at,
            Item.status,
            func.coalesce(Item.status_reason, AIAnnotation.reject_reason, Item.duplicate_reason),
            AIAnnotation.relevance_score,
            AIAnnotation.quality_score,
            Item.duplicate_of,
            Item.duplicate_similarity,
            Item.updated_at,
        )
        .outerjoin(AIAnnotation, AIAnnotation.item_id == Item.id)
        .where(where)
        .order_by(Item.updated_at.desc(), Item.id.desc())
        .offset(pg.offset)
        .limit(pg.page_size)
    ).all()
    keys = RejectedItem.model_fields.keys()  # same order as the columns above
    return Page[RejectedItem](
        items=[RejectedItem(**dict(zip(keys, r, strict=True))) for r in rows],
        page=pg.page,
        page_size=pg.page_size,
        total=total,
        has_more=pg.offset + len(rows) < total,
    )
