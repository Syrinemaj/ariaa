"""
AI-powered workflow description generator.

Produces fields complementary to enrich_workflow_with_ai (workflow_understanding.py,
which owns name/business_domain/confidence — see that module's docstring):
  - summary         : one sentence for end users
  - description     : 2-3 sentences with technical context
  - business_tags   : list of 3-5 domain tags
  - estimated_risk  : "low" | "medium" | "high"
  - risk_confidence : 0-1, how confident the model is in estimated_risk

All are stored in WorkflowModel.metadata_json by the caller:
  metadata_json["ai_description"]           = result["description"]
  metadata_json["business_tags"]            = result["business_tags"]
  metadata_json["estimated_risk"]           = result["estimated_risk"]
  metadata_json["estimated_risk_confidence"] = result["risk_confidence"]

Caching: Redis key workflow:desc:{md5(sorted canonical_keys)} — TTL 24h.
Falls back to an empty dict on any LLM or network error.

Usage (sync, call via asyncio.to_thread from async contexts):
    from app.workflows.workflow_descriptor import generate_workflow_description
    from app.ai.groq_client import GroqClient
    desc = generate_workflow_description(steps, GroqClient(), redis=get_redis())
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Dict, List, Optional

from app.workflows.models import WorkflowStep

logger = logging.getLogger(__name__)

_FALLBACK: Dict = {
    "summary":               "",
    "description":           "",
    "business_tags":         [],
    "estimated_risk":        "low",
    "risk_confidence":       0.0,
}

_SCHEMA = {
    "name": "workflow_description",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "summary":         {"type": "string"},
            "description":     {"type": "string"},
            "business_tags":   {"type": "array", "items": {"type": "string"}},
            "estimated_risk":  {"type": "string"},
            "risk_confidence": {"type": "number"},
        },
        "required": ["summary", "description", "business_tags", "estimated_risk", "risk_confidence"],
        "additionalProperties": False,
    },
}

_SYSTEM = """You are analyzing a sequence of API calls that form a business workflow, to
produce a user-facing description and a rough execution risk estimate.

INPUT: a numbered list of steps (method, path, one-line summary per step),
and the total step count.

OUTPUT:
- summary: exactly ONE sentence, plain language, for a non-technical reader
- description: 2-3 sentences, technical — name the resources involved and
  the overall data flow (what gets created/read/changed, in what order)
- business_tags: 3-5 lowercase tags naming the resources/domain involved
- estimated_risk: exactly one of "low", "medium", "high", based on:
    high   -> contains a DELETE, or a payment/financial mutation, or
              irreversible bulk operations
    medium -> contains create/update mutations on business-critical
              resources (employees, contracts, accounts) but no delete
    low    -> read-only, or only low-stakes create/update (e.g. logging,
              notifications)
- risk_confidence: 0.8-1.0 when the step list clearly matches one of the
  three cases above, <0.8 when the risk category is a judgment call (e.g.
  ambiguous step summaries, or a mix that doesn't clearly fit one tier)

Return strict JSON only — no markdown, no explanation."""


def generate_workflow_description(
    steps: List[WorkflowStep],
    ai_client=None,
    redis=None,
) -> Dict:
    """
    Generate a rich description for a workflow using the LLM (sync call).

    Parameters
    ----------
    steps     : ordered list of WorkflowStep (with ai_summary in metadata if available)
    ai_client : GroqClient or compatible — required; returns fallback if None
    redis     : sync Redis client (redis.Redis) — optional, caches result TTL 24h

    Returns
    -------
    dict with keys: summary, description, business_tags, estimated_risk
    """
    if not steps or ai_client is None:
        return dict(_FALLBACK)

    cache_key = "workflow:desc:" + hashlib.md5(
        "|".join(sorted(s.canonical_key for s in steps)).encode()
    ).hexdigest()

    if redis is not None:
        try:
            cached = redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    steps_text = "\n".join(
        f"{i + 1}. {s.method} {s.path}\n"
        f"   {s.metadata.get('ai_summary') or s.action or ''}"
        for i, s in enumerate(steps)
    )
    payload = {
        "workflow_steps": steps_text,
        "step_count":     len(steps),
    }

    try:
        result = ai_client.structured_chat(
            system_prompt=_SYSTEM,
            user_payload=payload,
            json_schema=_SCHEMA,
            task_name="workflow_description",
        )

        out: Dict = {
            "summary":         (result.get("summary")        or "").strip(),
            "description":     (result.get("description")    or "").strip(),
            "business_tags":   result.get("business_tags")   or [],
            "estimated_risk":  (result.get("estimated_risk") or "low").lower(),
            "risk_confidence": float(result.get("risk_confidence", 0.5)),
        }

        if out["estimated_risk"] not in {"low", "medium", "high"}:
            out["estimated_risk"] = "low"

        if redis is not None:
            try:
                redis.setex(cache_key, 86400, json.dumps(out))
            except Exception:
                pass

        logger.info(
            "workflow_description.done steps=%d risk=%s tags=%s",
            len(steps), out["estimated_risk"], out["business_tags"],
        )
        return out

    except Exception as exc:
        logger.warning("workflow_description.failed error=%s", exc)
        return dict(_FALLBACK)
