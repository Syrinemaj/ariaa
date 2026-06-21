import re

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


def _redis_base(url: str) -> str:
    """Strip the /N database-index suffix from a Redis URL."""
    return re.sub(r"/\d+$", "", url.rstrip("/"))


class Settings(BaseSettings):
    APP_NAME: str = "ARIA"

    DATABASE_URL: str
    # Legacy single-URL kept for backward compat; new code uses the three below.
    REDIS_URL: str

    # ── Redis namespaces ────────────────────────────────────────────────────
    # Separate DB indices prevent Celery queue messages, task results, and
    # application data from competing for the same keyspace.
    # Derived automatically from REDIS_URL if not set explicitly.
    REDIS_BROKER_URL: str = ""    # Celery task queue           → /0
    REDIS_BACKEND_URL: str = ""   # Celery task result backend  → /1
    REDIS_APP_URL: str = ""       # App cache, sessions, limits → /2

    @model_validator(mode="after")
    def derive_redis_urls(self) -> "Settings":
        base = _redis_base(self.REDIS_URL)
        if not self.REDIS_BROKER_URL:
            self.REDIS_BROKER_URL = f"{base}/0"
        if not self.REDIS_BACKEND_URL:
            self.REDIS_BACKEND_URL = f"{base}/1"
        if not self.REDIS_APP_URL:
            self.REDIS_APP_URL = f"{base}/2"
        return self

    # ── Azure OpenAI ────────────────────────────────────────────────────────
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_MODEL: str = "gpt-4o-mini"
    AZURE_OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    AZURE_OPENAI_API_VERSION: str = "2024-08-01-preview"

    # Dimensions produced by LOCAL_EMBEDDING_MODEL (BAAI/bge-small-en → 384).
    # Must match the vector(N) column in endpoint_embeddings (migration 011).
    EMBEDDING_DIMENSIONS: int = 384
    LOCAL_EMBEDDING_MODEL: str = "BAAI/bge-small-en"

    # ── Auth ────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET_KEY doit faire au minimum 32 octets (256 bits). "
                "Générer avec : python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    CORS_ORIGINS: str = "http://localhost:5173"

    DEFAULT_ORG_NAME: str = "ARIA Demo Organization"

    HAR_MAX_SIZE_MB: int = 50
    BULK_FILE_MAX_SIZE_MB: int = 20
    BULK_MAX_ROWS: int = 10000
    # Rows per Celery batch task — small enough for one task to finish in seconds
    BULK_BATCH_SIZE: int = 50

    ALLOWED_TARGET_DOMAINS: str = ""

    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_UPLOAD: str = "10/hour"
    RATE_LIMIT_EXECUTE: str = "5/minute"

    LLM_PROMPT_COST_PER_1K: float = 0.00015
    LLM_COMPLETION_COST_PER_1K: float = 0.00060
    LLM_HIGH_TOKEN_THRESHOLD: int = 5000
    LLM_MAX_COMPLETION_TOKENS: int = 1000
    LLM_MAX_INPUT_TOKENS: int = 120_000
    LLM_MAX_INPUT_CHARS: int = 32000  # backward-compat

    UPLOAD_DIR: str = "data/uploads"
    UPLOAD_FILE_TTL_DAYS: int = 7
    UPLOAD_FAILED_FILE_TTL_HOURS: int = 24
    CLEANUP_DRY_RUN: bool = False

    # ── AI provider selection ────────────────────────────────────────────────
    # "azure" (default) → AzureOpenAIClient (embeddings + structured outputs)
    # "groq"            → GroqClient (no embeddings, json_object fallback)
    AI_PROVIDER: str = "groq"
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "aria-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"
    PROMETHEUS_METRICS_ENABLED: bool = True

    # /metrics endpoint — IP whitelist (comma-separated) OR Bearer token auth
    # Set METRICS_BEARER_TOKEN to "" to disable token auth and use IP only.
    METRICS_ALLOWED_IPS: str = "127.0.0.1"
    METRICS_BEARER_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
