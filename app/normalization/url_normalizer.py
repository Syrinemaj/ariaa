"""
URL path normalizer — sync (backward compat) + async batch variants.

Fix 12.1 — Batch LLM inference:
  Old: 1 Azure OpenAI call per ambiguous segment → 200 calls for 100 endpoints.
  New: collect all ambiguous segments across the full endpoint list,
       check Redis cache per segment, batch ALL uncached ones in ONE LLM call.

Fix 12.2 — Query parameters:
  See normalization/query_params.py for classification and fingerprinting.

Backward compat: normalize_path() is kept synchronous for Celery tasks and
existing callers. Use normalize_paths_batch() for the async FastAPI pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import redis.asyncio as aioredis

from app.normalization.semantic_normalizer import SemanticNormalizer
from app.normalization.models import NormalizedEndpoint, PathParameter
from app.normalization.parameter_detector import detect_parameter_type, infer_parameter_name

_PARAM_CACHE_TTL: int = 86_400  # 24 h


@dataclass
class AmbiguousSegment:
    """Represents one path segment that needs LLM inference."""
    path: str           # full path with [PARAM] at the ambiguous position
    segment: str        # raw segment value (e.g. "9a2b3c4d")
    previous_segment: Optional[str]
    canonical_key: str  # identifies which endpoint this belongs to
    segment_index: int


# ─── Sync interface (Celery tasks, existing callers) ─────────────────────────

def normalize_path(
    method: str,
    path_or_url: str,
    request_body=None,
    response_body=None,
    use_ai: bool = True,
) -> Tuple[str, List[PathParameter]]:
    """
    Normalize a single path synchronously (one LLM call per ambiguous segment).

    Kept for Celery tasks and tests. For the async FastAPI pipeline with
    many endpoints, prefer normalize_paths_batch() to batch LLM calls.
    """
    parsed = urlparse(path_or_url)
    path = parsed.path if parsed.scheme else path_or_url
    path = path.strip()

    if not path.startswith("/"):
        path = f"/{path}"

    raw_segments = [s for s in path.split("/") if s]
    normalized_segments: List[str] = []
    parameters: List[PathParameter] = []

    ai_normalizer = SemanticNormalizer() if use_ai else None

    for index, segment in enumerate(raw_segments):
        previous_segment = raw_segments[index - 1] if index > 0 else None
        next_segment = raw_segments[index + 1] if index + 1 < len(raw_segments) else None
        detected_type = detect_parameter_type(segment)

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


# ─── Async batch interface (FastAPI pipeline) ─────────────────────────────────

async def get_cached_param_name(
    previous_segment: Optional[str],
    segment_pattern: str,
    redis_client: aioredis.Redis,
) -> Optional[str]:
    """
    Look up a previously inferred parameter name in Redis.

    Cache key: param_name:{previous_segment}:{segment_pattern}
    /users/{uuid} → user_id is reused for every /users/{uuid} occurrence.
    """
    cache_key = f"param_name:{previous_segment}:{segment_pattern}"
    cached = await redis_client.get(cache_key)
    return cached if isinstance(cached, str) else None


async def _store_param_name(
    previous_segment: Optional[str],
    segment_pattern: str,
    param_name: str,
    redis_client: aioredis.Redis,
) -> None:
    cache_key = f"param_name:{previous_segment}:{segment_pattern}"
    await redis_client.setex(cache_key, _PARAM_CACHE_TTL, param_name)


async def batch_infer_parameter_names(
    ambiguous_segments: List[AmbiguousSegment],
    ai_client,  # AIClientProtocol — GroqClient or AzureOpenAIClient
) -> Dict[str, str]:
    """
    Infer parameter names for ALL ambiguous segments in ONE LLM call.

    Prompt lists each path with [PARAM] at the ambiguous position.
    Response is a JSON object mapping each path to its inferred param name.

    Returns: {"path_with_[PARAM]": "param_name", ...}
    """
    if not ambiguous_segments:
        return {}

    path_list = "\n".join(f"- {seg.path}" for seg in ambiguous_segments)

    system_prompt = (
        "You are an API URL normalization engine.\n"
        "For each path below, infer the semantic parameter name for the [PARAM] segment.\n"
        "Use snake_case names like employee_id, invoice_id, department_id.\n"
        "Return strict JSON only: an object mapping each path string to its param name.\n"
        'Example: {"/users/[PARAM]/orders": "user_id"}'
    )

    user_payload: Dict[str, str] = {"paths": path_list}

    json_schema: Dict = {
        "name": "batch_param_inference",
        "strict": False,
        "schema": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    }

    result = await ai_client.structured_chat_async(
        system_prompt=system_prompt,
        user_payload=user_payload,
        json_schema=json_schema,
        task_name="batch_param_inference",
    )

    return {k: v for k, v in result.items() if isinstance(k, str) and isinstance(v, str)}


async def normalize_paths_batch(
    endpoints: List[NormalizedEndpoint],
    ai_client,  # AIClientProtocol — GroqClient or AzureOpenAIClient
    redis_client: aioredis.Redis,
) -> List[NormalizedEndpoint]:
    """
    Normalize a list of endpoints using a single batched LLM call for all
    ambiguous segments (confidence < 0.70 and not already in Redis cache).

    Returns the same endpoint list with updated normalized_path and
    path_parameters where AI inference improved the result.
    """
    # Phase 1: collect ambiguous segments across all endpoints
    ambiguous: List[AmbiguousSegment] = []
    endpoint_segment_map: Dict[str, Dict[int, Tuple[str, str, float]]] = {}

    for ep in endpoints:
        raw_segments = [s for s in ep.normalized_path.split("/") if s]
        seg_data: Dict[int, Tuple[str, str, float]] = {}

        for idx, segment in enumerate(raw_segments):
            detected_type = detect_parameter_type(segment)
            if not detected_type:
                continue

            previous_segment = raw_segments[idx - 1] if idx > 0 else None
            param_name, source, confidence = infer_parameter_name(
                previous_segment=previous_segment,
                detected_type=detected_type,
                raw_value=segment,
            )
            seg_data[idx] = (param_name, source, confidence)

            if confidence < 0.70:
                # Build path with [PARAM] at the ambiguous position
                display_segments = list(raw_segments)
                display_segments[idx] = "[PARAM]"
                display_path = "/" + "/".join(display_segments)

                # Check Redis cache first
                cached_name = await get_cached_param_name(
                    previous_segment, segment, redis_client
                )
                if cached_name:
                    seg_data[idx] = (cached_name, "redis_cache", 0.85)
                else:
                    ambiguous.append(AmbiguousSegment(
                        path=display_path,
                        segment=segment,
                        previous_segment=previous_segment,
                        canonical_key=ep.canonical_key,
                        segment_index=idx,
                    ))

        endpoint_segment_map[ep.canonical_key] = seg_data

    # Phase 2: one LLM call for all uncached ambiguous segments
    ai_names: Dict[str, str] = {}
    if ambiguous:
        ai_names = await batch_infer_parameter_names(ambiguous, ai_client)

        # Persist results to Redis for future runs
        for seg in ambiguous:
            inferred = ai_names.get(seg.path)
            if inferred:
                await _store_param_name(
                    seg.previous_segment, seg.segment, inferred, redis_client
                )

    # Phase 3: apply results back to endpoints
    updated: List[NormalizedEndpoint] = []
    for ep in endpoints:
        raw_segments = [s for s in ep.original_path.split("/") if s]
        seg_data = endpoint_segment_map.get(ep.canonical_key, {})
        normalized_segs: List[str] = []
        params: List[PathParameter] = []

        for idx, segment in enumerate(raw_segments):
            detected_type = detect_parameter_type(segment)
            if detected_type and idx in seg_data:
                param_name, source, confidence = seg_data[idx]

                # Override with AI result if available
                display_segs = list(raw_segments)
                display_segs[idx] = "[PARAM]"
                display_path = "/" + "/".join(display_segs)
                ai_name = ai_names.get(display_path)
                if ai_name:
                    param_name, source, confidence = ai_name, "groq_batch", 0.88

                normalized_segs.append(f"{{{param_name}}}")
                params.append(PathParameter(
                    name=param_name,
                    raw_value=segment,
                    type=detected_type,
                    source=source,
                    confidence=confidence,
                ))
            else:
                normalized_segs.append(segment.lower())

        new_path = "/" + "/".join(normalized_segs)
        if new_path != "/" and new_path.endswith("/"):
            new_path = new_path.rstrip("/")

        updated.append(ep.model_copy(update={
            "normalized_path": new_path,
            "path_parameters": params,
        }))

    return updated
