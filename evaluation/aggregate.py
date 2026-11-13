"""ARIA-EVAL: cross-task aggregation — turns the 8 separate per-task
comparison tables into ONE ranked decision per model.

Each `run_*_eval.py --models a,b,c` call already prints its own table; this
module additionally persists that same data as
`evaluation/results/summary_<task_id>.json` (via save_summary(), called at
the end of each script's run_comparison()), and `run_full_comparison.py`
reads whichever summary files exist and combines them.

Why a weighted composite instead of "pick whoever wins the most tables":
the 8 tasks are not equally important — a wrong reorder of 2 API calls is
recoverable, a wrong plan sent to production is not. TASK_CONFIG below
encodes that judgment explicitly (weight + which of that task's own metrics
count as "quality", with what internal split) so the reasoning is visible
and editable, not hidden inside one arbitrary composite number.

Weight rationale (0-100, must sum to 100):
  - planner_plan_generation (20) : core feature — directly produces plans
    executed against real APIs. Highest blast radius if wrong.
  - normalization (15)           : foundational, runs on every ingested
    endpoint — errors compound into every downstream task.
  - traffic_classification (15)  : gates what becomes an endpoint at all,
    highest call frequency (every captured HTTP exchange).
  - endpoint_understanding (13)  : shapes metadata used by grouping,
    description, and the planner's own grounding.
  - workflow_grouping (10)       : once per discovery run.
  - domain_canonicalization (10) : cached once per run (low frequency) but
    documented real-world impact — silently broke plan selection 4/4 times
    on a real HAR before this fix existed (see app/ai/domain_canonicalization.py).
  - sequence_reorder (9)         : gated by _needs_reorder(), only called
    when the captured order already looks wrong.
  - workflow_description (8)     : mostly UI-facing; risk_match still has
    real safety value (flags destructive workflows to the end user).

Each task's own metrics are combined into one 0-1 "quality" score using
sub-weights defined below (chosen to weigh the metric that would most
directly cause a wrong real-world outcome, not just any correct-looking
field), then multiplied by that run's completion_rate as a gate — a model
that fails to return valid structured output on some fraction of cases
should not out-rank one that returns valid output every time, even if its
valid answers score higher on paper.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

_EVAL_ROOT = os.path.dirname(os.path.abspath(__file__))
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

TASK_CONFIG: Dict[str, dict] = {
    "planner_plan_generation": {
        "weight": 20,
        "label": "Planner (intent + génération de plan)",
        # Not auto-exported by run_planner_eval.py (DB-bound, single-model
        # judge-scored harness, different shape) — placeholder key names
        # match evaluation/metrics/planner_metrics.py for when/if a summary
        # is dropped in manually.
        "primary_metrics": [("hit_rate", 0.4), ("mrr", 0.3), ("mapping_coverage", 0.3)],
    },
    "normalization": {
        "weight": 15,
        "label": "Normalisation sémantique + groupe",
        # Not auto-exported by run_normalization_eval.py (single-model
        # --with-ai runs, no --models comparison loop) — same caveat as above.
        "primary_metrics": [("hit_rate", 0.4), ("precision", 0.3), ("naming_accuracy", 0.3)],
    },
    "traffic_classification": {
        "weight": 15,
        "label": "Classification de trafic",
        "primary_metrics": [("f1", 0.6), ("domain_action_match", 0.4)],
    },
    "endpoint_understanding": {
        "weight": 13,
        "label": "Enrichissement d'endpoint",
        "primary_metrics": [
            ("domain_match", 0.35), ("action_match", 0.35),
            ("confidence_calibration", 0.20), ("tag_relevance", 0.10),
        ],
    },
    "workflow_grouping": {
        "weight": 10,
        "label": "Regroupement de workflows",
        "primary_metrics": [("pairwise_f1", 0.6), ("index_completeness", 0.2), ("naming_quality", 0.2)],
    },
    "domain_canonicalization": {
        "weight": 10,
        "label": "Canonicalisation de domaines",
        "primary_metrics": [("coverage", 0.4), ("distinctness", 0.4), ("count_accuracy", 0.2)],
    },
    "sequence_reorder": {
        "weight": 9,
        "label": "Réordonnancement des étapes",
        "primary_metrics": [
            ("order_constraints", 0.5), ("key_integrity", 0.3), ("confidence_calibration", 0.2),
        ],
    },
    "workflow_description": {
        "weight": 8,
        "label": "Description de workflow",
        "primary_metrics": [
            ("risk_match", 0.6), ("confidence_calibration", 0.3), ("tag_relevance", 0.1),
        ],
    },
}

assert sum(c["weight"] for c in TASK_CONFIG.values()) == 100, "TASK_CONFIG weights must sum to 100"


def save_summary(task_id: str, comparison_rows: List[dict]) -> str:
    """Persist one run_comparison() call's output rows for run_full_comparison.py
    to pick up later. Called at the end of each run_*_eval.py's run_comparison()."""
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = os.path.join(_RESULTS_DIR, f"summary_{task_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(comparison_rows, f, indent=2, ensure_ascii=False)
    return path


def load_summaries() -> Dict[str, List[dict]]:
    """Return {task_id: comparison_rows} for every summary_*.json currently
    present in evaluation/results/ — only tasks that have actually been run."""
    found: Dict[str, List[dict]] = {}
    if not os.path.isdir(_RESULTS_DIR):
        return found
    for task_id in TASK_CONFIG:
        path = os.path.join(_RESULTS_DIR, f"summary_{task_id}.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                found[task_id] = json.load(f)
    return found


def _task_quality(row: dict, primary_metrics: List[tuple]) -> Optional[float]:
    if row.get("skipped"):
        return None
    quality = sum(weight * float(row.get(key, 0.0)) for key, weight in primary_metrics)
    gate = float(row.get("completion_rate", 1.0))
    return quality * gate


def compute_rankings() -> List[dict]:
    """One row per model: overall weighted quality score (0-1, renormalized
    over only the tasks actually present), total cost across those tasks,
    and quality-per-dollar. Tasks missing a summary file are simply excluded
    from that model's denominator, not counted as zero."""
    summaries = load_summaries()
    if not summaries:
        return []

    models = sorted({row["model"] for rows in summaries.values() for row in rows})
    rankings: List[dict] = []

    for model in models:
        weighted_sum = 0.0
        weight_total = 0.0
        total_cost = 0.0
        per_task_quality: Dict[str, Optional[float]] = {}

        for task_id, rows in summaries.items():
            row = next((r for r in rows if r["model"] == model), None)
            if row is None:
                continue
            config = TASK_CONFIG[task_id]
            quality = _task_quality(row, config["primary_metrics"])
            per_task_quality[task_id] = quality
            total_cost += float(row.get("cost_usd", 0.0))
            if quality is not None:
                weighted_sum += config["weight"] * quality
                weight_total += config["weight"]

        overall = weighted_sum / weight_total if weight_total > 0 else 0.0
        rankings.append({
            "model": model,
            "overall_score": overall,
            "tasks_covered": weight_total,  # sum of weights actually scored, out of 100
            "total_cost_usd": total_cost,
            "quality_per_dollar": (overall / total_cost) if total_cost > 0 else None,
            "per_task_quality": per_task_quality,
        })

    rankings.sort(key=lambda r: r["overall_score"], reverse=True)
    return rankings
