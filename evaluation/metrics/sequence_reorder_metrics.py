"""ARIA-EVAL: pure metric calculations for the step-reordering golden dataset
(evaluation/golden_dataset/sequence_reorder_golden_dataset.json).

Reordering has no single "right" full permutation in general — e.g. when two
unrelated resources are both present, only their relative order to EACH
OTHER'S own constraint matters, not a total order. So instead of comparing
predicted ordered_keys to one fixed expected sequence, each case carries
`order_constraints`: a list of (key_a, key_b) pairs meaning "key_a must
appear before key_b". A case is scored correct when every pair holds in the
predicted order — this matches exactly what reorder_steps_sync()'s system
prompt actually asks for (4 relative-order rules), not an exact-match
sequence.
"""
from __future__ import annotations

from typing import List


def _scored(results: List[dict]) -> List[dict]:
    return [r for r in results if r.get("predicted") is not None]


def completion_rate(results: List[dict]) -> float:
    if not results:
        return 0.0
    return len(_scored(results)) / len(results)


def key_integrity_rate(results: List[dict]) -> float:
    """% de cas où ordered_keys est exactement une permutation des clés
    d'entrée — aucune clé perdue, dupliquée ou inventée (exigence explicite
    du prompt système)."""
    scored = _scored(results)
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        input_keys = [s["key"] for s in r["case"]["steps"]]
        predicted = r["predicted"].get("ordered_keys") or []
        if sorted(predicted) == sorted(input_keys) and len(predicted) == len(input_keys):
            hits += 1
    return hits / len(scored)


def order_constraints_satisfied_rate(results: List[dict]) -> float:
    """% de cas où TOUTES les contraintes d'ordre relatif attendues sont
    respectées dans ordered_keys. Un cas sans contrainte (genuinely_ambiguous)
    est compté comme satisfait par défaut — n'importe quel ordre est correct
    tant que les clés sont intactes."""
    scored = _scored(results)
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        predicted = r["predicted"].get("ordered_keys") or []
        position = {k: i for i, k in enumerate(predicted)}
        constraints = r["case"]["expected"].get("order_constraints", [])
        ok = True
        for a, b in constraints:
            if a not in position or b not in position or position[a] >= position[b]:
                ok = False
                break
        if ok:
            hits += 1
    return hits / len(scored)


def confidence_calibration_rate(results: List[dict]) -> float:
    """% de cas respectant la borne de confiance attendue — min_confidence
    (une correction est clairement nécessaire, doit dépasser le seuil de
    déclenchement 0.60) ou max_confidence (aucune règle ne s'applique, ne
    pas inventer une confiance élevée). Les cas 'already_correct' n'ont
    volontairement aucune borne — conserver l'ordre est correct quelle que
    soit la confiance rapportée — donc ils sont exclus, pas comptés comme
    des échecs."""
    scored = [
        r for r in _scored(results)
        if "min_confidence" in r["case"]["expected"] or "max_confidence" in r["case"]["expected"]
    ]
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        conf = r["predicted"].get("confidence", 0.0)
        exp = r["case"]["expected"]
        ok = True
        if "min_confidence" in exp and conf < exp["min_confidence"]:
            ok = False
        if "max_confidence" in exp and conf > exp["max_confidence"]:
            ok = False
        if ok:
            hits += 1
    return hits / len(scored)


def rule_type_accuracy(results: List[dict], rule_type: str) -> float:
    """order_constraints_satisfied_rate restreint à un seul rule_type —
    permet de voir si le modèle rate systématiquement UNE règle précise
    (ex : parent-enfant) plutôt qu'une moyenne globale qui la noierait."""
    scored = [r for r in _scored(results) if r["case"]["rule_type"] == rule_type]
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        predicted = r["predicted"].get("ordered_keys") or []
        position = {k: i for i, k in enumerate(predicted)}
        constraints = r["case"]["expected"].get("order_constraints", [])
        ok = True
        for a, b in constraints:
            if a not in position or b not in position or position[a] >= position[b]:
                ok = False
                break
        if ok:
            hits += 1
    return hits / len(scored)
