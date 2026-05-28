def build_canonical_key(method: str, normalized_path: str) -> str:
    """
    Shape key for an endpoint: METHOD /normalized/path
    Used during normalization and workflow discovery (org-agnostic).
    NOT the key stored in the database — use build_registry_key() for that.
    """
    method = method.upper().strip()
    path = normalized_path.strip()

    if not path.startswith("/"):
        path = f"/{path}"

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return f"{method} {path}"


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
