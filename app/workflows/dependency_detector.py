from typing import List

from app.workflows.models import WorkflowStep


def detect_dependencies(steps: List[WorkflowStep]) -> List[WorkflowStep]:
    previous_mutating_key = None
    for step in steps:
        if step.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if previous_mutating_key:
                step.depends_on.append(previous_mutating_key)
            previous_mutating_key = step.canonical_key
    return steps
