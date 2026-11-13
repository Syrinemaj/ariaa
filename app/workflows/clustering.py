"""
Endpoint clustering + naming — a workflow is fully named at the moment it's
created here. There is no separate later naming pass (see "Naming ownership"
below for why that changed).

Strategy:

  1. Group by _FUNCTIONAL_CATEGORIES — a fixed, deterministic taxonomy keyed
     off URL path keywords (auth/session, access control, app config,
     localization, indicators/KPI, task automation). NOT business_domain:
     that's free-text LLM output and fragments what a human would call one
     obvious category into a dozen near-synonyms per HAR ("human_resources"
     / "Human Resources" / "HR" / "hr_operations" / "hr_system"...), which
     starved real clusters below _MIN_CLUSTER_SIZE and forced most of the
     app into the catch-all bucket. Deliberately app-agnostic: every entry
     is a cross-cutting concern common to almost any web/enterprise app, not
     invented for one app — applies unchanged to any HAR uploaded. There is
     NO keyword for "the app's actual business data" (ForYou's HR dossier,
     another app's orders/patients/whatever) — that's app-specific by
     definition and can't be hardcoded here; see step 2.

  2. Everything left over — the app's actual business data — is clustered by
     _cluster_remaining_endpoints(), an LLM-first cascade:
       a. LLM grouping (_semantic_cluster_llm) is the PRIMARY strategy, not
          a last resort. Empirically it reasons about real business
          relationships that neither URL structure nor text similarity can
          see (e.g. recognizing "msg-get-dossier-data" and "hrqsql" as both
          HR-record operations). Result is cached in Redis by content hash
          (see _cluster_cache_key) — reprocessing the same HAR reuses the
          same grouping AND naming instead of re-rolling the LLM, which is
          the actual fix for run-to-run non-determinism (temperature alone
          only reduces it, cache eliminates it for repeat runs of the same
          input).
       b. Path-structure grouping (shared first-3-segments prefix) — used
          only when (a) is unavailable (no ai_client) or fails. Cheap,
          deterministic, but fragments real groups whenever a member's path
          happens to be short (e.g. /hr-rich-client/hrservlet/hrqsql, 3
          segments, becomes its own prefix and gets orphaned even though a
          real sibling group forms right next to it) — exactly the failure
          mode (a) exists to avoid.
       c. TF-IDF character n-grams + DBSCAN, then plain depth-2 prefix — last
          resorts if sklearn is also unavailable or errors. Embeddings were
          tried and rejected here: local sentence-transformers on short
          method+path+action phrases did NOT separate cleanly at any single
          DBSCAN eps in testing — too little context in a short phrase.

  3. Groups below _MIN_CLUSTER_SIZE (from any tier) are merged into a single
     catch-all, explicitly flagged (Workflow.metadata["is_catchall"]) and
     capped at low confidence — never dressed up as a real discovery.

Naming ownership (this changed from the previous design): _FUNCTIONAL_CATEGORIES
clusters are named directly from their category key, and _semantic_cluster_llm
returns name + business_domain + summary in the SAME call that does the
grouping — a workflow has no "provisional" name that a later pass silently
overwrites. This replaced a two-phase design (cheap keyword name here, then
workflow_understanding.enrich_workflow_with_ai renaming everything again
after the run was saved) that was the source of a real bug: the Celery
task's returned result used pre-rename objects and reported stale names.
Groups with no preset name (offline path-prefix/TF-IDF fallback, no
ai_client available) still fall back to workflow_classifier.classify_workflow_name.

Confidence is assigned deterministically by provenance, not taken from the
LLM's self-report (typically overconfident, not measurable): 0.9 for a
rule-matched functional category, whatever _semantic_cluster_llm's caller
assigns for an LLM-reasoned group (see _LLM_GROUP_CONFIDENCE), 0.2 for the
catch-all, or workflow_classifier's own keyword-based score for the offline
fallback path.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from app.normalization.models import NormalizedEndpoint
from app.workflows.models import Workflow
from app.workflows.sequence_builder import build_sequence, reorder_steps_sync
from app.workflows.dependency_detector import detect_dependencies
from app.workflows.workflow_classifier import classify_workflow_name
from app.workflows.workflow_descriptor import generate_workflow_description

logger = logging.getLogger(__name__)

_CATCHALL_DOMAIN   = "__ungrouped__"
_MIN_CLUSTER_SIZE  = 2

# Preset confidence values — see module docstring "Confidence is assigned
# deterministically by provenance".
_CATEGORY_CONFIDENCE   = 0.9
_LLM_GROUP_CONFIDENCE  = 0.75
_CATCHALL_CONFIDENCE   = 0.2

# Ordering matters: e.g. a widget's /configuration/app/... entry must resolve
# to "app_configuration" even though its widget name also contains
# "indicator", and attach-session/select-role must resolve to
# "authentication_session" even though they'd otherwise fall through
# unmatched into the generic business-data bucket. Keep ordered by specificity.
_FUNCTIONAL_CATEGORIES: List[tuple] = [
    ("localization", (
        "l10n/messages", "l10n/", "/i18n", "/locale", "localiz", "/translations",
        "getlocalization",
    )),
    ("app_configuration", (
        "/configuration/", "/config/", "/settings", "/preferences", "/sitemap",
        "menuconfig", "legacydiagnostic", "debug.allow_diagnostic", "admincsp",
    )),
    ("access_control", (
        "accessmanager", "/permissions", "/roles", "role-access", "access-level",
        "accessibilitylevel", "/actors", "authoriz", "/acl/",
    )),
    ("authentication_session", (
        "usermgt", "/login", "/logout", "/signin", "/signout", "/session",
        "attach-session", "select-role", "/auth/", "/oauth", "/token", "/sso",
    )),
    ("indicators_kpi", (
        "indicator", "kpimonitoring", "/kpi", "/dashboard", "/analytics",
        "/metrics", "/stats", "widget-config", "getpublishednews",
    )),
    ("task_automation", (
        "/tasks/", "/jobs/", "/queue", "/batch", "/cron", "workflows/requests",
    )),
]


def _classify_functional_category(path: str) -> Optional[str]:
    lower = path.lower()
    for category, keywords in _FUNCTIONAL_CATEGORIES:
        if any(keyword in lower for keyword in keywords):
            return category
    return None


# Each cluster costs up to 2 sequential LLM calls (reorder + description) in
# _build_workflow_from_cluster — run clusters concurrently instead of one at
# a time, same rationale as app/ingestion/noise_scoring.py's _AI_CONCURRENCY.
_CLUSTER_CONCURRENCY = 8

# Preset carried alongside a cluster of endpoints. None means "not named yet
# — use workflow_classifier.classify_workflow_name" (only reachable via the
# offline path-prefix/TF-IDF fallback, when no ai_client is available).
Preset = Optional[Dict[str, object]]


def _path_prefix(path: str, depth: int = 2) -> str:
    """Return the first `depth` non-parameter path segments as a prefix key."""
    parts = [
        seg for seg in path.split("/")
        if seg and not seg.startswith("{")
    ]
    return "/" + "/".join(parts[:depth]) if parts else "/"


def _cluster_cache_key(endpoints: List[NormalizedEndpoint]) -> str:
    """Same shape as workflow_descriptor.py's cache key (md5 of sorted
    method+path signatures) — same principle: identical input, identical
    (cached) output, no re-roll of the LLM's sampling on reprocessing."""
    sig = "|".join(sorted(f"{ep.method} {ep.normalized_path}" for ep in endpoints))
    return "workflow:group:" + hashlib.md5(sig.encode()).hexdigest()


