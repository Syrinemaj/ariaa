"""ARIA-EVAL: pure metric calculations for the traffic classification golden
dataset (evaluation/golden_dataset/traffic_classification_golden_dataset.json).

Each function takes the same shape: a list of per-case result dicts, one per
golden_dataset entry:
{
    "case": {...golden_dataset.json entry...},
    "predicted": {"should_keep": bool, "business_domain": str|None,
                  "business_action": str|None, "confidence": float,
                  "reason": str} | None (on error),
    "error": str | None,
}

Positive class = should_keep True (the call is a real business API worth
keeping). Domain/action match is scored separately from the True/False
classification — getting should_keep right but domain wrong is a smaller
mistake than the reverse.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    return "".join(c for c in text.lower() if c.isalnum())


def _scored(results: List[dict]) -> List[dict]:
    return [r for r in results if r.get("predicted") is not None]


def completion_rate(results: List[dict]) -> float:
    if not results:
        return 0.0
    return len(_scored(results)) / len(results)


def _confusion(results: List[dict]) -> Dict[str, int]:
    scored = _scored(results)
    tp = fp = fn = tn = 0
    for r in scored:
        expected = r["case"]["expected"]["should_keep"]
        actual = r["predicted"]["should_keep"]
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
    scored = _scored(results)
    if not scored:
        return 0.0
    c = _confusion(results)
    return (c["tp"] + c["tn"]) / len(scored)


def precision(results: List[dict]) -> float:
    """TP / (TP + FP) — quand should_keep=true, le modèle a-t-il raison ?
    Un FP ici pollue le catalogue d'endpoints avec du bruit."""
    c = _confusion(results)
    denom = c["tp"] + c["fp"]
    return c["tp"] / denom if denom else 0.0


def recall(results: List[dict]) -> float:
    """TP / (TP + FN) — un FN supprime silencieusement un vrai endpoint
    métier de tout le pipeline (c'est le risque explicitement documenté
    dans le prompt système lui-même)."""
    c = _confusion(results)
    denom = c["tp"] + c["fn"]
    return c["tp"] / denom if denom else 0.0


def specificity(results: List[dict]) -> float:
    c = _confusion(results)
    denom = c["tn"] + c["fp"]
    return c["tn"] / denom if denom else 0.0


def f1(results: List[dict]) -> float:
    p, r = precision(results), recall(results)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def domain_action_accuracy(results: List[dict]) -> float:
    """% des cas où expected.should_keep=True ET predicted.should_keep=True,
    et où business_domain ET business_action correspondent tous les deux
    (comparaison insensible à la casse/ponctuation)."""
    scored = [
        r for r in _scored(results)
        if r["case"]["expected"]["should_keep"] and r["predicted"]["should_keep"]
    ]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if _normalize(r["predicted"].get("business_domain")) == _normalize(r["case"]["expected"].get("business_domain"))
        and _normalize(r["predicted"].get("business_action")) == _normalize(r["case"]["expected"].get("business_action"))
    )
    return hits / len(scored)


def confidence_band_respected(results: List[dict]) -> float:
    """% des cas 'genuinely_ambiguous' où la confiance prédite reste sous le
    plafond annoté (confidence_ceiling) — vérifie que le modèle reconnaît
    bien l'incertitude plutôt que d'être artificiellement sûr de lui sur un
    cas réellement limite."""
    scored = [
        r for r in _scored(results)
        if r["case"]["strata"] == "genuinely_ambiguous" and "confidence_ceiling" in r["case"]["expected"]
    ]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if r["predicted"]["confidence"] <= r["case"]["expected"]["confidence_ceiling"]
    )
    return hits / len(scored)


def strata_accuracy(results: List[dict], strata: str) -> float:
    """Accuracy should_keep restreinte à une strate donnée — repère si un
    modèle échoue spécifiquement sur les pièges (noise_disguised_as_business
    / business_disguised_as_noise) plutôt que de ne voir qu'une moyenne
    globale qui masque ça."""
    scored = [r for r in _scored(results) if r["case"]["strata"] == strata]
    if not scored:
        return 0.0
    correct = sum(
        1 for r in scored
        if r["predicted"]["should_keep"] == r["case"]["expected"]["should_keep"]
    )
    return correct / len(scored)


def confusion_matrix(results: List[dict]) -> Dict[str, int]:
    return _confusion(results)


def strata_distribution(results: List[dict]) -> Dict[str, int]:
    return dict(Counter(r["case"]["strata"] for r in _scored(results)))
