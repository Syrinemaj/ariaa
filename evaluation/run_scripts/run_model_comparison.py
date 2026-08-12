"""ARIA-EVAL: multi-model comparison orchestrator for the normalization
confidence-gate points (semantic_normalizer.py / group_normalizer.py).

Runs run_normalization_eval.run_eval() once per (provider, model) pair,
sharing a SINGLE BudgetGuard across all of them — the budget is a ceiling
for the whole comparison, not per model. If the budget runs out mid-way
through model N, the remaining models are skipped (reported, not silently
dropped) rather than exceeding the cap.

    python -m evaluation.run_scripts.run_model_comparison \\
        --cases e03_single_prefixed_unknown_prefix,f01_unknown_prefix_repeated_3word,f02_unknown_prefix_2part,k01_group_llm_real_trigger,d03_shop_cart_item \\
        --models bedrock:eu.anthropic.claude-haiku-4-5,bedrock:eu.anthropic.claude-sonnet-5 \\
        --budget 0.10 --max-tokens 150

Each --models entry is "provider:model_id". Results land in
evaluation/results/normalization_results_<out-suffix-per-model>.csv (one
per model, via run_eval()'s existing --out-suffix mechanism) plus a final
comparison table printed to stdout — THIS COSTS REAL TOKENS, see --budget.
"""
from __future__ import annotations

import argparse
import re
from typing import List, Tuple

from evaluation.metrics.normalization_metrics import (
    exact_case_pass_rate,
    false_positive_count,
    is_risky,
    precision,
    recall,
    specificity,
)
from evaluation.run_scripts.run_normalization_eval import run_eval
from evaluation.tracer.normalization_tracer import BudgetExceeded, BudgetGuard


def _parse_models(spec: str) -> List[Tuple[str, str]]:
    """'bedrock:eu.anthropic.claude-haiku-4-5,bedrock:eu.anthropic.claude-sonnet-5'
    -> [("bedrock", "eu.anthropic.claude-haiku-4-5"), ("bedrock", "eu.anthropic.claude-sonnet-5")]"""
    pairs = []
    for entry in spec.split(","):
        provider, _, model = entry.partition(":")
        if not provider or not model:
            raise ValueError(f"Format attendu 'provider:model', reçu {entry!r}")
        pairs.append((provider.strip(), model.strip()))
    return pairs


def _safe_suffix(model_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", model_id)


def run_comparison(
    case_ids: List[str],
    models: List[Tuple[str, str]],
    total_budget_usd: float,
    max_tokens: int,
) -> List[dict]:
    guard = BudgetGuard(total_budget_usd)
    comparison_rows: List[dict] = []

    for provider, model in models:
        if guard.spent_usd >= guard.max_usd:
            print(f"\n🛑 Budget épuisé ({guard.spent_usd:.4f}$) — modèle {provider}/{model} sauté entièrement.")
            comparison_rows.append({
                "provider": provider, "model": model, "skipped": True,
            })
            continue

        print(f"\n{'=' * 70}\n▶ {provider} / {model}  (budget restant : {guard.max_usd - guard.spent_usd:.4f}$)\n{'=' * 70}")
        try:
            results = run_eval(
                use_ai=True, provider=provider, model=model,
                out_suffix=_safe_suffix(model), case_ids=list(case_ids),
                budget_guard=guard, max_tokens=max_tokens,
            )
        except BudgetExceeded as exc:
            print(f"🛑 Budget épuisé pendant {provider}/{model} : {exc}")
            results = []

        if not results:
            comparison_rows.append({"provider": provider, "model": model, "skipped": True})
            continue

        comparison_rows.append({
            "provider": provider, "model": model, "skipped": False,
            "cases_completed": len(results),
            "recall": recall(results),
            "precision": precision(results),
            "specificity": specificity(results),
            "false_positives": false_positive_count(results),
            "risky": is_risky(results),
            "exact_case_pass_rate": exact_case_pass_rate(results),
            "total_cost_usd": sum(r.get("trace", {}).get("total_estimated_cost_usd", 0.0) for r in results),
        })

    print(f"\n{'=' * 70}\n══ COMPARATIF FINAL ══  (budget total dépensé : {guard.spent_usd:.4f}$ / {guard.max_usd:.4f}$)\n{'=' * 70}")
    header = f"{'Modèle':40s} {'Recall':>8s} {'Precision':>10s} {'Specif.':>8s} {'FP':>4s} {'Risqué':>8s} {'Coût $':>10s}"
    print(header)
    print("-" * len(header))
    for row in comparison_rows:
        if row.get("skipped"):
            print(f"{row['provider'] + '/' + row['model']:40s} {'SAUTÉ (budget)':>50s}")
            continue
        label = f"{row['provider']}/{row['model']}"
        risky_marker = "⚠ OUI" if row["risky"] else "non"
        print(f"{label:40s} {row['recall']:>7.1%} {row['precision']:>9.1%} "
              f"{row['specificity']:>7.1%} {row['false_positives']:>4d} {risky_marker:>8s} "
              f"{row['total_cost_usd']:>9.4f}$")

    return comparison_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True,
                         help="IDs de cas séparés par des virgules")
    parser.add_argument("--models", required=True,
                         help="Modèles séparés par des virgules, format provider:model_id "
                              "(ex: bedrock:eu.anthropic.claude-haiku-4-5)")
    parser.add_argument("--budget", type=float, required=True,
                         help="Budget total USD partagé entre tous les modèles listés")
    parser.add_argument("--max-tokens", type=int, default=150)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_comparison(
        case_ids=args.cases.split(","),
        models=_parse_models(args.models),
        total_budget_usd=args.budget,
        max_tokens=args.max_tokens,
    )
