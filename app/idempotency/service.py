"""
Service d'idempotency — INSERT ON CONFLICT atomique.

Problème de l'ancienne version (race condition TOCTOU) :
  Worker A : SELECT → aucun enregistrement → va exécuter
  Worker B : SELECT → aucun enregistrement → va exécuter
  Worker A + B : exécutent tous les deux → doublon

Solution :
  INSERT INTO idempotency_records ... ON CONFLICT DO NOTHING RETURNING id
  Si RETURNING est vide → doublon → skip.
  Si RETURNING contient un id → premier worker → exécuter.
  Cette opération est ATOMIQUE au niveau PostgreSQL.

Flux complet :
  1. acquire_idempotency_lock() → INSERT → retourne True (exécuter) ou False (skip)
  2. [Exécution de l'étape]
  3. mark_idempotency_success() ou mark_idempotency_failure()
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.idempotency.key_generator import generate_idempotency_key


async def acquire_idempotency_lock(
    db: AsyncSession,
    idempotency_key: str,
    endpoint_key: str,
    org_id: str,
) -> bool:
    """
    Tente d'acquérir le verrou d'idempotency pour (idempotency_key, endpoint_key).

    Retourne True  → premier worker, doit exécuter l'étape.
    Retourne False → doublon détecté, doit skiper.

    ON CONFLICT DO NOTHING + RETURNING id :
    - Si la ligne n'existe pas → INSERT réussit → RETURNING renvoie l'id
    - Si la ligne existe déjà  → DO NOTHING   → RETURNING est vide
    """
    result = await db.execute(
        text("""
            INSERT INTO idempotency_records
                (id, idempotency_key, endpoint_key, org_id, status, created_at, updated_at)
            VALUES
                (gen_random_uuid()::text, :key, :endpoint_key, :org_id,
                 'pending', NOW(), NOW())
            ON CONFLICT (idempotency_key, endpoint_key)
            DO NOTHING
            RETURNING id
        """),
        {
            "key": idempotency_key,
            "endpoint_key": endpoint_key,
            "org_id": org_id,
        },
    )
    await db.flush()
    row = result.fetchone()
    return row is not None  # True = first, False = duplicate


async def mark_idempotency_success(
    db: AsyncSession,
    idempotency_key: str,
    endpoint_key: str,
    response_reference: dict,
) -> None:
    await db.execute(
        text("""
            UPDATE idempotency_records
            SET status = 'success',
                response_reference = CAST(:ref AS jsonb),
                updated_at = NOW()
            WHERE idempotency_key = :key
              AND endpoint_key = :endpoint_key
        """),
        {
            "key": idempotency_key,
            "endpoint_key": endpoint_key,
            "ref": __import__("json").dumps(response_reference),
        },
    )
    await db.flush()


async def mark_idempotency_failure(
    db: AsyncSession,
    idempotency_key: str,
    endpoint_key: str,
    error: str,
) -> None:
    await db.execute(
        text("""
            UPDATE idempotency_records
            SET status = 'failed',
                response_reference = jsonb_build_object('error', :error),
                updated_at = NOW()
            WHERE idempotency_key = :key
              AND endpoint_key = :endpoint_key
        """),
        {
            "key": idempotency_key,
            "endpoint_key": endpoint_key,
            "error": error[:2000],  # cap error message length
        },
    )
    await db.flush()


async def should_skip_due_to_idempotency(
    db: AsyncSession,
    workflow_name: str,
    endpoint_key: str,
    org_id: str,
    business_fields: dict,
) -> bool:
    """
    Vérifie si cette étape a déjà été exécutée avec succès.
    Utilise une requête SELECT simple (lecture seule, avant le lock).
    """
    key = generate_idempotency_key(
        workflow_name=workflow_name,
        endpoint_key=endpoint_key,
        org_id=org_id,
        business_fields=business_fields,
    )
    result = await db.execute(
        text("""
            SELECT status FROM idempotency_records
            WHERE idempotency_key = :key
              AND endpoint_key = :endpoint_key
            LIMIT 1
        """),
        {"key": key, "endpoint_key": endpoint_key},
    )
    row = result.fetchone()
    return row is not None and row[0] == "success"


async def save_success_idempotency(
    db: AsyncSession,
    automation_run_id: str,
    data_row_id: str | None,
    row_index: int,
    workflow_name: str,
    endpoint_key: str,
    org_id: str,
    business_fields: dict,
    response_reference: dict,
) -> None:
    """
    Convenience wrapper : génère la clé + marque le succès.
    Appelé après exécution réussie d'une étape.
    """
    key = generate_idempotency_key(
        workflow_name=workflow_name,
        endpoint_key=endpoint_key,
        org_id=org_id,
        business_fields=business_fields,
    )
    await mark_idempotency_success(
        db=db,
        idempotency_key=key,
        endpoint_key=endpoint_key,
        response_reference=response_reference,
    )
