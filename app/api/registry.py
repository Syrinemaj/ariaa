from typing import Dict, List, Literal, Optional, Set
from uuid import uuid4

from sqlalchemy.orm import attributes as sa_attributes

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.analysis_run import AnalysisRun
from app.models.endpoint import Endpoint
from app.models.user import User
from app.models.workflow import WorkflowModel, WorkflowStepModel

router = APIRouter(prefix="/registry", tags=["Registry"])


# ── Request bodies ────────────────────────────────────────────────────────────

class RunUpdateIn(BaseModel):
    file_name: Optional[str] = None


class WorkflowStepIn(BaseModel):
    order: int
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]  # [B3]
    path: str
    canonical_key: str
    action: Optional[str] = None
    risk: str = "low"
    auth: bool = True


class WorkflowUpdateIn(BaseModel):
    name: Optional[str] = None
    business_domain: Optional[str] = None
    steps: Optional[List[WorkflowStepIn]] = Field(default=None, max_length=50)  # [B2]


class WorkflowCreateIn(BaseModel):
    name: str
    business_domain: Optional[str] = None
    steps: List[WorkflowStepIn] = Field(default=[], max_length=50)  # [B2]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_workflow(wf: WorkflowModel) -> dict:
    steps = sorted(wf.steps, key=lambda s: s.step_order)
    return {
        "id": wf.id,
        "name": wf.name,
        "business_domain": wf.business_domain,
        "confidence": wf.confidence,
        "metadata": wf.metadata_json or {},
        "steps": [
            {
                "order":    s.step_order,
                "method":   s.method,
                "path":     s.path,
                "canonical": s.canonical_key,
                "action":   s.action,
                "depends":  s.depends_on or [],
                "risk":     (s.metadata_json or {}).get("risk", "low"),
                "auth":     (s.metadata_json or {}).get("auth_required", True),
            }
            for s in steps
        ],
    }


async def _validate_canonical_keys(  # [B1]
    db: AsyncSession,
    run_id: str,
    canonical_keys: List[str],
) -> None:
    """Raise 422 if any canonical_key doesn't belong to the given run."""
    if not canonical_keys:
        return
    result = await db.execute(
        select(Endpoint.canonical_key).where(
            Endpoint.run_id == run_id,
            Endpoint.canonical_key.in_(canonical_keys),
        )
    )
    found: Set[str] = {row[0] for row in result.all()}
    unknown = sorted(set(canonical_keys) - found)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown canonical_keys for this run: {unknown}",
        )


def _compute_depends_on(steps: List[WorkflowStepModel]) -> Dict[str, List[str]]:  # [B5]
    """
    Replicate dag_builder dependency detection logic for persisted step models.
    Returns {canonical_key: [dependency_canonical_key, ...]} for every step.
    """
    creator_map: Dict[str, str] = {}
    for s in steps:
        if s.method in {"POST", "PUT"}:
            segments = [seg for seg in s.path.split("/") if seg]
            resource = next(
                (seg for seg in reversed(segments) if not seg.startswith("{")), None
            )
            if resource:
                creator_map[resource] = s.canonical_key

    deps: Dict[str, List[str]] = {s.canonical_key: [] for s in steps}
    for s in steps:
        segments = [seg for seg in s.path.split("/") if seg]
        for i, seg in enumerate(segments):
            if seg.startswith("{") and seg.endswith("}") and i > 0:
                resource = segments[i - 1]
                creator_id = creator_map.get(resource)
                if creator_id and creator_id != s.canonical_key:
                    deps[s.canonical_key].append(creator_id)
    return deps


# ── Run routes ────────────────────────────────────────────────────────────────

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
    if current_user.role != "ADMIN":
        stmt = stmt.where(AnalysisRun.created_by_user_id == current_user.id)

    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(AnalysisRun).where(
        AnalysisRun.org_id == current_user.org_id
    )
    if status:
        count_stmt = count_stmt.where(AnalysisRun.status == status)
    if current_user.role != "ADMIN":
        count_stmt = count_stmt.where(AnalysisRun.created_by_user_id == current_user.id)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

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
                "created_by_user_id": r.created_by_user_id,
            }
            for r in runs
        ],
    }


