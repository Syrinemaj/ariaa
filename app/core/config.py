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
    # Set to true in development to allow HTTP URLs and skip private-IP checks.
    # NEVER enable in production.
    ALLOW_HTTP_TARGETS: bool = False

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
    # Low temperature for structured extraction/classification tasks (intent
    # analysis, entity extraction) — we want reproducible confidence scores,
    # not creative variation.
    LLM_STRUCTURED_TEMPERATURE: float = 0.15

    # ── Instruction → plan pipeline ──────────────────────────────────────────
    # Below this confidence, analyze_business_intent's output is considered
    # too unreliable to build a plan from, even if RAG happens to return
    # endpoints (embedding search always returns "closest" matches, relevant
    # or not — confidence is the only signal that the extraction itself made
    # sense of the instruction).
    PLAN_MIN_INTENT_CONFIDENCE: float = 0.4
    # Minimum RAG similarity score (0-1, higher = more similar) for an
    # endpoint to be included in a generated plan. Without this, top_k
    # endpoints are always returned regardless of relevance.
    #
    # LIMITATION (measured empirically, not guessed): with the BGE-small
    # embedding model on short business-action text, a genuine cross-domain
    # match (e.g. a "payment" endpoint correctly retrieved for a payment
    # instruction, in a multi-domain run) can score as low as ~0.74 — nearly
    # identical to a true mismatch (~0.75) in a single-domain run. This floor
    # only catches pathological cases (near-empty semantic signal); it is NOT
    # a reliable cross-domain relevance filter. The primary defense against
    # bad plans is PLAN_MIN_INTENT_CONFIDENCE above — ranking is correct
    # (the true best match is always first) even when the absolute score
    # isn't a clean separator.
    PLAN_MIN_RAG_SCORE: float = 0.4

    UPLOAD_DIR: str = "data/uploads"
    UPLOAD_FILE_TTL_DAYS: int = 7
    UPLOAD_FAILED_FILE_TTL_HOURS: int = 24
    CLEANUP_DRY_RUN: bool = False

    # ── AI provider selection ────────────────────────────────────────────────
    # "azure" (default) → AzureOpenAIClient (embeddings + structured outputs)
    # "groq"            → GroqClient (no embeddings, json_object fallback)
    AI_PROVIDER: str = "groq"
    GROQ_API_KEY: str | None = None
    # Second Groq account/key, tried before Azure when GROQ_API_KEY hits its
    # per-key rate limit (Groq's free tier caps tokens-per-day per key) —
    # see GroqClient._secondary_groq_fallback().
    GROQ_API_KEY_2: str | None = None
    # Third Groq account/key, tried after GROQ_API_KEY_2 also hits its daily
    # limit, before falling back to Azure — see
    # GroqClient._tertiary_groq_fallback(). Same rationale as GROQ_API_KEY_2:
    # each free-tier key has its own separate 100k-tokens-per-day cap.
    GROQ_API_KEY_3: str | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "aria-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"
    PROMETHEUS_METRICS_ENABLED: bool = True

    # /metrics endpoint — IP whitelist (comma-separated) OR Bearer token auth
    # Set METRICS_BEARER_TOKEN to "" to disable token auth and use IP only.
    METRICS_ALLOWED_IPS: str = "127.0.0.1"
    METRICS_BEARER_TOKEN: str = ""

    # ── Email / SMTP (Outlook Office365 ou autre fournisseur SMTP) ───────────
    # Pour Outlook/Office365 : SMTP_HOST=smtp.office365.com, SMTP_PORT=587
    # Pour Gmail             : SMTP_HOST=smtp.gmail.com,      SMTP_PORT=587
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""           # Votre adresse email Outlook
    SMTP_PASSWORD: str = ""       # Votre mot de passe (ou App Password)
    SMTP_FROM: str = ""           # Expéditeur affiché (défaut : SMTP_USER)
    SMTP_STARTTLS: bool = True    # STARTTLS (recommandé, Outlook le requiert)

    # URL publique du frontend (utilisée dans les liens des emails)
    FRONTEND_URL: str = "http://localhost:5173"
    # Durée de validité du token de réinitialisation (secondes)
    PASSWORD_RESET_TTL_SECONDS: int = 3600

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
