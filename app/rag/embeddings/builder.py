from typing import List

from app.models.endpoint import Endpoint

# Natural-language synonyms per HTTP method — bridge the gap between
# user intent ("créer", "supprimer") and REST conventions (POST, DELETE).
_METHOD_INTENT: dict[str, str] = {
    "GET":    "retrieve list read fetch get find search",
    "POST":   "create add insert new submit register upload",
    "PUT":    "replace update full overwrite set",
    "PATCH":  "update modify partial edit change patch",
    "DELETE": "delete remove revoke cancel deactivate purge",
}


def build_endpoint_embedding_text(endpoint: Endpoint) -> str:
    """Build the text string that is embedded for an endpoint.

    Priority order (most semantic → least):
    1. AI-generated summary / description / tags  (natural language, best for retrieval)
    2. Business domain + action                   (structured intent)
    3. HTTP method intent + path                  (bridged to natural language)
    4. Request/response field names               (technical discriminators)

    Intentionally excluded:
    - Auth type (identical across most endpoints → pure noise for retrieval)
    - "unknown" placeholder values (add noise without signal)
    """
    schema = endpoint.schema
    meta   = endpoint.metadata_json or {}

    ai_summary     = meta.get("ai_summary") or ""
    ai_description = meta.get("ai_description") or ""
    ai_tags        = meta.get("ai_tags") or []

    def _field_names(raw) -> str:
        if not raw:
            return ""
        try:
            props = raw.get("properties") or raw if isinstance(raw, dict) else {}
            return ", ".join(list(props.keys())[:20])
        except Exception:
            return ""

    req_fields  = _field_names(schema.request_schema  if schema else None)
    resp_fields = _field_names(schema.response_schema if schema else None)

    parts: list[str] = []

    # 1 — Natural-language semantic core
    if ai_summary:
        parts.append(f"Summary: {ai_summary}")
    if ai_description:
        parts.append(f"Description: {ai_description}")
    if ai_tags:
        parts.append(f"Tags: {', '.join(ai_tags)}")

    # 2 — Intent (only when set — skip "unknown" noise)
    if endpoint.business_domain:
        parts.append(f"Domain: {endpoint.business_domain}")
    if endpoint.business_action:
        parts.append(f"Action: {endpoint.business_action}")

    # 3 — HTTP method as natural language + structural identity
    method_intent = _METHOD_INTENT.get(endpoint.method, endpoint.method.lower())
    parts.append(f"Operation: {method_intent}")
    parts.append(f"{endpoint.method} {endpoint.path}")
    parts.append(f"Canonical: {endpoint.canonical_key}")

    # 4 — Field names (discriminators for specific queries like "IBAN", "badge")
    if req_fields:
        parts.append(f"Request fields: {req_fields}")
    if resp_fields:
        parts.append(f"Response fields: {resp_fields}")

    return "\n".join(parts)


def get_embedding(text: str) -> List[float]:
    """
    Embed a single text string using the local sentence-transformers model.

    Uses LocalEmbeddingClient with the class-level singleton — safe to call
    from both FastAPI routes and Celery workers.
    """
    from app.rag.embeddings.client import LocalEmbeddingClient
    return LocalEmbeddingClient().create_embedding(text)
