from typing import Literal

from fastapi import APIRouter, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import __version__, db
from app.config import get_settings
from app.logging import setup_logging

router = APIRouter(prefix="/api/v1")


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


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title="NewsDC API",
        version=__version__,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()
