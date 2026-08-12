"""ARIA-EVAL: LLM-as-judge — scores a generated plan (tracer.py output)
against a golden_dataset.json case, using a model independent of the
pipeline's own (settings.GROQ_MODEL) so the pipeline isn't grading its own
output.
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# ARIA-EVAL: llama-3.1-70b-versatile was deprecated by Groq during 2025 in
# favor of llama-3.3-70b-versatile (the pipeline's current
# settings.GROQ_MODEL) — confirmed decommissioned (HTTP 400
# model_decommissioned) via live testing. Tried first as requested; falls
# back to settings.GROQ_MODEL (the pipeline's own model) on any failure,
# exactly as the spec's own "si disponible, sinon le modèle actuel"
# anticipates.
JUDGE_MODEL_PREFERRED = "llama-3.1-70b-versatile"

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

# ARIA-EVAL: passed to GroqClient.structured_chat() (app/ai/groq_client.py)
# — reused for both the schema-injection prompt AND the required/non-null
# field validation + automatic retry that structured_chat() already does
# internally. No more manual "does the dict have the right keys" check here.
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


def judge_plan(case: dict, trace: dict, groq_client) -> dict:
    """
    Scores a generated plan (trace, produced by evaluation/tracer.py) against
    a golden_dataset.json case, on 4 criteria (1-5): correctness,
    faithfulness, completeness, mapping.

    # ARIA-EVAL: calls groq_client.structured_chat(model=...) — the same
    # method every other pipeline caller (intent_analyzer.py,
    # plan_generator.py) uses — instead of driving groq_client._sync
    # directly. This reuses GroqClient's existing primary -> secondary ->
    # tertiary -> Azure key fallback cascade for free; judge.py only adds
    # the model-level retry (preferred model, then the pipeline's own),
    # which is a judge-specific concern the shared method has no reason to
    # know about. Each of the two model attempts below still gets the full
    # multi-key cascade internally.

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
        try:
            return groq_client.structured_chat(
                system_prompt=SYSTEM_PROMPT,
                user_payload={"case_evaluation": user_prompt},
                json_schema=_JUDGE_SCHEMA,
                task_name="judge_evaluation",
                model=JUDGE_MODEL_PREFERRED,
            )
        except Exception as exc:
            logger.warning(
                "judge.preferred_model_failed model=%s error=%s — falling back to %s",
                JUDGE_MODEL_PREFERRED, exc, settings.GROQ_MODEL,
            )
            return groq_client.structured_chat(
                system_prompt=SYSTEM_PROMPT,
                user_payload={"case_evaluation": user_prompt},
                json_schema=_JUDGE_SCHEMA,
                task_name="judge_evaluation",
                model=settings.GROQ_MODEL,
            )
    except Exception as exc:
        return {"error": str(exc)}
