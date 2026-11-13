"""
Duplicate-conflict detection + auto-recovery for bulk create steps.

Scenario: re-running a bulk file (or two files whose rows overlap) hits a
row whose unique business field (email, matricule, ...) already exists in
the target system. The create call 409s. Before this module existed, that
row was just marked "failed" — indistinguishable in the report from a real
bug — and any later step in the same row (e.g. "submit leave request") never
ran, since there was no id to carry forward.

This module:
  1. Recognizes a 409 + "already exists"/duplicate-style response as a
     CONFLICT, not a generic failure (is_duplicate_conflict).
  2. Attempts to find the existing record via a GET to the same collection
     path (REST convention: POST /resource creates, GET /resource lists),
     matching the create payload's identity-looking fields (email, username,
     code, matricule, ...) against each returned item (find_existing_record).
  3. On exactly one match, the caller feeds that item's response fields into
     `state` via the same update_state_from_response/ENTITY_ID_ALIASES path
     a normal successful create uses — downstream steps resolve employee_id
     (etc.) exactly as if the create had just happened.
  4. On no match, more than one match, or any error during lookup, the
     caller must NOT auto-resolve — safer to surface for manual review than
     guess which existing record this row meant.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

_DUPLICATE_PATTERN = re.compile(r"already exists|duplicate|unique constraint|conflict", re.I)

# Checked in this order; the first one present in BOTH the create payload and
# a candidate record is used to match. Mirrors the identity-field intent of
# app/mapping/mapping_suggester.py's FIELD_SYNONYMS but scoped to conflict
# resolution (exact-value match, not fuzzy name matching).
_IDENTITY_FIELD_CANDIDATES = (
    "email", "username", "code", "matricule", "employee_code", "login", "national_id",
)


def is_duplicate_conflict(status_code: Optional[int], response_payload: Any) -> bool:
    if status_code != 409:
        return False
    text = response_payload if isinstance(response_payload, str) else json.dumps(response_payload or {})
    return bool(_DUPLICATE_PATTERN.search(text))


def _unwrap_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "employees", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [p for p in value if isinstance(p, dict)]
    return []


# Upper bound on list pages fetched while looking for the conflicting record.
_MAX_LOOKUP_PAGES = 50


def _next_page_params(body: Any, current_page: int, fetched: int) -> Optional[Dict[str, Any]]:
    """Query params for the next page of a page-numbered list response
    ({"items": [...], "total": N, "page": p, "page_size": s}), or None when
    the response isn't paginated that way or every item was already fetched."""
    if not isinstance(body, dict):
        return None
    total, page_size = body.get("total"), body.get("page_size")
    if not isinstance(total, int) or not isinstance(page_size, int) or page_size <= 0:
        return None
    if fetched >= total:
        return None
    return {"page": current_page + 1, "page_size": page_size}


def _identity_fields_present(payload: Dict[str, Any]) -> List[str]:
    return [f for f in _IDENTITY_FIELD_CANDIDATES if payload.get(f) not in (None, "")]


async def find_existing_record(
    client: httpx.AsyncClient,
    base_url: Optional[str],
    auth_headers: Dict[str, str],
    create_path: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Looks up the record that caused a 409 duplicate conflict on a create
    (POST) to `create_path`. Returns the matching item (so the caller can
    pull its id) or None if it can't confidently identify exactly one match.

    Assumes the REST convention that GET on the same collection path lists
    it — true for the common case (POST /api/employees creates, GET
    /api/employees lists). A create_path containing unresolved {param}
    placeholders (nested/non-collection creates) just 404s harmlessly and
    falls through to None below, same as any other lookup miss.
    """
    identity_fields = _identity_fields_present(payload)
    if not identity_fields:
        return None  # nothing reliable to match on — don't guess

    try:
        url = urljoin(base_url.rstrip("/") + "/", create_path.lstrip("/")) if base_url else create_path
        response = await client.request(method="GET", url=url, headers=auth_headers)
        if response.status_code >= 400:
            return None
        body = response.json()
        candidates = _unwrap_list(body)
        # Paginated collections: the existing record is often NOT on the
        # first page (observed: duplicates beyond the target's default 20
        # items stayed unresolved). Follow page numbers until every item
        # has been read.
        page = body.get("page", 1) if isinstance(body, dict) else 1
        for _ in range(_MAX_LOOKUP_PAGES):
            params = _next_page_params(body, page, len(candidates))
            if params is None:
                break
            response = await client.request(method="GET", url=url, headers=auth_headers, params=params)
            if response.status_code >= 400:
                break
            body = response.json()
            items = _unwrap_list(body)
            if not items:
                break
            candidates.extend(items)
            page = params["page"]
    except Exception:
        return None

    matches = [
        item for item in candidates
        if all(
            str(item.get(f, "")).strip().lower() == str(payload[f]).strip().lower()
            for f in identity_fields
        )
    ]
    return matches[0] if len(matches) == 1 else None
