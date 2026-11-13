import re

from cryptography.fernet import Fernet
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

    # ── Embedding provider ──────────────────────────────────────────────────
    # "bedrock" (default): Cohere Embed Multilingual v3 via AWS Bedrock —
    # replaced "local" (BAAI/bge-small-en) because bge-small-en is
    # English-only and ARIA's endpoint corpus / user queries are frequently
    # French; French content previously reached the index only by accident,
    # when an LLM summarization step happened to translate it.
    # "local": sentence-transformers, no network call, English-only, 384 dims.
    # See create_embedding_client() in app/ai/base_client.py.
    EMBEDDING_PROVIDER: str = "bedrock"
    # Fallback to "amazon.titan-embed-text-v2:0" is a one-line change here if
    # Cohere model access isn't enabled on the target AWS account/region —
    # both output 1024 dims by default, so no migration is needed to switch.
    BEDROCK_EMBEDDING_MODEL: str = "cohere.embed-multilingual-v3"
    # Dimensions produced by the active embedding provider. 1024 for both
    # Cohere Embed Multilingual v3 and Titan Text Embeddings V2 (Bedrock
    # defaults); 384 for LOCAL_EMBEDDING_MODEL (BAAI/bge-small-en). Must
    # match the vector(N) column in endpoint_embeddings — switching
    # EMBEDDING_PROVIDER requires re-running the matching Alembic migration
    # (011 for 384, 024 for 1024) and reindexing every run.
    EMBEDDING_DIMENSIONS: int = 1024
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

    # Fernet key for Connection.encrypted_secret (app/connections/crypto.py).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    CONNECTION_ENCRYPTION_KEY: str

    @field_validator("CONNECTION_ENCRYPTION_KEY")
    @classmethod
    def validate_connection_encryption_key(cls, v: str) -> str:
        try:
            Fernet(v.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                "CONNECTION_ENCRYPTION_KEY doit être une clé Fernet valide "
                "(32 octets url-safe base64). Générer avec : "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            ) from exc
        return v

    CORS_ORIGINS: str = "http://localhost:5173"

    DEFAULT_ORG_NAME: str = "ARIA Demo Organization"

    BULK_FILE_MAX_SIZE_MB: int = 20
    BULK_MAX_ROWS: int = 10000
    # Rows per Celery batch task — small enough for one task to finish in seconds
    BULK_BATCH_SIZE: int = 50
    # Outbound calls/second against the TARGET API, shared across every Celery
    # worker processing batches of the same job (Redis-backed — a per-worker
    # limiter can't coordinate: BULK_BATCH_SIZE batches for one job run on up
    # to `concurrency` workers at once, each blind to the others' traffic).
    BULK_RATE_LIMIT_PER_SECOND: float = 10.0
    BULK_STEP_RETRIES: int = 3

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
    # LIMITATION (measured empirically, not guessed): re-measured after the
    # BGE -> Cohere Embed Multilingual v3 migration (see EMBEDDING_PROVIDER
    # above) — Cohere's cosine scores run markedly lower than BGE's even for
    # confident, correct matches: a clean single-candidate-domain match
    # ("se connecter" -> POST /auth/login, only 3 close candidates) scored
    # ~0.37; a well-separated unambiguous match ("create a new employee" ->
    # POST /api/employees) scored ~0.70. Garbage/off-topic queries ("bake a
    # chocolate cake") topped out ~0.28. 0.4 (the BGE-era value) sits inside
    # the real-match range and would have silently dropped the 0.37 case from
    # a generated plan. 0.3 sits in the gap between the measured garbage
    # ceiling (~0.28) and the lowest measured genuine match (~0.37), same
    # spirit as the search endpoint's own floor (app/rag/models.py::
    # SemanticSearchRequest.score_threshold = 0.35). Still not a reliable
    # cross-domain relevance filter — the primary defense against bad plans
    # is PLAN_MIN_INTENT_CONFIDENCE above — ranking is correct (the true best
    # match is always first) even when the absolute score isn't a clean
    # separator.
    PLAN_MIN_RAG_SCORE: float = 0.3

    UPLOAD_DIR: str = "data/uploads"
    UPLOAD_FILE_TTL_DAYS: int = 7
    UPLOAD_FAILED_FILE_TTL_HOURS: int = 24
    CLEANUP_DRY_RUN: bool = False

    # ── AI provider ─────────────────────────────────────────────────────────
    # AWS Bedrock is the only completion provider — GroqClient and
    # AzureOpenAIClient (and the AI_PROVIDER switch that selected between
    # the three) were removed after the model-selection evaluation in
    # evaluation/aggregate.py made Bedrock's cost/latency/reliability case
    # decisive (see BEDROCK_MODEL below). create_ai_client() now always
    # returns a BedrockClient; this setting is kept only so log lines /
    # Prometheus labels that already carry a "provider" field stay meaningful.
    AI_PROVIDER: str = "bedrock"

    # ── AWS Bedrock ─────────────────────────────────────────────────────────
    AWS_REGION: str = "eu-west-2"
    # Chosen over deepseek.v3.2 (the prior default) after a full 8-task
    # comparison covering every real LLM call site in the app (see
    # evaluation/aggregate.py + evaluation/results/full_comparison.csv):
    # statistically tied on weighted quality (84.9% vs 85.1%, within noise),
    # but ~37x cheaper ($0.0199 vs $0.7501 total across the 8 tasks) and
    # ~2.4x faster with far more consistent latency (P50 1.7s/P95 2.1s vs
    # P50 4.1s/P95 63s — deepseek.v3.2 is a reasoning model that spends a
    # variable amount of time/tokens on internal reasoning before emitting
    # the tool call, which is also why it needed max_tokens >= ~1200 to
    # reliably avoid truncation; amazon.nova-lite-v1:0 has no such
    # requirement). moonshotai.kimi-k2.5/k3 were ruled out separately
    # (unresolved timeout / explicit IAM policy deny on this account) and
    # mistral.mistral-large-2402-v1:0 is structurally incompatible with
    # BedrockClient.structured_chat's forced toolChoice.tool on the Converse
    # API (ValidationException) — excluded from every task, not a quality
    # finding.
    BEDROCK_MODEL: str = "amazon.nova-lite-v1:0"

    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "aria-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"
    PROMETHEUS_METRICS_ENABLED: bool = True

    # ── AWS real billed cost sync ────────────────────────────────────────────
    # aria_llm_cost_total (Prometheus) only reflects calls that go through
    # app/llm_observability/service.py — production API traffic. It does NOT
    # see evaluation/run_scripts/* sweeps (evaluation/tracer/normalization_tracer.py
    # calls Bedrock directly via boto3 and intentionally skips app/ instrumentation),
    # so Grafana can show near-$0 while the real AWS bill is real dollars.
    # This polls Cost Explorer directly so Grafana reflects what AWS actually
    # billed, independent of which code path made the call.
    # Cost Explorer's GetCostAndUsage API costs $0.01/request and its data has
    # ~24h lag — polling faster than every few hours wastes money for no new
    # information. Default 6h = 4 calls/day ≈ $0.04/day.
    AWS_COST_SYNC_ENABLED: bool = True
    AWS_COST_SYNC_INTERVAL_SECONDS: int = 21600

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
