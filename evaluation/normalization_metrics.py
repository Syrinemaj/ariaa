"""ARIA-EVAL: pure metric calculations for the URL-normalization golden
dataset (evaluation/normalization_golden_dataset.json). No LLM involved —
normalization correctness is deterministic and exactly verifiable, unlike
plan-generation quality (see evaluation/metrics.py for that harness).

Each function takes the same shape: a list of per-case result dicts, one
per golden_dataset entry, produced by run_normalization_eval.py:
{
    "case": {...golden_dataset.json entry...},
    "id_hits": int, "id_total": int,           # expected-ID positions correctly templated
    "fixed_hits": int, "fixed_total": int,      # expected-fixed positions correctly kept literal
    "name_hits": int, "name_total": int,       # positions with an expected_names entry,
                                                # and how many matched (opt-in per case/position)
    "sources": [str, ...],                      # PathParameter.source for every detected param
    "leaked_names": [str, ...],                 # parameter names matching the raw-ID-leak pattern
    "consistency_violations": int,             # positions where sibling URLs of the same case
    "consistency_positions": int,              # got 2+ different names for "the same" parameter
}
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

_RAW_ID_LEAK_RE = re.compile(r"^[a-z]+_\d+_id$")


def hit_rate(results: List[dict]) -> float:
    """% des positions attendues comme ID qui sont effectivement devenues
    un {placeholder} — recall sur la détection d'ID. Cas sans position ID
    attendue (catégories bug1/accepted_tradeoff) exclus du dénominateur."""
    scored = [r for r in results if r["id_total"] > 0]
    if not scored:
        return 0.0
    hits = sum(r["id_hits"] for r in scored)
    total = sum(r["id_total"] for r in scored)
    return hits / total if total else 0.0


def precision(results: List[dict]) -> float:
    """% des positions attendues comme FIXES qui sont bien restées
    littérales — c'est la métrique qui détecte directement une régression
    du Bug 1 (sur-détection : une ressource sœur transformée en {x_id})."""
    scored = [r for r in results if r["fixed_total"] > 0]
    if not scored:
        return 0.0
    hits = sum(r["fixed_hits"] for r in scored)
    total = sum(r["fixed_total"] for r in scored)
    return hits / total if total else 0.0


def exact_case_pass_rate(results: List[dict]) -> float:
    """% de cas où TOUTES les positions (ID et fixes) sont correctes —
    la métrique la plus stricte, un seul segment faux fait échouer le cas."""
    if not results:
        return 0.0
    passed = sum(
        1 for r in results
        if r["id_hits"] == r["id_total"] and r["fixed_hits"] == r["fixed_total"]
    )
    return passed / len(results)


def naming_accuracy(results: List[dict]) -> float:
    """% des positions dotées d'un `expected_names` (golden_dataset.json,
    champ optionnel — opt-in, pas toutes les positions en ont) où le nom
    réellement généré fait partie des noms acceptables pour cette position.
    Comparaison déterministe par liste de tolérance, pas de string-exact ni
    de juge LLM (voir la discussion : la sortie est structurée, une liste
    de noms valides par cas suffit à couvrir l'ambiguïté légitime)."""
    scored = [r for r in results if r["name_total"] > 0]
    if not scored:
        return 0.0
    hits = sum(r["name_hits"] for r in scored)
    total = sum(r["name_total"] for r in scored)
    return hits / total if total else 0.0


def naming_consistency(results: List[dict]) -> float:
    """% des positions (par cas) où TOUTES les requêtes sœurs ont reçu
    exactement le même nom de paramètre — une position n'est pas cohérente
    si deux noms différents ont été assignés à ce qui devrait être le même
    paramètre conceptuel. Calculée sur toutes les positions dynamiques,
    pas seulement celles avec un `expected_names` (contrairement à
    naming_accuracy, ne nécessite aucune vérité terrain de nommage)."""
    total_positions = sum(r["consistency_positions"] for r in results)
    violations = sum(r["consistency_violations"] for r in results)
    if total_positions == 0:
        return 0.0
    return (total_positions - violations) / total_positions


def source_distribution(results: List[dict]) -> Dict[str, float]:
    """Répartition en % des `source` (PathParameter.source) sur tous les
    paramètres détectés — montre la part rules/context_rules/prefix_rules/
    payload/fallback (et groq_group/groq si le run inclut use_ai=True)."""
    counter: Counter = Counter()
    for r in results:
        counter.update(r["sources"])
    total = sum(counter.values())
    if total == 0:
        return {}
    return {source: count / total for source, count in counter.items()}


def raw_id_leak_count(results: List[dict]) -> int:
    """Nombre total de noms de paramètres qui embarquent une valeur d'ID
    brute (ex: emp_301_id) — garde-fou de régression du Bug 2. Doit
    toujours valoir 0."""
    return sum(len(r["leaked_names"]) for r in results)


def category_breakdown(results: List[dict]) -> Dict[str, dict]:
    """Taux de réussite par catégorie du golden dataset — utile pour voir
    si une régression future touche une famille de cas précise plutôt que
    tout le dataset."""
    by_category: Dict[str, List[dict]] = {}
    for r in results:
        by_category.setdefault(r["case"]["category"], []).append(r)

    breakdown = {}
    for category, cat_results in by_category.items():
        passed = sum(
            1 for r in cat_results
            if r["id_hits"] == r["id_total"] and r["fixed_hits"] == r["fixed_total"]
        )
        breakdown[category] = {
            "total_cases": len(cat_results),
            "passed_cases": passed,
            "pass_rate": passed / len(cat_results) if cat_results else 0.0,
        }
    return breakdown


if __name__ == "__main__":
    # ARIA-EVAL: 3 cas fictifs — vérifie que les fonctions tournent sans
    # crasher et donnent des chiffres plausibles, pas un test unitaire
    # exhaustif (voir tests/unit/ pour ça).
    fake_results = [
        {
            "case": {"id": "fake_ok", "category": "regex_forms"},
            "id_hits": 1, "id_total": 1, "fixed_hits": 1, "fixed_total": 1,
            "name_hits": 1, "name_total": 1,
            "sources": ["rules"], "leaked_names": [],
            "consistency_violations": 0, "consistency_positions": 1,
        },
        {
            "case": {"id": "fake_bug1_regression", "category": "bug1_sibling_resources"},
            "id_hits": 0, "id_total": 0, "fixed_hits": 1, "fixed_total": 2,  # 1 over-detected
            "name_hits": 0, "name_total": 0,
            "sources": ["context_rules"], "leaked_names": [],
            "consistency_violations": 0, "consistency_positions": 0,
        },
        {
            "case": {"id": "fake_bug2_regression", "category": "bug2_cascade_leak"},
            "id_hits": 1, "id_total": 1, "fixed_hits": 1, "fixed_total": 1,
            "name_hits": 0, "name_total": 1,  # wrong name: expected employee_id, got the leak
            "sources": ["prefix_rules"], "leaked_names": ["emp_301_id"],
            "consistency_violations": 1, "consistency_positions": 1,  # 2 sibling URLs, 2 different names
        },
    ]

    print(f"hit_rate          : {hit_rate(fake_results):.2%}")
    print(f"precision         : {precision(fake_results):.2%}")
    print(f"exact_case_pass   : {exact_case_pass_rate(fake_results):.2%}")
    print(f"naming_accuracy   : {naming_accuracy(fake_results):.2%}")
    print(f"naming_consistency: {naming_consistency(fake_results):.2%}")
    print(f"source_dist       : {source_distribution(fake_results)}")
    print(f"raw_id_leak_count : {raw_id_leak_count(fake_results)}")
    print(f"category_breakdown: {category_breakdown(fake_results)}")

    assert hit_rate(fake_results) == 1.0  # only fake_ok and fake_bug2 have id_total > 0, both hit
    # precision: (1 + 1 + 1) hits / (1 + 2 + 1) total = 3/4 — fake_bug1_regression
    # is the one dragging it down (1 of its 2 expected-fixed positions was
    # wrongly templated, simulating an unfixed Bug 1 regression).
    assert precision(fake_results) == 0.75
    # naming_accuracy: only fake_ok and fake_bug2 have name_total > 0 -> 1 hit / 2 total
    assert naming_accuracy(fake_results) == 0.5
    # naming_consistency: 1 consistent (fake_ok) + 1 inconsistent (fake_bug2) of 2 graded positions
    assert naming_consistency(fake_results) == 0.5
    assert raw_id_leak_count(fake_results) == 1
    assert hit_rate([]) == 0.0
    assert precision([]) == 0.0
    assert exact_case_pass_rate([]) == 0.0
    assert naming_accuracy([]) == 0.0
    assert naming_consistency([]) == 0.0
    print("\nSanity assertions passed.")
