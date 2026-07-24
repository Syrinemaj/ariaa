"""ARIA-EVAL: non-invasive pipeline instrumentation for evaluation/run_eval.py.

Records what happened at each pipeline stage (intent, RAG, plan, validation)
into a plain dict, for the judge/metrics to score afterwards. Only active
when EVAL_MODE=true — get_tracer() returns None otherwise, so every call site
in app/planner/service.py and app/planner/plan_builder.py is a no-op guarded
by `if EVAL_MODE and (t := get_tracer())`. Zero impact on production.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.planner.models import BusinessIntent, PlanValidationResult
    from app.rag.models import EndpointSearchResult

logger = logging.getLogger(__name__)

# ARIA-EVAL: single on/off switch, read once at import time. false by
# default — evaluation/ has zero effect on the app unless explicitly enabled.
EVAL_MODE = os.getenv("EVAL_MODE", "false").lower() == "true"


class ARIATracer:
    def __init__(self):
        self.trace = {}

    # ARIA-EVAL: every record_* method is wrapped in its own try/except —
    # the global constraint is that the tracer must never crash the real
    # pipeline, even if a field it expects is missing or an unexpected type
    # shows up. A tracing failure is logged and dropped, not raised.

    def record_intent(self, intent: "BusinessIntent"):
        try:
            self.trace["intent"] = {
                "action": intent.action,
                "entities": intent.entities,
                "confidence": intent.confidence,
                # ARIA-EVAL: BusinessIntent (app/planner/models.py) has no
                # data_source/csv_columns fields — checked before writing
                # this. getattr(..., default) keeps this from crashing, but
                # these two will always be None/[] when read off `intent`.
                # The real values only exist as call-site parameters to
                # build_automation_plan()/generate_plan_selection(), not on
                # the BusinessIntent object itself.
                "data_source": getattr(intent, "data_source", None),
                "csv_columns": getattr(intent, "csv_columns", []),
                "quantity": intent.quantity,
                "reason": intent.reason,
            }
        except Exception as exc:
            logger.warning("tracer.record_intent.failed error=%s", exc)

    def record_rag(self, query: str, results: list, context: str):
        try:
            self.trace["rag"] = {
                "query": query,
                "retrieved_count": len(results),
                "chunks": [
                    {"canonical_key": r.canonical_key, "score": r.score}
                    for r in results
                ],
                "context_length": len(context),
                "rag_triggered": len(results) > 0,
            }
        except Exception as exc:
            logger.warning("tracer.record_rag.failed error=%s", exc)

    def record_plan(self, plan_result: Optional[dict], steps: list):
        try:
            self.trace["plan"] = {
                "llm_called": plan_result is not None,
                "selected_keys": plan_result.get("selected_canonical_keys", [])
                                 if plan_result else [],
                "steps_count": len(steps),
                # ARIA-EVAL: PlanStep (app/planner/models.py) has no `loop`
                # field — only `field_mapping`. `loop` only exists in the raw
                # per-step dicts under plan_result["steps"] (the LLM's
                # steps_detail), before they're reconstructed into PlanStep.
                # getattr(s, "loop", None) is therefore always None if `steps`
                # here is the PlanStep list — has_loop would always read
                # False. plan_builder.py's tracer call site (Phase 3) passes
                # plan_result.get("steps", []) instead of the PlanStep list
                # for this reason, so `s` here is a plain dict, not a
                # PlanStep, and .get(...) is used below rather than getattr.
                "has_field_mapping": any(
                    (s.get("field_mapping") if isinstance(s, dict) else getattr(s, "field_mapping", {}))
                    for s in steps
                ),
                "has_loop": any(
                    (s.get("loop") if isinstance(s, dict) else getattr(s, "loop", None))
                    for s in steps
                ),
                "reasoning": plan_result.get("reasoning", "") if plan_result else "",
                "plan_confidence": plan_result.get("confidence", 0.0)
                                   if plan_result else 0.0,
                "missing_endpoints": plan_result.get("missing_endpoints", [])
                                     if plan_result else [],
            }
        except Exception as exc:
            logger.warning("tracer.record_plan.failed error=%s", exc)

    def record_validation(self, result: "PlanValidationResult"):
        try:
            self.trace["validation"] = {
                "is_valid": getattr(result, "is_valid", None),
                "issues_count": len(getattr(result, "issues", [])),
            }
        except Exception as exc:
            logger.warning("tracer.record_validation.failed error=%s", exc)

    def to_dict(self) -> dict:
        return self.trace


# ARIA-EVAL: singleton, only instantiated when EVAL_MODE is on — importing
# this module in production leaves _tracer as None and every call-site guard
# (`if EVAL_MODE and (t := get_tracer())`) short-circuits before touching it.
_tracer: Optional[ARIATracer] = ARIATracer() if EVAL_MODE else None


def get_tracer() -> Optional[ARIATracer]:
    return _tracer


def reset_tracer():
    global _tracer
    if EVAL_MODE:
        _tracer = ARIATracer()
