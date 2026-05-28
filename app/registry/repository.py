"""
Registry repository — async SQLAlchemy.

Pattern de migration vers async :
  AVANT : db.query(Model).filter(...).first()
  APRÈS : result = await db.execute(select(Model).where(...))
          obj = result.scalar_one_or_none()

  AVANT : db.add(obj); db.commit(); db.refresh(obj)
  APRÈS : db.add(obj); await db.flush(); await db.refresh(obj)
          # Le commit est géré par get_db() (auto-commit en fin de route)
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_run import AnalysisRun
from app.models.endpoint import Endpoint
from app.models.schema import EndpointSchema
from app.models.workflow import WorkflowModel, WorkflowStepModel
from app.normalization.canonicalizer import build_registry_key
from app.schema_inference.models import EndpointSchemaResult
from app.workflows.models import Workflow


async def create_analysis_run(
    db: AsyncSession,
    file_name: str,
    total_cleaned_api_calls: int,
    total_normalized_endpoints: int,
    total_schema_results: int,
    org_id: str = "",
    created_by_user_id: Optional[str] = None,
) -> AnalysisRun:
    run = AnalysisRun(
        file_name=file_name,
        total_cleaned_api_calls=total_cleaned_api_calls,
        total_normalized_endpoints=total_normalized_endpoints,
        total_schema_results=total_schema_results,
        org_id=org_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def save_endpoint_schema_result(
    db: AsyncSession,
    run_id: str,
    result: EndpointSchemaResult,
    org_id: str = "",
) -> Endpoint:
    endpoint = Endpoint(
        run_id=run_id,
        method=result.method,
        path=result.path,
        canonical_key=build_registry_key(org_id, result.method, result.path),
        source_count=result.examples_count,
        business_domain=result.metadata.get("business_domain"),
        business_action=result.metadata.get("business_action"),
        path_parameters={},
        metadata_json=result.metadata,
        org_id=org_id,
    )
    db.add(endpoint)
    await db.flush()

    schema = EndpointSchema(
        endpoint_id=endpoint.id,
        request_schema=result.request_schema.model_dump() if result.request_schema else None,
        response_schema=result.response_schema.model_dump() if result.response_schema else None,
        status_codes=result.status_codes,
        auth_required=result.auth.auth_required,
        auth_type=result.auth.auth_type,
        auth_location=result.auth.location,
        auth_header_name=result.auth.header_name,
        auth_confidence=result.auth.confidence,
        org_id=org_id,
    )
    db.add(schema)
    await db.flush()
    await db.refresh(endpoint)
    return endpoint


async def save_workflow(
    db: AsyncSession,
    run_id: str,
    workflow: Workflow,
) -> WorkflowModel:
    workflow_model = WorkflowModel(
        run_id=run_id,
        name=workflow.name,
        business_domain=workflow.business_domain,
        confidence=workflow.confidence,
        metadata_json=workflow.metadata,
    )
    db.add(workflow_model)
    await db.flush()

    for step in workflow.steps:
        step_model = WorkflowStepModel(
            workflow_id=workflow_model.id,
            step_order=step.order,
            method=step.method,
            path=step.path,
            canonical_key=step.canonical_key,
            action=step.action,
            depends_on=step.depends_on,
            metadata_json=step.metadata,
        )
        db.add(step_model)

    await db.flush()
    await db.refresh(workflow_model)
    return workflow_model


async def get_run_by_id(db: AsyncSession, run_id: str) -> Optional[AnalysisRun]:
    result = await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))
    return result.scalar_one_or_none()


async def get_endpoints_by_run_id(db: AsyncSession, run_id: str) -> list[Endpoint]:
    result = await db.execute(
        select(Endpoint).where(Endpoint.run_id == run_id)
    )
    return list(result.scalars().all())
