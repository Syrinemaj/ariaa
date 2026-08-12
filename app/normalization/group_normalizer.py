"""
Group-level LLM normalization.

url_normalizer.py calls the LLM one segment at a time, for one URL in
isolation (semantic_normalizer.py). That means the model never sees the
sibling requests of the same endpoint, so it cannot use the one signal
that reliably identifies non-standard ID formats: a segment whose value
changes between requests that are otherwise identical is almost always an
identifier, no matter what it looks like (business codes, hash-like
tokens, text+id combos, ...).

This module adds a step BEFORE the per-segment LLM call: group requests
that share the same structural skeleton (method + segment count + fixed
segments), then, only for positions the rules pipeline is not confident
about, send ALL sibling URLs of that group to the LLM in a single call.
The model compares them directly and returns one decision per segment
position, which url_normalizer.normalize_path() consumes as `group_hint`.

Rules-first is preserved: a group only reaches the LLM if at least one of
its positions has rule confidence < _CONFIDENCE_THRESHOLD (same threshold
used by the existing single-segment path). Groups fully resolved by rules
never trigger a group LLM call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.ai.base_client import AIClientProtocol, create_ai_client
from app.normalization.parameter_detector import detect_parameter_type, infer_parameter_name

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.70
_MAX_URLS_PER_GROUP = 20  # bounds prompt size for very large endpoints
_VAR_MARKER = "\0VAR\0"
_VALID_CONFIDENCE_LABELS = {"high", "medium", "low"}
_GROUP_CONFIDENCE_SCORE = {"high": 0.90, "medium": 0.75}

GroupKey = Tuple[str, int, Tuple[str, ...]]

_GROUP_SYSTEM_PROMPT = """Tu es un normalisateur d'URLs pour un pipeline d'automatisation API. Ta tâche : identifier TOUS les segments d'URL qui représentent des identifiants variables (à remplacer par des placeholders), même s'ils ne suivent pas un format standard.

## Contexte fourni
Tu reçois plusieurs URLs appartenant au MÊME endpoint (même méthode HTTP, même structure de chemin). Utilise cette comparaison pour détecter les segments variables :
- Un segment qui change de valeur d'une requête à l'autre est presque toujours un ID, MÊME s'il ne ressemble pas à un UUID ou un entier classique.
- Un segment identique dans toutes les requêtes est fixe (ne pas templatiser), sauf preuve contraire.

## Types d'IDs à détecter (liste non exhaustive, ne te limite pas aux formats évidents)
- Entiers purs : /users/123
- UUID : /orders/a1b2c3d4-...
- Alphanumériques courts : /items/AB12CD
- Codes métier structurés : /invoices/INV-2024-0891
- IDs collés à du texte : /user_45892, /order-8821-details (isole la partie variable)
- Hash ou tokens encodés (base64/hex tronqué)
- Tout segment dont la valeur varie entre requêtes du même groupe, quelle que soit sa forme

## Règles de décision
1. Priorité à la variabilité inter-requêtes sur la forme du segment.
2. Si un segment ressemble à une année, un statut, ou un mot métier connu (ex: "pending", "2024", "active") MAIS varie entre requêtes du même groupe → c'est un ID, pas un mot fixe.
3. Si un segment est mixte (texte + ID), retourne le template en isolant uniquement la partie variable (ex: order-8821-details → order-{id}-details).
4. En cas de doute réel (un seul exemple disponible, aucune variabilité observable) → signale le segment comme "incertain" plutôt que de forcer une décision. Dans le JSON, "incertain" se traduit par confidence: "low" — fournis quand même ta meilleure estimation de is_id, la confidence basse suffit à signaler le doute ; ne renvoie jamais un champ vide ou le texte littéral "incertain".

## Format de sortie (JSON strict, aucun texte hors JSON)
{
  "normalized_template": "string",
  "segments": [
    {
      "value": "string",
      "position": int,
      "is_id": true/false,
      "confidence": "high" / "medium" / "low",
      "reason": "string court justifiant la décision"
    }
  ]
}

## Exemples

Entrée (groupe de 3 URLs du même endpoint) :
["/api/orders/8821/details", "/api/orders/9034/details", "/api/orders/7756/details"]

Sortie :
{
  "normalized_template": "/api/orders/{id}/details",
  "segments": [
    {"value": "orders", "position": 2, "is_id": false, "confidence": "high", "reason": "segment fixe identique dans toutes les requêtes"},
    {"value": "8821", "position": 3, "is_id": true, "confidence": "high", "reason": "valeur variable entre requêtes, forme numérique"},
    {"value": "details", "position": 4, "is_id": false, "confidence": "high", "reason": "segment fixe identique dans toutes les requêtes"}
  ]
}

