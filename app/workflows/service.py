"""
Public API for workflow discovery.

`discover_workflows` is the canonical entry point — it returns one Workflow
per detected semantic cluster instead of collapsing everything into a single
workflow regardless of domain.

`discover_workflow` is kept for backward-compatibility with callers that
have not yet been updated (returns the first cluster's workflow).
"""
from __future__ import annotations

from typing import List

from app.normalization.models import NormalizedEndpoint
from app.workflows.clustering import discover_workflows
from app.workflows.models import Workflow


def discover_workflow(endpoints: List[NormalizedEndpoint]) -> Workflow:
    """
    Legacy single-workflow entry point.
    Returns the first (highest-confidence) workflow found in the cluster set.
    New callers should use discover_workflows() instead.
    """
    workflows = discover_workflows(endpoints)
    if not workflows:
        # Empty HAR edge-case: return an empty shell
        return Workflow(
            name="empty_workflow",
            confidence=0.0,
            metadata={"steps_count": 0, "discovery_method": "empty"},
        )
    # Return the cluster with the most steps as the "primary" workflow
    return max(workflows, key=lambda w: len(w.steps))
