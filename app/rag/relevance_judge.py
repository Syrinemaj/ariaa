"""
Post-retrieval relevance verification — LLM judge run on every search.

Why this exists
----------------
Cosine-similarity retrieval always returns the k nearest vectors, even when
nothing in the index actually answers the query — there is no "I don't
know" in nearest-neighbor search. Measured case: "refresh the token" against
an API with no refresh-token endpoint still returned 5 auth/session-domain
endpoints at 34-46% (display-rescaled) confidence, none of which perform the
requested action, with no path to an honest "nothing matches" result.

Why NOT gated on the top score (reversed from the first version of this
module)
----------------------------------------------------------------------------
The first version only ran the judge when the top1 score was below a
"confident" line (0.55), to save the extra Bedrock call on searches that
looked decisive. That gate was itself the bug, caught twice in a row:
  - "update the IBAN" scored low (~0.51) and got judged -> correctly
    rejected (no endpoint has an IBAN field).
  - "create a new employee with payroll and badge" scored high (~0.63,
    comfortably above the gate) and was therefore NEVER judged -> returned
    POST /api/employees at 82% display confidence as if the whole request
    were satisfied, when that endpoint's real fields are only
    full_name/email/department/hire_date/manager_id — no payroll, no badge.
A high overall cosine score means *something* in the query matched well; it
says nothing about whether *every* part of a multi-clause query is covered.
Gating on it reliably hides exactly the failure mode this module exists to
catch. So: always verify. The corpora here are small (tens of endpoints per
run) and this is a trust-critical surface, not a high-QPS path — the extra
latency is worth paying every time rather than guessing when it's needed.

What the judge now reports
---------------------------
Not just accept/reject: for a CORE match (e.g. "create a new employee" does
map to a real create-employee endpoint), it also lists named sub-requests
the endpoint's real fields do NOT cover (e.g. ["payroll", "badge"]), so the
caller can surface an honest caveat instead of silently implying full
coverage. A candidate with no real core match at all (e.g. IBAN update) is
dropped entirely, same as before.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.rag.models import EndpointSearchResult

logger = logging.getLogger(__name__)

_JUDGE_SCHEMA = {
    "name": "judge_relevance",
    "schema": {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "relevant": {
                            "type": "boolean",
                            "description": "True if this endpoint genuinely performs the core requested action (not just a related domain).",
                        },
                        "missing_aspects": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Specific things named in the query that this "
                                "endpoint's real fields do NOT support (e.g. "
                                "['payroll', 'badge']). Empty if the endpoint "
                                "fully covers everything asked. Only meaningful "
                                "when relevant=true."
                            ),
                        },
                    },
                    "required": ["id", "relevant", "missing_aspects"],
                },
            }
        },
        "required": ["judgments"],
    },
}

_SYSTEM_PROMPT = (
    "You are verifying search results for an API discovery tool. Given a "
    "user's natural-language request and a list of candidate API endpoints "
    "(each with its real method, path, and AI-generated summary/description/"
    "field list), judge each candidate on two separate questions:\n\n"
    "1. relevant: does this endpoint perform the CORE requested action? Be "
    "strict — a login endpoint is not relevant for 'refresh token' just "
    "because both involve authentication; a 'list balances' endpoint is not "
    "relevant for 'update balance'. If the core action itself doesn't exist "
    "on this candidate, relevant=false and missing_aspects can be empty.\n\n"
    "2. missing_aspects: ONLY for candidates where relevant=true — list any "
    "additional things specifically named in the query that this endpoint's "
    "real Request/Response fields do NOT include. Example: query 'create a "
    "new employee with payroll and badge' against an endpoint whose real "
    "fields are full_name/email/department/hire_date/manager_id -> "
    "relevant=true (it does create an employee) but "
    "missing_aspects=['payroll', 'badge'] (neither field exists on it). "
    "Do not silently ignore named details just because the core action "
    "matches — always check every noun/attribute the user explicitly asked "
    "for against the real field list.\n\n"
    "If no candidate is relevant at all, every judgment should have "
    "relevant=false — do not force the closest match."
)


async def verify_relevance_async(
    query: str,
    results: List[EndpointSearchResult],
    ai_client,
    db: Optional[Session] = None,
) -> List[EndpointSearchResult]:
    """Runs every search's results through an LLM relevance+coverage check.
    Drops candidates that don't genuinely perform the core requested action.
    Keeps the rest, annotating result.metadata['missing_aspects'] with any
    named sub-requirements the endpoint's real fields don't actually cover
    (e.g. a correct "create employee" match that doesn't support "payroll"),
    so callers can show an honest partial-match caveat instead of a flat
    confidence score implying full coverage."""
    if not results:
        return results

    candidates = [
        {
            "id": r.endpoint_id,
            "method": r.method,
            "path": r.path,
            # Full embedding text, not truncated: the Request/Response
            # fields line (needed to check both the action and the named
            # sub-requirements against real fields) is near the end of the
            # text built by app/rag/embeddings/builder.py.
            "summary": r.embedding_text,
        }
        for r in results
    ]

    try:
        raw = await ai_client.structured_chat_async(
            system_prompt=_SYSTEM_PROMPT,
            user_payload={"query": query, "candidates": candidates},
            json_schema=_JUDGE_SCHEMA,
            task_name="rag_relevance_judge",
            db=db,
        )
    except Exception as exc:
        # Fail open on the judge itself (e.g. Bedrock transient error) —
        # better to show the unverified-but-plausible embedding results than
        # to break search entirely over a verification-layer failure.
        logger.warning("rag.relevance_judge.failed query=%r error=%s", query, exc)
        return results

    judgments = {j["id"]: j for j in (raw.get("judgments") or []) if "id" in j}

    filtered: List[EndpointSearchResult] = []
    for r in results:
        judgment = judgments.get(r.endpoint_id)
        if judgment is None or not judgment.get("relevant"):
            continue
        missing = judgment.get("missing_aspects") or []
        if missing:
            r = r.model_copy(update={"metadata": {**r.metadata, "missing_aspects": missing}})
        filtered.append(r)

    logger.info(
        "rag.relevance_judge.applied query=%r candidates=%d kept=%d",
        query, len(results), len(filtered),
    )
    return filtered
