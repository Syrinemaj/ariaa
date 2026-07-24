"""
Endpoint clustering before workflow discovery.

Strategy (four-tier, with optional sklearn DBSCAN):

  1. Group by business_domain already inferred during HAR classification.
  2. Within domain-less endpoints, run TF-IDF + DBSCAN for semantic clustering
     (sklearn required; falls back to path-prefix grouping when unavailable).
  3. Single-endpoint clusters (noise) are merged into a catch-all group.
  4. Optional LLM enrichment per cluster: step reordering (sequence_builder)
     and rich description/tags/risk (workflow_descriptor) — requires
     ai_client and redis to be supplied.

Workflow naming ownership (prompt-engineering audit finding): this module
gives every workflow a cheap, keyword-based provisional name
(workflow_classifier.classify_workflow_name — no LLM call). The
LLM-refined name/business_domain/confidence, when a real ai_client is
available, is set ONCE downstream by workflow_understanding.enrich_workflow_with_ai
(ingestion.py Step 5) — that is the single source of truth for those three
fields; this module does not attempt to compete with it.

Backward compatibility:
  discover_workflows(endpoints) still works with no extra arguments.
  LLM-based reorder/description activate only when ai_client / redis are passed.

New optional signature:
  discover_workflows(endpoints, ai_client=None, redis=None) -> List[Workflow]
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from app.normalization.models import NormalizedEndpoint
from app.workflows.models import Workflow
from app.workflows.sequence_builder import build_sequence, reorder_steps_sync
from app.workflows.dependency_detector import detect_dependencies
from app.workflows.workflow_classifier import classify_workflow_name
from app.workflows.workflow_descriptor import generate_workflow_description

logger = logging.getLogger(__name__)

_CATCHALL_DOMAIN   = "__ungrouped__"
_MIN_CLUSTER_SIZE  = 2


def _path_prefix(path: str, depth: int = 2) -> str:
    """Return the first `depth` non-parameter path segments as a prefix key."""
    parts = [
        seg for seg in path.split("/")
        if seg and not seg.startswith("{")
    ]
    return "/" + "/".join(parts[:depth]) if parts else "/"


def _semantic_cluster_tfidf(
    ungrouped: List[NormalizedEndpoint],
) -> Dict[str, List[NormalizedEndpoint]]:
    """
    Cluster ungrouped endpoints using TF-IDF character n-grams on
    (method + path + action) text, then DBSCAN(eps=0.40, cosine distance).

    Returns a dict mapping cluster label → endpoint list.
    Noise points (DBSCAN label -1) get key "__ungrouped__".

    Falls back to path-prefix grouping when sklearn is unavailable or raises.
    """
    if len(ungrouped) < _MIN_CLUSTER_SIZE:
        return {_CATCHALL_DOMAIN: list(ungrouped)}

    try:
        from sklearn.cluster import DBSCAN
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = [
            ep.method.lower()
            + " "
            + ep.normalized_path
            + " "
            + (ep.metadata.get("business_action") or "")
            for ep in ungrouped
        ]

        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
        )
        X      = vectorizer.fit_transform(texts)
        labels = DBSCAN(eps=0.40, min_samples=2, metric="cosine").fit_predict(X)

        clusters: Dict[str, List[NormalizedEndpoint]] = {}
        for ep, label in zip(ungrouped, labels):
            key = f"semantic_cluster_{label}" if label >= 0 else _CATCHALL_DOMAIN
            clusters.setdefault(key, []).append(ep)

        logger.info(
            "tfidf_dbscan.done ungrouped=%d clusters=%d noise=%d",
            len(ungrouped),
            sum(1 for k in clusters if k != _CATCHALL_DOMAIN),
            len(clusters.get(_CATCHALL_DOMAIN, [])),
        )
        return clusters

    except ImportError:
        logger.info("tfidf_dbscan.sklearn_unavailable — using path-prefix fallback")
    except Exception as exc:
        logger.warning("tfidf_dbscan.failed error=%s — using path-prefix fallback", exc)

    # ── Fallback: path-prefix grouping (original behaviour) ─────────────────
    clusters_fb: Dict[str, List[NormalizedEndpoint]] = {}
    for ep in ungrouped:
        key = _path_prefix(ep.normalized_path)
        clusters_fb.setdefault(key, []).append(ep)
    return clusters_fb


def _cluster_endpoints(
    endpoints: List[NormalizedEndpoint],
) -> List[List[NormalizedEndpoint]]:
    """
    Return a list of endpoint groups (clusters).
    Deterministic and reproducible — no randomness introduced by this function.
    """
    by_domain: Dict[str, List[NormalizedEndpoint]] = defaultdict(list)
    ungrouped: List[NormalizedEndpoint] = []

    for ep in endpoints:
        domain = (ep.metadata or {}).get("business_domain") or ""
        if domain:
            by_domain[domain.strip().lower()].append(ep)
        else:
            ungrouped.append(ep)

    # ── Semantic clustering for ungrouped endpoints (TF-IDF DBSCAN) ─────────
    catchall: List[NormalizedEndpoint] = []
    semantic_clusters = _semantic_cluster_tfidf(ungrouped)

    prefix_clusters: List[List[NormalizedEndpoint]] = []
    for key, group in semantic_clusters.items():
        if key == _CATCHALL_DOMAIN or len(group) < _MIN_CLUSTER_SIZE:
            catchall.extend(group)
        else:
            prefix_clusters.append(group)

    # ── Merge tiny domain clusters into catch-all ────────────────────────────
    domain_clusters: List[List[NormalizedEndpoint]] = []
    for group in by_domain.values():
        if len(group) >= _MIN_CLUSTER_SIZE:
            domain_clusters.append(group)
        else:
            catchall.extend(group)

    all_clusters = domain_clusters + prefix_clusters
    if catchall:
        all_clusters.append(catchall)

    if not all_clusters:
        return [endpoints] if endpoints else []

    return all_clusters


def _build_workflow_from_cluster(
    endpoints: List[NormalizedEndpoint],
    cluster_index: int,
    ai_client=None,
    redis=None,
) -> Workflow:
    """
    Build a single Workflow Pydantic object from a cluster of endpoints.

    name/business_domain/confidence set here are PROVISIONAL (keyword-based,
    no LLM) — see the module docstring on why workflow_understanding.py owns
    the LLM-refined version of these three fields downstream.

    When ai_client is provided:
      - Steps are reordered into logical business sequence (sequence_builder).
      - A rich description (summary, tags, risk) is generated (workflow_descriptor).
    """
    steps = build_sequence(endpoints)

    # Amélioration 4: optional LLM step reordering
    steps = reorder_steps_sync(steps, ai_client=ai_client, redis=redis)

    steps = detect_dependencies(steps)

    # Cheap keyword classification — provisional, see docstring above.
    workflow_name, business_domain, confidence, _ = classify_workflow_name(
        steps,
        embeddings=None,
    )

    # Disambiguate repeated generic names across clusters
    if workflow_name == "generic_api_workflow" and cluster_index > 0:
        prefix = (
            _path_prefix(endpoints[0].normalized_path)
            .lstrip("/")
            .replace("/", "_")
            or f"cluster_{cluster_index}"
        )
        workflow_name = f"generic_api_workflow_{prefix}"

    # Amélioration 3: LLM-generated rich description (summary/tags/risk —
    # complementary to, not competing with, workflow_understanding.py's name/domain).
    description_data = generate_workflow_description(
        steps,
        ai_client=ai_client,
        redis=redis,
    )

    meta: Dict = {
        "steps_count":      len(steps),
        "discovery_method": "clustered_sequence_based",
        "cluster_index":    cluster_index,
    }
    if description_data.get("summary"):
        meta["ai_summary"] = description_data["summary"]
    if description_data.get("description"):
        meta["ai_description"] = description_data["description"]
    if description_data.get("business_tags"):
        meta["business_tags"] = description_data["business_tags"]
    if description_data.get("estimated_risk"):
        meta["estimated_risk"] = description_data["estimated_risk"]
        meta["estimated_risk_confidence"] = description_data.get("risk_confidence", 0.5)

    return Workflow(
        name=workflow_name,
        business_domain=business_domain,
        steps=steps,
        confidence=confidence,
        metadata=meta,
    )


def discover_workflows(
    endpoints: List[NormalizedEndpoint],
    ai_client=None,
    redis=None,
) -> List[Workflow]:
    """
    Cluster endpoints by semantic proximity then build one Workflow per cluster.

    Parameters
    ----------
    endpoints  : normalised endpoints from a HAR analysis run
    ai_client  : GroqClient — enables LLM step reordering and rich description
                 (summary/tags/risk). Workflow naming stays keyword-based here
                 regardless — see module docstring.
    redis      : sync Redis client (redis.Redis) — caches all LLM results TTL 24h

    Returns at least one Workflow (never an empty list when endpoints is non-empty).
    All new parameters are backward-compatible optional kwargs — existing callers
    need no changes.
    """
    if not endpoints:
        return []

    clusters = _cluster_endpoints(endpoints)
    return [
        _build_workflow_from_cluster(
            cluster, idx, ai_client=ai_client, redis=redis
        )
        for idx, cluster in enumerate(clusters)
        if cluster
    ]
