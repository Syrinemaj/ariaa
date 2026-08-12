"""ARIA-EVAL: Niveau 0 — balayage large de tous les modèles Bedrock
candidats (hors embeddings/vidéo, hors périmètre), 5 exemples "groupe"
(group_normalizer) par modèle, élimination immédiate sur mauvais format
de sortie OU tout faux positif détecté (rédhibitoire même sur petit
échantillon).

    python -m evaluation.run_scripts.run_niveau0_sweep --budget 3.0

THIS COSTS REAL TOKENS — voir le calcul de coût précis dans la
conversation avant de lancer. Le budget est un plafond dur partagé entre
TOUS les modèles (BudgetGuard) ; un modèle est sauté entièrement si le
budget est épuisé avant qu'on l'atteigne.

Modèles Amazon exclus volontairement : nova-pro-v1:0:24k / :300k — déjà
confirmés (session précédente) comme rejetant l'invocation on-demand
("doesn't support on-demand throughput"), inutile de payer pour re-
vérifier un échec connu.

Tarification : PRICING (app/llm_observability/pricing.py) ne couvre que
4 modèles vérifiés (3 Claude + Nova Lite). Tout autre modèle utilise un
tarif par défaut PRUDENT ($2/$10 par 1K, gamme Sonnet 5) pour que
BudgetGuard ne sous-compte jamais — le rapport final marque explicitement
"verified" vs "default_estimated" par modèle (demande explicite : devoir
distinguer les deux en soutenance).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from app.llm_observability.pricing import PRICING
from app.normalization.group_normalizer import (
    _GROUP_JSON_SCHEMA,
    _GROUP_SYSTEM_PROMPT,
    _validate_response,
)
from evaluation.tracer._clock_fix import apply_clock_fix
from evaluation.tracer.normalization_tracer import BudgetExceeded, BudgetGuard, TracingClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_HERE)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "normalization_golden_dataset.json")
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")

_DEFAULT_PRICE_PER_1K = (0.00200, 0.01000)  # (input, output) — prudent, gamme Sonnet 5
_MAX_TOKENS = 400

_EXAMPLE_CASE_IDS = [
    "a01_entier_pur",
    "b01_hr_employees_vs_departments",   # piège FP — ne doit RIEN templatiser
    "c01_contract_vs_salary",             # piège FP — templatise emp_NNN, pas contract/salary
    "f01_unknown_prefix_repeated_3word",  # ambigu, jugement réel
    "l02_boolean_flag_stays_literal",     # piège FP bruité — ne doit RIEN templatiser
]

# (label_libre, api_model_id_ou_profile, pricing_key)
# pricing_key = clé à chercher dans PRICING ; absente -> tarif par défaut prudent
CANDIDATE_MODELS: List[Tuple[str, str, str]] = [
    # Anthropic
    ("anthropic.claude-3-haiku-20240307-v1:0", "anthropic.claude-3-haiku-20240307-v1:0", "anthropic.claude-3-haiku-20240307-v1:0"),
    ("anthropic.claude-3-sonnet-20240229-v1:0", "anthropic.claude-3-sonnet-20240229-v1:0", "anthropic.claude-3-sonnet-20240229-v1:0"),
    ("anthropic.claude-3-7-sonnet-20250219-v1:0", "anthropic.claude-3-7-sonnet-20250219-v1:0", "anthropic.claude-3-7-sonnet-20250219-v1:0"),
    ("anthropic.claude-haiku-4-5-20251001-v1:0", "eu.anthropic.claude-haiku-4-5-20251001-v1:0", "anthropic.claude-haiku-4-5-20251001-v1:0"),
    ("anthropic.claude-sonnet-4-5-20250929-v1:0", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0", "anthropic.claude-sonnet-4-5-20250929-v1:0"),
    ("anthropic.claude-sonnet-4-6", "eu.anthropic.claude-sonnet-4-6", "anthropic.claude-sonnet-4-6"),
    ("anthropic.claude-sonnet-5", "eu.anthropic.claude-sonnet-5", "anthropic.claude-sonnet-5"),
    ("anthropic.claude-opus-4-5-20251101-v1:0", "eu.anthropic.claude-opus-4-5-20251101-v1:0", "anthropic.claude-opus-4-5-20251101-v1:0"),
    ("anthropic.claude-opus-4-6-v1", "eu.anthropic.claude-opus-4-6-v1", "anthropic.claude-opus-4-6-v1"),
    ("anthropic.claude-opus-4-7", "eu.anthropic.claude-opus-4-7", "anthropic.claude-opus-4-7"),
    ("anthropic.claude-opus-4-8", "eu.anthropic.claude-opus-4-8", "anthropic.claude-opus-4-8"),
    ("anthropic.claude-opus-5", "eu.anthropic.claude-opus-5", "anthropic.claude-opus-5"),
    ("anthropic.claude-fable-5", "global.anthropic.claude-fable-5", "anthropic.claude-fable-5"),
    # Amazon (nova-pro-v1:0:24k / :300k exclus — cf. docstring)
    ("amazon.nova-lite-v1:0", "amazon.nova-lite-v1:0", "amazon.nova-lite-v1:0"),
    ("amazon.nova-micro-v1:0", "amazon.nova-micro-v1:0", "amazon.nova-micro-v1:0"),
    ("amazon.nova-pro-v1:0", "amazon.nova-pro-v1:0", "amazon.nova-pro-v1:0"),
    ("amazon.nova-2-lite-v1:0", "global.amazon.nova-2-lite-v1:0", "amazon.nova-2-lite-v1:0"),
    # Meta
    ("meta.llama3-8b-instruct-v1:0", "meta.llama3-8b-instruct-v1:0", "meta.llama3-8b-instruct-v1:0"),
    ("meta.llama3-70b-instruct-v1:0", "meta.llama3-70b-instruct-v1:0", "meta.llama3-70b-instruct-v1:0"),
    # Mistral
    ("mistral.devstral-2-123b", "mistral.devstral-2-123b", "mistral.devstral-2-123b"),
    ("mistral.magistral-small-2509", "mistral.magistral-small-2509", "mistral.magistral-small-2509"),
    ("mistral.ministral-3-14b-instruct", "mistral.ministral-3-14b-instruct", "mistral.ministral-3-14b-instruct"),
    ("mistral.ministral-3-3b-instruct", "mistral.ministral-3-3b-instruct", "mistral.ministral-3-3b-instruct"),
    ("mistral.ministral-3-8b-instruct", "mistral.ministral-3-8b-instruct", "mistral.ministral-3-8b-instruct"),
    ("mistral.mistral-7b-instruct-v0:2", "mistral.mistral-7b-instruct-v0:2", "mistral.mistral-7b-instruct-v0:2"),
    ("mistral.mistral-large-2402-v1:0", "mistral.mistral-large-2402-v1:0", "mistral.mistral-large-2402-v1:0"),
    ("mistral.mixtral-8x7b-instruct-v0:1", "mistral.mixtral-8x7b-instruct-v0:1", "mistral.mixtral-8x7b-instruct-v0:1"),
    ("mistral.voxtral-mini-3b-2507", "mistral.voxtral-mini-3b-2507", "mistral.voxtral-mini-3b-2507"),
    ("mistral.voxtral-small-24b-2507", "mistral.voxtral-small-24b-2507", "mistral.voxtral-small-24b-2507"),
    # DeepSeek
    ("deepseek.v3-v1:0", "deepseek.v3-v1:0", "deepseek.v3-v1:0"),
    ("deepseek.v3.2", "deepseek.v3.2", "deepseek.v3.2"),
    # Qwen
    ("qwen.qwen3-235b-a22b-2507-v1:0", "qwen.qwen3-235b-a22b-2507-v1:0", "qwen.qwen3-235b-a22b-2507-v1:0"),
    ("qwen.qwen3-32b-v1:0", "qwen.qwen3-32b-v1:0", "qwen.qwen3-32b-v1:0"),
    ("qwen.qwen3-coder-30b-a3b-v1:0", "qwen.qwen3-coder-30b-a3b-v1:0", "qwen.qwen3-coder-30b-a3b-v1:0"),
    ("qwen.qwen3-coder-480b-a35b-v1:0", "qwen.qwen3-coder-480b-a35b-v1:0", "qwen.qwen3-coder-480b-a35b-v1:0"),
    ("qwen.qwen3-coder-next", "qwen.qwen3-coder-next", "qwen.qwen3-coder-next"),
    ("qwen.qwen3-next-80b-a3b", "qwen.qwen3-next-80b-a3b", "qwen.qwen3-next-80b-a3b"),
    ("qwen.qwen3-vl-235b-a22b", "qwen.qwen3-vl-235b-a22b", "qwen.qwen3-vl-235b-a22b"),
    # Google
    ("google.gemma-3-12b-it", "google.gemma-3-12b-it", "google.gemma-3-12b-it"),
    ("google.gemma-3-27b-it", "google.gemma-3-27b-it", "google.gemma-3-27b-it"),
    ("google.gemma-3-4b-it", "google.gemma-3-4b-it", "google.gemma-3-4b-it"),
    # NVIDIA
    ("nvidia.nemotron-nano-12b-v2", "nvidia.nemotron-nano-12b-v2", "nvidia.nemotron-nano-12b-v2"),
    ("nvidia.nemotron-nano-3-30b", "nvidia.nemotron-nano-3-30b", "nvidia.nemotron-nano-3-30b"),
    ("nvidia.nemotron-nano-9b-v2", "nvidia.nemotron-nano-9b-v2", "nvidia.nemotron-nano-9b-v2"),
    ("nvidia.nemotron-super-3-120b", "nvidia.nemotron-super-3-120b", "nvidia.nemotron-super-3-120b"),
    # MiniMax
    ("minimax.minimax-m2", "minimax.minimax-m2", "minimax.minimax-m2"),
    ("minimax.minimax-m2.1", "minimax.minimax-m2.1", "minimax.minimax-m2.1"),
    ("minimax.minimax-m2.5", "minimax.minimax-m2.5", "minimax.minimax-m2.5"),
    # Z.AI
    ("zai.glm-4.7", "zai.glm-4.7", "zai.glm-4.7"),
    ("zai.glm-4.7-flash", "zai.glm-4.7-flash", "zai.glm-4.7-flash"),
    ("zai.glm-5", "zai.glm-5", "zai.glm-5"),
    # OpenAI gpt-oss
    ("openai.gpt-oss-120b-1:0", "openai.gpt-oss-120b-1:0", "openai.gpt-oss-120b-1:0"),
    ("openai.gpt-oss-20b-1:0", "openai.gpt-oss-20b-1:0", "openai.gpt-oss-20b-1:0"),
    ("openai.gpt-oss-safeguard-120b", "openai.gpt-oss-safeguard-120b", "openai.gpt-oss-safeguard-120b"),
    ("openai.gpt-oss-safeguard-20b", "openai.gpt-oss-safeguard-20b", "openai.gpt-oss-safeguard-20b"),
    # Moonshot
    ("moonshotai.kimi-k2.5", "moonshotai.kimi-k2.5", "moonshotai.kimi-k2.5"),
]


def _load_examples() -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        cases = {c["id"]: c for c in json.load(f)}
    return [cases[cid] for cid in _EXAMPLE_CASE_IDS]


def _check_example(case: dict, validated: dict) -> Tuple[bool, bool]:
    """Returns (structurally_correct, false_positive_detected).
    validated["segments"]: [{value, position, is_id, confidence, reason}, ...]
    position is 1-indexed over the full path per group_normalizer's contract."""
    id_positions = set(case["id_positions"])
    fixed_positions = set(case["fixed_positions"])
    by_pos = {seg["position"] - 1: seg["is_id"] for seg in validated["segments"]}

    false_positive = any(by_pos.get(pos) is True for pos in fixed_positions)
    id_hits = sum(1 for pos in id_positions if by_pos.get(pos) is True)
    correct = (id_hits == len(id_positions)) and not false_positive
    return correct, false_positive


