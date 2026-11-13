from typing import Optional

# Fallback only: field names one specific backend (SopraHR's hrservlet)
# happens to use for multiplexing several business actions onto one URL.
# The real, app-agnostic mechanism is action_discriminator.py, which detects
# this pattern structurally from the batch of bodies observed for an
# endpoint in the current run — it works for any app doing this, not just
# this one. That detector needs sibling requests to compare against, so it
# runs once per (method, normalized_path) group in normalization/service.py
# and passes its result in as `discriminator_field` below. This fixed list
# only matters when build_canonical_key() is called without that batch
# context (a single isolated entry, a unit test) and happens to hit one of
# these three known names.
_ACTION_DISCRIMINATOR_FIELDS = ("dataSectionName", "dsName", "dataStructureName")

# Sentinel distinguishing "caller never ran batch detection" (fall back to
# the fixed list above) from "batch detection ran and concluded there is no
# discriminator" (explicit None from service.py — must NOT fall back, or
# every app ends up silently re-depending on the SopraHR-specific list
# whenever the generic detector's structural check doesn't fire, which
# defeats the point of having a generic detector at all).
_NOT_PROVIDED = object()


def _find_field_anywhere(body, field: str, depth: int = 0):
    """Depth-first search for `field` anywhere in the tree — deliberately
    not depth-first-per-level across all fields at once, so a generic
    top-level marker (e.g. dataStructureName, always "ZY" for this data
    structure) can't shadow a more specific one nested deeper
    (dataSectionName, which actually varies: "AG" congé vs "AD" address)."""
    if depth > 4 or body is None:
        return None
    if isinstance(body, dict):
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        for v in body.values():
            found = _find_field_anywhere(v, field, depth + 1)
            if found:
                return found
        return None
    if isinstance(body, list):
        for item in body[:5]:
            found = _find_field_anywhere(item, field, depth + 1)
            if found:
                return found
    return None


def _find_action_discriminator(body):
    for field in _ACTION_DISCRIMINATOR_FIELDS:
        found = _find_field_anywhere(body, field)
        if found:
            return found
    return None


def build_canonical_key(
    method: str,
    normalized_path: str,
    request_body=None,
    discriminator_field: Optional[str] = _NOT_PROVIDED,
) -> str:
    """
    Shape key for an endpoint: METHOD /normalized/path
    Used during normalization and workflow discovery (org-agnostic).
    NOT the key stored in the database — use build_registry_key() for that.

    discriminator_field: the body field (if any) that action_discriminator.py
    detected as multiplexing several business actions onto this URL, from
    comparing this endpoint's sibling requests in the current run.
      - a field name  -> look up that field's value, append if present.
      - None          -> batch detection ran and found nothing; do not guess,
                         leave the key as-is. This is the normal outcome for
                         most endpoints (most APIs are not multiplexed).
      - not passed    -> caller has no batch context at all (a single
                         isolated entry — normalize_entry(), a direct unit
                         test call). Falls back to the fixed, SopraHR-
                         specific _ACTION_DISCRIMINATOR_FIELDS list, since
                         that's the only signal available without siblings
                         to compare against.
    """
    method = method.upper().strip()
    path = normalized_path.strip()

    if not path.startswith("/"):
        path = f"/{path}"

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    key = f"{method} {path}"

    if discriminator_field is _NOT_PROVIDED:
        discriminator = _find_action_discriminator(request_body)
    elif discriminator_field:
        discriminator = _find_field_anywhere(request_body, discriminator_field)
    else:
        discriminator = None

    if discriminator:
        key = f"{key}#{discriminator}"

    return key


def build_registry_key(org_id: str, method: str, normalized_path: str) -> str:
    """
    Org-scoped canonical key stored in the endpoints table.
    Format: {org_id}:{METHOD} {/normalized/path}

    Including org_id in the key prevents cross-org canonical key collisions
    even if a query somehow escapes org_id filtering.
    The database also enforces a composite UNIQUE (org_id, canonical_key, run_id)
    constraint as a belt-and-suspenders measure.
    """
    shape_key = build_canonical_key(method, normalized_path)
    return f"{org_id}:{shape_key}"
