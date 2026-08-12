"""ARIA-EVAL: normalization pipeline instrumentation.

Unlike tracer/planner_tracer.py (which app/planner/service.py and
app/planner/plan_builder.py call directly via get_tracer().record_*()),
app/normalization/{semantic_normalizer.py,group_normalizer.py} have no
instrumentation call sites, and neither passes a `db` session to
structured_chat(), so their LLM calls are never logged to
app/llm_observability/ in production either.

Rather than adding record_*() calls inside app/normalization/ (an app/
change, out of scope per project rule 5), this tracer is a CLIENT WRAPPER:
TracingClient decorates a real AI client (GroqClient, or the new
app.ai.bedrock_client.BedrockClient) and is substituted in place of the
real client via monkeypatch at the two known instantiation sites — see
run_scripts/run_normalization_eval.py for where the patch is applied.

Every .structured_chat() call the app makes during a case IS the
confidence-gate firing — no separate "did it trigger" bookkeeping needed;
absence of a call record for a case means the rules resolved it without
LLM.

Token counts are ESTIMATED (app.ai.token_counter.count_tokens on the
serialized prompt/response), not the exact billed count — structured_chat()
returns only the parsed JSON result, not raw API usage, and exposing raw
usage would require an app/ change. Estimates are internally consistent
across models, which is what matters for A/B cost comparison — label any
report built from this "estimated cost", never "billed cost".
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ai.token_counter import count_tokens
from app.llm_observability.cost_estimator import estimate_llm_cost

EVAL_MODE = os.getenv("EVAL_MODE", "false").lower() == "true"


@dataclass
class NormalizationCallRecord:
    task_name: str  # "url_param_normalization" | "url_group_normalization"
    model: str
    latency_ms: float
    estimated_prompt_tokens: int
    estimated_completion_tokens: int
    estimated_cost_usd: float
    error: Optional[str] = None


@dataclass
class NormalizationTrace:
    calls: list[NormalizationCallRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "llm_triggered": len(self.calls) > 0,
            "call_count": len(self.calls),
            "calls": [c.__dict__ for c in self.calls],
            "total_estimated_cost_usd": sum(c.estimated_cost_usd for c in self.calls),
        }


_trace: Optional[NormalizationTrace] = NormalizationTrace() if EVAL_MODE else None


def get_trace() -> Optional[NormalizationTrace]:
    return _trace


def reset_trace() -> None:
    global _trace
    if EVAL_MODE:
        _trace = NormalizationTrace()


class BudgetExceeded(Exception):
    """Raised by BudgetGuard.check() when a call would push cumulative
    estimated spend past the fixed cap. Checked BEFORE the call is made,
    not after — a call that would exceed budget is never sent."""


class BudgetGuard:
    """Tracks cumulative estimated spend across an entire run (potentially
    multiple models) and refuses any call that would exceed the cap."""

    def __init__(self, max_usd: float) -> None:
        self.max_usd = max_usd
        self.spent_usd = 0.0

    def check(self, projected_cost_usd: float) -> None:
        if self.spent_usd + projected_cost_usd > self.max_usd:
            raise BudgetExceeded(
                f"Budget dépassé : {self.spent_usd + projected_cost_usd:.4f}$ "
                f"> {self.max_usd:.4f}$ autorisé (déjà dépensé : {self.spent_usd:.4f}$)"
            )

    def record(self, actual_cost_usd: float) -> None:
        self.spent_usd += actual_cost_usd


class TracingClient:
    """Drop-in replacement for GroqClient/BedrockClient — same
    .structured_chat() signature and return value. Records latency/
    estimated tokens/estimated cost into the module-level trace (EVAL_MODE
    only; pure passthrough otherwise, zero overhead outside eval runs).

    If budget_guard is set, estimates the call's cost from the outgoing
    prompt BEFORE sending it (worst case: assumes the full max_tokens is
    used for the completion) and raises BudgetExceeded without ever
    calling the real client if that would exceed the cap."""

    def __init__(
        self,
        real_client: Any,
        model_name: str,
        budget_guard: Optional[BudgetGuard] = None,
        max_tokens: int = 1024,
    ) -> None:
        self._client = real_client
        self._model_name = model_name
        self._budget_guard = budget_guard
        self._max_tokens = max_tokens

    def structured_chat(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        prompt_text = system_prompt + json.dumps(user_payload, ensure_ascii=False)
        prompt_tokens = count_tokens(prompt_text, model=self._model_name)

        if self._budget_guard is not None:
            try:
                worst_case_cost = estimate_llm_cost(prompt_tokens, self._max_tokens, model=self._model_name)
            except Exception:
                worst_case_cost = 0.0
            self._budget_guard.check(worst_case_cost)

        kwargs.setdefault("max_tokens", self._max_tokens)
        start = time.perf_counter()
        try:
            result = self._client.structured_chat(
                system_prompt=system_prompt,
                user_payload=user_payload,
                json_schema=json_schema,
                task_name=task_name,
                **kwargs,
            )
            error = None
        except Exception as exc:
            result = {"error": str(exc)}
            error = str(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            completion_tokens = count_tokens(json.dumps(result, ensure_ascii=False), model=self._model_name)
            try:
                actual_cost = estimate_llm_cost(prompt_tokens, completion_tokens, model=self._model_name)
            except Exception:
                actual_cost = 0.0
            if self._budget_guard is not None:
                self._budget_guard.record(actual_cost)
            if EVAL_MODE and (trace := get_trace()) is not None:
                trace.calls.append(NormalizationCallRecord(
                    task_name=task_name, model=self._model_name, latency_ms=latency_ms,
                    estimated_prompt_tokens=prompt_tokens, estimated_completion_tokens=completion_tokens,
                    estimated_cost_usd=actual_cost, error=error,
                ))
        return result
