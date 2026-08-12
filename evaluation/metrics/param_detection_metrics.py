"""ARIA-EVAL: pure metric calculations for the URL-segment parameter-
detection golden dataset (evaluation/golden_dataset/param_detection_golden_dataset.jsonl).

Unlike normalization_metrics.py (deterministic pipeline, exactly
verifiable), this dataset has no wired pipeline code yet — the metrics
here score a MODEL'S free-form is_parameter/param_name prediction against
`proposed` in the golden dataset, produced by
run_scripts/run_param_detection_eval.py.

Each function takes the same shape: a list of per-case result dicts, one
per golden_dataset entry:
{
    "case": {...golden_dataset.jsonl entry...},
    "predicted": {"is_parameter": bool, "param_name": str|None,
                  "confidence": float, "reason": str} | None (on error),
    "error": str | None,
}

Positive class = is_parameter True (the segment is a dynamic path
parameter that should be templated). Name comparison is separated from
the True/False classification on purpose: getting is_parameter right but
param_name wrong is a much smaller mistake than the reverse, and the two
should never be blended into one pass/fail number.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional

# Golden dataset names use camelCase ("employeeId"); a model prompted for
# snake_case would answer "employee_id" — both correct, different spelling.
# Naming comparison strips separators/case so either convention matches.
_NORMALIZE_RE = re.compile(r"[^a-z0-9]")


def _normalize_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return _NORMALIZE_RE.sub("", name.lower())


def _scored(results: List[dict]) -> List[dict]:
    """Excludes cases where the call itself failed (no predicted dict) —
    those count against completion rate, not classification accuracy."""
    return [r for r in results if r.get("predicted") is not None]


def completion_rate(results: List[dict]) -> float:
    """% de cas ayant reçu une réponse exploitable (pas d'erreur API, pas de
    JSON hors-schéma). Un modèle avec un faible completion_rate est
    disqualifié avant même de regarder ses autres métriques."""
    if not results:
        return 0.0
    return len(_scored(results)) / len(results)


def _confusion(results: List[dict]) -> Dict[str, int]:
    scored = _scored(results)
    tp = fp = fn = tn = 0
    for r in scored:
        expected = r["case"]["proposed"]["is_parameter"]
        actual = r["predicted"]["is_parameter"]
        if expected and actual:
            tp += 1
        elif not expected and actual:
            fp += 1
        elif expected and not actual:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def accuracy(results: List[dict]) -> float:
    """% de cas où is_parameter (bool) est correctement classé — toutes
    strates confondues, y compris les cas 'constant'/'ambiguous' où la
    bonne réponse est False."""
    scored = _scored(results)
    if not scored:
        return 0.0
    c = _confusion(results)
    return (c["tp"] + c["tn"]) / len(scored)


def precision(results: List[dict]) -> float:
    """TP / (TP + FP) — quand le modèle dit "c'est un paramètre", a-t-il
    raison ? Un FP ici correspond à un segment constant/statique (ex: 'v2',
    'me', 'bulk') templatisé à tort — casserait un endpoint réel en
    production si ce composant alimentait la normalisation."""
    c = _confusion(results)
    denom = c["tp"] + c["fp"]
    return c["tp"] / denom if denom else 0.0


def recall(results: List[dict]) -> float:
    """TP / (TP + FN) — parmi les vrais paramètres dynamiques, combien sont
    détectés ? Un FN laisse un segment variable figé en littéral (fragmente
    un endpoint en autant d'entrées que de valeurs observées)."""
    c = _confusion(results)
    denom = c["tp"] + c["fn"]
    return c["tp"] / denom if denom else 0.0


def specificity(results: List[dict]) -> float:
    """TN / (TN + FP) — parmi les vrais segments statiques, combien restent
    correctement non-templatisés."""
    c = _confusion(results)
    denom = c["tn"] + c["fp"]
    return c["tn"] / denom if denom else 0.0


def false_positive_count(results: List[dict]) -> int:
    return _confusion(results)["fp"]


def false_negative_count(results: List[dict]) -> int:
    return _confusion(results)["fn"]


def f1(results: List[dict]) -> float:
    p, r = precision(results), recall(results)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def naming_accuracy(results: List[dict]) -> float:
    """% des cas où golden ET modèle s'accordent sur is_parameter=True, et
    où le param_name proposé correspond (comparaison insensible à la casse
    et aux séparateurs — camelCase vs snake_case tous deux acceptés). Ne
    pénalise pas un mauvais nom quand la classification True/False elle-
    même était fausse — ce sont deux erreurs distinctes, voir le docstring
    du module."""
    scored = [
        r for r in _scored(results)
        if r["case"]["proposed"]["is_parameter"] and r["predicted"]["is_parameter"]
    ]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if _normalize_name(r["predicted"].get("param_name"))
        == _normalize_name(r["case"]["proposed"]["param_name"])
    )
    return hits / len(scored)


