"""ARIA-EVAL: parameter-detection evaluation harness — sends each case in
golden_dataset/param_detection_golden_dataset.jsonl to one or more LLMs and
scores their is_parameter/param_name prediction against `proposed`.

Unlike run_normalization_eval.py, there is no wired pipeline call site for
this dataset yet (dynamic_segment_detector.py / parameter_detector.py are
purely deterministic — see their docstrings). This script prompts the
model directly, independent of app/ code, to evaluate CANDIDATE models
before any of them get wired into the pipeline.

THIS COSTS REAL TOKENS. Default is a small stratified sample (2 cases per
(strata, is_parameter) bucket, ~20-24 cases) — pass --full for all 140.

    # sample first (recommended) — validates prompt/schema cheaply
    python -m evaluation.run_scripts.run_param_detection_eval \\
        --models moonshotai.kimi-k2.5,deepseek.v3.2 --budget 0.20

    # explicit case ids
    python -m evaluation.run_scripts.run_param_detection_eval \\
        --models moonshotai.kimi-k2.5 --cases uuid_0001,constant_0002 --budget 0.05

    # full dataset, once the sample looks right
    python -m evaluation.run_scripts.run_param_detection_eval \\
        --models moonshotai.kimi-k2.5,deepseek.v3.2 --full --budget 2.00

Both target models (moonshotai.kimi-k2.5, deepseek.v3.2) are unpriced in
app/llm_observability/pricing.py — same situation as
run_niveau0_sweep.py's CANDIDATE_MODELS, same fix: a prudent default rate
($2/$10 per 1K, Sonnet 5 range) is registered into PRICING for the run so
BudgetGuard never under-counts, restored after so it doesn't leak. The CSV
marks cost as "default_estimated" (vs "verified") accordingly.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List, Optional, Tuple

from evaluation.metrics.param_detection_metrics import (
    _normalize_name,
    accuracy,
    completion_rate,
    confusion_matrix,
    f1,
    false_positive_count,
    false_negative_count,
    naming_accuracy,
    precision,
    recall,
    specificity,
    trap_accuracy,
)
from evaluation.tracer._clock_fix import apply_clock_fix
from evaluation.tracer.normalization_tracer import BudgetExceeded, BudgetGuard, TracingClient

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "param_detection_golden_dataset.jsonl")
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

_DEFAULT_PRICE_PER_1K = (0.00200, 0.01000)  # (input, output) — prudent, gamme Sonnet 5
_DEFAULT_MODELS = ["moonshotai.kimi-k2.5", "deepseek.v3.2"]
_DEFAULT_SAMPLE_PER_BUCKET = 2

_DIFFICULTY_RANK = {"hard": 0, "medium": 1, "easy": 2}

_SCHEMA: dict = {
    "name": "param_detection",
    "schema": {
        "type": "object",
        "properties": {
            "is_parameter": {"type": "boolean"},
            "param_name": {"type": "string"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["is_parameter", "param_name", "confidence", "reason"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """You are an API URL structure analysis engine. For ONE path segment of an
HTTP request URL, decide whether it is a DYNAMIC PARAMETER (a resource
identifier whose value varies per request — should be templated, e.g.
/employees/{employeeId}) or a STATIC/LITERAL segment (a fixed keyword that
is part of the endpoint's structure itself, identical across every request
to that endpoint).

INPUT you receive (JSON):
- method, url_raw: the HTTP method and full path
- segment_index: the 0-indexed position of the target segment in the path
- segment_value: the exact segment text to classify
- previous_segment / next_segment: path segments immediately around it
  (may be null at path boundaries)

STATIC, not a parameter, even though it may LOOK like an identifier:
- API version markers: v1, v2, v20260101, 2024-01 ...
- lifecycle/environment words: latest, stable, beta, current, staging ...
- fixed REST conventions and self-reference aliases: me, self, current
- action/verb suffixes: bulk, search, export, summary, count ...
- enum-like fixed values (status names, boolean flags: true/false/active)
- a resource collection name that just happens to sit where an id could
  be (e.g. the LAST segment of a collection-list endpoint, not an item
  endpoint)

DYNAMIC PARAMETER — genuinely varies per request:
- UUIDs (with or without dashes), hashes, ULIDs, JWTs
- numeric or composite numeric ids
- business-prefixed ids (emp_301, inv_2024_00042, ch_1AbC...)
- timestamps used as a resource key (not a version marker)
- opaque business codes that identify one specific record

