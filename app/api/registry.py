from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.analysis_run import AnalysisRun
from app.models.endpoint import Endpoint
from app.models.user import User
from app.models.workflow import WorkflowModel, WorkflowStepModel

router = APIRouter(prefix="/registry", tags=["Registry"])


@router.get("/runs")
def list_runs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    query = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.org_id == current_user.org_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    if status:
        query = query.filter(AnalysisRun.status == status)

    total = query.count()
    runs = query.offset(offset).limit(limit).all()

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
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id, AnalysisRun.org_id == current_user.org_id)
        .first()
    )
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
def list_endpoints(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id, AnalysisRun.org_id == current_user.org_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    endpoints = (
        db.query(Endpoint)
        .filter(Endpoint.run_id == run_id)
        .all()
    )

    result = []
    for e in endpoints:
        schema = e.schema if hasattr(e, "schema") and e.schema else None
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
        })

    return {"run_id": run_id, "total": len(result), "endpoints": result}


@router.get("/runs/{run_id}/workflows")
def list_workflows(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id, AnalysisRun.org_id == current_user.org_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    workflows = (
        db.query(WorkflowModel)
        .filter(WorkflowModel.run_id == run_id)
        .all()
    )

    result = []
    for wf in workflows:
        steps = (
            db.query(WorkflowStepModel)
            .filter(WorkflowStepModel.workflow_id == wf.id)
            .order_by(WorkflowStepModel.step_order)
            .all()
        )
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
