"""ARIA-EVAL: workflow description evaluation harness — sends each case in
golden_dataset/workflow_description_golden_dataset.json through the SAME
prompt/schema used in production (app/workflows/workflow_descriptor.py::
generate_workflow_description), reproducing exactly the payload shape
(workflow_steps: numbered "METHOD path\\n   summary" text block, step_count).

summary/description are free text with no single correct wording — NOT
scored here (no LLM judge wired, to stay free/fast). Only estimated_risk
(against the prompt's own explicit rules), business_tags relevance, and
risk_confidence calibration are measured (see
evaluation/metrics/workflow_description_metrics.py).

THIS COSTS REAL TOKENS.

    python -m evaluation.run_scripts.run_workflow_description_eval \\
        --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \\
        --budget 0.30
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List

from app.workflows.workflow_descriptor import _SCHEMA, _SYSTEM
from evaluation.metrics.workflow_description_metrics import (
    completion_rate,
    confidence_calibration_rate,
    risk_match_rate,
    tag_relevance_rate,
)
from evaluation.aggregate import save_summary
from evaluation.tracer._clock_fix import apply_clock_fix
from evaluation.tracer.normalization_tracer import BudgetExceeded, BudgetGuard, TracingClient

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "workflow_description_golden_dataset.json")
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

_DEFAULT_PRICE_PER_1K = (0.00200, 0.01000)
_DEFAULT_MAX_TOKENS = 500


def _load_golden_cases() -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_payload(case: dict) -> dict:
    # Exactly generate_workflow_description()'s steps_text/payload shape.
    steps_text = "\n".join(
        f"{i + 1}. {s['method']} {s['path']}\n   {s.get('summary') or ''}"
        for i, s in enumerate(case["steps"])
    )
    return {"workflow_steps": steps_text, "step_count": len(case["steps"])}


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
            note="workflow_description eval default rate (default_estimated, unpriced candidate model)",
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
            system_prompt=_SYSTEM,
            user_payload=payload,
            json_schema=_SCHEMA,
            task_name="workflow_description_eval",
        )
    except BudgetExceeded:
        raise
    except Exception as exc:
        return {"case": case, "predicted": None, "error": f"api_error: {type(exc).__name__}: {str(exc)[:150]}"}

    required = {"summary", "description", "business_tags", "estimated_risk", "risk_confidence"}
    if not isinstance(raw, dict) or not required.issubset(raw.keys()):
        return {"case": case, "predicted": None, "error": "bad_output_format"}

    return {"case": case, "predicted": raw, "error": None}


def _print_report(model_id: str, results: List[dict]) -> None:
    print(f"\n── {model_id} ──")
    print(f"  Cas testés              : {len(results)}")
    print(f"  Completion rate         : {completion_rate(results):.1%}")
    print(f"  Correspondance risque   : {risk_match_rate(results):.1%}")
    print(f"  Pertinence des tags     : {tag_relevance_rate(results):.1%}")
    print(f"  Calibration confiance   : {confidence_calibration_rate(results):.1%}")
    print("  (résumé/description non notés — texte libre, pas de vérité unique)")


def _write_csv(model_id: str, results: List[dict], out_suffix: str) -> str:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    import re
    suffix = re.sub(r"[^a-zA-Z0-9_-]", "_", f"_{out_suffix or model_id}")
    path = os.path.join(_RESULTS_DIR, f"workflow_description_results{suffix}.csv")

    fieldnames = [
        "case_id", "category", "difficulty", "n_steps",
        "predicted_risk", "risk_confidence", "predicted_tags", "summary", "error",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            case, pred = r["case"], r.get("predicted")
            writer.writerow({
                "case_id": case["case_id"], "category": case["category"], "difficulty": case["difficulty"],
                "n_steps": len(case["steps"]),
                "predicted_risk": (pred.get("estimated_risk") or "") if pred else "",
                "risk_confidence": pred.get("risk_confidence") if pred else "",
                "predicted_tags": "; ".join(pred.get("business_tags", [])) if pred else "",
                "summary": (pred.get("summary") or "") if pred else "",
                "error": r.get("error") or "",
            })
    return path


def run_eval_for_model(api_model_id: str, cases: List[dict], budget_guard: BudgetGuard, max_tokens: int, out_suffix: str) -> List[dict]:
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
            "risk_match": risk_match_rate(results),
            "tag_relevance": tag_relevance_rate(results),
            "confidence_calibration": confidence_calibration_rate(results),
            "cost_usd": guard.spent_usd - spent_before,
        })

    print(f"\n{'=' * 70}\n══ COMPARATIF FINAL ══  (budget total dépensé : {guard.spent_usd:.4f}$ / {guard.max_usd:.4f}$)\n{'=' * 70}")
    header = (f"{'Modèle':38s} {'Complet.':>9s} {'Risque':>8s} "
              f"{'Tags':>7s} {'Calibr.':>8s} {'Coût $':>9s}")
    print(header)
    print("-" * len(header))
    for row in comparison_rows:
        if row.get("skipped"):
            print(f"{row['model']:38s} {'SAUTÉ (budget)':>60s}")
            continue
        print(f"{row['model']:38s} {row['completion_rate']:>8.1%} {row['risk_match']:>7.1%} "
              f"{row['tag_relevance']:>6.1%} {row['confidence_calibration']:>7.1%} {row['cost_usd']:>8.4f}$")

    summary_path = save_summary("workflow_description", comparison_rows)
    print(f"\nRésumé agrégable exporté → {summary_path}")
    return comparison_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="IDs de modèle Bedrock séparés par des virgules")
    parser.add_argument("--cases", default=None, help="IDs de cas séparés par des virgules — sinon les 12 cas complets")
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
