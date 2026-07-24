"""
AI enrichment for discovered workflows.

Called after endpoint enrichment so that business_domain / business_action
from AI-enriched endpoints can be passed as context to the workflow LLM.

One Groq call per workflow — typically 3–8 calls per run.
Falls back silently to the keyword-based name if the LLM call fails.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.structured_outputs import WORKFLOW_UNDERSTANDING_SCHEMA

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are an API workflow analysis engine — the single authoritative source
for this workflow's name, business_domain and confidence (a cheap
keyword-based guess may already exist from an earlier clustering pass;
your answer replaces it, so make it count).

Given a list of HTTP API steps (method, path, business domain, action), infer:
- name: a short snake_case workflow name describing the business process
  (e.g. "employee_onboarding", "payment_processing", "badge_provisioning")
- business_domain: the primary business domain (e.g. "HR", "Finance", "Auth", "Ecommerce")
- summary: one sentence describing what this workflow accomplishes end-to-end
- confidence:
    0.90-0.97 -> a clear, single-domain business process (e.g. all steps are
                 HR CRUD on the same employee resource)
    0.70-0.90 -> domain is clear but the process is generic or only partly
                 covered by the steps shown
    0.55-0.70 -> steps span multiple domains, or the business intent is a
                 reasonable guess rather than obvious from the paths alone

Rules:
- name must be snake_case, descriptive, and end with _workflow or _flow if needed
- Use the business context of the steps, not just the HTTP paths
- If steps span multiple domains, pick the primary business goal
- Do not invent a business process that isn't supported by the steps shown
- Return strict JSON only. No markdown, no explanation.
"""


def enrich_workflow_with_ai(
    workflow_id: str,
    steps: list[dict],
    client=None,
) -> Optional[dict]:
    """
    Call the LLM to generate a meaningful name, domain, summary and confidence
    for a workflow identified by its steps.

    steps: list of dicts with keys: order, method, path, action, business_domain
    Returns: dict with keys name, business_domain, summary, confidence — or None on failure.
    """
    if not steps:
        return None

    if client is None:
        from app.ai.groq_client import GroqClient
        client = GroqClient()

    payload = {
        "steps": [
            {
                "order":           s.get("order"),
                "method":          s.get("method"),
                "path":            s.get("path"),
                "action":          s.get("action") or "",
                "business_domain": s.get("business_domain") or "",
            }
            for s in steps[:15]  # cap at 15 steps to stay within token budget
        ]
    }

    try:
        result = client.structured_chat(
            system_prompt=_SYSTEM_PROMPT,
            user_payload=payload,
            json_schema=WORKFLOW_UNDERSTANDING_SCHEMA,
            task_name="workflow_understanding",
        )

        name       = result.get("name", "").strip()
        domain     = result.get("business_domain", "").strip()
        summary    = result.get("summary", "").strip()
        confidence = float(result.get("confidence", 0.70))

        if not name:
            return None

        logger.info(
            "workflow_understanding.done workflow_id=%s name=%s domain=%s confidence=%.2f",
            workflow_id, name, domain, confidence,
        )
        return {
            "name":            name,
            "business_domain": domain,
            "summary":         summary,
            "confidence":      max(0.50, min(0.99, confidence)),
        }

    except Exception as exc:
        logger.warning(
            "workflow_understanding.failed workflow_id=%s error=%s",
            workflow_id, exc,
        )
        return None