Entrée (groupe de 2 URLs) :
["/api/invoices/INV-2024-0891", "/api/invoices/INV-2024-1123"]

Sortie :
{
  "normalized_template": "/api/invoices/INV-2024-{id}",
  "segments": [
    {"value": "invoices", "position": 2, "is_id": false, "confidence": "high", "reason": "segment fixe"},
    {"value": "INV-2024-0891", "position": 3, "is_id": true, "confidence": "high", "reason": "partie numérique finale variable malgré préfixe fixe partagé"}
  ]
}

Entrée (groupe de 1 seule URL — aucune comparaison possible) :
["/api/batches/zx9k2m"]

Sortie :
{
  "normalized_template": "/api/batches/zx9k2m",
  "segments": [
    {"value": "batches", "position": 2, "is_id": false, "confidence": "high", "reason": "segment fixe"},
    {"value": "zx9k2m", "position": 3, "is_id": true, "confidence": "low", "reason": "forme non standard, mais un seul exemple observé — aucune variabilité à comparer, décision incertaine"}
  ]
}

## Ta tâche maintenant
Voici le groupe d'URLs à analyser : {urls_du_meme_endpoint}

Retourne uniquement le JSON, sans commentaire."""

_GROUP_JSON_SCHEMA: dict = {
    "name": "group_url_normalization",
    "schema": {
        "type": "object",
        "properties": {
            "normalized_template": {"type": "string"},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "position": {"type": "integer"},
                        "is_id": {"type": "boolean"},
                        "confidence": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["value", "position", "is_id", "confidence", "reason"],
                },
            },
        },
        "required": ["normalized_template", "segments"],
        "additionalProperties": False,
    },
}


@dataclass
class GroupStats:
    """Simple counters for tracing rules-vs-LLM usage (evaluation/reporting)."""
    groups_seen: int = 0
    groups_needing_llm: int = 0
    llm_calls: int = 0
    fallback_single_example: int = 0
    fallback_invalid_response: int = 0
    fallback_low_confidence_segments: int = 0

    def reset(self) -> None:
        self.groups_seen = 0
        self.groups_needing_llm = 0
        self.llm_calls = 0
        self.fallback_single_example = 0
        self.fallback_invalid_response = 0
        self.fallback_low_confidence_segments = 0


_stats = GroupStats()


def get_stats() -> GroupStats:
    return _stats


def reset_stats() -> None:
    _stats.reset()


def _raw_segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


def _build_skeleton_key(method: str, segments: List[str], dynamic_positions: Set[int]) -> GroupKey:
    """
    Same method + segment count + fixed segments = same endpoint.
    A position is masked (candidate variable) if regex already flags it as
    an ID, or if dynamic_segment_detector observed it varying across other
    requests of this shape in the current batch.
    """
    skeleton = tuple(
        _VAR_MARKER if (i in dynamic_positions or detect_parameter_type(seg) is not None) else seg.lower()
        for i, seg in enumerate(segments)
    )
    return (method.upper(), len(segments), skeleton)


def _find_ambiguous_positions(skeleton: Tuple[str, ...], segment_rows: List[List[str]]) -> List[int]:
    """
    Among masked (variable) positions, keep only those the rules pipeline
    is not confident about (min confidence across all observed rows below
    threshold) — these are the ones worth spending an LLM call on.
    """
    ambiguous: List[int] = []
    for pos, marker in enumerate(skeleton):
        if marker != _VAR_MARKER:
            continue

        min_confidence = 1.0
        for row in segment_rows:
            segment = row[pos]
            previous_segment = row[pos - 1] if pos > 0 else None
            detected_type = detect_parameter_type(segment) or "observed_variable"
            _, _, confidence = infer_parameter_name(previous_segment, detected_type, segment)
            min_confidence = min(min_confidence, confidence)

        if min_confidence < _CONFIDENCE_THRESHOLD:
            ambiguous.append(pos)

    return ambiguous


def _call_group_llm(client: AIClientProtocol, method: str, urls: List[str]) -> dict:
    return client.structured_chat(
        system_prompt=_GROUP_SYSTEM_PROMPT,
        user_payload={"method": method, "urls_du_meme_endpoint": urls},
        json_schema=_GROUP_JSON_SCHEMA,
        task_name="url_group_normalization",
    )


def _validate_response(response: object) -> Optional[dict]:
    """Schema check beyond what the AI client itself guarantees (top-level
    required keys only) — validates each segment's inner structure."""
    if not isinstance(response, dict):
        return None

    template = response.get("normalized_template")
    segments = response.get("segments")
    if not isinstance(template, str) or not isinstance(segments, list):
        return None

    for seg in segments:
        if not isinstance(seg, dict):
            return None
        if not isinstance(seg.get("value"), str):
            return None
        if not isinstance(seg.get("position"), int):
            return None
        if not isinstance(seg.get("is_id"), bool):
            return None
        if seg.get("confidence") not in _VALID_CONFIDENCE_LABELS:
            return None
        if not isinstance(seg.get("reason"), str):
            return None

    return {"normalized_template": template, "segments": segments}


