"""
Générateur de clés d'idempotency — champs métier uniquement.

Problème de l'ancienne version :
  hash(row_data COMPLET) incluait les timestamps, IDs internes, champs de
  traçabilité → deux exécutions logiquement identiques produisaient des clés
  différentes → doublon en base.

Solution :
  Hasher UNIQUEMENT les champs qui identifient l'opération métier :
    org_id         : isolation multi-tenant
    workflow_name  : contexte du workflow
    endpoint_key   : endpoint cible
    business_fields: données fonctionnelles passées en paramètre par l'appelant

  L'appelant est responsable de n'inclure que les champs stables
  (ex: email, user_id) et d'exclure les champs volatils
  (ex: timestamp, request_id, _metadata).

  Tri récursif des clés → sérialisation canonique (JSON déterministe).
  Séparateurs compacts (',', ':') → pas d'espace dans le JSON.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def _canonical(obj: Any) -> Any:
    """Trie récursivement les clés de dicts pour une sérialisation déterministe."""
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_canonical(i) for i in obj]
    return obj


def generate_idempotency_key(
    workflow_name: str,
    endpoint_key: str,
    org_id: str,
    business_fields: Dict[str, Any],
) -> str:
    """
    Génère une clé SHA-256 stable pour une opération métier.

    business_fields doit contenir UNIQUEMENT les champs qui
    définissent l'unicité métier de l'opération, par exemple :
      {"employee_id": "E-123", "contract_type": "CDI"}

    NE PAS inclure :
      - timestamp, created_at, updated_at
      - row_index, _metadata, request_id
      - tout champ qui varie entre deux exécutions identiques
    """
    canonical = {
        "org_id": org_id,
        "workflow_name": workflow_name,
        "endpoint_key": endpoint_key,
        "fields": _canonical(business_fields),
    }
    serialized = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
