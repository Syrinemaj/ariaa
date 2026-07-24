from typing import Any, Optional

from app.normalization.patterns import (
    COMPOSITE_NUMERIC_ID_PATTERN,
    CONTRACT_ID_PATTERN,
    CUSTOMER_ID_PATTERN,
    DATE_PATTERN,
    DATETIME_PATTERN,
    EMPLOYEE_ID_PATTERN,
    GENERIC_BUSINESS_ID_PATTERN,
    HASH_PATTERN,
    HEX_0X_PATTERN,
    INVOICE_ID_PATTERN,
    JWT_PATTERN,
    NUMERIC_ID_PATTERN,
    ORDER_ID_PATTERN,
    PAYMENT_ID_PATTERN,
    PREFIXED_RESOURCE_ID_PATTERN,
    PREFIXED_UUID_PATTERN,
    SHORT_HEX_ID_PATTERN,
    SHORT_PREFIXED_ID_PATTERN,
    SKU_CODE_PATTERN,
    SLUG_ID_PREFIX_PATTERN,
    SLUG_ID_SUFFIX_PATTERN,
    STRIPE_ID_PATTERN,
    ULID_PATTERN,
    UUID_PATTERN,
    VERSION_SEGMENT_PATTERN,
)
from app.normalization.payload_analyzer import find_parameter_name_from_payload

# ── Amélioration 2 : segments statiques connus à exclure ──────────────────────
# Ces tokens ressemblent à des IDs mais sont des mots-clés d'API ou de versioning.
_STATIC_SEGMENTS: frozenset[str] = frozenset({
    # Versions d'API
    "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9",
    "v10", "v11", "v12", "v13", "v14", "v15", "v16", "v17", "v18", "v19", "v20",
    # Environnements / lifecycles
    "latest", "stable", "beta", "alpha", "preview", "next",
    "current", "dev", "staging", "prod", "production",
    # Raccourcis utilisateur courants
    "me", "self", "new", "all", "any",
})

# Amélioration 1a : préfixes Stripe (avant le premier underscore).
# ch_1AbC… → prefix "ch" → charge_id
_STRIPE_PREFIX_TO_PARAM: dict[str, tuple[str, float]] = {
    "ch":    ("charge_id",             0.92),
    "sub":   ("subscription_id",       0.92),
    "cus":   ("customer_id",           0.92),
    "inv":   ("invoice_id",            0.92),
    "pi":    ("payment_intent_id",     0.92),
    "pm":    ("payment_method_id",     0.92),
    "re":    ("refund_id",             0.90),
    "po":    ("payout_id",             0.90),
    "tr":    ("transfer_id",           0.90),
    "evt":   ("event_id",              0.88),
    "prod":  ("product_id",            0.90),
    "price": ("price_id",              0.92),
    "si":    ("subscription_item_id",  0.90),
    "sku":   ("sku_id",                0.88),
    "file":  ("file_id",               0.88),
    "acct":  ("account_id",            0.92),
    "tok":   ("token_id",              0.88),
    "src":   ("source_id",             0.88),
    "dis":   ("discount_id",           0.85),
    "dp":    ("dispute_id",            0.85),
}

