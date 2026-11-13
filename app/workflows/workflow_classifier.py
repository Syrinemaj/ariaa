"""
Workflow classification — keyword matching only.

classify_workflow_name() returns a 4-tuple:
    (name, business_domain, confidence, description)

description is always None here — this module no longer calls an LLM.

Ownership note: a workflow is normally named at creation time in
clustering.py — either directly from a matched _FUNCTIONAL_CATEGORIES key,
or by the LLM grouping call in app/ai/endpoint_grouping.py, which returns
name + business_domain + summary in the same response that does the
grouping. This module's keyword-only classification is reached ONLY as the
offline fallback: no ai_client available, or the LLM grouping call failed —
see clustering.py's _build_workflow_from_cluster. workflow_descriptor.py
remains complementary (summary/tags/risk), not competing with naming.

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
    None; kept in the return shape for backward compatibility with existing
    call sites rather than changing this to a 3-tuple.
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
