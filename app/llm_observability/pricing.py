"""
Per-model token pricing table.

Used for two things:
  1. Accurate cost estimation for whichever model is actually configured
     (see cost_estimator.py) — previously every provider was billed at a
     single hardcoded rate (settings.LLM_PROMPT_COST_PER_1K /
     LLM_COMPLETION_COST_PER_1K), which happened to match Azure's
     gpt-4o-mini pricing and was silently wrong for Groq.
  2. Projecting what real historical usage would cost under a different
     model (compare_models / get_model_cost_comparison in service.py) —
     the decision tool for "is switching provider worth it".

Only Groq (current provider) and Amazon Bedrock Claude models are priced
here — Azure is intentionally excluded from the comparison (it's not a
migration candidate, even though AzureOpenAIClient remains available as
a standalone provider option elsewhere in the app).

Prices are USD per 1,000 tokens (input, output). They are a cached
snapshot, not a live lookup — provider pricing pages change. Re-verify
before using this for a high-stakes migration decision:
  - Groq:    https://console.groq.com/docs/pricing (cached, verify)
  - Bedrock: https://aws.amazon.com/bedrock/pricing/ (cached 2026-06-24;
    Anthropic model pricing on Bedrock has historically matched Anthropic's
    first-party rates, but confirm for your region before committing)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_per_1k: float
    output_per_1k: float
    note: str = ""


PRICING: dict[str, ModelPrice] = {
    # ── Current production provider ────────────────────────────────────────
    "llama-3.3-70b-versatile": ModelPrice(
        provider="groq", model="llama-3.3-70b-versatile",
        input_per_1k=0.00059, output_per_1k=0.00079,
        note="Groq public pricing snapshot — verify at console.groq.com/docs/pricing",
    ),
    # ── Amazon Bedrock candidates for the Groq → AWS migration ─────────────
    # Bedrock model IDs take the "anthropic." prefix (vs. bare "claude-..."
    # on the first-party Anthropic API) — use these exact strings when
    # calling bedrock-runtime.converse(). Keys here are the PRICING lookup
    # form (region prefix "eu."/"global." stripped — see
    # evaluation/run_scripts/run_normalization_eval.py::_pricing_key()),
    # NOT necessarily the literal inference-profile ID the API call itself
    # needs. Re-verified against a live account 2026-08-04 via
    # bedrock.list_inference_profiles() — Haiku 4.5 requires the dated
    # suffix, Sonnet 5 doesn't (as returned by that account at that date;
    # re-check before trusting for a different account/date).
    "anthropic.claude-haiku-4-5-20251001-v1:0": ModelPrice(
        provider="bedrock", model="anthropic.claude-haiku-4-5-20251001-v1:0",
        input_per_1k=0.00100, output_per_1k=0.00500,
        note="Cheapest Claude tier — fastest, best fit for high-volume classification/extraction",
    ),
    "anthropic.claude-sonnet-5": ModelPrice(
        provider="bedrock", model="anthropic.claude-sonnet-5",
        input_per_1k=0.00300, output_per_1k=0.01500,
        note="Intro pricing $0.00200/$0.01000 per 1K through 2026-08-31 (first-party; verify on Bedrock)",
    ),
    "anthropic.claude-opus-4-8": ModelPrice(
        provider="bedrock", model="anthropic.claude-opus-4-8",
        input_per_1k=0.00500, output_per_1k=0.02500,
        note="Most capable Claude tier — priced accordingly",
    ),
    # ── Non-Anthropic Bedrock candidate (provider-agnostic via Converse) ──
    "amazon.nova-lite-v1:0": ModelPrice(
        provider="bedrock", model="amazon.nova-lite-v1:0",
        input_per_1k=0.00006, output_per_1k=0.00024,
        note="Verified via web search earlier in this session, not re-checked live on Bedrock pricing page — "
             "re-verify before a final production cost decision. ~15-40x cheaper than Haiku 4.5; early test "
             "(n=1) showed it returning the raw segment value instead of a semantic name — watch naming_accuracy.",
    ),
    # ── Production default (AI_PROVIDER=bedrock) ───────────────────────────
    "deepseek.v3.2": ModelPrice(
        provider="bedrock", model="deepseek.v3.2",
        input_per_1k=0.00200, output_per_1k=0.01000,
        note="Not verified on a live Bedrock pricing page (deepseek.v3.2 absent from the 4 models "
             "spot-checked for this table) — same prudent default rate used by evaluation/run_scripts/"
             "run_niveau0_sweep.py and run_param_detection_eval.py for unpriced candidates. Re-verify "
             "before trusting aria_llm_cost_total for a real budget decision.",
    ),
}


def get_price(model: str) -> ModelPrice:
    """Raises KeyError if `model` has no pricing entry — callers decide the fallback."""
    return PRICING[model]


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Cost in USD for a call against `model`. Raises KeyError if unpriced."""
    price = get_price(model)
    return round(
        (prompt_tokens / 1000) * price.input_per_1k
        + (completion_tokens / 1000) * price.output_per_1k,
        6,
    )


def compare_models(
    prompt_tokens: int,
    completion_tokens: int,
    models: list[str] | None = None,
) -> list[dict]:
    """
    Cost of the SAME token volume under every model in `models`
    (default: everything in PRICING), cheapest first.
    """
    names = models or list(PRICING.keys())
    rows = [
        {
            "model": name,
            "provider": PRICING[name].provider,
            "input_per_1k": PRICING[name].input_per_1k,
            "output_per_1k": PRICING[name].output_per_1k,
            "estimated_cost_usd": estimate_cost(prompt_tokens, completion_tokens, name),
            "note": PRICING[name].note,
        }
        for name in names
        if name in PRICING
    ]
    rows.sort(key=lambda r: r["estimated_cost_usd"])
    return rows
