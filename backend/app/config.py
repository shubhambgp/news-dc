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
    admin_token: str = ""
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
    job_lease_seconds: int = 600
    github_token: str = ""
    log_level: str = "INFO"
    # Repo-root config/ (categories.yaml, sources.yaml). In the container this resolves to /config.
    config_dir: Path = Path(__file__).resolve().parents[2] / "config"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
