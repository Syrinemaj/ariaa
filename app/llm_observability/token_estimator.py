"""
Pre-execution LLM token estimator.

Counts prompt tokens BEFORE sending to the LLM so the benchmark can compare
estimated vs actual usage per task type.

Usage pattern:
  1. Before calling the LLM, call estimate_prompt_tokens(prompt_text).
  2. Pass the result as estimated_prompt_tokens= to create_llm_call().
  3. The benchmark endpoint compares this against the actual prompt_tokens
     returned by the API response.

Why this matters:
  A large gap (estimated << actual) reveals hidden context injection —
  system prompts, RAG chunks, or tool definitions that inflate costs
  beyond what the raw user input suggests.
"""
from __future__ import annotations

import json
from typing import Any

from app.ai.token_counter import count_tokens
from app.core.config import settings

# ── Task-level system prompt overhead (measured on real ARIA prompts) ─────────
# These constants approximate how many tokens each task type spends on its
# system prompt + schema definitions before the user content is appended.
# Values are conservative lower bounds; update after profiling real calls.
_SYSTEM_OVERHEAD: dict[str, int] = {
    "intent_analyzer":       180,
    "plan_builder":          320,
    "plan_validator":        150,
    "schema_inference":      260,
    "normalizer":            200,
    "heuristic_filter":      120,
    "payload_classifier":    140,
    "endpoint_understanding": 300,
    "rag_context_builder":   100,
}

_DEFAULT_OVERHEAD = 200  # fallback for unknown task types


def _active_model() -> str:
    """Return the model name used for token counting."""
    if settings.AI_PROVIDER == "groq":
        return settings.GROQ_MODEL
    if settings.AI_PROVIDER == "bedrock":
        return settings.BEDROCK_MODEL
    return settings.AZURE_OPENAI_MODEL


def estimate_prompt_tokens(prompt_text: str, task_name: str = "") -> int:
    """
    Count tokens in a raw prompt string plus the system overhead for the task.

    Args:
        prompt_text: The full prompt string (system + user content combined),
                     or just the user content if the system prompt is separate.
        task_name:   Used to add the appropriate system-prompt overhead constant.

    Returns:
        Estimated total prompt token count before submission.
    """
    content_tokens = count_tokens(prompt_text, model=_active_model())
    overhead = _SYSTEM_OVERHEAD.get(task_name, _DEFAULT_OVERHEAD)
    return content_tokens + overhead


def estimate_prompt_tokens_from_dict(
    payload: dict[str, Any],
    task_name: str = "",
) -> int:
    """
    Count tokens from a dict payload (serialised to JSON before counting).
    Useful when the prompt is built from structured data (endpoint list, etc.).
    """
    serialized = json.dumps(payload, ensure_ascii=False)
    return estimate_prompt_tokens(serialized, task_name=task_name)


