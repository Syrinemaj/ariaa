"""ARIA-EVAL: pure metric calculations over evaluation run results — no LLM
calls here (that's evaluation/judge.py). Each function takes the same shape:

cases_results: list[dict], each dict = {
    "case": {...golden_dataset.json entry...},
    "trace": {...evaluation/tracer.py ARIATracer.to_dict() output, or
              {"error": str} if the pipeline call itself raised...},
    "scores": {...evaluation/judge.py judge_plan() output...},
}
"""
from __future__ import annotations

from typing import Dict, List


# ARIA-EVAL: canonical_key (app/normalization/canonicalizer.py:
# build_registry_key) is "{org_id}:{METHOD} {/path}" — org_id is a UUID
# (hyphens, never colons), so splitting on the first ":" cleanly isolates
# "{METHOD} {/path}", which is the format golden_dataset.json's
# expected_steps_contain uses (no org prefix). Without this, hit_rate/mrr/
# context_precision would never match anything — every trace value carries
# the org prefix, every golden-dataset value doesn't.
def _normalize_key(key: str) -> str:
    return key.split(":", 1)[-1] if ":" in key else key


def _expected_steps(case: dict) -> List[str]:
    return case.get("expected_steps_contain", [])


def hit_rate(cases_results: List[dict]) -> float:
    """% de cas où au moins un expected_step est dans les steps générés
    (trace["plan"]["selected_keys"] — le plan final, après filtrage LLM).
    Cas sans expected_steps_contain (catégorie C) exclus du dénominateur :
    il n'y a rien à "retrouver" pour ces cas (voir workflow_conformity pour
    la vérification "aucune étape générée" attendue en catégorie C)."""
    scored = [r for r in cases_results if _expected_steps(r["case"])]
    if not scored:
        return 0.0

    hits = 0
    for r in scored:
        expected = set(_expected_steps(r["case"]))
        selected = {
            _normalize_key(k)
            for k in r.get("trace", {}).get("plan", {}).get("selected_keys", [])
        }
        if expected & selected:
            hits += 1
    return hits / len(scored)


def mrr(cases_results: List[dict]) -> float:
    """Mean Reciprocal Rank : rang moyen du premier expected_step trouvé
    dans trace["rag"]["chunks"] (résultats RAG, déjà triés par score
    décroissant — voir merge_deduplicate() dans app/rag/pipeline.py).
    Cas sans expected_steps_contain (catégorie C) exclus, même raison que
    hit_rate."""
    scored = [r for r in cases_results if _expected_steps(r["case"])]
    if not scored:
        return 0.0

    reciprocal_ranks = []
    for r in scored:
        expected = set(_expected_steps(r["case"]))
        chunks = r.get("trace", {}).get("rag", {}).get("chunks", [])
        rank_found = None
        for rank, chunk in enumerate(chunks, start=1):
            if _normalize_key(chunk.get("canonical_key", "")) in expected:
                rank_found = rank
                break
        reciprocal_ranks.append(1.0 / rank_found if rank_found else 0.0)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def context_precision(cases_results: List[dict]) -> float:
    """Parmi les chunks RAG récupérés (trace["rag"]["chunks"]), % qui sont
    dans expected_steps_contain — moyenne par cas (macro-average), cas sans
    chunk récupéré exclus (0/0 non défini)."""
    per_case_precision = []
    for r in cases_results:
        expected = set(_expected_steps(r["case"]))
        chunks = r.get("trace", {}).get("rag", {}).get("chunks", [])
        if not chunks:
            continue
        relevant = sum(
            1 for c in chunks if _normalize_key(c.get("canonical_key", "")) in expected
        )
        per_case_precision.append(relevant / len(chunks))

    if not per_case_precision:
        return 0.0
    return sum(per_case_precision) / len(per_case_precision)


def workflow_conformity(cases_results: List[dict]) -> float:
    """% de cas où rag_triggered == expects_rag ET la confidence est dans
    les bornes [expected_confidence_min, expected_confidence_max].

    ARIA-EVAL: "la confidence" = trace["intent"]["confidence"] (intent
    analyzer), pas trace["plan"]["plan_confidence"] — les bornes du golden
    dataset (0.7-1.0 pour A/B, 0.0-0.25 pour C) reproduisent exactement
    l'échelle documentée dans app/planner/intent_analyzer.py's
    SYSTEM_PROMPT_TEMPLATE ("CONFIDENCE SCALE"), qui note la confiance de
    l'intent analyzer, pas celle (distincte) du plan generator."""
    if not cases_results:
        return 0.0

    conforming = 0
    for r in cases_results:
        case = r["case"]
        trace = r.get("trace", {})
        rag_triggered = trace.get("rag", {}).get("rag_triggered", False)
        confidence = trace.get("intent", {}).get("confidence", 0.0)

        rag_ok = rag_triggered == case.get("expects_rag", True)
        conf_ok = (
            case.get("expected_confidence_min", 0.0)
            <= confidence
            <= case.get("expected_confidence_max", 1.0)
        )
        if rag_ok and conf_ok:
            conforming += 1
    return conforming / len(cases_results)


