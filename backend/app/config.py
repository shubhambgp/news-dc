from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://newsdc:newsdc@localhost:5433/newsdc"
    anthropic_api_key: str = ""
    # No default model IDs on purpose: they must be verified against provider docs (PLAN 11.5).
    classifier_model: str = ""
    assistant_model: str = ""
    # Admin (Phase 8, §11.9). Admin is disabled unless ADMIN_TOKEN (≥ 16 chars) and a separate
    # SESSION_SECRET (≥ 32 chars, signs the session cookie) are both set.
    admin_token: str = ""
    session_secret: str = ""
    admin_session_minutes: int = 30
    rate_limit_admin_login: str = "5/minute"  # per client IP
    rate_limit_admin_login_global: str = "30/minute"  # all clients together
    cors_origins: str = "http://localhost:5173"  # comma-separated
    ingest_interval_minutes: int = 60
    relevance_threshold: int = 55
    quality_threshold: int = 40
    max_llm_items_per_run: int = 300
    # Phase 3 AI pipeline (§11.5). Prices are per million tokens for CLASSIFIER_MODEL; copy them
    # from the provider's pricing page. 0 = unknown, so the daily USD limit cannot trigger.
    classifier_effort: str = "low"  # output_config.effort; empty = omit (models without effort)
    classifier_input_usd_per_mtok: float = 0.0
    classifier_output_usd_per_mtok: float = 0.0
    daily_llm_budget_usd: float = 5.0
    llm_concurrency: int = 5
    llm_timeout_seconds: float = 60.0
    near_duplicate_threshold: float = 0.92
    # Semantic search hits below this cosine similarity are dropped (bge-small: off-topic queries
    # peak around 0.5-0.6 on this corpus, see VERIFICATION_LOG Phase 4).
    search_min_similarity: float = 0.6
    # Ask NewsDC (Phase 6). Prices are per million tokens for ASSISTANT_MODEL (cost logging only).
    assistant_effort: str = "low"  # output_config.effort; empty = omit
    assistant_max_tokens: int = 4000  # hard cap per answer (thinking + text)
    assistant_input_usd_per_mtok: float = 0.0
    assistant_output_usd_per_mtok: float = 0.0
    rate_limit_ask: str = "10/minute"  # per client IP, on top of RATE_LIMIT_DEFAULT
    # All clients together: the ceiling on Ask spend, whatever the number of IPs (`;` separates).
    rate_limit_ask_global: str = "30/minute;500/day"
    # Swagger UI + openapi.json. Off in production: the page loads a CDN script on the admin's
    # origin.
    api_docs: bool = True
    job_lease_seconds: int = 600
    github_token: str = ""
    log_level: str = "INFO"
    # Limit for every public route, per client IP, in-process memory (`limits` syntax).
    rate_limit_default: str = "60/minute"
    # Repo-root config/ (categories.yaml, sources.yaml). In the container this resolves to /config.
    config_dir: Path = Path(__file__).resolve().parents[2] / "config"

    @property
    def admin_enabled(self) -> bool:
        return len(self.admin_token) >= 16 and len(self.session_secret) >= 32

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
