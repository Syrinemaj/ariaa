"""ARIA-EVAL: main evaluation harness — runs every case in
golden_dataset/planner_golden_dataset.json through the real pipeline
(app/planner/service.py::create_plan_from_instruction), scores it with the
LLM judge, computes aggregate metrics, and exports a CSV for the PFE report.

Must run with EVAL_MODE=true, and against a database reachable at
settings.DATABASE_URL — in this project that means inside the aria-api
container (DATABASE_URL's host "postgres" only resolves on the Docker
network), not on the host machine directly. See evaluation/README.md.

    EVAL_MODE=true python evaluation/run_scripts/run_planner_eval.py

AWS Bedrock is the only completion provider (see app/ai/base_client.py).
Default behavior (no flags) uses settings.BEDROCK_MODEL, no budget cap, no
cost tracking. --model/--budget (added for the model-selection comparison,
mirrors run_normalization_eval.py's --with-ai flags) only change behavior
when explicitly passed:

    EVAL_MODE=true python evaluation/run_scripts/run_planner_eval.py \\
        --model amazon.nova-lite-v1:0 --budget 0.30 --out-suffix novalite

The judge always uses evaluation/judge/planner_judge.py's fixed JUDGE_MODEL
— never whatever --model the pipeline under test is using — since grading a
model's plans with itself would bias the score (see aggregate.py's
weighting rationale for why planner quality can't be self-graded).

# ARIA-EVAL: evaluation/ folder restructuring (Phase 2) — this file used to
# be evaluation/run_eval.py. Moved into run_scripts/; golden_dataset.json,
# judge.py, metrics.py, tracer.py moved into their own subpackages at the
# same time — imports and path constants below updated accordingly. No
# behavior change.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from typing import Optional

from app.ai.bedrock_client import BedrockClient
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.planner.service import create_plan_from_instruction
from app.rag.embeddings.client import LocalEmbeddingClient
from evaluation.aggregate import save_summary
from evaluation.judge.planner_judge import JUDGE_MODEL, judge_plan
from evaluation.metrics.planner_metrics import (
    context_precision,
    hit_rate,
    mapping_coverage,
    mrr,
    workflow_conformity,
)
from evaluation.tracer.planner_tracer import EVAL_MODE, get_tracer, reset_tracer

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "planner_golden_dataset.json")
RESULTS_CSV_PATH = os.path.join(_EVAL_ROOT, "results", "results.csv")


def _pricing_key(model_id: str) -> str:
    for prefix in ("eu.", "global.", "us."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def _build_ai_client(model: Optional[str], budget_guard):
    """Only called when --budget is explicitly passed. Returns a
    TracingClient-wrapped BedrockClient so --budget is enforced and real
    cost is tracked, mirroring run_normalization_eval.py's --with-ai path."""
    from evaluation.tracer._clock_fix import apply_clock_fix
    from evaluation.tracer.normalization_tracer import TracingClient

    apply_clock_fix()
    api_model = model or settings.BEDROCK_MODEL
    return TracingClient(
        BedrockClient(model=api_model), model_name=_pricing_key(api_model), budget_guard=budget_guard,
    )

# ARIA-EVAL: golden_dataset.json sets "run_id"/"org_id" explicitly per case
# (Phase 1 — needed so category A/B cases target runs that actually have the
# expected endpoints ingested). These are only a fallback for a case that
# omits them, via case.get("run_id", RUN_ID_FOR_EVAL).
RUN_ID_FOR_EVAL = "75152650-6f9d-4adf-a841-b29a375b8b3b"  # test_hr_api.har
ORG_ID_FOR_EVAL = "0d7f6484-7119-4e42-b6ec-4c88a1649e50"