DECISION ORDER when ambiguous (highest priority first):
1. Known static keyword/convention (see list above) -> is_parameter=false,
   regardless of how ID-shaped the value looks (this is the #1 trap).
2. previous_segment is a plural/singular resource name and segment_value
   has no static-keyword shape -> is_parameter=true, name it
   "<singular resource>Id" (camelCase, e.g. "employeeId").
3. segment_value's own shape (uuid/hash/prefixed business code) with no
   resource-name context -> is_parameter=true, name it from the shape
   (e.g. a bare uuid with no context -> "id" or a prefix-derived name).
4. Genuinely ambiguous, no signal either way -> your best guess, but keep
   confidence <= 0.5.

OUTPUT (strict JSON, matches the schema you were given):
- is_parameter: boolean
- param_name: camelCase parameter name when is_parameter=true (e.g.
  "employeeId", "invoiceId"); empty string "" when is_parameter=false
- confidence: 0.85-1.0 when a static keyword or a clear resource-name
  match applies, 0.5-0.85 for shape-only inference, <= 0.5 when genuinely
  ambiguous
- Never return markdown or text outside the JSON object.

EXAMPLES

url_raw=/api/v2/employees, segment_index=1, segment_value="v2", previous_segment="api", next_segment="employees"
-> {"is_parameter": false, "param_name": "", "confidence": 0.95, "reason": "API version marker, fixed across all requests"}

url_raw=/api/v1/employees/3fa85f64-5717-4562-b3fc-2c963f66afa6, segment_index=3, segment_value="3fa85f64-5717-4562-b3fc-2c963f66afa6", previous_segment="employees", next_segment=null
-> {"is_parameter": true, "param_name": "employeeId", "confidence": 0.95, "reason": "uuid shape, previous segment 'employees' gives resource name"}

url_raw=/api/v1/employees/me, segment_index=3, segment_value="me", previous_segment="employees", next_segment=null
-> {"is_parameter": false, "param_name": "", "confidence": 0.9, "reason": "'me' is a fixed self-reference alias, not a variable id, despite sitting in the usual id position"}"""


def _load_golden_cases() -> List[dict]:
    cases: List[dict] = []
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cases.append(json.loads(line))
    return cases


def _stratified_sample(cases: List[dict], per_bucket: int) -> List[dict]:
    """Groups by (strata, is_parameter) so both classes of every strata are
    represented, then picks up to `per_bucket` per group — trap cases and
    harder difficulty first, so a small sample still stresses the traps
    the dataset was built to cover rather than only its easy cases."""
    buckets: dict = {}
    for case in cases:
        key = (case["strata"], case["proposed"]["is_parameter"])
        buckets.setdefault(key, []).append(case)

    def _sort_key(case: dict) -> tuple:
        return (
            0 if case.get("trap") else 1,
            _DIFFICULTY_RANK.get(case.get("difficulty"), 3),
            case["case_id"],
        )

    sample: List[dict] = []
    for key in sorted(buckets):
        ordered = sorted(buckets[key], key=_sort_key)
        sample.extend(ordered[:per_bucket])
    return sample


def _pricing_key_for(model_id: str) -> str:
    for prefix in ("eu.", "global.", "us."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def _register_default_pricing(pricing_key: str):
    """Returns the original PRICING entry (or None) so the caller can
    restore it — mirrors run_niveau0_sweep.py's monkeypatch so
    estimate_llm_cost() resolves for models absent from pricing.py without
    editing that file for what may turn out to be a rejected candidate."""
    from app.llm_observability import pricing as pricing_module

    original = pricing_module.PRICING.get(pricing_key)
    if original is None:
        from app.llm_observability.pricing import ModelPrice
        pricing_module.PRICING[pricing_key] = ModelPrice(
            provider="bedrock", model=pricing_key,
            input_per_1k=_DEFAULT_PRICE_PER_1K[0], output_per_1k=_DEFAULT_PRICE_PER_1K[1],
            note="param_detection eval default rate (default_estimated, unpriced candidate model)",
        )
    return original


def _restore_pricing(pricing_key: str, original) -> None:
    from app.llm_observability import pricing as pricing_module
    if original is not None:
        pricing_module.PRICING[pricing_key] = original
    else:
        pricing_module.PRICING.pop(pricing_key, None)


def run_single_case(case: dict, client: TracingClient) -> dict:
    context = case.get("context", {})
    payload = {
        "method": context.get("method"),
        "url_raw": case["url_raw"],
        "segment_index": case["segment_index"],
        "segment_value": case["segment_value"],
        "previous_segment": context.get("prev"),
        "next_segment": context.get("next"),
    }
    try:
        raw = client.structured_chat(
            system_prompt=_SYSTEM_PROMPT,
            user_payload=payload,
            json_schema=_SCHEMA,
            task_name="param_detection_eval",
        )
    except BudgetExceeded:
        raise
    except Exception as exc:
        return {"case": case, "predicted": None, "error": f"api_error: {type(exc).__name__}: {str(exc)[:150]}"}

    if not isinstance(raw, dict) or "is_parameter" not in raw:
        return {"case": case, "predicted": None, "error": "bad_output_format"}

    predicted = {
        "is_parameter": bool(raw["is_parameter"]),
        "param_name": raw.get("param_name") or None,
        "confidence": raw.get("confidence"),
        "reason": raw.get("reason", ""),
    }
    return {"case": case, "predicted": predicted, "error": None}


def _print_report(model_id: str, results: List[dict]) -> None:
    print(f"\n── {model_id} ──")
    print(f"  Cas testés         : {len(results)}")
    print(f"  Completion rate    : {completion_rate(results):.1%}")
    print(f"  Accuracy (is_param): {accuracy(results):.1%}")
    print(f"  Precision          : {precision(results):.1%}")
    print(f"  Recall             : {recall(results):.1%}")
    print(f"  Specificity        : {specificity(results):.1%}")
    print(f"  F1                 : {f1(results):.1%}")
    print(f"  False positives    : {false_positive_count(results)}")
    print(f"  False negatives    : {false_negative_count(results)}")
    print(f"  Naming accuracy    : {naming_accuracy(results):.1%} (sur TP is_parameter)")
    print(f"  Trap-case accuracy : {trap_accuracy(results):.1%}")
    print(f"  Confusion          : {confusion_matrix(results)}")


def _write_csv(model_id: str, results: List[dict], out_suffix: str) -> str:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    suffix = f"_{out_suffix}" if out_suffix else f"_{model_id}"
    import re
    suffix = re.sub(r"[^a-zA-Z0-9_-]", "_", suffix)
    path = os.path.join(_RESULTS_DIR, f"param_detection_results{suffix}.csv")

    fieldnames = [
        "case_id", "strata", "difficulty", "trap", "url_raw", "segment_value",
        "expected_is_parameter", "expected_param_name",
        "predicted_is_parameter", "predicted_param_name", "name_match",
        "confidence", "error",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            case, pred = r["case"], r.get("predicted")
            expected = case["proposed"]
            name_match = ""
            if pred is not None and expected["is_parameter"] and pred["is_parameter"]:
                name_match = _normalize_name(pred["param_name"]) == _normalize_name(expected["param_name"])
            writer.writerow({
                "case_id": case["case_id"], "strata": case["strata"], "difficulty": case["difficulty"],
                "trap": case.get("trap") or "", "url_raw": case["url_raw"], "segment_value": case["segment_value"],
                "expected_is_parameter": expected["is_parameter"], "expected_param_name": expected["param_name"] or "",
                "predicted_is_parameter": pred["is_parameter"] if pred else "",
                "predicted_param_name": (pred.get("param_name") or "") if pred else "",
                "name_match": name_match,
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
            "naming_accuracy": naming_accuracy(results),
            "trap_accuracy": trap_accuracy(results),
            "false_positives": false_positive_count(results),
            "cost_usd": guard.spent_usd - spent_before,
        })

    print(f"\n{'=' * 70}\n══ COMPARATIF FINAL ══  (budget total dépensé : {guard.spent_usd:.4f}$ / {guard.max_usd:.4f}$)\n{'=' * 70}")
    header = (f"{'Modèle':30s} {'Complet.':>9s} {'Accuracy':>9s} {'Precision':>10s} "
              f"{'Recall':>8s} {'F1':>7s} {'Naming':>8s} {'Trap':>7s} {'FP':>4s} {'Coût $':>9s}")
    print(header)
    print("-" * len(header))
    for row in comparison_rows:
        if row.get("skipped"):
            print(f"{row['model']:30s} {'SAUTÉ (budget)':>60s}")
            continue
        print(f"{row['model']:30s} {row['completion_rate']:>8.1%} {row['accuracy']:>8.1%} "
              f"{row['precision']:>9.1%} {row['recall']:>7.1%} {row['f1']:>6.1%} "
              f"{row['naming_accuracy']:>7.1%} {row['trap_accuracy']:>6.1%} "
              f"{row['false_positives']:>4d} {row['cost_usd']:>8.4f}$")

    return comparison_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default=",".join(_DEFAULT_MODELS),
                         help=f"IDs de modèle Bedrock séparés par des virgules (défaut: {','.join(_DEFAULT_MODELS)})")
    parser.add_argument("--cases", default=None,
                         help="IDs de cas séparés par des virgules — prioritaire sur --sample-per-bucket/--full")
    parser.add_argument("--sample-per-bucket", type=int, default=_DEFAULT_SAMPLE_PER_BUCKET,
                         help=f"Cas par bucket (strata, is_parameter) — défaut {_DEFAULT_SAMPLE_PER_BUCKET} "
                              "(~20-24 cas au total). Ignoré si --cases ou --full.")
    parser.add_argument("--full", action="store_true", help="Lance les 140 cas du golden dataset (coûteux)")
    parser.add_argument("--budget", type=float, required=True,
                         help="Budget total USD partagé entre tous les modèles listés")
    parser.add_argument("--max-tokens", type=int, default=300)
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
    elif args.full:
        selected = all_cases
    else:
        selected = _stratified_sample(all_cases, args.sample_per_bucket)
        print(f"Échantillon stratifié : {len(selected)}/{len(all_cases)} cas "
              f"({args.sample_per_bucket} par bucket strata×is_parameter, pièges priorisés). "
              f"Utiliser --full pour le dataset complet.")

    run_comparison(
        model_ids=[m.strip() for m in args.models.split(",")],
        cases=selected,
        total_budget_usd=args.budget,
        max_tokens=args.max_tokens,
    )
