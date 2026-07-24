"""
Workflow deduplication via embedding centroid similarity.

Two async functions intended to be called from ingestion Step 5 (or any
post-processing step that has a live AsyncSession):

compute_workflow_centroid(canonical_keys, run_id, db)
    Fetches embeddings from endpoint_embeddings for the given canonical_keys,
    computes their mean vector (centroid), and returns it as list[float].
    Returns None when no embeddings are found.

find_duplicate_workflows(centroid, org_id, run_id, db)
    Scans all workflows in the same org (excluding current run) whose
    metadata_json["centroid"] was previously stored.
    Computes cosine distance in Python (no pgvector JSONB cast needed).
    Returns workflows with cosine distance < threshold (default 0.15,
    i.e. cosine similarity > 0.85).

Typical usage in ingestion Step 5:
    from app.workflows.workflow_deduplicator import (
        compute_workflow_centroid, find_duplicate_workflows
    )
    centroid = await compute_workflow_centroid(canonical_keys, run_id, db)
    if centroid:
        wf.metadata_json = {**(wf.metadata_json or {}), "centroid": centroid}
        dupes = await find_duplicate_workflows(centroid, org_id, run_id, db)
        if dupes:
            wf.metadata_json["duplicate_of"] = dupes
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def compute_workflow_centroid(
    canonical_keys: List[str],
    run_id: str,
    db: AsyncSession,
) -> Optional[List[float]]:
    """
    Compute the mean embedding (centroid) for a set of endpoints identified
    by their canonical_keys within a specific run.

    Joins endpoints → endpoint_embeddings to locate the vectors.
    Returns None if numpy is unavailable or no embeddings exist.
    """
    if not canonical_keys:
        return None

    try:
        import numpy as np
        from app.models.endpoint import Endpoint
        from app.models.embedding import EndpointEmbedding

        # Resolve canonical_keys to endpoint IDs within this run
        ep_res = await db.execute(
            select(Endpoint.id)
            .where(
                Endpoint.canonical_key.in_(canonical_keys),
                Endpoint.run_id == run_id,
            )
        )
        ep_ids = [row[0] for row in ep_res.all()]
        if not ep_ids:
            logger.debug(
                "workflow_deduplicator.no_endpoints run=%s keys=%d",
                run_id, len(canonical_keys),
            )
            return None

        # Fetch their embeddings
        emb_res = await db.execute(
            select(EndpointEmbedding.embedding)
            .where(EndpointEmbedding.endpoint_id.in_(ep_ids))
        )
        raw_embeddings = emb_res.scalars().all()
        vectors = [np.array(e, dtype=float) for e in raw_embeddings if e is not None]

        if not vectors:
            return None

        centroid = np.mean(vectors, axis=0)
        return centroid.tolist()

    except ImportError:
        logger.warning("workflow_deduplicator: numpy not available — skipping centroid")
        return None
    except Exception as exc:
        logger.warning("workflow_deduplicator.centroid_failed error=%s", exc)
        return None


async def find_duplicate_workflows(
    centroid: List[float],
    org_id: str,
    run_id: str,
    db: AsyncSession,
    threshold: float = 0.15,
    limit: int = 5,
) -> List[Dict]:
    """
    Find existing workflows (same org, different run) whose stored centroid
    is close to the given centroid (cosine distance < threshold).

    Similarity is computed in Python over the metadata_json["centroid"] field
    — no pgvector operator on JSONB required.

    Returns a list (sorted by similarity desc) of:
        [{"id": ..., "name": ..., "run_id": ..., "similarity": 0.92}, ...]
    """
    if not centroid:
        return []

    try:
        import numpy as np
        from app.models.workflow import WorkflowModel
        from app.models.analysis_run import AnalysisRun

        wf_res = await db.execute(
            select(
                WorkflowModel.id,
                WorkflowModel.name,
                WorkflowModel.run_id,
                WorkflowModel.metadata_json,
            )
            .join(AnalysisRun, AnalysisRun.id == WorkflowModel.run_id)
            .where(
                AnalysisRun.org_id == org_id,
                WorkflowModel.run_id != run_id,
            )
        )
        rows = wf_res.all()
        if not rows:
            return []

        query_vec  = np.array(centroid, dtype=float)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)

        duplicates = []
        for row in rows:
            stored = (row.metadata_json or {}).get("centroid")
            if not stored:
                continue
            try:
                candidate_vec  = np.array(stored, dtype=float)
                candidate_norm = candidate_vec / (np.linalg.norm(candidate_vec) + 1e-9)
                distance       = float(1.0 - np.dot(query_norm, candidate_norm))
                if distance < threshold:
                    duplicates.append({
                        "id":         row.id,
                        "name":       row.name,
                        "run_id":     row.run_id,
                        "similarity": round(1.0 - distance, 4),
                    })
            except Exception:
                continue

        duplicates.sort(key=lambda d: d["similarity"], reverse=True)
        result = duplicates[:limit]

        if result:
            logger.info(
                "workflow_deduplicator.duplicates_found count=%d top=%s sim=%.2f",
                len(result), result[0]["name"], result[0]["similarity"],
            )
        return result

    except ImportError:
        logger.warning("workflow_deduplicator: numpy not available — skipping deduplication")
        return []
    except Exception as exc:
        logger.warning("workflow_deduplicator.find_duplicates_failed error=%s", exc)
        return []