async def run_single_case(case, db, embedding_client, ai_client, judge_client):
    if EVAL_MODE:
        reset_tracer()

    plan = None
    try:
        plan, _validation = await create_plan_from_instruction(
            db=db,
            run_id=case.get("run_id", RUN_ID_FOR_EVAL),
            instruction=case["instruction"],
            embedding_client=embedding_client,
            ai_client=ai_client,
            org_id=case.get("org_id", ORG_ID_FOR_EVAL),
            # ARIA-EVAL: create_plan_from_instruction() returns
            # (AutomationPlan, PlanValidationResult), not just a plan — the
            # original pseudocode's `plan = await create_plan_from_instruction(...)`
            # would have bound `plan` to the tuple itself.
            csv_columns=case.get("csv_columns"),
        )
        tracer = get_tracer()
        trace = tracer.to_dict() if EVAL_MODE and tracer else {}
    except Exception as e:
        trace = {"error": str(e)}
        plan = None

    scores = judge_plan(case, trace, judge_client)
    return {"case": case, "trace": trace, "scores": scores, "plan": plan}


async def run_eval(
    model: Optional[str] = None,
    budget_usd: Optional[float] = None,
    out_suffix: str = "",
    case_ids: Optional[list] = None,
):
    if not EVAL_MODE:
        # ARIA-EVAL: not a hard failure — the run still executes the real
        # pipeline and the judge still scores plan quality — but every trace
        # will be {} (tracer.get_tracer() returns None), so hit_rate/mrr/
        # context_precision/workflow_conformity/mapping_coverage (all of
        # which read trace["rag"]/trace["plan"]/trace["intent"]) will all
        # read as 0%. Warn loudly rather than silently produce a
        # misleadingly empty report.
        print(
            "⚠ EVAL_MODE is not set to true — traces will be empty and every "
            "trace-based metric below will read 0%. Run with:\n"
            "    EVAL_MODE=true python evaluation/run_scripts/run_planner_eval.py\n"
        )

    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
        missing = wanted - {c["id"] for c in cases}
        if missing:
            raise SystemExit(f"Cas introuvables : {sorted(missing)}")

    embedding_client = LocalEmbeddingClient()
    # ARIA-EVAL: judge always stays on JUDGE_MODEL, a plain unwrapped
    # BedrockClient — never TracingClient-wrapped, never the model under
    # test — see module docstring and evaluation/judge/planner_judge.py.
    judge_client = BedrockClient(model=JUDGE_MODEL)

    budget_guard = None
    if budget_usd is not None or model is not None:
        from evaluation.tracer.normalization_tracer import BudgetGuard

        budget_guard = BudgetGuard(budget_usd) if budget_usd is not None else None
        ai_client = _build_ai_client(model, budget_guard)
        print(f"⚠ model={model or settings.BEDROCK_MODEL} actif — coûte des tokens réels\n")
    else:
        # Default path — plain BedrockClient on settings.BEDROCK_MODEL, no
        # budget tracking.
        ai_client = BedrockClient(model=settings.BEDROCK_MODEL)

    results = []
    budget_stopped_early = False
    for case in cases:
        # ARIA-EVAL: run_single_case() catches every exception internally
        # (including BudgetExceeded, turned into trace={"error": ...}) so it
        # can still score the errored case — checking the guard directly
        # here, before spending anything on the next case, is what actually
        # stops the loop, not a try/except around the call below.
        if budget_guard is not None and budget_guard.spent_usd >= budget_guard.max_usd:
            print(f"\n🛑 Budget épuisé avant '{case['id']}' — arrêt. "
                  f"({budget_guard.spent_usd:.4f}$ / {budget_guard.max_usd:.4f}$)")
            budget_stopped_early = True
            break
        print(f"→ {case['id']} : {case['instruction'][:50]}...")
        async with AsyncSessionLocal() as db:
            result = await run_single_case(case, db, embedding_client, ai_client, judge_client)
        results.append(result)

    print("\n══ RÉSULTATS ══")
    print(f"Cas testés        : {len(results)} / {len(cases)} demandés"
          + (" (arrêt anticipé — budget)" if budget_stopped_early else ""))
    print(f"Hit rate          : {hit_rate(results):.2%}")
    print(f"MRR               : {mrr(results):.3f}")
    print(f"Context precision : {context_precision(results):.2%}")
    print(f"Workflow conform. : {workflow_conformity(results):.2%}")
    print(f"Mapping coverage  : {mapping_coverage(results):.2%}")

    for criterion in ["correctness", "faithfulness", "completeness", "mapping"]:
        scores = [
            r["scores"].get(criterion, 0) for r in results if "error" not in r["scores"]
        ]
        if scores:
            print(f"{criterion:20s}: {sum(scores) / len(scores):.2f}/5")

    if budget_guard is not None:
        print(f"\nCoût total dépensé : {budget_guard.spent_usd:.4f}$ / {budget_guard.max_usd:.4f}$")

    # ARIA-EVAL: the original pseudocode built each row via
    # {**r["trace"].get("rag", {}), **r["trace"].get("plan", {}), **r["trace"].get("intent", {}), **r["scores"]}
    # spread directly into the fieldnames below. That crashes: csv.DictWriter
    # raises ValueError on any key not in fieldnames by default, and
    # trace["rag"]/["plan"]/["intent"] carry many keys that aren't in this
    # list (query, chunks, selected_keys, entities, ...). It also silently
    # mis-populates "intent_confidence": that column reads trace["intent"]
    # ["confidence"], but a raw spread would write it under the key
    # "confidence" (unused, not a fieldname) — "intent_confidence" would
    # stay empty in every row. Building each row explicitly avoids both.
    fieldnames = [
        "id", "category", "instruction",
        "rag_triggered", "steps_count", "has_field_mapping", "has_loop",
        "plan_confidence", "intent_confidence",
        "correctness", "faithfulness", "completeness", "mapping",
        "justification",
    ]
    results_csv_path = RESULTS_CSV_PATH
    if out_suffix:
        results_csv_path = os.path.join(_EVAL_ROOT, "results", f"results_{out_suffix}.csv")
    with open(results_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            rag_trace = r["trace"].get("rag", {})
            plan_trace = r["trace"].get("plan", {})
            intent_trace = r["trace"].get("intent", {})
            scores = r["scores"]
            writer.writerow({
                "id": r["case"]["id"],
                "category": r["case"]["category"],
                "instruction": r["case"]["instruction"],
                "rag_triggered": rag_trace.get("rag_triggered"),
                "steps_count": plan_trace.get("steps_count"),
                "has_field_mapping": plan_trace.get("has_field_mapping"),
                "has_loop": plan_trace.get("has_loop"),
                "plan_confidence": plan_trace.get("plan_confidence"),
                "intent_confidence": intent_trace.get("confidence"),
                "correctness": scores.get("correctness"),
                "faithfulness": scores.get("faithfulness"),
                "completeness": scores.get("completeness"),
                "mapping": scores.get("mapping"),
                "justification": scores.get("justification", scores.get("error", "")),
            })

    print(f"\nRésultats exportés → {results_csv_path}")

    if model is not None or budget_guard is not None:
        summary_model = model or settings.BEDROCK_MODEL
        row = {
            "model": summary_model,
            "skipped": len(results) == 0,
            "cases_completed": len(results),
            "completion_rate": len(results) / len(cases) if cases else 0.0,
            "hit_rate": hit_rate(results),
            "mrr": mrr(results),
            "mapping_coverage": mapping_coverage(results),
            "cost_usd": budget_guard.spent_usd if budget_guard is not None else 0.0,
        }
        existing = []
        try:
            import json as _json
            summary_path_check = os.path.join(_EVAL_ROOT, "results", "summary_planner_plan_generation.json")
            if os.path.isfile(summary_path_check):
                with open(summary_path_check, encoding="utf-8") as f:
                    existing = _json.load(f)
        except Exception:
            existing = []
        existing = [r for r in existing if r.get("model") != summary_model] + [row]
        summary_path = save_summary("planner_plan_generation", existing)
        print(f"Résumé agrégable exporté → {summary_path}")

    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=None,
                         help="ID de modèle Bedrock exact (ex: amazon.nova-lite-v1:0). "
                              "Si omis : settings.BEDROCK_MODEL, pas de budget tracké.")
    parser.add_argument("--budget", type=float, default=None, help="Plafond USD")
    parser.add_argument("--out-suffix", default="", help="Suffixe du CSV de sortie (ex: --out-suffix novalite)")
    parser.add_argument("--cases", default=None, help="IDs de cas séparés par des virgules — sinon tous")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    case_ids = args.cases.split(",") if args.cases else None
    asyncio.run(run_eval(
        model=args.model, budget_usd=args.budget,
        out_suffix=args.out_suffix, case_ids=case_ids,
    ))