def _build_llm_groups(
    groups_data: List[dict],
    ungrouped: List[NormalizedEndpoint],
) -> List[Tuple[List[NormalizedEndpoint], Preset]]:
    """
    Validate + materialize an endpoint_grouping response (fresh or from
    cache) into (members, preset) tuples.

    Tolerant of a partial/imperfect response — observed in practice on a
    26-endpoint HAR (historically with llama-3.3-70b via Groq, since
    removed as a provider — the failure mode itself is model-agnostic):
    the model drops one index out of 26 roughly every other call. The
    previous version treated ANY
    coverage gap as total failure and discarded the entire grouping —
    throwing away 25 correctly-grouped endpoints because of one mistake,
    and falling all the way back to the flat path-prefix bundle this
    mechanism exists to avoid. A bad/duplicate index is now skipped (never
    added twice, never assigned to a nonexistent endpoint) rather than
    raising immediately, and whatever indices no group ever claimed are
    salvaged into their own catch-all bucket — still never silently
    dropped, never duplicated, but no longer an excuse to discard
    everything else that WAS grouped correctly.

    Still raises when the response is mostly empty or wrong (more than
    half the endpoints uncovered) — that's not "one dropped index", that's
    the LLM call having failed outright, and the caller's existing
    path-prefix/TF-IDF fallback cascade is the right response to it, not a
    catch-all covering nearly the whole HAR.
    """
    seen_indices: set = set()
    out: List[Tuple[List[NormalizedEndpoint], Preset]] = []
    for group in groups_data:
        indices = group.get("endpoint_indices") or []
        members = []
        for idx in indices:
            if not isinstance(idx, int) or idx < 0 or idx >= len(ungrouped) or idx in seen_indices:
                logger.info(
                    "llm_endpoint_grouping.bad_index skipped=%r label=%r",
                    idx, group.get("name") or group.get("label"),
                )
                continue
            seen_indices.add(idx)
            members.append(ungrouped[idx])
        if not members:
            continue
        preset = {
            "name":            group.get("name") or "business_operations",
            "business_domain": group.get("business_domain") or "",
            "summary":         group.get("summary") or "",
            "confidence":      _LLM_GROUP_CONFIDENCE,
        }
        out.append((members, preset))

    missing = [i for i in range(len(ungrouped)) if i not in seen_indices]
    if len(missing) > len(ungrouped) // 2:
        raise ValueError(
            f"LLM grouping covered only {len(seen_indices)}/{len(ungrouped)} endpoints — too incomplete to salvage"
        )
    if missing:
        logger.info(
            "llm_endpoint_grouping.partial_coverage missing=%d/%d — salvaging into catch-all",
            len(missing), len(ungrouped),
        )
        out.append(([ungrouped[i] for i in missing], _CATCHALL_DOMAIN))

    return out


