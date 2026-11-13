"""ARIA-EVAL: workflow grouping evaluation harness — sends each scenario in
golden_dataset/workflow_grouping_golden_dataset.json through the SAME
prompt/schema used in production (app/ai/endpoint_grouping.py), reproducing
exactly the payload shape and call built by
app/workflows/clustering.py::_semantic_cluster_llm
(user_payload={"endpoints": build_grouping_payload(...)}).

Grouping has no single "right" per-item label — scored via PAIRWISE
co-membership precision/recall/F1 against the annotated partition (see
evaluation/metrics/workflow_grouping_metrics.py for why).

THIS COSTS REAL TOKENS.

    python -m evaluation.run_scripts.run_workflow_grouping_eval \\
        --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \\
        --budget 0.30
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List

from app.ai.endpoint_grouping import ENDPOINT_GROUPING_SCHEMA, SYSTEM_PROMPT
from evaluation.metrics.workflow_grouping_metrics import (
    completion_rate,
    confusion_totals,
    group_count_match_rate,
    index_completeness,
    naming_quality_rate,
    pairwise_f1,
    pairwise_precision,
    pairwise_recall,
)
from evaluation.aggregate import save_summary
from evaluation.tracer._clock_fix import apply_clock_fix
from evaluation.tracer.normalization_tracer import BudgetExceeded, BudgetGuard, TracingClient

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "workflow_grouping_golden_dataset.json")
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

_DEFAULT_PRICE_PER_1K = (0.00200, 0.01000)
_DEFAULT_MAX_TOKENS = 700  # scenarios have up to 12 endpoints + group summaries — needs more room than classification


def _load_golden_cases() -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_payload(case: dict) -> dict:
    # Exactly build_grouping_payload()'s shape: index/method/path/business_action
    return {
        "endpoints": [
            {"index": i, "method": ep["method"], "path": ep["path"], "business_action": ep.get("business_action")}
            for i, ep in enumerate(case["endpoints"])
        ]
    }


def _pricing_key_for(model_id: str) -> str:
    for prefix in ("eu.", "global.", "us."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def _register_default_pricing(pricing_key: str):
    from app.llm_observability import pricing as pricing_module

    original = pricing_module.PRICING.get(pricing_key)
    if original is None:
        from app.llm_observability.pricing import ModelPrice
        pricing_module.PRICING[pricing_key] = ModelPrice(
            provider="bedrock", model=pricing_key,
            input_per_1k=_DEFAULT_PRICE_PER_1K[0], output_per_1k=_DEFAULT_PRICE_PER_1K[1],
            note="workflow_grouping eval default rate (default_estimated, unpriced candidate model)",
        )
    return original


def _restore_pricing(pricing_key: str, original) -> None:
    from app.llm_observability import pricing as pricing_module
    if original is not None:
        pricing_module.PRICING[pricing_key] = original
    else:
        pricing_module.PRICING.pop(pricing_key, None)


def run_single_case(case: dict, tracing_client: TracingClient) -> dict:
    payload = _build_payload(case)
    try:
        raw = tracing_client.structured_chat(
            system_prompt=SYSTEM_PROMPT,
            user_payload=payload,
            json_schema=ENDPOINT_GROUPING_SCHEMA,
            task_name="endpoint_grouping_eval",
        )
    except BudgetExceeded:
        raise
    except Exception as exc:
        return {"case": case, "predicted": None, "error": f"api_error: {type(exc).__name__}: {str(exc)[:150]}"}

    if not isinstance(raw, dict) or "groups" not in raw:
        return {"case": case, "predicted": None, "error": "bad_output_format"}

    return {"case": case, "predicted": raw, "error": None}


def _print_report(model_id: str, results: List[dict]) -> None:
    print(f"\n── {model_id} ──")
    print(f"  Scénarios testés        : {len(results)}")
    print(f"  Completion rate         : {completion_rate(results):.1%}")
    print(f"  Complétude des indices  : {index_completeness(results):.1%} (chaque index dans exactement 1 groupe)")
    print(f"  Precision par paires    : {pairwise_precision(results):.1%}")
    print(f"  Recall par paires       : {pairwise_recall(results):.1%}")
    print(f"  F1 par paires           : {pairwise_f1(results):.1%}")
    print(f"  Nombre de groupes exact : {group_count_match_rate(results):.1%}")
    print(f"  Qualité du nommage      : {naming_quality_rate(results):.1%} (snake_case, non générique, domaine renseigné)")
    print(f"  Totaux paires           : {confusion_totals(results)}")


def _write_csv(model_id: str, results: List[dict], out_suffix: str) -> str:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    import re
    suffix = re.sub(r"[^a-zA-Z0-9_-]", "_", f"_{out_suffix or model_id}")
    path = os.path.join(_RESULTS_DIR, f"workflow_grouping_results{suffix}.csv")

    fieldnames = [
        "case_id", "scenario", "difficulty", "n_endpoints",
        "expected_groups", "predicted_groups", "group_count_match",
        "predicted_names", "error",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            case, pred = r["case"], r.get("predicted")
            groups = pred.get("groups", []) if pred else []
            writer.writerow({
                "case_id": case["case_id"], "scenario": case["scenario"], "difficulty": case["difficulty"],
                "n_endpoints": len(case["endpoints"]),
                "expected_groups": len(case["expected_partition"]),
                "predicted_groups": len(groups),
                "group_count_match": len(groups) == len(case["expected_partition"]) if pred else "",
                "predicted_names": "; ".join(g.get("name", "") for g in groups),
                "error": r.get("error") or "",
            })
    return path


def run_eval_for_model(
    api_model_id: str,
    cases: List[dict],
    budget_guard: BudgetGuard,
    max_tokens: int,
    out_suffix: str,
) -> List[dict]:
    from app.ai.bedrock_client import BedrockClient

    pricing_key = _pricing_key_for(api_model_id)
    original_pricing = _register_default_pricing(pricing_key)
    try:
        client = BedrockClient(model=api_model_id)
        tracing_client = TracingClient(client, model_name=pricing_key, budget_guard=budget_guard, max_tokens=max_tokens)

        results: List[dict] = []
        for case in cases:
            try:
                results.append(run_single_case(case, tracing_client))
            except BudgetExceeded as exc:
                print(f"\n🛑 Budget dépassé au cas '{case['case_id']}' ({api_model_id}) — arrêt. {exc}")
                break
    finally:
        _restore_pricing(pricing_key, original_pricing)

    if results:
        _print_report(api_model_id, results)
        path = _write_csv(api_model_id, results, out_suffix or api_model_id)
        print(f"  Résultats exportés → {path}")
    return results


def run_comparison(model_ids: List[str], cases: List[dict], total_budget_usd: float, max_tokens: int) -> List[dict]:
    apply_clock_fix()
    guard = BudgetGuard(total_budget_usd)
    comparison_rows: List[dict] = []

    for model_id in model_ids:
        if guard.spent_usd >= guard.max_usd:
            print(f"\n🛑 Budget épuisé — {model_id} sauté entièrement.")
            comparison_rows.append({"model": model_id, "skipped": True})
            continue

        spent_before = guard.spent_usd
        print(f"\n{'=' * 70}\n▶ {model_id}  (budget restant : {guard.max_usd - guard.spent_usd:.4f}$)\n{'=' * 70}")
        results = run_eval_for_model(model_id, cases, guard, max_tokens, out_suffix=model_id)

        if not results:
            comparison_rows.append({"model": model_id, "skipped": True})
            continue

        comparison_rows.append({
            "model": model_id, "skipped": False,
            "cases_completed": len(results),
            "completion_rate": completion_rate(results),
            "index_completeness": index_completeness(results),
            "pairwise_f1": pairwise_f1(results),
            "group_count_match": group_count_match_rate(results),
            "naming_quality": naming_quality_rate(results),
            "cost_usd": guard.spent_usd - spent_before,
        })

    print(f"\n{'=' * 70}\n══ COMPARATIF FINAL ══  (budget total dépensé : {guard.spent_usd:.4f}$ / {guard.max_usd:.4f}$)\n{'=' * 70}")
    header = (f"{'Modèle':38s} {'Complet.':>9s} {'Indices':>9s} {'F1 paires':>10s} "
              f"{'Nb groupes':>11s} {'Nommage':>9s} {'Coût $':>9s}")
    print(header)
    print("-" * len(header))
    for row in comparison_rows:
        if row.get("skipped"):
            print(f"{row['model']:38s} {'SAUTÉ (budget)':>60s}")
            continue
        print(f"{row['model']:38s} {row['completion_rate']:>8.1%} {row['index_completeness']:>8.1%} "
              f"{row['pairwise_f1']:>9.1%} {row['group_count_match']:>10.1%} "
              f"{row['naming_quality']:>8.1%} {row['cost_usd']:>8.4f}$")

    summary_path = save_summary("workflow_grouping", comparison_rows)
    print(f"\nRésumé agrégable exporté → {summary_path}")
    return comparison_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="IDs de modèle Bedrock séparés par des virgules")
    parser.add_argument("--cases", default=None, help="IDs de cas séparés par des virgules — sinon les 10 scénarios complets")
    parser.add_argument("--budget", type=float, required=True)
    parser.add_argument("--max-tokens", type=int, default=_DEFAULT_MAX_TOKENS)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    all_cases = _load_golden_cases()

    if args.cases:
        wanted = set(args.cases.split(","))
        selected = [c for c in all_cases if c["case_id"] in wanted]
        missing = wanted - {c["case_id"] for c in selected}
        if missing:
            raise SystemExit(f"Cas introuvables : {sorted(missing)}")
    else:
        selected = all_cases

    run_comparison(
        model_ids=[m.strip() for m in args.models.split(",")],
        cases=selected,
        total_budget_usd=args.budget,
        max_tokens=args.max_tokens,
    )