def breakdown_by(results: List[dict], key: str) -> Dict[str, dict]:
    """Accuracy is_parameter par valeur de `key` (case["strata"] ou
    case["difficulty"]) — repère si un modèle échoue sur une strate
    spécifique (ex: bon sur 'uuid', mauvais sur 'ambiguous') plutôt que de
    ne voir qu'une moyenne globale qui masque ça."""
    by_key: Dict[str, List[dict]] = {}
    for r in _scored(results):
        by_key.setdefault(r["case"][key], []).append(r)

    breakdown = {}
    for value, group in by_key.items():
        correct = sum(
            1 for r in group
            if r["predicted"]["is_parameter"] == r["case"]["proposed"]["is_parameter"]
        )
        breakdown[value] = {
            "total": len(group),
            "correct": correct,
            "accuracy": correct / len(group) if group else 0.0,
        }
    return breakdown


def trap_accuracy(results: List[dict]) -> float:
    """Accuracy is_parameter restreinte aux cas avec un `trap` non-null —
    le sous-ensemble conçu pour être trompeur (piège). C'est le chiffre qui
    discrimine le mieux deux modèles par ailleurs proches en accuracy
    globale : un modèle qui devine bien sur les cas faciles mais échoue sur
    les pièges a un score global gonflé par le déséquilibre du dataset."""
    trap_cases = [r for r in _scored(results) if r["case"].get("trap")]
    if not trap_cases:
        return 0.0
    correct = sum(
        1 for r in trap_cases
        if r["predicted"]["is_parameter"] == r["case"]["proposed"]["is_parameter"]
    )
    return correct / len(trap_cases)


def confusion_matrix(results: List[dict]) -> Dict[str, int]:
    return _confusion(results)


def source_distribution(results: List[dict]) -> Dict[str, float]:
    """Répartition en % des strates ('uuid', 'hash', 'constant', ...) sur
    l'ensemble des cas notés — pour vérifier que le sample utilisé est
    représentatif avant de comparer deux modèles dessus."""
    counter: Counter = Counter(r["case"]["strata"] for r in _scored(results))
    total = sum(counter.values())
    if total == 0:
        return {}
    return {strata: count / total for strata, count in counter.items()}


if __name__ == "__main__":
    fake_results = [
        {  # true positive, name correct (camelCase vs snake_case)
            "case": {"strata": "uuid", "difficulty": "easy", "trap": None,
                      "proposed": {"is_parameter": True, "param_name": "employeeId"}},
            "predicted": {"is_parameter": True, "param_name": "employee_id", "confidence": 0.9, "reason": ""},
        },
        {  # true negative
            "case": {"strata": "constant", "difficulty": "easy", "trap": "'v2' looks like a value",
                      "proposed": {"is_parameter": False, "param_name": None}},
            "predicted": {"is_parameter": False, "param_name": None, "confidence": 0.9, "reason": ""},
        },
        {  # false positive: model templated a constant
            "case": {"strata": "constant", "difficulty": "hard", "trap": "date-like version",
                      "proposed": {"is_parameter": False, "param_name": None}},
            "predicted": {"is_parameter": True, "param_name": "version_id", "confidence": 0.6, "reason": ""},
        },
        {  # false negative: model missed a real id
            "case": {"strata": "hash", "difficulty": "medium", "trap": None,
                      "proposed": {"is_parameter": True, "param_name": "resourceId"}},
            "predicted": {"is_parameter": False, "param_name": None, "confidence": 0.55, "reason": ""},
        },
        {  # true positive, name wrong
            "case": {"strata": "uuid", "difficulty": "hard", "trap": "sibling uuids",
                      "proposed": {"is_parameter": True, "param_name": "contractId"}},
            "predicted": {"is_parameter": True, "param_name": "employee_id", "confidence": 0.5, "reason": ""},
        },
        {  # completion failure
            "case": {"strata": "ambiguous", "difficulty": "hard", "trap": "no signal",
                      "proposed": {"is_parameter": True, "param_name": "genericId"}},
            "predicted": None, "error": "bad_output_format",
        },
    ]

    print(f"completion_rate : {completion_rate(fake_results):.2%}")
    print(f"accuracy        : {accuracy(fake_results):.2%}")
    print(f"precision       : {precision(fake_results):.2%}")
    print(f"recall          : {recall(fake_results):.2%}")
    print(f"specificity     : {specificity(fake_results):.2%}")
    print(f"f1              : {f1(fake_results):.2%}")
    print(f"naming_accuracy : {naming_accuracy(fake_results):.2%}")
    print(f"trap_accuracy   : {trap_accuracy(fake_results):.2%}")
    print(f"confusion       : {confusion_matrix(fake_results)}")
    print(f"by strata       : {breakdown_by(fake_results, 'strata')}")

    # 5 scored (1 error excluded) -> confusion tp=2,fp=1,fn=1,tn=1
    assert completion_rate(fake_results) == 5 / 6
    assert confusion_matrix(fake_results) == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    assert accuracy(fake_results) == 3 / 5
    assert abs(precision(fake_results) - 2 / 3) < 1e-9
    assert recall(fake_results) == 2 / 3
    assert specificity(fake_results) == 0.5
    # naming_accuracy: 2 cases with both sides True (case0 name-match, case4 name-mismatch) -> 1/2
    assert naming_accuracy(fake_results) == 0.5
    assert accuracy([]) == 0.0
    assert precision([]) == 0.0
    assert recall([]) == 0.0
    assert naming_accuracy([]) == 0.0
    print("\nSanity assertions passed.")