@router.patch("/runs/{run_id}")
async def update_run(
    run_id: str,
    body: RunUpdateIn,
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
    if current_user.role != "ADMIN" and run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres analyses")
    if body.file_name is not None:
        run.file_name = body.file_name.strip() or run.file_name
    await db.commit()
    return {"id": run.id, "file_name": run.file_name}


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
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
    if current_user.role != "ADMIN" and run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos propres analyses")
    await db.delete(run)
    await db.commit()


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


# ── Workflow routes ───────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/workflows")
async def list_workflows(
    run_id: str,
    limit: int = Query(default=50, le=200),  # [B7]
    offset: int = Query(default=0),           # [B7]
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

    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    total_result = await db.execute(
        select(func.count()).select_from(WorkflowModel).where(WorkflowModel.run_id == run_id)
    )
    total = total_result.scalar_one()

    wf_result = await db.execute(
        select(WorkflowModel)
        .options(selectinload(WorkflowModel.steps))
        .where(WorkflowModel.run_id == run_id)
        .offset(offset)
        .limit(limit)
    )
    workflows = wf_result.scalars().all()

    return {
        "run_id": run_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "workflows": [_serialize_workflow(wf) for wf in workflows],
    }


@router.post("/runs/{run_id}/workflows")
async def create_workflow(
    run_id: str,
    body: WorkflowCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run_res = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    if not run_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Run not found")

    # [B1] Validate canonical_keys belong to this run
    if body.steps:
        await _validate_canonical_keys(db, run_id, [s.canonical_key for s in body.steps])

    wf = WorkflowModel(
        id=str(uuid4()),
        run_id=run_id,
        name=body.name,
        business_domain=body.business_domain,
        confidence=1.0,
        metadata_json={"created_by": "user"},
    )
    db.add(wf)
    await db.flush()

    step_models: List[WorkflowStepModel] = []
    for s in body.steps:
        step_model = WorkflowStepModel(
            id=str(uuid4()),
            workflow_id=wf.id,
            step_order=s.order,
            method=s.method,
            path=s.path,
            canonical_key=s.canonical_key,
            action=s.action,
            depends_on=[],
            metadata_json={"risk": s.risk, "auth_required": s.auth},
        )
        db.add(step_model)
        step_models.append(step_model)

    await db.flush()

    # [B5] Compute and apply depends_on for new steps
    if step_models:
        deps = _compute_depends_on(step_models)
        for step_model in step_models:
            step_model.depends_on = deps.get(step_model.canonical_key, [])

    await db.commit()

    # [B8] Audit log
    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.WORKFLOW_CREATED,
        resource_type="workflow",
        resource_id=wf.id,
        metadata={"name": wf.name, "run_id": run_id, "steps_count": len(step_models)},
    )
    await db.commit()

    # [B12] Single SELECT with selectinload (removed the redundant one)
    from sqlalchemy.orm import selectinload
    res = await db.execute(
        select(WorkflowModel)
        .options(selectinload(WorkflowModel.steps))
        .where(WorkflowModel.id == wf.id)
    )
    return _serialize_workflow(res.scalar_one())


@router.patch("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    from sqlalchemy.orm import selectinload

    # BUG-007 IDOR: join AnalysisRun to verify workflow belongs to the caller's org
    res = await db.execute(
        select(WorkflowModel)
        .join(AnalysisRun, AnalysisRun.id == WorkflowModel.run_id)
        .options(selectinload(WorkflowModel.steps))
        .where(
            WorkflowModel.id == workflow_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    wf = res.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # [B1] Validate canonical_keys belong to this run
    if body.steps is not None:
        await _validate_canonical_keys(
            db, wf.run_id, [s.canonical_key for s in body.steps]
        )

    # Snapshot original state on first edit (before any change)
    existing_meta = dict(wf.metadata_json or {})
    if "_original" not in existing_meta and existing_meta.get("created_by") != "user":
        existing_meta["_original"] = {
            "name":            wf.name,
            "business_domain": wf.business_domain,
            "steps": [
                {
                    "order":         s.step_order,
                    "method":        s.method,
                    "path":          s.path,
                    "canonical_key": s.canonical_key,
                    "action":        s.action,
                    "risk":          (s.metadata_json or {}).get("risk", "low"),
                    "auth":          (s.metadata_json or {}).get("auth_required", True),
                }
                for s in sorted(wf.steps, key=lambda x: x.step_order)
            ],
        }
        wf.metadata_json = existing_meta
        sa_attributes.flag_modified(wf, "metadata_json")

    if body.name is not None:
        wf.name = body.name
    if body.business_domain is not None:
        wf.business_domain = body.business_domain

    if body.steps is not None:
        # [B11] Diff partial steps instead of delete+recreate
        existing_by_canonical = {s.canonical_key: s for s in wf.steps}
        new_canonicals = {s.canonical_key for s in body.steps}

        # Delete steps no longer present
        for canonical, step_model in existing_by_canonical.items():
            if canonical not in new_canonicals:
                await db.delete(step_model)

        # Update existing or create new
        active_steps: List[WorkflowStepModel] = []
        for s in body.steps:
            if s.canonical_key in existing_by_canonical:
                step_model = existing_by_canonical[s.canonical_key]
                step_model.step_order = s.order
                step_model.method = s.method
                step_model.path = s.path
                step_model.action = s.action
                step_model.metadata_json = {"risk": s.risk, "auth_required": s.auth}
            else:
                step_model = WorkflowStepModel(
                    id=str(uuid4()),
                    workflow_id=wf.id,
                    step_order=s.order,
                    method=s.method,
                    path=s.path,
                    canonical_key=s.canonical_key,
                    action=s.action,
                    depends_on=[],
                    metadata_json={"risk": s.risk, "auth_required": s.auth},
                )
                db.add(step_model)
            active_steps.append(step_model)

        await db.flush()

        # [B5] Recompute depends_on after any step change
        deps = _compute_depends_on(active_steps)
        for step_model in active_steps:
            step_model.depends_on = deps.get(step_model.canonical_key, [])

    await db.commit()

    # [B8] Audit log
    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.WORKFLOW_UPDATED,
        resource_type="workflow",
        resource_id=workflow_id,
        metadata={"name": wf.name},
    )
    await db.commit()

    res2 = await db.execute(
        select(WorkflowModel)
        .options(selectinload(WorkflowModel.steps))
        .where(WorkflowModel.id == workflow_id)
    )
    return _serialize_workflow(res2.scalar_one())


@router.post("/workflows/{workflow_id}/restore")
async def restore_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    from sqlalchemy.orm import selectinload

    # BUG-007 IDOR: join AnalysisRun to verify workflow belongs to the caller's org
    res = await db.execute(
        select(WorkflowModel)
        .join(AnalysisRun, AnalysisRun.id == WorkflowModel.run_id)
        .options(selectinload(WorkflowModel.steps))
        .where(
            WorkflowModel.id == workflow_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    wf = res.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    original = (wf.metadata_json or {}).get("_original")
    if not original:
        raise HTTPException(status_code=400, detail="Aucune version originale disponible pour ce workflow")

    wf.name            = original["name"]
    wf.business_domain = original.get("business_domain")

    # Clear _original snapshot — workflow is back to AI state, badge shows "IA"
    # Rebuild as a new dict (JSONB without MutableDict needs explicit flag_modified)
    wf.metadata_json = {k: v for k, v in (wf.metadata_json or {}).items() if k != "_original"}
    sa_attributes.flag_modified(wf, "metadata_json")

    for s in wf.steps:
        await db.delete(s)
    await db.flush()

    restored_steps: List[WorkflowStepModel] = []
    for s in original.get("steps", []):
        step_model = WorkflowStepModel(
            id=str(uuid4()),
            workflow_id=wf.id,
            step_order=s["order"],
            method=s["method"],
            path=s["path"],
            canonical_key=s["canonical_key"],
            action=s.get("action"),
            depends_on=[],
            metadata_json={"risk": s.get("risk", "low"), "auth_required": s.get("auth", True)},
        )
        db.add(step_model)
        restored_steps.append(step_model)

    await db.flush()

    # [B5] Recompute depends_on after restore
    if restored_steps:
        deps = _compute_depends_on(restored_steps)
        for step_model in restored_steps:
            step_model.depends_on = deps.get(step_model.canonical_key, [])

    await db.commit()

    # [B8] Audit log
    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.WORKFLOW_RESTORED,
        resource_type="workflow",
        resource_id=workflow_id,
        metadata={"name": wf.name},
    )
    await db.commit()

    res2 = await db.execute(
        select(WorkflowModel)
        .options(selectinload(WorkflowModel.steps))
        .where(WorkflowModel.id == workflow_id)
    )
    return _serialize_workflow(res2.scalar_one())


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007 IDOR: verify workflow belongs to the caller's org before deleting
    res = await db.execute(
        select(WorkflowModel)
        .join(AnalysisRun, AnalysisRun.id == WorkflowModel.run_id)
        .where(
            WorkflowModel.id == workflow_id,
            AnalysisRun.org_id == current_user.org_id,
        )
    )
    wf = res.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    wf_name = wf.name

    # [B8] Audit log before deletion
    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.WORKFLOW_DELETED,
        resource_type="workflow",
        resource_id=workflow_id,
        metadata={"name": wf_name},
    )

    await db.delete(wf)
    await db.commit()
