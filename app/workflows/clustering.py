"""
Endpoint clustering before workflow discovery.

Strategy (three-tier, no external ML dependencies):
  1. Group by business_domain already inferred during HAR classification.
  2. Within domain-less endpoints, group by shared path-prefix (depth 2).
  3. Single-endpoint clusters are merged into a generic catch-all group
     (avoids creating dozens of trivial single-step workflows).

Each resulting cluster is handed to discover_workflow() so the existing
sequence-builder and dependency-detector logic is reused unchanged.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List

from app.normalization.models import NormalizedEndpoint
from app.workflows.models import Workflow
from app.workflows.sequence_builder import build_sequence
from app.workflows.dependency_detector import detect_dependencies
from app.workflows.workflow_classifier import classify_workflow_name

_CATCHALL_DOMAIN = "__ungrouped__"
_MIN_CLUSTER_SIZE = 2


def _path_prefix(path: str, depth: int = 2) -> str:
    """Return the first `depth` non-parameter path segments as a prefix key."""
    parts = [
        seg for seg in path.split("/")
        if seg and not seg.startswith("{")
    ]
    return "/" + "/".join(parts[:depth]) if parts else "/"


def _cluster_endpoints(
    endpoints: List[NormalizedEndpoint],
) -> List[List[NormalizedEndpoint]]:
    """
    Return a list of endpoint groups (clusters).
    Deterministic and reproducible — no randomness.
    """
    by_domain: dict[str, List[NormalizedEndpoint]] = defaultdict(list)
    ungrouped: List[NormalizedEndpoint] = []

    for ep in endpoints:
        domain = (ep.metadata or {}).get("business_domain") or ""
        if domain:
            by_domain[domain.strip().lower()].append(ep)
        else:
            ungrouped.append(ep)

    # Sub-cluster ungrouped endpoints by path prefix
    by_prefix: dict[str, List[NormalizedEndpoint]] = defaultdict(list)
    for ep in ungrouped:
        key = _path_prefix(ep.normalized_path)
        by_prefix[key].append(ep)

    # Merge tiny prefix clusters (< MIN_CLUSTER_SIZE) into a catch-all
    prefix_clusters: List[List[NormalizedEndpoint]] = []
    catchall: List[NormalizedEndpoint] = []
    for group in by_prefix.values():
        if len(group) >= _MIN_CLUSTER_SIZE:
            prefix_clusters.append(group)
        else:
            catchall.extend(group)

    # Merge tiny domain clusters into catch-all too
    domain_clusters: List[List[NormalizedEndpoint]] = []
    for group in by_domain.values():
        if len(group) >= _MIN_CLUSTER_SIZE:
            domain_clusters.append(group)
        else:
            catchall.extend(group)

    all_clusters = domain_clusters + prefix_clusters
    if catchall:
        all_clusters.append(catchall)

    # If everything ended up in one bucket, return it as-is
    if not all_clusters:
        return [endpoints] if endpoints else []

    return all_clusters


def _build_workflow_from_cluster(
    endpoints: List[NormalizedEndpoint],
    cluster_index: int,
) -> Workflow:
    """Build a single Workflow Pydantic object from a cluster of endpoints."""
    steps = build_sequence(endpoints)
    steps = detect_dependencies(steps)
    workflow_name, business_domain, confidence = classify_workflow_name(steps)

    # Disambiguate when classifier returns the same generic name for all clusters
    if workflow_name == "generic_api_workflow" and cluster_index > 0:
        # Use path prefix of first endpoint as a stable suffix
        prefix = _path_prefix(endpoints[0].normalized_path).lstrip("/").replace("/", "_") or f"cluster_{cluster_index}"
        workflow_name = f"generic_api_workflow_{prefix}"

    return Workflow(
        name=workflow_name,
        business_domain=business_domain,
        steps=steps,
        confidence=confidence,
        metadata={
            "steps_count": len(steps),
            "discovery_method": "clustered_sequence_based",
            "cluster_index": cluster_index,
        },
    )


def discover_workflows(endpoints: List[NormalizedEndpoint]) -> List[Workflow]:
    """
    Cluster endpoints by semantic proximity then build one Workflow per cluster.
    Returns at least one Workflow (never an empty list when endpoints is non-empty).

    Callers that previously used `discover_workflow()` (single result) should
    migrate to this function and handle the list.
    """
    if not endpoints:
        return []

    clusters = _cluster_endpoints(endpoints)
    return [
        _build_workflow_from_cluster(cluster, idx)
        for idx, cluster in enumerate(clusters)
        if cluster  # guard against empty clusters
    ]