def _semantic_cluster_llm(
    ungrouped: List[NormalizedEndpoint],
    ai_client,
    redis=None,
) -> Optional[List[Tuple[List[NormalizedEndpoint], Preset]]]:
    """
    Group + name leftover endpoints in one LLM call reasoning about the
    actual list, rather than a numeric similarity threshold. Returns None
    (never raises) on any failure — missing client, malformed response, or
    an index the model dropped/duplicated/invented — so the caller falls
    through to path-prefix/TF-IDF instead of trusting a broken result.
    """
    if ai_client is None:
        return None

    cache_key = _cluster_cache_key(ungrouped) if redis is not None else None
    if cache_key:
        try:
            cached = redis.get(cache_key)
            if cached:
                result = _build_llm_groups(json.loads(cached), ungrouped)
                logger.info("llm_endpoint_grouping.cache_hit ungrouped=%d", len(ungrouped))
                return result
        except Exception as exc:
            logger.info("llm_endpoint_grouping.cache_read_failed error=%s", exc)

    try:
        from app.ai.endpoint_grouping import (
            ENDPOINT_GROUPING_SCHEMA,
            SYSTEM_PROMPT,
            build_grouping_payload,
        )

        response = ai_client.structured_chat(
            system_prompt=SYSTEM_PROMPT,
            user_payload={"endpoints": build_grouping_payload(ungrouped)},
            json_schema=ENDPOINT_GROUPING_SCHEMA,
            task_name="endpoint_grouping",
        )
        groups_data = response.get("groups") or []
        result = _build_llm_groups(groups_data, ungrouped)

        if cache_key:
            try:
                redis.setex(cache_key, 86400, json.dumps(groups_data))
            except Exception:
                pass

        logger.info(
            "llm_endpoint_grouping.done ungrouped=%d groups=%d",
            len(ungrouped), len(result),
        )
        return result

    except Exception as exc:
        logger.info("llm_endpoint_grouping.failed error=%s — falling back to path-prefix", exc)
        return None


def _cluster_via_tfidf(ungrouped: List[NormalizedEndpoint]) -> Dict[str, List[NormalizedEndpoint]]:
    """TF-IDF character n-grams + DBSCAN(eps=0.40, cosine); falls back to a
    plain depth-2 prefix if sklearn is unavailable or errors. Never raises."""
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

        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
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

    clusters_fb: Dict[str, List[NormalizedEndpoint]] = {}
    for ep in ungrouped:
        key = _path_prefix(ep.normalized_path)
        clusters_fb.setdefault(key, []).append(ep)
    return clusters_fb


