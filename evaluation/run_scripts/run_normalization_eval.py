"""ARIA-EVAL: normalization evaluation harness — runs every case in
golden_dataset/normalization_golden_dataset.json through the real pipeline
(app/normalization/service.py::normalize_entries), computes structural
metrics, and exports a CSV.

No LLM involved by default (use_ai=False) — deterministic, free, fast,
reproducible identically on every run.

    python -m evaluation.run_scripts.run_normalization_eval

To measure the REAL LLM-fallback rate and compare providers/models on the
2 confidence-gated points (group_normalizer.py / semantic_normalizer.py),
opt in explicitly — THIS COSTS REAL TOKENS on whichever provider you pick:

    python -m evaluation.run_scripts.run_normalization_eval --with-ai
    python -m evaluation.run_scripts.run_normalization_eval --with-ai --provider groq
    python -m evaluation.run_scripts.run_normalization_eval --with-ai --provider bedrock --model eu.anthropic.claude-haiku-4-5
    python -m evaluation.run_scripts.run_normalization_eval --with-ai --provider bedrock --model eu.anthropic.claude-sonnet-5

To compare several Bedrock models, run this script once per model (each
run is independent and writes its own results CSV suffixed by model — see
--out-suffix) rather than looping models inside one process, so a crash on
model N doesn't lose results for models 1..N-1.

# ARIA-EVAL: evaluation/ folder restructuring (Phase 2) — this file used to
# be evaluation/run_normalization_eval.py. Phase 4/5: comparison logic
# extracted to judge/normalization_judge.py; --with-ai now wires
# tracer/normalization_tracer.py's TracingClient + app.ai.bedrock_client.
# BedrockClient (new, additive) via monkeypatch of the 2 confidence-gated
# call sites — no app/ file touched by this change.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import List, Optional

from app.core.config import settings
from app.ingestion.models import TrafficEntry
from app.normalization.service import normalize_entries
from evaluation.judge.normalization_judge import judge_normalization_case
from evaluation.metrics.normalization_metrics import (
    category_breakdown,
    exact_case_pass_rate,
    false_positive_count,
    is_risky,
    naming_accuracy,
    naming_consistency,
    precision,
    raw_id_leak_count,
    recall,
    source_distribution,
    specificity,
)
from evaluation.tracer.normalization_tracer import (
    BudgetExceeded,
    BudgetGuard,
    TracingClient,
    get_trace,
    reset_trace,
)

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "normalization_golden_dataset.json")
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

_DEFAULT_BEDROCK_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _pricing_key(model_id: str) -> str:
    """app/llm_observability/pricing.py's PRICING dict is keyed by the bare
    model id ("anthropic.claude-haiku-4-5"), but the Bedrock API call itself
    needs the inference-profile-prefixed id ("eu.anthropic.claude-haiku-4-5")
    on this account (verified earlier against the real Bedrock endpoint).
    Strip the region prefix ONLY for the pricing/token-counting lookup —
    never for the actual API call."""
    for prefix in ("eu.", "global.", "us."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def _build_client(provider: str, model: Optional[str]):
    """Returns (real_client, api_model_id, pricing_model_id). Only called
    when --with-ai is set — the default deterministic path never imports a
    provider client at all."""
    if provider == "groq":
        from app.ai.groq_client import GroqClient
        api_model = model or settings.GROQ_MODEL
        return GroqClient(), api_model, api_model
    if provider == "bedrock":
        from app.ai.bedrock_client import BedrockClient
        from evaluation.tracer._clock_fix import apply_clock_fix
        # ARIA-EVAL: sandbox-only workaround — no-op (offset < 60s) on a
        # correctly NTP-synced machine. See _clock_fix.py docstring.
        offset = apply_clock_fix()
        if offset.total_seconds() != 0:
            print(f"⏱ Correctif d'horloge appliqué : {offset} (sandbox uniquement)")
        api_model = model or _DEFAULT_BEDROCK_MODEL
        return BedrockClient(model=api_model), api_model, _pricing_key(api_model)
    raise ValueError(f"Unknown provider: {provider!r} (expected 'groq' or 'bedrock')")


def _patch_normalization_clients(tracing_client: TracingClient) -> None:
    """Monkeypatch the 2 known AI-client instantiation points so
    app/normalization/{group_normalizer,semantic_normalizer}.py construct
    `tracing_client` instead of a real provider client — no app/ file edited
    for eval purposes. Both modules call create_ai_client() (see
    app/ai/base_client.py — provider selection now goes through this single
    factory instead of each module importing GroqClient directly), so
    patching that one name in each module covers whichever provider
    settings.AI_PROVIDER actually points at.
    group_normalizer.py's own optional ai_client= parameter isn't reached by
    normalize_entries() today, so patching the factory name is the only
    lever available without an app/ change."""
    import app.normalization.group_normalizer as group_normalizer_module
    import app.normalization.semantic_normalizer as semantic_normalizer_module

    def _factory(*_args, **_kwargs):
        return tracing_client

    group_normalizer_module.create_ai_client = _factory
    semantic_normalizer_module.create_ai_client = _factory


def run_single_case(case: dict, use_ai: bool = False) -> dict:
    urls = case["urls"]
    request_bodies: List[Optional[dict]] = case.get("request_bodies") or [None] * len(urls)
    response_bodies: List[Optional[dict]] = case.get("response_bodies") or [None] * len(urls)

    entries = [
        TrafficEntry(
            method=case["method"],
            url=f"https://example.com{u}",
            path=u,
            request_body=request_bodies[i],
            response_body=response_bodies[i],
        )
        for i, u in enumerate(urls)
    ]

    if use_ai:
        reset_trace()

    try:
        # ARIA-EVAL: use_ai=False by default. deduplicate=False so every
        # individual URL's own normalized_path is graded (a case's expected
        # id/fixed positions apply per-URL, not to a merged catalog entry).
        endpoints = normalize_entries(entries, use_ai=use_ai, deduplicate=False)
    except BudgetExceeded as exc:
        return {"case": case, "budget_exceeded": True, "budget_exceeded_reason": str(exc)}

    trace = get_trace() if use_ai else None
    result = judge_normalization_case(case, endpoints, trace=trace)
    if trace is not None:
        result["trace"] = trace.to_dict()
    return result


def run_eval(
    use_ai: bool = False,
    provider: str = "groq",
    model: Optional[str] = None,
    out_suffix: str = "",
    case_ids: Optional[List[str]] = None,
    budget_guard: Optional[BudgetGuard] = None,
    max_tokens: int = 1024,
) -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
        missing = wanted - {c["id"] for c in cases}
        if missing:
            raise ValueError(f"Cas introuvables dans le golden dataset : {sorted(missing)}")

    pricing_model_id = None
    if use_ai:
        real_client, api_model, pricing_model_id = _build_client(provider, model)
        # ARIA-EVAL: budget_guard, when passed, is shared across every call
        # this TracingClient makes — and, when run_eval() is invoked once per
        # model by run_model_comparison.py, across models too (same instance
        # passed to each run_eval() call). check() runs BEFORE the real
        # client is called, so an over-budget call is never sent.
        tracing_client = TracingClient(
            real_client, model_name=pricing_model_id,
            budget_guard=budget_guard, max_tokens=max_tokens,
        )
        _patch_normalization_clients(tracing_client)
        print(f"⚠ --with-ai actif : provider={provider} model={api_model} "
              f"(pricing lookup: {pricing_model_id}, max_tokens={max_tokens}) — coûte des tokens réels\n")

    results: List[dict] = []
    for case in cases:
        r = run_single_case(case, use_ai=use_ai)
        if r.get("budget_exceeded"):
            print(f"\n🛑 Budget dépassé au cas '{case['id']}' — arrêt. {r['budget_exceeded_reason']}")
            print(f"   Cas déjà traités avant l'arrêt : {len(results)}/{len(cases)}\n")
            break
        results.append(r)

    if not results:
        print("Aucun cas traité (budget dépassé dès le premier appel) — rien à rapporter.")
        return results

    print("══ RÉSULTATS ══")
    print(f"Cas testés         : {len(results)} / {len(cases)} demandés"
          + (" (arrêt anticipé — budget)" if len(results) < len(cases) else ""))
    print(f"Mode               : {'use_ai=True (' + provider + '/' + str(model or '(défaut)') + ') — tokens réels' if use_ai else 'use_ai=False (déterministe)'}")
    print(f"Recall             : {recall(results):.2%}  (TP/(TP+FN) sur les positions ID)")
    print(f"Precision          : {precision(results):.2%}  (TP/(TP+FP))")
    print(f"Specificity        : {specificity(results):.2%}  (TN/(TN+FP) — ex-'precision', régression Bug 1)")
    fp_count = false_positive_count(results)
    risky = is_risky(results)
    print(f"Faux positifs (abs): {fp_count}" + ("  ⚠ MODÈLE RISQUÉ (FP > 0)" if risky else "  — aucun, OK"))
    print(f"Exact case pass    : {exact_case_pass_rate(results):.2%}")
    print(f"Naming accuracy    : {naming_accuracy(results):.2%} (positions avec expected_names uniquement)")
    print(f"Naming consistency : {naming_consistency(results):.2%}")
    print(f"Fuite d'ID brut    : {raw_id_leak_count(results)} (doit être 0)")

    print("\n── Répartition par source ──")
    dist = source_distribution(results)
    for source, pct in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"  {source:25s}: {pct:.1%}")
    llm_pct = sum(pct for src, pct in dist.items() if src in ("groq_group", "groq"))
    if use_ai:
        print(f"  → taux de fallback LLM réel : {llm_pct:.1%}")
    else:
        print("  → fallback LLM jamais sollicité (use_ai=False) — relancer avec --with-ai pour le taux réel")

    print("\n── Répartition par catégorie ──")
    for category, stats in sorted(category_breakdown(results).items()):
        print(f"  {category:28s}: {stats['passed_cases']}/{stats['total_cases']} ({stats['pass_rate']:.0%})")

    # ARIA-EVAL: confidence-gate accuracy (new) — only cases with
    # expected_llm_triggered/expected_source in the golden dataset
    # contribute; see judge/normalization_judge.py.
    gate_cases = [r for r in results if "confidence_gate" in r]
    if gate_cases:
        gate_matches = sum(1 for r in gate_cases if r["confidence_gate"]["match"])
        print(f"\n── Confidence gate (cas opt-in : {len(gate_cases)}) ──")
        if not use_ai:
            print("  ⚠ use_ai=False : aucun LLM appelé, actual_triggered=False partout par construction.")
            print("    Les MISMATCH sur des cas 'expected_llm_triggered=true' sont donc ATTENDUS ici —")
            print("    relancer avec --with-ai pour une vérification réelle de la porte de confiance.")
        print(f"  Décision correcte : {gate_matches}/{len(gate_cases)} ({gate_matches / len(gate_cases):.0%})")
        for r in gate_cases:
            gc = r["confidence_gate"]
            status = "OK" if gc["match"] else "MISMATCH"
            print(f"  [{status}] {r['case']['id']}: attendu triggered={gc['expected_triggered']} "
                  f"source={gc['expected_source']} | réel triggered={gc['actual_triggered']} "
                  f"sources={gc['actual_sources']}")

    if use_ai:
        total_cost = sum(r["trace"]["total_estimated_cost_usd"] for r in results if "trace" in r)
        total_calls = sum(r["trace"]["call_count"] for r in results if "trace" in r)
        latencies = [
            c["latency_ms"] for r in results if "trace" in r for c in r["trace"]["calls"]
        ]
        print(f"\n── Coût / latence estimés ({provider}/{model or '(défaut)'}) ──")
        print(f"  Appels LLM réels   : {total_calls}")
        print(f"  Coût total estimé  : ${total_cost:.4f}")
        if latencies:
            latencies_sorted = sorted(latencies)
            p50 = latencies_sorted[len(latencies_sorted) // 2]
            p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
            print(f"  Latence P50 / P95  : {p50:.0f}ms / {p95:.0f}ms")

    failed = [
        r for r in results
        if r["id_hits"] != r["id_total"] or r["fixed_hits"] != r["fixed_total"]
    ]
    if failed:
        print("\n── Cas en échec ──")
        for r in failed:
            print(f"  {r['case']['id']}: id {r['id_hits']}/{r['id_total']}, "
                  f"fixed {r['fixed_hits']}/{r['fixed_total']} -> {r['sample_templates']}")

    name_mismatches = [r for r in results if r["name_hits"] != r["name_total"]]
    if name_mismatches:
        print("\n── Noms de paramètre inattendus ──")
        for r in name_mismatches:
            print(f"  {r['case']['id']}: naming {r['name_hits']}/{r['name_total']}")

    inconsistent = [r for r in results if r["consistency_violations"] > 0]
    if inconsistent:
        print("\n── Incohérences de nommage (même position, noms différents) ──")
        for r in inconsistent:
            print(f"  {r['case']['id']}: {r['consistency_violations']} position(s) incohérente(s)")

    os.makedirs(_RESULTS_DIR, exist_ok=True)
    suffix = f"_{out_suffix}" if out_suffix else ""
    results_csv_path = os.path.join(_RESULTS_DIR, f"normalization_results{suffix}.csv")

    fieldnames = [
        "id", "category", "method", "id_hits", "id_total",
        "fixed_hits", "fixed_total", "false_positives", "name_hits", "name_total",
        "consistency_violations", "consistency_positions",
        "passed", "leaked_names", "sample_templates",
        "gate_expected_triggered", "gate_actual_triggered", "gate_match",
        "estimated_cost_usd", "call_count",
    ]
    with open(results_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            gc = r.get("confidence_gate", {})
            trace = r.get("trace", {})
            writer.writerow({
                "id": r["case"]["id"],
                "category": r["case"]["category"],
                "method": r["case"]["method"],
                "id_hits": r["id_hits"], "id_total": r["id_total"],
                "fixed_hits": r["fixed_hits"], "fixed_total": r["fixed_total"],
                "false_positives": r["fixed_total"] - r["fixed_hits"],
                "name_hits": r["name_hits"], "name_total": r["name_total"],
                "consistency_violations": r["consistency_violations"],
                "consistency_positions": r["consistency_positions"],
                "passed": r["id_hits"] == r["id_total"] and r["fixed_hits"] == r["fixed_total"],
                "leaked_names": ";".join(r["leaked_names"]),
                "sample_templates": ";".join(r["sample_templates"]),
                "gate_expected_triggered": gc.get("expected_triggered", ""),
                "gate_actual_triggered": gc.get("actual_triggered", ""),
                "gate_match": gc.get("match", ""),
                "estimated_cost_usd": trace.get("total_estimated_cost_usd", ""),
                "call_count": trace.get("call_count", ""),
            })

    print(f"\nRésultats exportés → {results_csv_path}")
    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-ai", action="store_true",
                         help="Active le fallback LLM réel (coûte des tokens)")
    parser.add_argument("--provider", choices=["groq", "bedrock"], default="groq",
                         help="Provider pour le fallback LLM (défaut: groq)")
    parser.add_argument("--model", default=None,
                         help="ID de modèle exact (ex: eu.anthropic.claude-sonnet-5). "
                              "Défaut : settings.GROQ_MODEL pour groq, "
                              f"{_DEFAULT_BEDROCK_MODEL} pour bedrock.")
    parser.add_argument("--out-suffix", default="",
                         help="Suffixe du fichier CSV de sortie, pour ne pas écraser "
                              "les résultats d'un autre modèle (ex: --out-suffix haiku45)")
    parser.add_argument("--cases", default=None,
                         help="Liste d'IDs de cas séparés par des virgules, pour un run "
                              "réduit (ex: test à blanc avant un run complet coûteux) — "
                              "défaut : tous les cas du golden dataset")
    parser.add_argument("--budget", type=float, default=None,
                         help="Plafond de coût estimé en USD pour ce run — arrêt automatique "
                              "avant tout appel qui le dépasserait (défaut : pas de plafond)")
    parser.add_argument("--max-tokens", type=int, default=1024,
                         help="max_tokens envoyé au modèle (défaut: 1024 ; réduire pour un "
                              "test à blanc bon marché, ex: 150)")
    return parser.parse_args()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = _parse_args()
        run_eval(
            use_ai=args.with_ai, provider=args.provider, model=args.model,
            out_suffix=args.out_suffix,
            case_ids=args.cases.split(",") if args.cases else None,
            budget_guard=BudgetGuard(args.budget) if args.budget is not None else None,
            max_tokens=args.max_tokens,
        )
    else:
        # ARIA-EVAL: back-compat — `python -m evaluation.run_scripts.run_normalization_eval`
        # with no flags stays the free deterministic path, argparse untouched.
        run_eval(use_ai=False)