def mapping_coverage(cases_results: List[dict]) -> float:
    """% de cas catégorie A où has_field_mapping == True."""
    category_a = [r for r in cases_results if r["case"].get("category") == "A"]
    if not category_a:
        return 0.0

    covered = sum(
        1 for r in category_a
        if r.get("trace", {}).get("plan", {}).get("has_field_mapping", False)
    )
    return covered / len(category_a)


if __name__ == "__main__":
    # ARIA-EVAL: 3 cas fictifs — vérifie juste que les fonctions tournent
    # sans crasher et donnent des chiffres plausibles, pas un test unitaire
    # exhaustif (voir tests/unit/ pour ça si besoin).
    fake_results = [
        {
            "case": {
                "id": "fake_A", "category": "A",
                "expected_steps_contain": ["POST /api/v1/employees"],
                "expects_rag": True,
                "expected_confidence_min": 0.7, "expected_confidence_max": 1.0,
            },
            "trace": {
                "intent": {"confidence": 0.9},
                "rag": {
                    "rag_triggered": True,
                    "chunks": [
                        {"canonical_key": "org-1:POST /api/v1/employees", "score": 0.9},
                        {"canonical_key": "org-1:GET /api/v1/employees", "score": 0.8},
                    ],
                },
                "plan": {
                    "selected_keys": ["org-1:POST /api/v1/employees"],
                    "has_field_mapping": True,
                },
            },
            "scores": {"correctness": 5, "faithfulness": 5, "completeness": 4, "mapping": 5},
        },
        {
            "case": {
                "id": "fake_B", "category": "B",
                "expected_steps_contain": ["GET /api/v1/employees"],
                "expects_rag": True,
                "expected_confidence_min": 0.7, "expected_confidence_max": 1.0,
            },
            "trace": {
                "intent": {"confidence": 0.85},
                "rag": {
                    "rag_triggered": True,
                    "chunks": [{"canonical_key": "org-1:GET /api/v1/employees", "score": 0.95}],
                },
                "plan": {
                    "selected_keys": ["org-1:GET /api/v1/employees"],
                    "has_field_mapping": False,
                },
            },
            "scores": {"correctness": 5, "faithfulness": 5, "completeness": 5, "mapping": 5},
        },
        {
            "case": {
                "id": "fake_C", "category": "C",
                "expected_steps_contain": [],
                "expects_rag": False,
                "expected_confidence_min": 0.0, "expected_confidence_max": 0.25,
            },
            "trace": {
                "intent": {"confidence": 0.1},
                "rag": {"rag_triggered": False, "chunks": []},
                "plan": {"selected_keys": [], "has_field_mapping": False},
            },
            "scores": {"correctness": 5, "faithfulness": 5, "completeness": 5, "mapping": 5},
        },
    ]

    print(f"hit_rate          : {hit_rate(fake_results):.2%}")
    print(f"mrr               : {mrr(fake_results):.3f}")
    print(f"context_precision : {context_precision(fake_results):.2%}")
    print(f"workflow_conform. : {workflow_conformity(fake_results):.2%}")
    print(f"mapping_coverage  : {mapping_coverage(fake_results):.2%}")

    assert hit_rate(fake_results) == 1.0
    assert mrr(fake_results) == 1.0
    # fake_A retrieves 2 chunks (POST + GET /employees) but only POST is
    # expected -> 1/2 precision for that case; fake_B is 1/1; fake_C has 0
    # chunks (excluded). Average of [0.5, 1.0] = 0.75.
    assert context_precision(fake_results) == 0.75
    assert workflow_conformity(fake_results) == 1.0
    assert mapping_coverage(fake_results) == 1.0
    assert hit_rate([]) == 0.0
    assert mrr([]) == 0.0
    assert context_precision([]) == 0.0
    assert workflow_conformity([]) == 0.0
    assert mapping_coverage([]) == 0.0
    print("\nAll sanity assertions passed.")