def estimate_run_cost(
    instruction: str,
    context_endpoints: list[dict[str, Any]],
    plan_steps: int,
) -> dict[str, Any]:
    """
    Estimate the total LLM cost for a full automation run BEFORE execution.

    Covers all LLM calls in the typical pipeline:
      1. Intent analysis   (instruction → structured intent)
      2. Plan building     (intent + endpoints → plan)
      3. Plan validation   (plan → validation report)

    Args:
        instruction:        The natural-language automation instruction.
        context_endpoints:  The top-k endpoint dicts retrieved by RAG.
        plan_steps:         Number of steps in the generated plan (if known).
                            Use 0 to skip the plan-validation estimate.

    Returns dict with per-phase and total estimates.
    """
    model = _active_model()

    # ── Phase 1: intent analysis ──────────────────────────────────────────────
    intent_prompt_tokens = estimate_prompt_tokens(instruction, "intent_analyzer")
    intent_completion_tokens = _estimate_completion(intent_prompt_tokens, ratio=0.25)

    # ── Phase 2: plan building ────────────────────────────────────────────────
    context_text = json.dumps(context_endpoints, ensure_ascii=False)
    plan_content = f"{instruction}\n{context_text}"
    plan_prompt_tokens = estimate_prompt_tokens(plan_content, "plan_builder")
    plan_completion_tokens = _estimate_completion(plan_prompt_tokens, ratio=0.30)

    # ── Phase 3: plan validation (scales with step count) ────────────────────
    if plan_steps > 0:
        # Each step adds ~40 tokens of context to the validation prompt
        val_base = _SYSTEM_OVERHEAD["plan_validator"] + (plan_steps * 40)
        val_completion_tokens = _estimate_completion(val_base, ratio=0.20)
    else:
        val_base = 0
        val_completion_tokens = 0

    total_prompt = intent_prompt_tokens + plan_prompt_tokens + val_base
    total_completion = (
        intent_completion_tokens + plan_completion_tokens + val_completion_tokens
    )
    total_tokens = total_prompt + total_completion

    from app.llm_observability.cost_estimator import estimate_llm_cost
    cost = estimate_llm_cost(total_prompt, total_completion)

    return {
        "model": model,
        "phases": {
            "intent_analysis": {
                "estimated_prompt_tokens":     intent_prompt_tokens,
                "estimated_completion_tokens": intent_completion_tokens,
            },
            "plan_building": {
                "estimated_prompt_tokens":     plan_prompt_tokens,
                "estimated_completion_tokens": plan_completion_tokens,
            },
            "plan_validation": {
                "estimated_prompt_tokens":     val_base,
                "estimated_completion_tokens": val_completion_tokens,
            },
        },
        "total_estimated_prompt_tokens":      total_prompt,
        "total_estimated_completion_tokens":  total_completion,
        "total_estimated_tokens":             total_tokens,
        "estimated_cost_usd":                 cost,
        "is_high_token_estimate":             total_tokens >= settings.LLM_HIGH_TOKEN_THRESHOLD,
    }


def _estimate_completion(prompt_tokens: int, ratio: float) -> int:
    """
    Heuristic: completion is typically 20–35% of prompt length for ARIA tasks.
    Capped at LLM_MAX_COMPLETION_TOKENS.
    """
    estimated = int(prompt_tokens * ratio)
    return min(estimated, settings.LLM_MAX_COMPLETION_TOKENS)


# ── HAR file estimation ───────────────────────────────────────────────────────

# Heuristic score thresholds for candidate selection
_HAR_MIN_SCORE = 0.60   # strict: only clear API calls (POST+JSON+API path)
_HAR_MAX_SCORE = 0.30   # loose: includes borderline calls (GET with API hint)

# Typical deduplication rate for real-world HAR files.
# After normalization, ~40% of similar paths collapse into one endpoint template.
_DEDUP_RATE = 0.60      # min scenario: 60% of candidates survive dedup

# API hint patterns (mirrors heuristic_filter.py)
_API_HINTS = {"/api/", "/graphql", "/rest/", "/v1/", "/v2/", "/v3/", "/backend/", "/services/"}


def _har_heuristic_score(method: str, path: str, has_json: bool, status: int) -> float:
    score = 0.0
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        score += 0.25
    elif method == "GET":
        score += 0.05
    if has_json:
        score += 0.35
    if any(hint in path.lower() for hint in _API_HINTS):
        score += 0.25
    if 200 <= status < 400:
        score += 0.10
    return min(score, 1.0)


def _entry_body_tokens(request: dict, response: dict) -> int:
    """Count tokens from the combined request + response body text of a HAR entry."""
    req_text = (request.get("postData") or {}).get("text", "") or ""
    resp_text = (response.get("content") or {}).get("text", "") or ""
    combined = f"{req_text} {resp_text}".strip()
    return count_tokens(combined) if combined else 0


