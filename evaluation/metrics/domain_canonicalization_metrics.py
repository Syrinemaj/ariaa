"""ARIA-EVAL: pure metric calculations for the domain canonicalization golden
dataset (evaluation/golden_dataset/domain_canonicalization_golden_dataset.json).

Unlike endpoint/workflow grouping, this task's output (canonical_domains)
carries NO mapping back to which raw label became which canonical label —
production only ever consumes the final deduplicated list (see
app/planner/service.py::_get_known_domains), so scoring is done at the
canonical-SET level against each case's expected_groups: how many distinct
real domains should exist after merging, and whether each is represented by
at least one matching predicted label (loose keyword match, since the exact
wording of a canonical label has no single correct answer per the prompt's
own "prefer the clearest, most complete form" instruction — only which
raw variants got merged together is checkable).
"""
from __future__ import annotations

from typing import List


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _scored(results: List[dict]) -> List[dict]:
    return [r for r in results if r.get("predicted") is not None]


def completion_rate(results: List[dict]) -> float:
    if not results:
        return 0.0
    return len(_scored(results)) / len(results)


def _label_matches_group(label_norm: str, group_keywords_norm: List[str]) -> bool:
    return any(kw in label_norm or label_norm in kw for kw in group_keywords_norm)


def count_accuracy(results: List[dict]) -> float:
    """% de cas où le nombre de labels canoniques prédits correspond
    exactement au nombre de domaines réellement distincts attendus — capture
    à la fois la sous-fusion (doublons non fusionnés) et la sur-fusion
    (domaines distincts regroupés à tort)."""
    scored = _scored(results)
    if not scored:
        return 0.0
    hits = sum(
        1 for r in scored
        if len(r["predicted"].get("canonical_domains") or []) == len(r["case"]["expected_groups"])
    )
    return hits / len(scored)


def coverage_rate(results: List[dict]) -> float:
    """Moyenne, sur les cas notés, de la fraction des domaines attendus
    ayant AU MOINS UN label canonique prédit qui leur correspond (par
    sous-chaîne, insensible à la casse) — détecte un domaine entièrement
    manqué (mal fusionné dans un autre ou renommé de façon méconnaissable)."""
    scored = _scored(results)
    if not scored:
        return 0.0
    total = 0.0
    for r in scored:
        predicted_norm = [_norm(d) for d in (r["predicted"].get("canonical_domains") or [])]
        groups = r["case"]["expected_groups"]
        matched = sum(
            1 for g in groups
            if any(_label_matches_group(p, [_norm(k) for k in g["keywords_any_of"]]) for p in predicted_norm)
        )
        total += matched / len(groups) if groups else 1.0
    return total / len(scored)


def distinctness_rate(results: List[dict]) -> float:
    """% de cas où aucun label canonique prédit ne correspond simultanément
    à DEUX groupes attendus différents — détecte une sur-fusion (deux
    domaines réellement distincts regroupés sous un seul label), le piège
    explicite illustré par dc_004 (localization / monitoring) et dc_010
    (departments / projects)."""
    scored = _scored(results)
    if not scored:
        return 0.0
    hits = 0
    for r in scored:
        predicted_norm = [_norm(d) for d in (r["predicted"].get("canonical_domains") or [])]
        groups = r["case"]["expected_groups"]
        group_keywords = [[_norm(k) for k in g["keywords_any_of"]] for g in groups]
        over_merged = False
        for p in predicted_norm:
            matches = sum(1 for kws in group_keywords if _label_matches_group(p, kws))
            if matches >= 2:
                over_merged = True
                break
        if not over_merged:
            hits += 1
    return hits / len(scored)