# Maps the first underscore-segment of a prefixed ID to a parameter name.
# e.g. "emp_soph_001" → prefix "emp" → "employee_id"
_PREFIX_TO_PARAM: dict[str, tuple[str, float]] = {
    "emp":          ("employee_id",   0.88),
    "employee":     ("employee_id",   0.88),
    "ctr":          ("contract_id",   0.88),
    "cont":         ("contract_id",   0.88),
    "contract":     ("contract_id",   0.88),
    "pay":          ("payment_id",    0.85),
    "payment":      ("payment_id",    0.85),
    "payroll":      ("payroll_id",    0.85),
    "ord":          ("order_id",      0.88),
    "order":        ("order_id",      0.88),
    "inv":          ("invoice_id",    0.88),
    "invoice":      ("invoice_id",    0.88),
    "cus":          ("customer_id",   0.88),
    "cust":         ("customer_id",   0.88),
    "customer":     ("customer_id",   0.88),
    "usr":          ("user_id",       0.88),
    "user":         ("user_id",       0.88),
    "dept":         ("department_id", 0.85),
    "dep":          ("department_id", 0.85),
    "pos":          ("position_id",   0.60),
    "position":     ("position_id",   0.85),
    "badge":        ("badge_id",      0.88),
    "doc":          ("document_id",   0.88),
    "document":     ("document_id",   0.88),
    "job":          ("job_id",        0.85),
    "tok":          ("token",         0.85),
    "token":        ("token",         0.85),
    "notif":        ("notification_id", 0.82),
    "notification": ("notification_id", 0.82),
    "batch":        ("batch_id",      0.85),
    "prod":         ("product_id",    0.85),
    "product":      ("product_id",    0.85),
    "ticket":       ("ticket_id",     0.85),
    "tick":         ("ticket_id",     0.85),
    "cart":         ("cart_id",       0.88),
    "sess":         ("session_id",    0.85),
    "session":      ("session_id",    0.85),
}


RESOURCE_PARAMETER_NAMES = {
    "users": "user_id",
    "user": "user_id",
    "employees": "employee_id",
    "employee": "employee_id",
    "customers": "customer_id",
    "customer": "customer_id",
    "orders": "order_id",
    "order": "order_id",
    "invoices": "invoice_id",
    "invoice": "invoice_id",
    "payments": "payment_id",
    "payment": "payment_id",
    "contracts": "contract_id",
    "contract": "contract_id",
    "departments": "department_id",
    "department": "department_id",
    "products": "product_id",
    "product": "product_id",
    "tickets": "ticket_id",
    "ticket": "ticket_id",
    "documents": "document_id",
    "document": "document_id",
    "files": "file_id",
    "file": "file_id",
}


def detect_parameter_type(segment: str) -> Optional[str]:
    if not segment:
        return None

    # Amélioration 2 : exclure les segments statiques connus avant tout pattern.
    # Amélioration 4 : v21+, versions mineures (v2.3) — la liste _STATIC_SEGMENTS
    # n'énumère que v1-v20, une regex couvre le reste.
    if segment.lower() in _STATIC_SEGMENTS or VERSION_SEGMENT_PATTERN.match(segment):
        return None

    if NUMERIC_ID_PATTERN.match(segment):
        return "integer"
    if COMPOSITE_NUMERIC_ID_PATTERN.match(segment):
        return "composite_numeric_id"
    if UUID_PATTERN.match(segment):
        return "uuid"
    if JWT_PATTERN.match(segment):
        return "token"
    if DATE_PATTERN.match(segment):
        return "date"
    if DATETIME_PATTERN.match(segment):
        return "datetime"
    if INVOICE_ID_PATTERN.match(segment):
        return "invoice_id"
    if PAYMENT_ID_PATTERN.match(segment):
        return "payment_id"
    if EMPLOYEE_ID_PATTERN.match(segment):
        return "employee_id"
    if ORDER_ID_PATTERN.match(segment):
        return "order_id"
    if CUSTOMER_ID_PATTERN.match(segment):
        return "customer_id"
    if CONTRACT_ID_PATTERN.match(segment):
        return "contract_id"
    if HASH_PATTERN.match(segment):
        return "hash"
    if GENERIC_BUSINESS_ID_PATTERN.match(segment):
        return "business_id"
    # Amélioration 3 : SKU / slug+id — après GENERIC_BUSINESS_ID_PATTERN pour
    # que le cas 2-segments déjà couvert (ex: "user-482") garde son chemin
    # existant ; ces deux patterns ne couvrent que le résidu (suffixe mixte,
    # ou 3+ segments).
    if SKU_CODE_PATTERN.match(segment):
        return "sku_code"
    if SLUG_ID_SUFFIX_PATTERN.match(segment) or SLUG_ID_PREFIX_PATTERN.match(segment):
        return "slug_with_id"
    # Amélioration 3 : préfixe + UUID complet — avant PREFIXED_RESOURCE_ID_PATTERN
    # (celui-ci exige un suffixe purement numérique, jamais de tiret, donc pas
    # de collision, mais la forme UUID est plus spécifique).
    if PREFIXED_UUID_PATTERN.match(segment):
        return "prefixed_uuid"
    if PREFIXED_RESOURCE_ID_PATTERN.match(segment):
        return "prefixed_resource_id"
    # Amélioration 1a : Stripe-style avant SHORT_PREFIXED pour éviter la collision.
    if STRIPE_ID_PATTERN.match(segment):
        return "stripe_id"
    if SHORT_PREFIXED_ID_PATTERN.match(segment):
        return "short_prefixed_id"
    # Amélioration 3 : "0x..." avant SHORT_HEX_ID_PATTERN (même famille hex).
    if HEX_0X_PATTERN.match(segment):
        return "hex_0x"
    if SHORT_HEX_ID_PATTERN.match(segment):
        return "short_hex_id"
    # Amélioration 1b : ULID (26 chars Crockford Base32).
    if ULID_PATTERN.match(segment):
        return "ulid"

    return None


