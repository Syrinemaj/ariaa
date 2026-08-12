"""ARIA-EVAL: normalization judge — deterministic structural comparison of
a run's output against a normalization_golden_dataset.json case, plus (when
the case opts in) a check of the confidence-gate decision against
tracer/normalization_tracer.py's NormalizationTrace.

No LLM-as-judge here — normalization correctness is exactly verifiable
against ground truth, unlike planner/RAG plan quality (see
judge/planner_judge.py for that one).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_PLACEHOLDER_RE = re.compile(r"^\{.+\}$")
_RAW_ID_LEAK_RE = re.compile(r"^[a-z]+_\d+_id$")

# Translates the pipeline's actual PathParameter.source values (provider-
# specific — "groq_group"/"groq" today, will grow a Bedrock equivalent)
# into the golden dataset's provider-agnostic vocabulary. Any source not
# listed here canonicalizes to "rules" (none of the rules-* sources ever
# call an LLM).
_SOURCE_TO_CANONICAL: Dict[str, str] = {
    "groq_group": "group_normalizer",
    "groq": "semantic_normalizer",
}


def _canonical_source(raw_source: str) -> str:
    return _SOURCE_TO_CANONICAL.get(raw_source, "rules")


def _segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


def judge_normalization_case(
    case: Dict[str, Any],
    endpoints: List[Any],
    trace: Optional[Any] = None,  # tracer.normalization_tracer.NormalizationTrace
) -> Dict[str, Any]:
    id_positions = set(case["id_positions"])
    fixed_positions = set(case["fixed_positions"])
    expected_names: Dict[str, List[str]] = case.get("expected_names", {})

    id_hits = id_total = fixed_hits = fixed_total = 0
    name_hits = name_total = 0
    sources: List[str] = []
    leaked_names: List[str] = []
    names_by_position: Dict[int, set] = {}

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

        placeholder_positions = [i for i, s in enumerate(segs) if _PLACEHOLDER_RE.match(s)]
        for pos, param in zip(placeholder_positions, ep.path_parameters):
            names_by_position.setdefault(pos, set()).add(param.name)
            pos_key = str(pos)
            if pos_key in expected_names:
                name_total += 1
                if param.name in expected_names[pos_key]:
                    name_hits += 1

    consistency_violations = sum(1 for names in names_by_position.values() if len(names) > 1)

    result: Dict[str, Any] = {
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

    expected_triggered = case.get("expected_llm_triggered")
    expected_source = case.get("expected_source")
    if expected_triggered is not None or expected_source is not None:
        actual_sources = {_canonical_source(s) for s in sources}
        # ARIA-EVAL: derive actual_triggered from actual_sources (built from
        # the real PathParameter.source values the pipeline just produced —
        # always reliable) rather than from `trace` (an EVAL_MODE-gated
        # side-channel that silently reads as "nothing happened" whenever
        # EVAL_MODE isn't set, even though real LLM calls did occur — this
        # produced a false MISMATCH on a real run before the fix). `trace`
        # is still the only source for cost/latency, kept for that.
        actual_triggered = bool(actual_sources - {"rules"})
        match = True
        if expected_triggered is not None:
            match = match and (actual_triggered == expected_triggered)
        if expected_source is not None:
            match = match and (expected_source in actual_sources)
        result["confidence_gate"] = {
            "expected_triggered": expected_triggered,
            "actual_triggered": actual_triggered,
            "expected_source": expected_source,
            "actual_sources": sorted(actual_sources),
            "match": match,
        }

    return result
