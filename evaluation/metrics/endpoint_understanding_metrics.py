"""ARIA-EVAL: pure metric calculations for the endpoint enrichment golden
dataset (evaluation/golden_dataset/endpoint_understanding_golden_dataset.json).

This task produces free text (summary/description) that has no single
correct wording — those two fields are deliberately NOT scored here (no
LLM judge wired for this task, to stay free/fast). Only the structurally
verifiable parts are measured: business_domain/business_action correctness
(confirm vs. refine vs. infer), tag relevance (loose keyword match), and
confidence calibration (does the model stay appropriately unsure on sparse
schemas, as the prompt itself demands).
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


def domain_match_rate(results: List[dict]) -> float:
    """% de cas où business_domain prédit correspond à l'une des valeurs
    acceptées (business_domain_any_of) — ignore les cas où l'attendu est
    volontairement null (schéma trop pauvre pour juger)."""
    scored = [
        r for r in _scored(results)
        if r["case"]["expected"].get("business_domain_any_of") is not None
    ]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if _norm(r["predicted"].get("business_domain")) in
           {_norm(v) for v in r["case"]["expected"]["business_domain_any_of"]}
    )
    return hits / len(scored)


def action_match_rate(results: List[dict]) -> float:
    scored = [
        r for r in _scored(results)
        if r["case"]["expected"].get("business_action_any_of") is not None
    ]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if _norm(r["predicted"].get("business_action")) in
           {_norm(v) for v in r["case"]["expected"]["business_action_any_of"]}
    )
    return hits / len(scored)


def tag_relevance_rate(results: List[dict]) -> float:
    """% de cas où AU MOINS UN tag prédit correspond (par sous-chaîne,
    insensible à la casse) à l'un des mots-clés attendus — vérification
    souple, la formulation exacte des tags n'a pas de vérité unique."""
    scored = [
        r for r in _scored(results)
        if r["case"]["expected"].get("tag_keywords_any_of")
    ]
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        tags = [_norm(t) for t in (r["predicted"].get("tags") or [])]
        keywords = [_norm(k) for k in r["case"]["expected"]["tag_keywords_any_of"]]
        if any(kw in tag or tag in kw for tag in tags for kw in keywords):
            hits += 1
    return hits / len(scored)


def confidence_calibration_rate(results: List[dict]) -> float:
    """% de cas respectant la borne de confiance attendue — min_confidence
    (cas clairs, doit être confiant) OU max_confidence (schéma pauvre, doit
    rester prudent, exigence explicite du prompt système)."""
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


def strata_domain_match(results: List[dict], strata: str) -> float:
    scored = [
        r for r in _scored(results)
        if r["case"]["strata"] == strata and r["case"]["expected"].get("business_domain_any_of") is not None
    ]
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if _norm(r["predicted"].get("business_domain")) in
           {_norm(v) for v in r["case"]["expected"]["business_domain_any_of"]}
    )
    return hits / len(scored)
