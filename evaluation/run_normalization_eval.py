"""ARIA-EVAL: normalization evaluation harness — runs every case in
normalization_golden_dataset.json through the real pipeline
(app/normalization/service.py::normalize_entries), computes structural
metrics, and exports a CSV.

No LLM involved by default (use_ai=False) — deterministic, free, fast,
reproducible identically on every run. This is the deliberate choice made
for this harness (see conversation): normalization correctness is exactly
verifiable, unlike plan-generation quality, so there is no judge.py
equivalent here.

    python -m evaluation.run_normalization_eval

To measure the REAL LLM-fallback rate (how many of the 15% residual cases
actually reach group_normalizer.py's Groq call) rather than the always-0%
figure the deterministic default gives by construction, opt in explicitly —
this costs real Groq tokens and is non-deterministic run to run:

    python -m evaluation.run_normalization_eval --with-ai
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from typing import Dict, List, Optional, Set

from app.ingestion.models import TrafficEntry
from app.normalization.service import normalize_entries
from evaluation.normalization_metrics import (
    category_breakdown,
    exact_case_pass_rate,
    hit_rate,
    naming_accuracy,
    naming_consistency,
    precision,
    raw_id_leak_count,
    source_distribution,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DATASET_PATH = os.path.join(_HERE, "normalization_golden_dataset.json")
RESULTS_CSV_PATH = os.path.join(_HERE, "normalization_results.csv")

_PLACEHOLDER_RE = re.compile(r"^\{.+\}$")
_RAW_ID_LEAK_RE = re.compile(r"^[a-z]+_\d+_id$")


def _segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


def run_single_case(case: dict, use_ai: bool = False) -> dict:
    urls = case["urls"]
    request_bodies: List[Optional[dict]] = case.get("request_bodies") or [None] * len(urls)
    response_bodies: List[Optional[dict]] = case.get("response_bodies") or [None] * len(urls)

    entries = [
        TrafficEntry(
            method=case["method"],
            url=f"https://example.com{u}",
            path=u,
            request_body=request_bodies[i],
            response_body=response_bodies[i],
        )
        for i, u in enumerate(urls)
    ]

    # ARIA-EVAL: use_ai=False by default — see module docstring. deduplicate=
    # False so every individual URL's own normalized_path is graded (a
    # case's expected id/fixed positions apply per-URL, not to a merged
    # catalog entry — deduplication is a separate, already-tested concern in
    # tests/unit/test_dynamic_segment_detector.py etc.).
    endpoints = normalize_entries(entries, use_ai=use_ai, deduplicate=False)

    id_positions = set(case["id_positions"])
    fixed_positions = set(case["fixed_positions"])
    # ARIA-EVAL: opt-in — golden_dataset.json cases without this field
    # simply contribute nothing to naming_accuracy, not a failure.
    expected_names: Dict[str, List[str]] = case.get("expected_names", {})

    id_hits = id_total = fixed_hits = fixed_total = 0
    name_hits = name_total = 0
    sources: List[str] = []
    leaked_names: List[str] = []
    # ARIA-EVAL: tracks, per absolute segment position, every distinct name
    # generated across this case's sibling URLs — feeds naming_consistency.
    names_by_position: Dict[int, Set[str]] = {}

    for ep in endpoints:
        segs = _segments(ep.normalized_path)
        for pos in id_positions:
            id_total += 1
            if pos < len(segs) and _PLACEHOLDER_RE.match(segs[pos]):
                id_hits += 1
        for pos in fixed_positions:
            fixed_total += 1
            if pos < len(segs) and not _PLACEHOLDER_RE.match(segs[pos]):
                fixed_hits += 1

        for param in ep.path_parameters:
            sources.append(param.source)
            if _RAW_ID_LEAK_RE.match(param.name):
                leaked_names.append(param.name)

        # ARIA-EVAL: PathParameter carries no absolute position — it's
        # appended in the same left-to-right order normalize_path() walks
        # segments, so zipping the placeholder positions found in
        # normalized_path with path_parameters (both in that same order)
        # reconstructs the position -> name mapping.
        placeholder_positions = [i for i, s in enumerate(segs) if _PLACEHOLDER_RE.match(s)]
        for pos, param in zip(placeholder_positions, ep.path_parameters):
            names_by_position.setdefault(pos, set()).add(param.name)
            pos_key = str(pos)
            if pos_key in expected_names:
                name_total += 1
                if param.name in expected_names[pos_key]:
                    name_hits += 1

    consistency_violations = sum(1 for names in names_by_position.values() if len(names) > 1)

    return {
        "case": case,
        "id_hits": id_hits, "id_total": id_total,
        "fixed_hits": fixed_hits, "fixed_total": fixed_total,
        "name_hits": name_hits, "name_total": name_total,
        "sources": sources,
        "leaked_names": leaked_names,
        "consistency_violations": consistency_violations,
        "consistency_positions": len(names_by_position),
        "sample_templates": sorted({ep.normalized_path for ep in endpoints}),
    }


def run_eval(use_ai: bool = False) -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    results = [run_single_case(case, use_ai=use_ai) for case in cases]

    print("══ RÉSULTATS ══")
    print(f"Cas testés         : {len(results)}")
    print(f"Mode               : {'use_ai=True (coûte des tokens Groq réels)' if use_ai else 'use_ai=False (déterministe)'}")
    print(f"Hit rate (recall)  : {hit_rate(results):.2%}")
    print(f"Precision          : {precision(results):.2%}")
    print(f"Exact case pass    : {exact_case_pass_rate(results):.2%}")
    print(f"Naming accuracy    : {naming_accuracy(results):.2%} (positions avec expected_names uniquement)")
    print(f"Naming consistency : {naming_consistency(results):.2%}")
    print(f"Fuite d'ID brut    : {raw_id_leak_count(results)} (doit être 0)")

    print("\n── Répartition par source ──")
    dist = source_distribution(results)
    for source, pct in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"  {source:25s}: {pct:.1%}")
    llm_pct = sum(pct for src, pct in dist.items() if src in ("groq_group", "groq"))
    if use_ai:
        print(f"  → taux de fallback LLM réel : {llm_pct:.1%}")
    else:
        print("  → fallback LLM jamais sollicité (use_ai=False) — relancer avec --with-ai pour le taux réel")

    print("\n── Répartition par catégorie ──")
    for category, stats in sorted(category_breakdown(results).items()):
        print(f"  {category:28s}: {stats['passed_cases']}/{stats['total_cases']} ({stats['pass_rate']:.0%})")

    failed = [
        r for r in results
        if r["id_hits"] != r["id_total"] or r["fixed_hits"] != r["fixed_total"]
    ]
    if failed:
        print("\n── Cas en échec ──")
        for r in failed:
            print(f"  {r['case']['id']}: id {r['id_hits']}/{r['id_total']}, "
                  f"fixed {r['fixed_hits']}/{r['fixed_total']} -> {r['sample_templates']}")

    name_mismatches = [r for r in results if r["name_hits"] != r["name_total"]]
    if name_mismatches:
        print("\n── Noms de paramètre inattendus ──")
        for r in name_mismatches:
            print(f"  {r['case']['id']}: naming {r['name_hits']}/{r['name_total']}")

    inconsistent = [r for r in results if r["consistency_violations"] > 0]
    if inconsistent:
        print("\n── Incohérences de nommage (même position, noms différents) ──")
        for r in inconsistent:
            print(f"  {r['case']['id']}: {r['consistency_violations']} position(s) incohérente(s)")

    fieldnames = [
        "id", "category", "method", "id_hits", "id_total",
        "fixed_hits", "fixed_total", "name_hits", "name_total",
        "consistency_violations", "consistency_positions",
        "passed", "leaked_names", "sample_templates",
    ]
    with open(RESULTS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "id": r["case"]["id"],
                "category": r["case"]["category"],
                "method": r["case"]["method"],
                "id_hits": r["id_hits"], "id_total": r["id_total"],
                "fixed_hits": r["fixed_hits"], "fixed_total": r["fixed_total"],
                "name_hits": r["name_hits"], "name_total": r["name_total"],
                "consistency_violations": r["consistency_violations"],
                "consistency_positions": r["consistency_positions"],
                "passed": r["id_hits"] == r["id_total"] and r["fixed_hits"] == r["fixed_total"],
                "leaked_names": ";".join(r["leaked_names"]),
                "sample_templates": ";".join(r["sample_templates"]),
            })

    print(f"\nRésultats exportés → {RESULTS_CSV_PATH}")
    return results


if __name__ == "__main__":
    run_eval(use_ai="--with-ai" in sys.argv)
