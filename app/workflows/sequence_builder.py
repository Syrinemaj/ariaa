from typing import List

from app.normalization.models import NormalizedEndpoint
from app.workflows.models import WorkflowStep


def build_sequence(endpoints: List[NormalizedEndpoint]) -> List[WorkflowStep]:
    steps: List[WorkflowStep] = []
    for index, endpoint in enumerate(endpoints):
        steps.append(WorkflowStep(
            order=index + 1,
            method=endpoint.method,
            path=endpoint.normalized_path,
            canonical_key=endpoint.canonical_key,
            action=endpoint.metadata.get("business_action"),
            status=endpoint.status,
            metadata={
                "business_domain": endpoint.metadata.get("business_domain"),
                "source_count": endpoint.source_count,
                "original_path": endpoint.original_path,
            },
        ))
    return steps