def _cluster_remaining_endpoints(
    ungrouped: List[NormalizedEndpoint],
    ai_client=None,
    redis=None,
) -> List[Tuple[List[NormalizedEndpoint], Preset]]:
    """
    Cluster the endpoints left over after _FUNCTIONAL_CATEGORIES — i.e. the
    app's actual business data. See module docstring for the full LLM-first
    cascade rationale.
    """
    if len(ungrouped) < _MIN_CLUSTER_SIZE:
        return [(list(ungrouped), None)]

    llm_result = _semantic_cluster_llm(ungrouped, ai_client, redis=redis)
    if llm_result is not None:
        return llm_result

    prefix_groups: Dict[str, List[NormalizedEndpoint]] = {}
    for ep in ungrouped:
        prefix_groups.setdefault(_path_prefix(ep.normalized_path, depth=3), []).append(ep)

    # Degenerate in both directions disqualifies this tier: everything
    # sharing one prefix (didn't discriminate at all) and the opposite,
    # every path getting its own unique prefix (pure ID-bearing paths like
    # /orders/1 vs /orders/2 with no {id} templating yet). Only trust it if
    # it produced at least one group meeting _MIN_CLUSTER_SIZE.
    if any(len(group) >= _MIN_CLUSTER_SIZE for group in prefix_groups.values()):
        logger.info(
            "path_prefix_cluster.done ungrouped=%d groups=%d",
            len(ungrouped), len(prefix_groups),
        )
        return [(members, None) for members in prefix_groups.values()]

    tfidf_groups = _cluster_via_tfidf(ungrouped)
    return [
        (members, _CATCHALL_DOMAIN if key == _CATCHALL_DOMAIN else None)
        for key, members in tfidf_groups.items()
    ]


def _cluster_endpoints(
    endpoints: List[NormalizedEndpoint],
    ai_client=None,
    redis=None,
) -> List[Tuple[List[NormalizedEndpoint], bool, Preset]]:
    """
    Return (members, is_catchall, preset) per cluster. Deterministic and
    reproducible when ai_client is None; when both ai_client and redis are
    given, LLM-grouped results are cache-keyed by content so reprocessing
    the same HAR reproduces the same clusters and names.
    """
    by_category: Dict[str, List[NormalizedEndpoint]] = defaultdict(list)
    ungrouped: List[NormalizedEndpoint] = []

    for ep in endpoints:
        category = _classify_functional_category(ep.normalized_path)
        if category:
            by_category[category].append(ep)
        else:
            ungrouped.append(ep)

    remaining = _cluster_remaining_endpoints(ungrouped, ai_client=ai_client, redis=redis)

    catchall: List[NormalizedEndpoint] = []
    real_clusters: List[Tuple[List[NormalizedEndpoint], Preset]] = []

    for category, members in by_category.items():
        if len(members) >= _MIN_CLUSTER_SIZE:
            real_clusters.append((members, {
                "name": category, "business_domain": category,
                "summary": "", "confidence": _CATEGORY_CONFIDENCE,
            }))
        else:
            catchall.extend(members)

    for members, preset in remaining:
        if preset == _CATCHALL_DOMAIN or len(members) < _MIN_CLUSTER_SIZE:
            catchall.extend(members)
        else:
            real_clusters.append((members, preset))

    if not real_clusters and not catchall:
        return []
    if not real_clusters:
        # Nothing clustered at all — the single group returned here is
        # exactly as arbitrary as the catch-all bucket, flagged the same way.
        return [(catchall, True, None)]

    result = [(members, False, preset) for members, preset in real_clusters]
    if catchall:
        result.append((catchall, True, None))
    return result