def _singularize(resource: str) -> str:
    resource = resource.lower().strip()
    if resource.endswith("ies"):
        return resource[:-3] + "y"
    if resource.endswith("s"):
        return resource[:-1]
    return resource


def _context_param_name(
    previous_segment: Optional[str],
    known_confidence: float,
    singular_confidence: Optional[float] = None,
) -> Optional[tuple[str, str, float]]:
    """
    Resolve a parameter name from the previous path segment — used when the
    ID's own value gives no direct naming signal (short/hex/ULID/unknown-
    prefix cases, or the fully generic fallback). Returns None when there's
    no usable previous segment.

    # ARIA-NORM-FIX: previous_segment is always the raw, unnormalized
    # segment text (url_normalizer.normalize_path passes
    # raw_segments[index - 1], never an already-templated form). If it
    # itself looks ID-shaped, using it as naming material would embed a
    # concrete ID value into the parameter name — e.g. "emp_301" ->
    # "emp_301_id" — instead of a genuine resource name. This happened via
    # dynamic_segment_detector.py's cascade bug: once a real ID position was
    # excluded from further diff-counts, an adjacent literal segment (e.g.
    # "contract") could get wrongly marked dynamic too, and its
    # previous_segment was the raw ID value, not a resource word. Fixed at
    # the source in dynamic_segment_detector.py, but guarded here too as a
    # second line of defense — this function must never trust
    # previous_segment without checking its shape first.
    """
    if not previous_segment:
        return None
    normalized_previous = previous_segment.lower().strip()
    if detect_parameter_type(normalized_previous) is not None:
        return None
    if normalized_previous in RESOURCE_PARAMETER_NAMES:
        return RESOURCE_PARAMETER_NAMES[normalized_previous], "context_rules", known_confidence
    if singular_confidence is not None:
        singular = _singularize(normalized_previous)
        if singular:
            return f"{singular}_id", "context_rules", singular_confidence
    return None


