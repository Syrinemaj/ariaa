from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.analysis_run import AnalysisRun
from app.models.endpoint import Endpoint
from app.models.user import User
from app.models.workflow import WorkflowModel, WorkflowStepModel

router = APIRouter(prefix="/registry", tags=["Registry"])


@router.get("/runs")
async def list_runs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    stmt = (
        select(AnalysisRun)
        .where(AnalysisRun.org_id == current_user.org_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    if status:
        stmt = stmt.where(AnalysisRun.status == status)

    total_result = await db.execute(select(AnalysisRun).where(
        AnalysisRun.org_id == current_user.org_id,
        *(([AnalysisRun.status == status]) if status else []),
    ))
    runs_all = total_result.scalars().all()
    total = len(runs_all)

    result = await db.execute(stmt.offset(offset).limit(limit))
    runs = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "file_name": r.file_name,
                "status": r.status,
                "total_cleaned_api_calls": r.total_cleaned_api_calls,
                "total_normalized_endpoints": r.total_normalized_endpoints,
                "total_schema_results": r.total_schema_results,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ],
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    return {
        "id": run.id,
        "file_name": run.file_name,
        "status": run.status,
        "total_cleaned_api_calls": run.total_cleaned_api_calls,
        "total_normalized_endpoints": run.total_normalized_endpoints,
        "total_schema_results": run.total_schema_results,
        "created_at": run.created_at.isoformat(),
    }


@router.get("/runs/{run_id}/endpoints")
async def list_endpoints(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run_result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    if not run_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis run not found")

    from sqlalchemy.orm import selectinload
    ep_result = await db.execute(
        select(Endpoint)
        .options(selectinload(Endpoint.schema))
        .where(Endpoint.run_id == run_id)
    )
    endpoints = ep_result.scalars().all()

    result = []
    for e in endpoints:
        schema = e.schema
        result.append({
            "id": e.id,
            "method": e.method,
            "path": e.path,
            "canonical_key": e.canonical_key,
            "business_domain": e.business_domain,
            "business_action": e.business_action,
            "source_count": e.source_count,
            "metadata": e.metadata_json or {},
            "auth_required": schema.auth_required if schema else None,
            "auth_type": schema.auth_type if schema else None,
            "status_codes": schema.status_codes if schema else [],
            "risk": (e.metadata_json or {}).get("risk", "low"),
            "confidence": (e.metadata_json or {}).get("confidence", 0.0),
            "tags": (e.metadata_json or {}).get("tags", []),
            "ai_summary": (e.metadata_json or {}).get("ai_summary"),
            "ai_description": (e.metadata_json or {}).get("ai_description"),
            "ai_tags": (e.metadata_json or {}).get("ai_tags", []),
            "ai_confidence": (e.metadata_json or {}).get("ai_confidence"),
        })

    return {"run_id": run_id, "total": len(result), "endpoints": result}


@router.get("/runs/{run_id}/workflows")
async def list_workflows(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run_result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    if not run_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis run not found")

    from sqlalchemy.orm import selectinload
    wf_result = await db.execute(
        select(WorkflowModel)
        .options(selectinload(WorkflowModel.steps))
        .where(WorkflowModel.run_id == run_id)
    )
    workflows = wf_result.scalars().all()

    result = []
    for wf in workflows:
        steps = sorted(wf.steps, key=lambda s: s.step_order)
        result.append({
            "id": wf.id,
            "name": wf.name,
            "business_domain": wf.business_domain,
            "confidence": wf.confidence,
            "metadata": wf.metadata_json or {},
            "steps": [
                {
                    "order": s.step_order,
                    "method": s.method,
                    "path": s.path,
                    "canonical": s.canonical_key,
                    "action": s.action,
                    "depends": s.depends_on or [],
                    "risk": (s.metadata_json or {}).get("risk", "low"),
                    "auth": (s.metadata_json or {}).get("auth_required", True),
                }
                for s in steps
            ],
        })

    return {"run_id": run_id, "total": len(result), "workflows": result}
