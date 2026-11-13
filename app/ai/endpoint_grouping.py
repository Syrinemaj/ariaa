"""
LLM-based grouping for app/workflows/clustering.py — the PRIMARY strategy
for whatever endpoints don't match _FUNCTIONAL_CATEGORIES's generic
keywords (auth, config, i18n...), i.e. the app's actual business data,
worded however that app's developers named it (ForYou's HR dossier,
another app's orders/patients/whatever — never hardcoded here).

Design history (why this shape, not something simpler):

- Path-prefix grouping alone fragments real groups: endpoints whose path
  happens to be short (e.g. /hr-rich-client/hrservlet/hrqsql, 3 segments)
  become their own singleton "prefix" and get orphaned into the catch-all
  even when a real sibling group (the rest of the HR dossier calls) forms
  right next to them. Kept only as the offline/no-ai_client fallback below.

- Embeddings were tried and rejected: local sentence-transformers
  (bge-small-en) on short method+path+action phrases does NOT separate
  cleanly at any single DBSCAN eps — e.g. "fetch employee record" /
  "retrieve worker details" (should cluster) vs "submit billing receipt"
  (should NOT) landed in the same cluster at every eps that wasn't
  degenerate the other way. Too little context in a short phrase.

- Naming used to be a SEPARATE, later pass (workflow_understanding.
  enrich_workflow_with_ai, run once per workflow after the run was already
  saved) — two LLM calls, two sources of truth, and the thing that caused
  a real bug: the Celery task's returned summary used the pre-rename
  objects and reported stale names. This schema returns name +
  business_domain + summary in the SAME call that does the grouping, so a
  workflow is fully named at the moment it's created. There is no second
  naming pass anymore.

- Confidence is NOT taken from the model's self-report here — LLM
  "confidence" fields are typically overconfident and don't reflect
  anything measurable. app/workflows/clustering.py assigns confidence
  deterministically instead (by provenance: rule-matched category vs.
  LLM-reasoned group vs. catch-all), so this schema doesn't ask for one.

Caching: callers key on a hash of the endpoint set and cache the result
(see clustering.py's _semantic_cluster_llm) — same reprocessed HAR = same
grouping, without re-paying for or re-rolling the LLM call.
"""
from __future__ import annotations

from typing import Any, Dict, List

SYSTEM_PROMPT = """You group API endpoints into coherent business-capability clusters — by what
they DO together in a real business process, not by how similar their text
looks — and you name each cluster.

You receive a JSON array of endpoints, each with an "index", "method",
"path", and "business_action" (may be null/generic — infer from path/method
when it is).

RULES
- Every index in the input must appear in exactly one group's
  endpoint_indices — no index skipped, no index in two groups.
- Prefer 2-6 groups. A group of one endpoint is fine if nothing else in the
  list genuinely relates to it — do not force unrelated endpoints together
  just to avoid singletons.
- Group by real-world business relationship (e.g. "read + write the same
  resource", "steps of the same task"), not by shared words or URL prefix.
- name: a short snake_case name for the group's business capability (e.g.
  "employee_record_management", "invoice_processing") — not generic like
  "group_1" or "misc".
- business_domain: the broader business area this group belongs to (e.g.
  "human_resources", "billing", "user_management") — snake_case, one to
  three words.
- summary: ONE plain-language sentence describing what this group of calls
  does together, for a non-technical reader.

Return strict JSON only, matching the schema exactly.
"""

ENDPOINT_GROUPING_SCHEMA: Dict[str, Any] = {
    "name": "endpoint_grouping",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":              {"type": "string"},
                        "business_domain":   {"type": "string"},
                        "summary":           {"type": "string"},
                        "endpoint_indices":  {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["name", "business_domain", "summary", "endpoint_indices"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["groups"],
        "additionalProperties": False,
    },
}


def build_grouping_payload(endpoints: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "index": i,
            "method": ep.method,
            "path": ep.normalized_path,
            "business_action": (ep.metadata or {}).get("business_action"),
        }
        for i, ep in enumerate(endpoints)
    ]
