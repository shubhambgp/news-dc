from functools import lru_cache

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
    github_token: str = ""
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
