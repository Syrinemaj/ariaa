"""ARIA-EVAL: LLM-as-judge — scores a generated plan (tracer.py output)
against a golden_dataset.json case, using a Bedrock model independent of
settings.BEDROCK_MODEL (the pipeline's own) so the pipeline isn't grading
its own output. BedrockClient.structured_chat() accepts a `model` override
per call (see app/ai/bedrock_client.py), so the judge client can be any
BedrockClient instance — only the model id passed below matters for
independence, not which model the instance was constructed with.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ARIA-EVAL: deepseek.v3.2 was the production model before the 8-task
# evaluation (evaluation/aggregate.py) replaced it with amazon.nova-lite-v1:0
# for cost/latency reasons unrelated to judging quality — reusing it here
# keeps the judge on a different model family than whatever
# settings.BEDROCK_MODEL currently is, without needing a third model just
# for this role. Previously this pointed at two Groq model ids
# (llama-3.1-70b-versatile, with settings.GROQ_MODEL as fallback) — both
# were confirmed decommissioned/inaccessible via live testing, and Groq was
# removed as a provider entirely (see app/ai/base_client.py).
JUDGE_MODEL = "deepseek.v3.2"

SYSTEM_PROMPT = """Tu es un évaluateur de systèmes d'automatisation d'API.
Tu notes la qualité d'un plan généré par rapport à ce qui était attendu.
Réponds UNIQUEMENT en JSON valide."""

USER_PROMPT_TEMPLATE = """
INSTRUCTION : {instruction}
CATEGORIE : {category}

PLAN GÉNÉRÉ :
- Steps : {steps}
- Field mapping présent : {has_field_mapping}
- Loop détecté : {has_loop}
- Confidence plan : {plan_confidence}
- Intent confidence : {intent_confidence}
- RAG déclenché : {rag_triggered}
- Reasoning : {reasoning}

ATTENDU (golden dataset) :
- Steps doivent contenir : {expected_steps_contain}
- Field mapping attendu : {expected_field_mapping}
- Loop attendu : {expected_loop}
- Confidence min attendue : {expected_confidence_min}

NOTE chaque critère de 1 à 5 :
- correctness  : les steps générés correspondent-ils à ce qui était attendu ?
- faithfulness : le plan est-il ancré dans le RAG (pas d'endpoints inventés) ?
- completeness : les étapes implicites sont-elles présentes (contrat, congés...) ?
- mapping      : le field_mapping est-il cohérent si CSV attendu ?

Réponds en JSON :
{{
  "correctness": 1-5,
  "faithfulness": 1-5,
  "completeness": 1-5,
  "mapping": 1-5,
  "justification": "1 phrase"
}}
"""

# ARIA-EVAL: passed to BedrockClient.structured_chat() (app/ai/bedrock_client.py)
# — reused for both the tool schema AND the required/non-null field
# validation + automatic retry that structured_chat() already does
# internally. No manual "does the dict have the right keys" check needed here.
_JUDGE_SCHEMA = {
    "name": "judge_evaluation",
    "schema": {
        "type": "object",
        "properties": {
            "correctness": {"type": "integer"},
            "faithfulness": {"type": "integer"},
            "completeness": {"type": "integer"},
            "mapping": {"type": "integer"},
            "justification": {"type": "string"},
        },
        "required": [
            "correctness", "faithfulness", "completeness", "mapping", "justification",
        ],
        "additionalProperties": False,
    },
}


def judge_plan(case: dict, trace: dict, ai_client) -> dict:
    """
    Scores a generated plan (trace, produced by evaluation/tracer.py) against
    a golden_dataset.json case, on 4 criteria (1-5): correctness,
    faithfulness, completeness, mapping.

    ai_client — any BedrockClient instance; structured_chat(model=JUDGE_MODEL)
    below overrides whatever model the instance was constructed with, so the
    judge stays on JUDGE_MODEL regardless of which model is under test.

    Returns the judge's JSON dict (correctness/faithfulness/completeness/
    mapping/justification), or {"error": str(exc)} if the call fails for
    any reason — a judge failure must never abort the eval run for the
    other cases.
    """
    plan_trace = trace.get("plan", {}) or {}
    intent_trace = trace.get("intent", {}) or {}
    rag_trace = trace.get("rag", {}) or {}

    user_prompt = USER_PROMPT_TEMPLATE.format(
        instruction=case.get("instruction", ""),
        category=case.get("category", ""),
        steps=plan_trace.get("selected_keys", []),
        has_field_mapping=plan_trace.get("has_field_mapping", False),
        has_loop=plan_trace.get("has_loop", False),
        plan_confidence=plan_trace.get("plan_confidence", 0.0),
        intent_confidence=intent_trace.get("confidence", 0.0),
        rag_triggered=rag_trace.get("rag_triggered", False),
        reasoning=plan_trace.get("reasoning", ""),
        expected_steps_contain=case.get("expected_steps_contain", []),
        expected_field_mapping=case.get("expected_field_mapping", False),
        expected_loop=case.get("expected_loop"),
        expected_confidence_min=case.get("expected_confidence_min", 0.0),
    )

    try:
        return ai_client.structured_chat(
            system_prompt=SYSTEM_PROMPT,
            user_payload={"case_evaluation": user_prompt},
            json_schema=_JUDGE_SCHEMA,
            task_name="judge_evaluation",
            model=JUDGE_MODEL,
        )
    except Exception as exc:
        logger.warning("judge.failed model=%s error=%s", JUDGE_MODEL, exc)
        return {"error": str(exc)}