def _build_workflow_from_cluster(
    endpoints: List[NormalizedEndpoint],
    cluster_index: int,
    ai_client=None,
    redis=None,
    is_catchall: bool = False,
    preset: Preset = None,
    raw_calls: Optional[List[NormalizedEndpoint]] = None,
) -> Workflow:
    """
    Build a single Workflow Pydantic object from a cluster of endpoints.

    preset (name/business_domain/summary/confidence) comes from
    _cluster_endpoints — a functional-category match or an LLM grouping
    result — and is used as-is; this function does not re-derive or
    override it. Only the offline fallback path (no ai_client, or the LLM
    grouping call failed) reaches classify_workflow_name below.

    is_catchall=True means this cluster is endpoints that didn't fit any
    real category/group — sequencing/reordering has no real meaning for an
    arbitrary bag of unrelated calls, so LLM enrichment is skipped and the
    confidence is capped low, rather than dress it up as a real discovery.
    """
    steps = build_sequence(endpoints)

    if not is_catchall:
        steps = reorder_steps_sync(steps, ai_client=ai_client, redis=redis)

    steps = detect_dependencies(steps, raw_calls=raw_calls)

    if is_catchall:
        workflow_name, business_domain, confidence = "uncategorized_calls", "", _CATCHALL_CONFIDENCE
    elif preset:
        workflow_name    = str(preset["name"])
        business_domain  = str(preset["business_domain"])
        confidence       = float(preset["confidence"])
    else:
        # Offline fallback only (no ai_client available) — cheap keyword
        # classification, no LLM call.
        workflow_name, business_domain, confidence, _ = classify_workflow_name(steps, embeddings=None)
        if workflow_name == "generic_api_workflow" and cluster_index > 0:
            prefix = (
                _path_prefix(endpoints[0].normalized_path)
                .lstrip("/").replace("/", "_")
                or f"cluster_{cluster_index}"
            )
            workflow_name = f"generic_api_workflow_{prefix}"

    # Rich description (tags/risk) — complementary to name/domain above, not
    # competing with it. Skipped for catch-all: describing an arbitrary bag
    # of unrelated calls is meaningless and just spends tokens on noise.
    description_data = {} if is_catchall else generate_workflow_description(steps, ai_client=ai_client, redis=redis)
    preset_summary = (preset or {}).get("summary") if preset else None

    meta: Dict = {
        "steps_count":      len(steps),
        "discovery_method": "clustered_sequence_based",
        "cluster_index":    cluster_index,
        "is_catchall":      is_catchall,
    }
    if preset_summary:
        meta["ai_summary"] = preset_summary
    elif description_data.get("summary"):
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
    raw_calls: Optional[List[NormalizedEndpoint]] = None,
) -> List[Workflow]:
    """
    Cluster endpoints then build one fully-named Workflow per cluster.

    Parameters
    ----------
    endpoints  : normalised (deduplicated) endpoints from a HAR analysis run
    ai_client  : enables LLM-first business-data grouping (with naming) and
                 step reordering/description. Without it, everything falls
                 back to deterministic path-prefix/TF-IDF grouping and
                 keyword-based naming — still fully functional, just less
                 precise on endpoints with no shared URL structure.
    redis      : sync Redis client (redis.Redis) — caches LLM grouping and
                 per-workflow description results, TTL 24h. Passing this is
                 what makes reprocessing the same HAR reproduce the same
                 workflows rather than re-rolling the LLM's sampling.
    raw_calls  : the PRE-deduplication per-call list (one entry per original
                 HAR call, real request/response bodies — see
                 app.normalization.service.normalize_entries_with_raw).
                 Optional: when given, dependency_detector.py's value-
                 correlation pass can link steps by an actual id a call's
                 response produced and a later call's path/body consumed,
                 instead of only guessing from step order or field names.
                 Omitting it just skips that pass (steps 1-2 still run).

    Returns at least one Workflow (never an empty list when endpoints is non-empty).
    """
    if not endpoints:
        return []

    clusters = [
        (idx, members, is_catchall, preset)
        for idx, (members, is_catchall, preset) in enumerate(
            _cluster_endpoints(endpoints, ai_client=ai_client, redis=redis)
        )
        if members
    ]
    if not clusters:
        return []

    if len(clusters) == 1 or ai_client is None:
        return [
            _build_workflow_from_cluster(
                members, idx, ai_client=ai_client, redis=redis, is_catchall=is_catchall, preset=preset,
                raw_calls=raw_calls,
            )
            for idx, members, is_catchall, preset in clusters
        ]

    with ThreadPoolExecutor(max_workers=_CLUSTER_CONCURRENCY) as pool:
        return list(pool.map(
            lambda item: _build_workflow_from_cluster(
                item[1], item[0], ai_client=ai_client, redis=redis, is_catchall=item[2], preset=item[3],
                raw_calls=raw_calls,
            ),
            clusters,
        ))