def estimate_har_tokens(har_data: dict) -> dict[str, Any]:
    """
    Estimate min/max LLM token usage for the ARIA ingestion pipeline.

    No LLM calls — pure static analysis: parse HAR entries, apply the same
    heuristic scoring used by the real pipeline, then compute per-stage token
    estimates under two scenarios:

    MIN: strict candidate filter (score ≥ 0.60) + aggressive deduplication.
         Represents a clean, well-structured API traffic capture.

    MAX: loose candidate filter (score ≥ 0.30) + no deduplication.
         Represents a noisy capture where every variant is treated separately.

    Pipeline stages covered:
      - payload_classifier  (per candidate)
      - normalizer          (per candidate)
      - schema_inference    (per unique endpoint)
      - endpoint_understanding (per unique endpoint)
    """
    from urllib.parse import urlparse

    raw_entries = har_data.get("log", {}).get("entries", [])

    # ── Analyse each entry ─────────────────────────────────────────────────────
    scored: list[dict] = []
    for entry in raw_entries:
        req  = entry.get("request",  {})
        resp = entry.get("response", {})

        method = req.get("method", "GET").upper()
        url    = req.get("url", "")
        path   = urlparse(url).path or "/"
        status = resp.get("status") or 0

        resp_mime    = (resp.get("content") or {}).get("mimeType", "") or ""
        req_ct       = next(
            (h["value"] for h in req.get("headers", [])
             if h.get("name", "").lower() == "content-type"),
            "",
        )
        has_json = "application/json" in resp_mime or "application/json" in req_ct

        heuristic = _har_heuristic_score(method, path, has_json, status)
        body_tok  = _entry_body_tokens(req, resp)
        path_tok  = count_tokens(f"{method} {path}")

        scored.append({
            "method":    method,
            "path":      path,
            "score":     heuristic,
            "body_tok":  body_tok,
            "path_tok":  path_tok,
        })

    # ── Candidate sets ─────────────────────────────────────────────────────────
    min_cands = [e for e in scored if e["score"] >= _HAR_MIN_SCORE]
    max_cands = [e for e in scored if e["score"] >= _HAR_MAX_SCORE]

    # ── Unique endpoint counts ─────────────────────────────────────────────────
    # MIN: apply deduplication rate estimate
    # MAX: every candidate treated as a distinct endpoint
    min_unique = max(1, int(len(min_cands) * _DEDUP_RATE)) if min_cands else 0
    max_unique = len(max_cands)

    def _avg(vals: list[int]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    avg_body_min  = _avg([e["body_tok"]  for e in min_cands])
    avg_body_max  = _avg([e["body_tok"]  for e in max_cands])
    avg_path_min  = _avg([e["path_tok"]  for e in min_cands])
    avg_path_max  = _avg([e["path_tok"]  for e in max_cands])

    # ── Per-stage token formula ────────────────────────────────────────────────
    #   per_entry = overhead + content_fraction * avg_body_tok
    #   per_endpoint uses the same avg body as representative example
    def _stage(count: int, overhead: int, content: float) -> int:
        return int(count * (overhead + content))

    def _scenario(cands: list[dict], unique: int, avg_body: float, avg_path: float) -> dict:
        n = len(cands)
        payload_cl  = _stage(n,      _SYSTEM_OVERHEAD["payload_classifier"],    avg_body * 0.30)
        normalizer  = _stage(n,      _SYSTEM_OVERHEAD["normalizer"],             avg_path + avg_body * 0.15)
        schema_inf  = _stage(unique, _SYSTEM_OVERHEAD["schema_inference"],       avg_body * 0.25)
        ep_und      = _stage(unique, _SYSTEM_OVERHEAD["endpoint_understanding"], avg_path * 0.50)
        prompt_tok  = payload_cl + normalizer + schema_inf + ep_und
        compl_tok   = _estimate_completion(prompt_tok, ratio=0.20)
        total       = prompt_tok + compl_tok
        from app.llm_observability.cost_estimator import estimate_llm_cost
        return {
            "api_candidates":    n,
            "unique_endpoints":  unique,
            "prompt_tokens":     prompt_tok,
            "completion_tokens": compl_tok,
            "total_tokens":      total,
            "estimated_cost_usd": estimate_llm_cost(prompt_tok, compl_tok),
            "breakdown": {
                "payload_classifier":    payload_cl,
                "normalizer":            normalizer,
                "schema_inference":      schema_inf,
                "endpoint_understanding": ep_und,
            },
        }

    min_est = _scenario(min_cands, min_unique, avg_body_min, avg_path_min)
    max_est = _scenario(max_cands, max_unique, avg_body_max, avg_path_max)

    return {
        "model": _active_model(),
        "har_stats": {
            "total_entries":            len(raw_entries),
            "min_api_candidates":       len(min_cands),
            "max_api_candidates":       len(max_cands),
            "min_unique_endpoints":     min_unique,
            "max_unique_endpoints":     max_unique,
        },
        "min_estimate": min_est,
        "max_estimate": max_est,
    }
