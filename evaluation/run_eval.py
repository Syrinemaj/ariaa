"""ARIA-EVAL: main evaluation harness — runs every case in golden_dataset.json
through the real pipeline (app/planner/service.py::create_plan_from_instruction),
scores it with the LLM judge, computes aggregate metrics, and exports a CSV
for the PFE report.

Must run with EVAL_MODE=true, and against a database reachable at
settings.DATABASE_URL — in this project that means inside the aria-api
container (DATABASE_URL's host "postgres" only resolves on the Docker
network), not on the host machine directly. See evaluation/README.md.

    EVAL_MODE=true python evaluation/run_eval.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import os

from app.ai.groq_client import GroqClient
from app.db.session import AsyncSessionLocal
from app.planner.service import create_plan_from_instruction
from app.rag.embeddings.client import LocalEmbeddingClient
from evaluation.judge import judge_plan
from evaluation.metrics import (
    context_precision,
    hit_rate,
    mapping_coverage,
    mrr,
    workflow_conformity,
)
from evaluation.tracer import EVAL_MODE, get_tracer, reset_tracer

_HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DATASET_PATH = os.path.join(_HERE, "golden_dataset.json")
RESULTS_CSV_PATH = os.path.join(_HERE, "results.csv")

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


async def run_eval():
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
            "    EVAL_MODE=true python evaluation/run_eval.py\n"
        )

    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    embedding_client = LocalEmbeddingClient()
    ai_client = GroqClient()
    # ARIA-EVAL: judge.py picks its own model (JUDGE_MODEL_PREFERRED) off of
    # whatever GroqClient it's given — reusing the same instance as the
    # pipeline's ai_client is fine (GroqClient holds only API credentials,
    # no per-call state) and avoids spinning up a redundant SDK client.
    judge_client = ai_client

    results = []
    for case in cases:
        print(f"→ {case['id']} : {case['instruction'][:50]}...")
        async with AsyncSessionLocal() as db:
            result = await run_single_case(case, db, embedding_client, ai_client, judge_client)
        results.append(result)

    print("\n══ RÉSULTATS ══")
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
    with open(RESULTS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
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

    print(f"\nRésultats exportés → {RESULTS_CSV_PATH}")


if __name__ == "__main__":
    asyncio.run(run_eval())
