"""
Workflow sequence builder — converts NormalizedEndpoints to WorkflowSteps.

Amélioration 4 : optional LLM-based step reordering.
  reorder_steps_sync(steps, ai_client, redis) reorders steps into the correct
  business execution order when the captured sequence appears wrong
  (e.g. auth step not first, DELETE before POST on the same resource).

Backward compatibility:
  build_sequence(endpoints) signature unchanged — new params are keyword-only
  and default to None so existing callers need no changes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import List, Optional

from app.normalization.models import NormalizedEndpoint
from app.workflows.models import WorkflowStep

logger = logging.getLogger(__name__)

_AUTH_KEYWORDS = frozenset({"login", "token", "auth", "signin", "refresh", "oauth"})

_REORDER_SCHEMA = {
    "name": "step_reorder",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "ordered_keys": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {"type": "number"},
        },
        "required": ["ordered_keys", "confidence"],
        "additionalProperties": False,
    },
}

# Confidence threshold below which a proposed reorder is discarded rather
# than applied — see the audit note on reorder_steps_sync: a bad reorder
# used to be applied unconditionally, with no signal to gate on.
_REORDER_MIN_CONFIDENCE = 0.60

_REORDER_SYSTEM = """You are an API workflow sequencing expert. Reorder the given API steps into
the correct business execution sequence, applying these rules in order:
1. Authentication (login/token/auth/oauth) must be FIRST.
2. POST (create) before GET (read) of the same resource type.
3. DELETE must be LAST for a given resource.
4. Respect parent-child order (create the parent resource before its children).

Return ordered_keys containing EXACTLY the same canonical_key values you were
given, in the corrected order — never drop, duplicate, or invent a key. If
you are not confident the sequence actually needs correction, return the
keys in their original order rather than guessing, and set confidence low.

confidence: 0.8-1.0 when the rules above clearly dictate a specific order,
0.5-0.8 when the reorder is a reasonable guess, <0.5 when you are unsure a
reorder is even needed.

Return strict JSON only — no markdown, no explanation."""


def _path_prefix(path: str, depth: int = 2) -> str:
    parts = [seg for seg in path.split("/") if seg and not seg.startswith("{")]
    return "/" + "/".join(parts[:depth]) if parts else "/"


def _needs_reorder(steps: List[WorkflowStep]) -> bool:
    """
    Return True when the step sequence is detectably out of logical order:
    - An auth endpoint (login/token/oauth…) is not at position 0.
    - A DELETE step precedes a POST on the same resource prefix.
    """
    for i, step in enumerate(steps):
        if any(kw in step.path.lower() for kw in _AUTH_KEYWORDS) and i > 0:
            return True

    for i, step_i in enumerate(steps):
        if step_i.method != "DELETE":
            continue
        prefix_i = _path_prefix(step_i.path)
        for step_j in steps[i + 1:]:
            if step_j.method == "POST" and _path_prefix(step_j.path) == prefix_i:
                return True

    return False


def build_sequence(endpoints: List[NormalizedEndpoint]) -> List[WorkflowStep]:
    """
    Convert a list of NormalizedEndpoints to WorkflowSteps in insertion order.
    Stores response_body and ai_summary in step metadata so that downstream
    modules (dependency_detector, workflow_descriptor) can use them without
    re-querying the database.
    """
    steps: List[WorkflowStep] = []
    for index, endpoint in enumerate(endpoints):
        response_body = endpoint.response_body
        if isinstance(response_body, str):
            try:
                response_body = json.loads(response_body)
            except Exception:
                response_body = None

        steps.append(WorkflowStep(
            order=index + 1,
            method=endpoint.method,
            path=endpoint.normalized_path,
            canonical_key=endpoint.canonical_key,
            action=endpoint.metadata.get("business_action"),
            status=endpoint.status,
            metadata={
                "business_domain": endpoint.metadata.get("business_domain"),
                "source_count":    endpoint.source_count,
                "original_path":   endpoint.original_path,
                "ai_summary":      endpoint.metadata.get("ai_summary"),
                "response_body":   response_body,
            },
        ))
    return steps


def reorder_steps_sync(
    steps: List[WorkflowStep],
    ai_client=None,
    redis=None,
) -> List[WorkflowStep]:
    """
    Reorder workflow steps into the correct business execution sequence.

    Uses a sync LLM call (GroqClient.structured_chat) — call via asyncio.to_thread
    if invoked from an async context.

    Returns steps unchanged when:
    - ai_client is None, OR
    - _needs_reorder() returns False (sequence already looks correct), OR
    - the LLM's own confidence is below _REORDER_MIN_CONFIDENCE.

    Redis caches {ordered_keys, confidence} with TTL 24h.
    """
    if ai_client is None or not _needs_reorder(steps):
        return steps

    cache_key = "workflow:order:" + hashlib.md5(
        "|".join(s.canonical_key for s in steps).encode()
    ).hexdigest()

    ordered_keys: Optional[List[str]] = None
    confidence: float = 1.0  # cached results were already confidence-gated before being stored

    if redis is not None:
        try:
            cached = redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                ordered_keys = cached_data.get("ordered_keys")
        except Exception:
            pass

    if ordered_keys is None:
        steps_payload = [
            {
                "key":     s.canonical_key,
                "method":  s.method,
                "path":    s.path,
                "summary": s.metadata.get("ai_summary") or "",
            }
            for s in steps
        ]
        user_payload = {"steps": steps_payload}
        try:
            result = ai_client.structured_chat(
                system_prompt=_REORDER_SYSTEM,
                user_payload=user_payload,
                json_schema=_REORDER_SCHEMA,
                task_name="workflow_reorder",
            )
            confidence = float(result.get("confidence", 0.0))
            if confidence < _REORDER_MIN_CONFIDENCE:
                logger.info(
                    "workflow_reorder.low_confidence steps=%d confidence=%.2f — keeping original order",
                    len(steps), confidence,
                )
                return steps

            ordered_keys = result.get("ordered_keys") or []
            if redis is not None and ordered_keys:
                try:
                    redis.setex(cache_key, 86400, json.dumps({
                        "ordered_keys": ordered_keys,
                        "confidence": confidence,
                    }))
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("workflow_reorder.failed error=%s", exc)
            return steps

    if not ordered_keys:
        return steps

    key_to_step = {s.canonical_key: s for s in steps}
    reordered   = [key_to_step[k] for k in ordered_keys if k in key_to_step]
    seen        = set(ordered_keys)
    reordered  += [s for s in steps if s.canonical_key not in seen]

    for i, s in enumerate(reordered):
        s.order = i + 1

    logger.info("workflow_reorder.done steps=%d confidence=%.2f", len(reordered), confidence)
    return reordered
