"""ARIA-EVAL: pure metric calculations for the workflow grouping golden
dataset (evaluation/golden_dataset/workflow_grouping_golden_dataset.json).

Grouping (clustering) has no single "right" per-item label to compare
against — the standard way to score a predicted partition against a gold
partition is PAIRWISE co-membership agreement: for every pair of endpoints,
does "are they in the same group?" agree between gold and prediction?
This is robust to group *numbering* being arbitrary (group 0 in the
prediction doesn't need to correspond to group 0 in the gold set).

Each function takes a list of per-case result dicts:
{
    "case": {...golden_dataset.json entry...},
    "predicted": {"groups": [{"name":..., "business_domain":..., "summary":...,
                  "endpoint_indices": [...]}]} | None (on error),
    "error": str | None,
}
"""
from __future__ import annotations

import re
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

_BANNED_NAMES = {"group", "group_1", "group1", "misc", "other", "others", "default", "unknown", ""}
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _scored(results: List[dict]) -> List[dict]:
    return [r for r in results if r.get("predicted") is not None]


def completion_rate(results: List[dict]) -> float:
    if not results:
        return 0.0
    return len(_scored(results)) / len(results)


def _gold_pairs(partition: List[List[int]]) -> Set[Tuple[int, int]]:
    pairs = set()
    for group in partition:
        for a, b in combinations(sorted(group), 2):
            pairs.add((a, b))
    return pairs


def _predicted_pairs(groups: List[dict]) -> Set[Tuple[int, int]]:
    pairs = set()
    for g in groups:
        indices = sorted(set(g.get("endpoint_indices", [])))
        for a, b in combinations(indices, 2):
            pairs.add((a, b))
    return pairs


def _all_pairs(n: int) -> Set[Tuple[int, int]]:
    return set(combinations(range(n), 2))


def index_completeness(results: List[dict]) -> float:
    """% de cas où chaque index d'entrée apparaît dans EXACTEMENT un groupe
    de la sortie — condition structurelle stricte imposée par le prompt
    lui-même ('no index skipped, no index in two groups')."""
    scored = _scored(results)
    if not scored:
        return 0.0
    ok = 0
    for r in scored:
        n = len(r["case"]["endpoints"])
        all_indices: List[int] = []
        for g in r["predicted"].get("groups", []):
            all_indices.extend(g.get("endpoint_indices", []))
        if sorted(all_indices) == list(range(n)):
            ok += 1
    return ok / len(scored)


def pairwise_precision(results: List[dict]) -> float:
    """Parmi les paires que le modèle place dans le même groupe, combien le
    sont réellement selon la référence ? Un score bas = sur-regroupement
    (fusionne des capacités métier qui devraient rester séparées)."""
    scored = _scored(results)
    tp = fp = 0
    for r in scored:
        gold = _gold_pairs(r["case"]["expected_partition"])
        pred = _predicted_pairs(r["predicted"].get("groups", []))
        tp += len(gold & pred)
        fp += len(pred - gold)
    return tp / (tp + fp) if (tp + fp) else 0.0


def pairwise_recall(results: List[dict]) -> float:
    """Parmi les paires qui devraient être ensemble selon la référence,
    combien le sont réellement dans la prédiction ? Un score bas =
    sur-découpage (sépare des endpoints qui forment une même capacité)."""
    scored = _scored(results)
    tp = fn = 0
    for r in scored:
        gold = _gold_pairs(r["case"]["expected_partition"])
        pred = _predicted_pairs(r["predicted"].get("groups", []))
        tp += len(gold & pred)
        fn += len(gold - pred)
    return tp / (tp + fn) if (tp + fn) else 0.0


def pairwise_f1(results: List[dict]) -> float:
    p, r = pairwise_precision(results), pairwise_recall(results)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def group_count_match_rate(results: List[dict]) -> float:
    """% de cas où le nombre de groupes prédits == nombre de groupes attendus.
    Signal plus strict et plus lisible que le F1 par paires seul."""
    scored = _scored(results)
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if len(r["predicted"].get("groups", [])) == len(r["case"]["expected_partition"])
    )
    return hits / len(scored)


def naming_quality_rate(results: List[dict]) -> float:
    """% de GROUPES (pas de cas) dont le nom respecte le format snake_case
    demandé par le prompt et n'est pas un nom générique interdit ('misc',
    'group_1'...), et dont business_domain n'est pas vide. Vérification
    structurelle/heuristique, pas une évaluation sémantique fine (pas de
    juge LLM ici pour rester gratuit)."""
    scored = _scored(results)
    total = 0
    ok = 0
    for r in scored:
        for g in r["predicted"].get("groups", []):
            total += 1
            name = (g.get("name") or "").strip().lower()
            domain = (g.get("business_domain") or "").strip()
            if name in _BANNED_NAMES:
                continue
            if not _SNAKE_CASE_RE.match(name):
                continue
            if not domain:
                continue
            ok += 1
    return ok / total if total else 0.0


def confusion_totals(results: List[dict]) -> Dict[str, int]:
    scored = _scored(results)
    tp = fp = fn = 0
    for r in scored:
        gold = _gold_pairs(r["case"]["expected_partition"])
        pred = _predicted_pairs(r["predicted"].get("groups", []))
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
    return {"tp": tp, "fp": fp, "fn": fn}