def _price_for(pricing_key: str) -> Tuple[float, float, str]:
    if pricing_key in PRICING:
        p = PRICING[pricing_key]
        return p.input_per_1k, p.output_per_1k, "verified"
    return _DEFAULT_PRICE_PER_1K[0], _DEFAULT_PRICE_PER_1K[1], "default_estimated"


def run_sweep(total_budget_usd: float) -> List[dict]:
    apply_clock_fix()
    from app.ai.bedrock_client import BedrockClient

    examples = _load_examples()
    guard = BudgetGuard(total_budget_usd)
    rows: List[dict] = []

    for label, api_model_id, pricing_key in CANDIDATE_MODELS:
        if guard.spent_usd >= guard.max_usd:
            rows.append({"model": label, "status": "skipped_budget"})
            print(f"🛑 Budget épuisé — {label} sauté (et tous les suivants).")
            break

        input_price, output_price, pricing_source = _price_for(pricing_key)
        # Monkeypatch a per-model price into PRICING for this run so
        # TracingClient's estimate_llm_cost() lookup resolves — restored
        # after this model's examples are done, doesn't leak across models.
        from app.llm_observability import pricing as pricing_module
        original_entry = pricing_module.PRICING.get(pricing_key)
        if original_entry is None:
            from app.llm_observability.pricing import ModelPrice
            pricing_module.PRICING[pricing_key] = ModelPrice(
                provider="bedrock", model=pricing_key,
                input_per_1k=input_price, output_per_1k=output_price,
                note=f"Niveau 0 sweep default rate ({pricing_source})",
            )

        client = BedrockClient(model=api_model_id)
        tracing_client = TracingClient(client, model_name=pricing_key, budget_guard=guard, max_tokens=_MAX_TOKENS)

        eliminated = False
        elimination_reason = None
        examples_tested = 0
        examples_correct = 0
        model_cost = guard.spent_usd  # will subtract at the end

        for case in examples:
            if eliminated:
                break
            payload = {"method": case["method"], "urls_du_meme_endpoint": case["urls"]}
            try:
                raw_response = tracing_client.structured_chat(
                    system_prompt=_GROUP_SYSTEM_PROMPT,
                    user_payload=payload,
                    json_schema=_GROUP_JSON_SCHEMA,
                    task_name="niveau0_sweep",
                )
            except BudgetExceeded:
                raise
            except Exception as exc:
                eliminated = True
                elimination_reason = f"api_error: {type(exc).__name__}: {str(exc)[:150]}"
                break

            validated = _validate_response(raw_response)
            examples_tested += 1
            if validated is None:
                eliminated = True
                elimination_reason = "bad_output_format: reponse ne respecte pas le schema attendu"
                break

            correct, false_positive = _check_example(case, validated)
            if false_positive:
                eliminated = True
                elimination_reason = f"false_positive: cas '{case['id']}' a templatise une position censee rester fixe"
                break
            if correct:
                examples_correct += 1

        model_cost = guard.spent_usd - model_cost
        if original_entry is not None:
            pricing_module.PRICING[pricing_key] = original_entry  # restore, don't leak

        status = "eliminated" if eliminated else "survivor"
        rows.append({
            "model": label, "api_model_id": api_model_id, "status": status,
            "elimination_reason": elimination_reason or "",
            "examples_tested": examples_tested, "examples_correct": examples_correct,
            "pricing_source": pricing_source, "cost_usd": round(model_cost, 6),
        })
        marker = "❌" if eliminated else "✅"
        print(f"{marker} {label:50s} [{pricing_source:17s}] "
              f"{examples_correct}/{examples_tested} ok  ${model_cost:.4f}  "
              f"{elimination_reason or ''}")

    os.makedirs(_RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(_RESULTS_DIR, "niveau0_sweep_results.csv")
    fieldnames = ["model", "api_model_id", "status", "elimination_reason",
                  "examples_tested", "examples_correct", "pricing_source", "cost_usd"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    survivors = [r["model"] for r in rows if r.get("status") == "survivor"]
    eliminated_models = [r for r in rows if r.get("status") == "eliminated"]
    skipped = [r for r in rows if r.get("status") == "skipped_budget"]

    print(f"\n══ NIVEAU 0 — RÉSUMÉ ══")
    print(f"Budget dépensé : ${guard.spent_usd:.4f} / ${guard.max_usd:.4f}")
    print(f"Survivants ({len(survivors)}) : {survivors}")
    print(f"Éliminés ({len(eliminated_models)})")
    print(f"Sautés faute de budget ({len(skipped)})")
    print(f"\nRésultats exportés → {out_path}")
    return rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_sweep(total_budget_usd=args.budget)
