# Field names legacy "multiplexed" endpoints (one URL, many distinct
# business actions selected by a body field) use to carry the actual action
# — e.g. this app's msg-update-dossier/msg-get-dossier-data accept the same
# URL for an address change, a salary change, or an absence/congé entry,
# distinguished only by dataSectionName inside the payload. Without this,
# every such call collapses into one canonical_key/row and whichever example
# body scores richest (see deduplication.py) silently hides the others.
_ACTION_DISCRIMINATOR_FIELDS = ("dataSectionName", "dsName", "dataStructureName")


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
) -> str:
    """
    Shape key for an endpoint: METHOD /normalized/path
    Used during normalization and workflow discovery (org-agnostic).
    NOT the key stored in the database — use build_registry_key() for that.

    When request_body carries one of _ACTION_DISCRIMINATOR_FIELDS, it is
    appended to the key so distinct business actions multiplexed onto the
    same URL/method get separate rows instead of merging into one.
    """
    method = method.upper().strip()
    path = normalized_path.strip()

    if not path.startswith("/"):
        path = f"/{path}"

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    key = f"{method} {path}"

    discriminator = _find_action_discriminator(request_body)
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
