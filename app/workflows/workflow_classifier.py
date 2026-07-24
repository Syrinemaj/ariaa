"""
Workflow classification — keyword matching only.

classify_workflow_name() returns a 4-tuple:
    (name, business_domain, confidence, description)

description is always None here — this module no longer calls an LLM.

Ownership note (prompt-engineering audit, see ingestion.py Step 5): naming a
workflow used to be attempted by THREE separate LLM prompts (this module,
workflow_descriptor.py, workflow_understanding.py) computing overlapping
name/domain/confidence from the same step list, with no coordination — the
last one to run (workflow_understanding.enrich_workflow_with_ai, in
ingestion.py Step 5) always won, silently discarding whatever the other two
produced. This module's LLM fallback (_classify_with_llm) was also never
reachable in production: discover_workflows() is never called with a real
ai_client at either of its two call sites (ingestion.py, workflows/service.py).

Fix: this module now does keyword matching ONLY (cheap, deterministic,
rules-first) as a provisional name used until Step 5 runs. All LLM-based
naming lives solely in workflow_understanding.py — see that module's
docstring for why it is the single source of truth for name/business_domain/
confidence, and workflow_descriptor.py for the complementary (non-competing)
summary/tags/risk enrichment.

Coherence score:
    When endpoint embeddings are supplied, the confidence is adjusted:
        final = 0.4 * keyword_confidence + 0.6 * cluster_coherence
    This makes confidence reflect actual semantic homogeneity of the cluster,
    not just keyword hit count.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from app.workflows.models import WorkflowStep

HR_KEYWORDS = {"employee", "employees", "contract", "contracts", "onboarding", "department", "hire"}
FINANCE_KEYWORDS = {"invoice", "payment", "payments", "refund", "billing", "transaction"}
ECOMMERCE_KEYWORDS = {"cart", "checkout", "order", "orders", "product", "shipment"}


def _workflow_text(steps: List[WorkflowStep]) -> str:
    return " ".join(
        step.path.lower() + " " + str(step.action or "").lower()
        for step in steps
    )


def compute_cluster_coherence(embeddings: list) -> float:
    """
    Mean pairwise cosine similarity of a set of embedding vectors.
    Returns 0.5 (neutral) when fewer than 2 embeddings or numpy is unavailable.
    """
    if len(embeddings) < 2:
        return 0.5
    try:
        import numpy as np
        vecs = [np.array(e, dtype=float) for e in embeddings]
        normed = [v / (np.linalg.norm(v) + 1e-9) for v in vecs]
        sims = [
            float(np.dot(normed[i], normed[j]))
            for i in range(len(normed))
            for j in range(i + 1, len(normed))
        ]
        return float(np.mean(sims)) if sims else 0.5
    except Exception:
        return 0.5


def classify_workflow_name(
    steps: List[WorkflowStep],
    embeddings: Optional[list] = None,
) -> Tuple[str, Optional[str], float, Optional[str]]:
    """
    Classify a workflow by keyword matching against 3 known domain buckets.

    Parameters
    ----------
    steps      : workflow steps to classify
    embeddings : list of 384-dim vectors for cluster coherence scoring

    Returns
    -------
    (name, business_domain, confidence, description) — description is always
    None; kept in the return shape so ingestion.py/tests don't need a 3-tuple
    special case, since workflow_understanding.py may still set a real
    description downstream in Step 5.
    """
    text = _workflow_text(steps)

    hr_score        = sum(1 for kw in HR_KEYWORDS        if kw in text)
    finance_score   = sum(1 for kw in FINANCE_KEYWORDS   if kw in text)
    ecommerce_score = sum(1 for kw in ECOMMERCE_KEYWORDS if kw in text)

    scores = {
        "employee_onboarding_workflow": ("HR",        hr_score),
        "finance_payment_workflow":     ("Finance",   finance_score),
        "ecommerce_checkout_workflow":  ("Ecommerce", ecommerce_score),
    }

    best_name = max(scores, key=lambda n: scores[n][1])
    best_domain, best_score = scores[best_name]

    if best_score == 0:
        return "generic_api_workflow", None, 0.40, None

    keyword_confidence = min(0.50 + best_score * 0.10, 0.95)
    if embeddings:
        coherence          = compute_cluster_coherence(embeddings)
        final_confidence   = round(0.4 * keyword_confidence + 0.6 * coherence, 3)
    else:
        final_confidence   = keyword_confidence

    return best_name, best_domain, final_confidence, None