def infer_parameter_name(
    previous_segment: Optional[str],
    detected_type: str,
    raw_value: str,
    request_body: Any = None,
    response_body: Any = None,
) -> tuple[str, str, float]:
    payload_name = find_parameter_name_from_payload(
        raw_value=raw_value,
        request_body=request_body,
        response_body=response_body,
    )
    # "_id" is produced when the JSON key is the bare word "id" — too generic
    # to override a resource-context name (employee_id, user_id, etc.)
    if payload_name and payload_name not in {"_id", "id"}:
        return payload_name, "payload", 0.95

    if detected_type in {"invoice_id", "payment_id", "employee_id", "order_id", "customer_id", "contract_id"}:
        return detected_type, "rules", 0.95

    if detected_type == "prefixed_resource_id":
        prefix = raw_value.split("_")[0].lower()
        if prefix in _PREFIX_TO_PARAM:
            param_name, confidence = _PREFIX_TO_PARAM[prefix]
            return param_name, "prefix_rules", confidence
        # Unknown prefix → low confidence so Groq is called
        return "resource_id", "prefix_rules_ambiguous", 0.45

    # Amélioration 3 : préfixe + UUID complet — même logique de table de
    # préfixes que prefixed_resource_id, la forme de la partie variable
    # (UUID vs _NNN) ne change rien au sens du préfixe.
    if detected_type == "prefixed_uuid":
        prefix = raw_value.split("_")[0].lower()
        if prefix in _PREFIX_TO_PARAM:
            param_name, confidence = _PREFIX_TO_PARAM[prefix]
            return param_name, "prefix_rules", confidence
        if prefix in _STRIPE_PREFIX_TO_PARAM:
            param_name, confidence = _STRIPE_PREFIX_TO_PARAM[prefix]
            return param_name, "prefix_rules", confidence
        return "resource_id", "prefix_rules_ambiguous", 0.45

    # Amélioration 3 : code SKU — type déjà sémantiquement explicite, pas
    # besoin de table de préfixes ni de contexte.
    if detected_type == "sku_code":
        return "sku", "rules", 0.75

    # Amélioration 3 : slug+id, code hex "0x", clé composite — aucun signal
    # de préfixe direct, on retombe sur le segment précédent (même logique
    # que short_hex_id/ulid), sinon nom générique à faible confiance.
    if detected_type in ("slug_with_id", "hex_0x", "composite_numeric_id"):
        context = _context_param_name(previous_segment, known_confidence=0.85, singular_confidence=0.75)
        if context:
            return context
        return "resource_id", f"{detected_type}_ambiguous", 0.45

    if detected_type == "short_prefixed_id":
        # Single-letter prefix: u→user, p→product, o→order, c→customer …
        _LETTER_TO_PARAM: dict[str, tuple[str, float]] = {
            "u": ("user_id",     0.82),
            "p": ("product_id",  0.80),
            "o": ("order_id",    0.82),
            "c": ("customer_id", 0.80),
            "e": ("employee_id", 0.80),
            "i": ("invoice_id",  0.80),
            "d": ("document_id", 0.75),
            "b": ("batch_id",    0.72),
        }
        letter = raw_value[0].lower()
        if letter in _LETTER_TO_PARAM:
            param_name, confidence = _LETTER_TO_PARAM[letter]
            return param_name, "short_prefix_rules", confidence
        # Fall through to context_rules below
        context = _context_param_name(previous_segment, known_confidence=0.90)
        if context:
            return context

    if detected_type == "short_hex_id":
        # Rely entirely on context (previous path segment) for naming
        context = _context_param_name(previous_segment, known_confidence=0.85, singular_confidence=0.75)
        if context:
            return context
        return "resource_id", "short_hex_rules_ambiguous", 0.45

    if detected_type == "stripe_id":
        # Extract prefix before the first underscore and look it up.
        prefix = raw_value.split("_")[0].lower()
        if prefix in _STRIPE_PREFIX_TO_PARAM:
            param_name, confidence = _STRIPE_PREFIX_TO_PARAM[prefix]
            return param_name, "stripe_prefix_rules", confidence
        # Unknown Stripe-style prefix → fall back to context then LLM.
        context = _context_param_name(previous_segment, known_confidence=0.80)
        if context:
            return context
        return "resource_id", "stripe_prefix_ambiguous", 0.45

    if detected_type == "ulid":
        # ULID carries no semantic prefix — rely on context like UUID.
        context = _context_param_name(previous_segment, known_confidence=0.90, singular_confidence=0.80)
        if context:
            return context
        return "ulid", "rules", 0.75

    context = _context_param_name(previous_segment, known_confidence=0.90, singular_confidence=0.80)
    if context:
        return context

    if detected_type == "uuid":
        return "uuid", "rules", 0.75
    if detected_type == "token":
        return "token", "rules", 0.90
    if detected_type == "date":
        return "date", "rules", 0.90
    if detected_type == "datetime":
        return "datetime", "rules", 0.90
    if detected_type == "hash":
        return "hash", "rules", 0.70
    if detected_type == "business_id":
        return "business_id", "rules_ambiguous", 0.50

    return "id", "fallback", 0.40
