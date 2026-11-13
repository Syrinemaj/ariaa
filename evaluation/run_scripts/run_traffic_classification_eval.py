"""ARIA-EVAL: traffic classification evaluation harness — sends each case in
golden_dataset/traffic_classification_golden_dataset.json through the SAME
prompt/schema/validation used in production (app/ai/traffic_classification.py
+ app/ai/response_schemas.py::ClassificationResponse), for one or more
Bedrock models.

Unlike run_param_detection_eval.py, this reuses the real production
prompt/schema/response-validation path exactly as app/ingestion/
semantic_filter.py calls it via client.classify_api_call() — inlined here
through TracingClient (which only wraps .structured_chat()) so budget
tracking still applies, rather than a hand-written standalone prompt.

THIS COSTS REAL TOKENS. Default is the full 30-case dataset (small enough
that a stratified sample isn't needed) — pass --cases to restrict.

    python -m evaluation.run_scripts.run_traffic_classification_eval \\
        --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \\
        --budget 0.30
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List, Tuple

from app.ai.response_schemas import ClassificationResponse
from app.ai.token_counter import truncate_dict_to_token_limit
from app.ai.traffic_classification import CLASSIFY_SCHEMA, SYSTEM_PROMPT
from evaluation.metrics.traffic_classification_metrics import (
    accuracy,
    completion_rate,
    confidence_band_respected,
    confusion_matrix,
    domain_action_accuracy,
    f1,
    precision,
    recall,
    specificity,
    strata_accuracy,
)
from evaluation.aggregate import save_summary
from evaluation.tracer._clock_fix import apply_clock_fix
from evaluation.tracer.normalization_tracer import BudgetExceeded, BudgetGuard, TracingClient

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "traffic_classification_golden_dataset.json")
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

_DEFAULT_PRICE_PER_1K = (0.00200, 0.01000)  # (input, output) — prudent, gamme Sonnet 5
_DEFAULT_MAX_TOKENS = 300


def _load_golden_cases() -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_payload(case: dict) -> dict:
    return {
        "method": case["method"],
        "url": case["url"],
        "path": case["path"],
        "status": case["status"],
        "mime_type": case.get("mime_type"),
        "request_headers": case.get("request_headers", {}),
        "response_headers": case.get("response_headers", {}),
        "request_body": case.get("request_body"),
        "response_body": case.get("response_body"),
        "heuristic_score": case["heuristic_score"],
        "payload_score": case["payload_score"],
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
            note="traffic_classification eval default rate (default_estimated, unpriced candidate model)",
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
    safe_payload, _truncated = truncate_dict_to_token_limit(
        payload, tracing_client._model_name, 120_000
    )
    try:
        raw = tracing_client.structured_chat(
            system_prompt=SYSTEM_PROMPT,
            user_payload=safe_payload,
            json_schema=CLASSIFY_SCHEMA,
            task_name="har_classification_eval",
        )
    except BudgetExceeded:
        raise
    except Exception as exc:
        return {"case": case, "predicted": None, "error": f"api_error: {type(exc).__name__}: {str(exc)[:150]}"}

    # Exactly the same validation/fallback path production uses.
    parsed = ClassificationResponse.parse_llm_response(raw, ClassificationResponse.fallback())
    if parsed.reason == "validation_failed":
        return {"case": case, "predicted": None, "error": "bad_output_format"}

    predicted = {
        "should_keep": parsed.should_keep,
        "business_domain": parsed.business_domain,
        "business_action": parsed.business_action,
        "confidence": parsed.confidence,
        "reason": parsed.reason,
    }
    return {"case": case, "predicted": predicted, "error": None}


def _print_report(model_id: str, results: List[dict]) -> None:
    print(f"\n── {model_id} ──")
    print(f"  Cas testés            : {len(results)}")
    print(f"  Completion rate       : {completion_rate(results):.1%}")
    print(f"  Accuracy (should_keep): {accuracy(results):.1%}")
    print(f"  Precision             : {precision(results):.1%}")
    print(f"  Recall                : {recall(results):.1%}")
    print(f"  Specificity           : {specificity(results):.1%}")
    print(f"  F1                    : {f1(results):.1%}")
    print(f"  Domain+action match   : {domain_action_accuracy(results):.1%} (sur TP)")
    print(f"  Bornes de confiance   : {confidence_band_respected(results):.1%} (cas 'genuinely_ambiguous')")
    for strata in ("clear_business_gray_zone", "noise_disguised_as_business", "business_disguised_as_noise", "genuinely_ambiguous"):
        print(f"  Accuracy [{strata:28s}] : {strata_accuracy(results, strata):.1%}")
    print(f"  Confusion             : {confusion_matrix(results)}")


def _write_csv(model_id: str, results: List[dict], out_suffix: str) -> str:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    import re
    suffix = re.sub(r"[^a-zA-Z0-9_-]", "_", f"_{out_suffix or model_id}")
    path = os.path.join(_RESULTS_DIR, f"traffic_classification_results{suffix}.csv")

    fieldnames = [
        "case_id", "strata", "difficulty", "method", "path",
        "expected_should_keep", "expected_domain", "expected_action",
        "predicted_should_keep", "predicted_domain", "predicted_action",
        "domain_action_match", "confidence", "error",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            case, pred = r["case"], r.get("predicted")
            expected = case["expected"]
            match = ""
            if pred is not None and expected["should_keep"] and pred["should_keep"]:
                match = (
                    (pred.get("business_domain") or "").lower() == (expected.get("business_domain") or "").lower()
                    and (pred.get("business_action") or "").lower() == (expected.get("business_action") or "").lower()
                )
            writer.writerow({
                "case_id": case["case_id"], "strata": case["strata"], "difficulty": case["difficulty"],
                "method": case["method"], "path": case["path"],
                "expected_should_keep": expected["should_keep"],
                "expected_domain": expected.get("business_domain", ""),
                "expected_action": expected.get("business_action", ""),
                "predicted_should_keep": pred["should_keep"] if pred else "",
                "predicted_domain": (pred.get("business_domain") or "") if pred else "",
                "predicted_action": (pred.get("business_action") or "") if pred else "",
                "domain_action_match": match,
                "confidence": pred.get("confidence") if pred else "",
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


def run_comparison(
    model_ids: List[str],
    cases: List[dict],
    total_budget_usd: float,
    max_tokens: int,
) -> List[dict]:
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
            "accuracy": accuracy(results),
            "precision": precision(results),
            "recall": recall(results),
            "f1": f1(results),
            "domain_action_match": domain_action_accuracy(results),
            "cost_usd": guard.spent_usd - spent_before,
        })

    print(f"\n{'=' * 70}\n══ COMPARATIF FINAL ══  (budget total dépensé : {guard.spent_usd:.4f}$ / {guard.max_usd:.4f}$)\n{'=' * 70}")
    header = (f"{'Modèle':38s} {'Complet.':>9s} {'Accuracy':>9s} {'Precision':>10s} "
              f"{'Recall':>8s} {'F1':>7s} {'Domain+Act':>11s} {'Coût $':>9s}")
    print(header)
    print("-" * len(header))
    for row in comparison_rows:
        if row.get("skipped"):
            print(f"{row['model']:38s} {'SAUTÉ (budget)':>60s}")
            continue
        print(f"{row['model']:38s} {row['completion_rate']:>8.1%} {row['accuracy']:>8.1%} "
              f"{row['precision']:>9.1%} {row['recall']:>7.1%} {row['f1']:>6.1%} "
              f"{row['domain_action_match']:>10.1%} {row['cost_usd']:>8.4f}$")

    summary_path = save_summary("traffic_classification", comparison_rows)
    print(f"\nRésumé agrégable exporté → {summary_path}")
    return comparison_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True,
                         help="IDs de modèle Bedrock séparés par des virgules")
    parser.add_argument("--cases", default=None,
                         help="IDs de cas séparés par des virgules — sinon les 30 cas complets")
    parser.add_argument("--budget", type=float, required=True,
                         help="Budget total USD partagé entre tous les modèles listés")
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
            raise SystemExit(f"Cas introuvables dans le golden dataset : {sorted(missing)}")
    else:
        selected = all_cases

    run_comparison(
        model_ids=[m.strip() for m in args.models.split(",")],
        cases=selected,
        total_budget_usd=args.budget,
        max_tokens=args.max_tokens,
    )
