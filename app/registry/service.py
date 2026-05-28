from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.endpoint import Endpoint
from app.models.workflow import WorkflowModel
from app.registry.repository import create_analysis_run, save_endpoint_schema_result, save_workflow
from app.schema_inference.models import EndpointSchemaResult
from app.workflows.models import Workflow


def save_registry_results(
    db: Session,
    file_name: str,
    cleaned_api_calls_count: int,
    normalized_endpoints_count: int,
    schema_results: List[EndpointSchemaResult],
    workflows: Optional[List[Workflow]] = None,
    # Legacy single-workflow kwarg kept for backward compatibility
    workflow: Optional[Workflow] = None,
    org_id: str = "",
    created_by_user_id: Optional[str] = None,
) -> Tuple[AnalysisRun, List[Endpoint], List[WorkflowModel]]:
    run = create_analysis_run(
        db=db,
        file_name=file_name,
        total_cleaned_api_calls=cleaned_api_calls_count,
        total_normalized_endpoints=normalized_endpoints_count,
        total_schema_results=len(schema_results),
        org_id=org_id,
        created_by_user_id=created_by_user_id,
    )

    saved_endpoints = []
    for result in schema_results:
        endpoint = save_endpoint_schema_result(db=db, run_id=run.id, result=result, org_id=org_id)
        saved_endpoints.append(endpoint)

    # Accept either the new list form or the legacy single-workflow kwarg
    workflow_list: List[Workflow] = workflows or ([workflow] if workflow else [])
    saved_workflows = [
        save_workflow(db=db, run_id=run.id, workflow=wf)
        for wf in workflow_list
    ]

    return run, saved_endpoints, saved_workflows