def build_group_hints(
    entries: Sequence[Tuple[str, str]],
    dynamic_positions_per_entry: Sequence[Set[int]],
    ai_client: Optional[AIClientProtocol] = None,
) -> List[Optional[Dict[int, dict]]]:
    """
    entries: (method, path) per request, in the same order the caller will
    iterate to build NormalizedEndpoint objects.

    dynamic_positions_per_entry: ARIA-NORM-FIX — one already per-entry-
    validated position set per request, aligned by index with `entries`
    (produced by service.py via dynamic_segment_detector.
    is_position_dynamic_for_entry()). This used to be a single dict keyed
    by (method, segment_count) shared across every path of that shape —
    which meant a position legitimately dynamic for one endpoint family
    (e.g. /webhooks/{hex}) leaked onto an unrelated family that merely had
    the same segment count (e.g. /hr/employees vs /hr/departments), since
    _build_skeleton_key() below would then mask that position for BOTH,
    grouping them as "the same endpoint" and asking the LLM to compare
    literally unrelated resources. Taking pre-validated per-entry sets
    instead of the coarse dict closes that at the source.

    Returns one entry per input, aligned by index: None if the request has
    no group-resolved position, otherwise a dict of
    {0-indexed segment position: {"is_id": bool, "confidence_label": str, "reason": str}}
    for positions the group step resolved (or explicitly marked low-confidence).

    url_normalizer.normalize_path() treats confidence_label == "low" as "no
    decision" and keeps its own rules/single-segment-LLM fallback.
    """
    n = len(entries)
    hints: List[Optional[Dict[int, dict]]] = [None] * n
    if n == 0:
        return hints

    groups: Dict[GroupKey, List[int]] = {}
    segments_cache: List[List[str]] = []
    for idx, (method, path) in enumerate(entries):
        segments = _raw_segments(path)
        segments_cache.append(segments)
        dynamic_positions = dynamic_positions_per_entry[idx]
        key = _build_skeleton_key(method, segments, dynamic_positions)
        groups.setdefault(key, []).append(idx)

    client: Optional[AIClientProtocol] = ai_client

    for key, indices in groups.items():
        method, _length, skeleton = key
        _stats.groups_seen += 1

        rows = [segments_cache[i] for i in indices]
        ambiguous_positions = _find_ambiguous_positions(skeleton, rows)
        if not ambiguous_positions:
            continue

        _stats.groups_needing_llm += 1

        if len(indices) < 2:
            # Single observation — no cross-request variability to compare,
            # can't distinguish a real ID from a one-off static word. Don't
            # guess: mark low-confidence so the caller falls back to rules.
            _stats.fallback_single_example += 1
            logger.info(
                "group_normalizer.fallback_single_example group=%s positions=%s",
                key, ambiguous_positions,
            )
            for i in indices:
                hints[i] = {
                    pos: {"is_id": None, "confidence_label": "low", "reason": "single example, no observable variability"}
                    for pos in ambiguous_positions
                }
            continue

        urls = ["/" + "/".join(row) for row in rows][:_MAX_URLS_PER_GROUP]

        if client is None:
            client = create_ai_client()

        try:
            raw_response = _call_group_llm(client, method, urls)
        except Exception as exc:
            _stats.fallback_invalid_response += 1
            logger.warning(
                "group_normalizer.llm_call_failed group=%s error=%s — falling back to rules pipeline",
                key, exc,
            )
            continue
        finally:
            _stats.llm_calls += 1

        validated = _validate_response(raw_response)
        if validated is None:
            _stats.fallback_invalid_response += 1
            logger.warning(
                "group_normalizer.invalid_llm_response group=%s — falling back to rules pipeline", key,
            )
            continue

        # LLM "position" is 1-indexed over the full path (matches the prompt's
        # own examples) — convert to the 0-indexed segments used internally.
        per_position = {seg["position"] - 1: seg for seg in validated["segments"]}

        for pos in ambiguous_positions:
            seg_info = per_position.get(pos)
            if seg_info is None:
                continue  # LLM didn't cover this position — leave to existing fallback

            confidence_label = seg_info["confidence"]
            if confidence_label == "low":
                _stats.fallback_low_confidence_segments += 1

            hint_entry = {
                "is_id": bool(seg_info["is_id"]),
                "confidence_label": confidence_label,
                "reason": seg_info.get("reason", ""),
            }
            for i in indices:
                hints[i] = hints[i] or {}
                hints[i][pos] = hint_entry

    return hints
