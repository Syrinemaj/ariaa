"""
URL path normalizer.

normalize_path() is the single entry point: rules first (parameter_detector.py),
then group_hint (group_normalizer.py — one LLM call per endpoint group), then
a per-segment LLM fallback (semantic_normalizer.py) for whatever neither
resolved with confidence >= 0.70.

Fix 12.2 — Query parameters:
  See normalization/query_params.py for classification and fingerprinting.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.normalization.semantic_normalizer import SemanticNormalizer
from app.normalization.models import PathParameter
from app.normalization.parameter_detector import detect_parameter_type, infer_parameter_name

# Confidence score assigned when a group_hint decision is applied — "low"
# labels never reach here (normalize_path skips them, see below).
_GROUP_CONFIDENCE_SCORE: Dict[str, float] = {"high": 0.90, "medium": 0.75}


def normalize_path(
    method: str,
    path_or_url: str,
    request_body=None,
    response_body=None,
    use_ai: bool = True,
    observed_dynamic_positions: Optional[Set[int]] = None,
    group_hint: Optional[Dict[int, dict]] = None,
) -> Tuple[str, List[PathParameter]]:
    """
    Normalize a single path synchronously.

    observed_dynamic_positions — segment indices already known (from
    dynamic_segment_detector.detect_dynamic_positions, run once per ingestion
    batch) to vary across other requests of this same method+shape. Used as a
    fallback when regex-based detection finds nothing, so ID formats outside
    the anticipated patterns (parameter_detector.py) still get templated.

    group_hint — per-position decisions already resolved by
    group_normalizer.build_group_hints(), which compared this URL against
    its siblings (same endpoint) in a single LLM call instead of one call
    per isolated segment. Keyed by 0-indexed segment position. A position
    with confidence_label == "low" is treated as "no decision" and falls
    through to the normal rules/single-segment-LLM path below; otherwise it
    takes priority and skips that per-segment LLM call entirely.
    """
    parsed = urlparse(path_or_url)
    path = parsed.path if parsed.scheme else path_or_url
    path = path.strip()

    if not path.startswith("/"):
        path = f"/{path}"

    raw_segments = [s for s in path.split("/") if s]
    normalized_segments: List[str] = []
    parameters: List[PathParameter] = []
    dynamic_positions = observed_dynamic_positions or set()

    ai_normalizer = SemanticNormalizer() if use_ai else None

    for index, segment in enumerate(raw_segments):
        previous_segment = raw_segments[index - 1] if index > 0 else None
        next_segment = raw_segments[index + 1] if index + 1 < len(raw_segments) else None
        detected_type = detect_parameter_type(segment)
        if not detected_type and index in dynamic_positions:
            detected_type = "observed_variable"

        hint = group_hint.get(index) if group_hint else None
        if hint is not None and hint.get("confidence_label") != "low":
            if hint.get("is_id"):
                effective_type = detected_type or "group_llm_id"
                parameter_name, _source, _confidence = infer_parameter_name(
                    previous_segment=previous_segment,
                    detected_type=effective_type,
                    raw_value=segment,
                    request_body=request_body,
                    response_body=response_body,
                )
                normalized_segments.append(f"{{{parameter_name}}}")
                parameters.append(PathParameter(
                    name=parameter_name,
                    raw_value=segment,
                    type=effective_type,
                    source="groq_group",
                    confidence=_GROUP_CONFIDENCE_SCORE[hint["confidence_label"]],
                ))
            else:
                normalized_segments.append(segment.lower())
            continue

        if detected_type:
            parameter_name, source, confidence = infer_parameter_name(
                previous_segment=previous_segment,
                detected_type=detected_type,
                raw_value=segment,
                request_body=request_body,
                response_body=response_body,
            )

            if use_ai and confidence < 0.70 and ai_normalizer:
                try:
                    ai_result = ai_normalizer.infer_parameter_name(
                        method=method,
                        path=path,
                        raw_segment=segment,
                        previous_segment=previous_segment,
                        next_segment=next_segment,
                        request_body=request_body,
                        response_body=response_body,
                    )
                    ai_confidence = float(ai_result.get("confidence", 0.0))
                    ai_name = ai_result.get("parameter_name", parameter_name)
                    if ai_confidence >= confidence:
                        parameter_name = ai_name
                        detected_type = ai_result.get("parameter_type", detected_type)
                        source = "groq"
                        confidence = ai_confidence
                except Exception:
                    pass

            normalized_segments.append(f"{{{parameter_name}}}")
            parameters.append(PathParameter(
                name=parameter_name,
                raw_value=segment,
                type=detected_type,
                source=source,
                confidence=confidence,
            ))
        else:
            normalized_segments.append(segment.lower())

    normalized_path = "/" + "/".join(normalized_segments)
    if normalized_path != "/" and normalized_path.endswith("/"):
        normalized_path = normalized_path.rstrip("/")

    return normalized_path, parameters
