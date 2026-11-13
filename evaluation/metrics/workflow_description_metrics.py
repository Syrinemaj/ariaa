"""ARIA-EVAL: pure metric calculations for the workflow description golden
dataset (evaluation/golden_dataset/workflow_description_golden_dataset.json).

summary/description are free text with no single correct wording — NOT
scored here (no LLM judge wired for this task, to stay free/fast). Only the
structurally verifiable parts are measured: estimated_risk correctness
against the prompt's own explicit rules (DELETE/payment/bulk -> high,
critical create/update -> medium, read-only/low-stakes -> low), tag
relevance, and risk_confidence calibration.
"""
from __future__ import annotations

from typing import List, Optional


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return "".join(c for c in s.lower() if c.isalnum())


def _scored(results: List[dict]) -> List[dict]:
    return [r for r in results if r.get("predicted") is not None]


def completion_rate(results: List[dict]) -> float:
    if not results:
        return 0.0
    return len(_scored(results)) / len(results)


def risk_match_rate(results: List[dict]) -> float:
    """% de cas où estimated_risk prédit est dans estimated_risk_any_of —
    pour les cas 'ambiguous', plusieurs niveaux de risque sont acceptés
    (jugement, pas une vérité binaire), pour tous les autres un seul niveau
    est correct d'après les règles explicites du prompt système."""
    scored = _scored(results)
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if (r["predicted"].get("estimated_risk") or "").lower() in
           set(r["case"]["expected"]["estimated_risk_any_of"])
    )
    return hits / len(scored)


def tag_relevance_rate(results: List[dict]) -> float:
    """% de cas où AU MOINS UN tag prédit correspond (par sous-chaîne,
    insensible à la casse) à l'un des mots-clés attendus."""
    scored = [
        r for r in _scored(results)
        if r["case"]["expected"].get("tag_keywords_any_of")
    ]
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        tags = [_norm(t) for t in (r["predicted"].get("business_tags") or [])]
        keywords = [_norm(k) for k in r["case"]["expected"]["tag_keywords_any_of"]]
        if any(kw in tag or tag in kw for tag in tags for kw in keywords):
            hits += 1
    return hits / len(scored)


def confidence_calibration_rate(results: List[dict]) -> float:
    """% de cas respectant la borne de confiance attendue sur
    risk_confidence — min_confidence (cas clair, la règle du prompt
    s'applique sans ambiguïté) ou max_confidence (jugement, le prompt exige
    explicitement <0.8 dans ce cas)."""
    scored = [
        r for r in _scored(results)
        if "min_confidence" in r["case"]["expected"] or "max_confidence" in r["case"]["expected"]
    ]
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        conf = r["predicted"].get("risk_confidence", 0.0)
        exp = r["case"]["expected"]
        ok = True
        if "min_confidence" in exp and conf < exp["min_confidence"]:
            ok = False
        if "max_confidence" in exp and conf > exp["max_confidence"]:
            ok = False
        if ok:
            hits += 1
    return hits / len(scored)


def category_risk_match(results: List[dict], category: str) -> float:
    """risk_match_rate restreint à une catégorie (ex : 'high_bulk') — pour
    voir si le modèle rate systématiquement une des 3 sous-règles de 'high'
    plutôt qu'une moyenne globale qui la noierait."""
    scored = [r for r in _scored(results) if r["case"]["category"] == category]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if (r["predicted"].get("estimated_risk") or "").lower() in
           set(r["case"]["expected"]["estimated_risk_any_of"])
    )
    return hits / len(scored)
