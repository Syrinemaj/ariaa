"""
WorkflowDAG — models workflow steps as a directed acyclic graph.

Replaces the linear sequence_builder. Independent steps are grouped into
parallel execution batches; each batch runs via asyncio.gather in dag_executor.
Kahn's algorithm guarantees correctness and detects cycles early.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Set

from app.normalization.models import NormalizedEndpoint
from app.workflows.models import WorkflowStep


@dataclass
class WorkflowNode:
    endpoint_id: str
    endpoint: NormalizedEndpoint
    dependencies: Set[str] = field(default_factory=set)


class WorkflowDAG:
    """Directed acyclic graph of API workflow steps."""

    def __init__(self) -> None:
        self._nodes: Dict[str, WorkflowNode] = {}

    def add_node(self, node: WorkflowNode) -> None:
        """Register a node in the DAG."""
        self._nodes[node.endpoint_id] = node

    def add_dependency(self, node_id: str, depends_on_id: str) -> None:
        """Declare that node_id must execute after depends_on_id."""
        if node_id in self._nodes:
            self._nodes[node_id].dependencies.add(depends_on_id)

    def detect_dependencies(self, endpoints: List[NormalizedEndpoint]) -> None:
        """
        Auto-detect data dependencies between endpoints.

        Rule: endpoint B depends on endpoint A when:
        - A is POST/PUT (creates a resource)
        - B's path contains {resource_id} where the preceding segment matches
          A's last non-param segment (e.g. POST /users → GET /users/{user_id}/*)

        Only intra-graph dependencies are registered (nodes must be in the DAG).
        """
        creator_map: Dict[str, str] = {}
        for ep in endpoints:
            if ep.method in {"POST", "PUT"}:
                segments = [s for s in ep.normalized_path.split("/") if s]
                resource = next(
                    (s for s in reversed(segments) if not s.startswith("{")),
                    None,
                )
                if resource:
                    creator_map[resource] = ep.canonical_key

        for ep in endpoints:
            segments = [s for s in ep.normalized_path.split("/") if s]
            for i, seg in enumerate(segments):
                if seg.startswith("{") and seg.endswith("}") and i > 0:
                    resource = segments[i - 1]
                    creator_id = creator_map.get(resource)
                    if creator_id and creator_id != ep.canonical_key:
                        self.add_dependency(ep.canonical_key, creator_id)

    def topological_sort(self) -> List[List[str]]:
        """
        Return parallel execution groups (Kahn's algorithm).

        Each inner list contains node IDs with no pending dependencies —
        they can all execute concurrently.

        Example:
            [
                ["POST /employees"],
                ["POST .../departments", "POST .../roles"],
                ["POST .../benefits"],
            ]

        Raises ValueError on cycle detection.
        """
        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        dependents: Dict[str, List[str]] = {nid: [] for nid in self._nodes}

        for node_id, node in self._nodes.items():
            for dep_id in node.dependencies:
                if dep_id in self._nodes:
                    in_degree[node_id] += 1
                    dependents[dep_id].append(node_id)

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        groups: List[List[str]] = []
        visited = 0

        while queue:
            current_group = list(queue)
            queue.clear()
            groups.append(current_group)
            visited += len(current_group)

            for node_id in current_group:
                for dependent_id in dependents[node_id]:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

        if visited != len(self._nodes):
            raise ValueError(
                "WorkflowDAG contains a cycle — topological sort is impossible."
            )

        return groups

    @classmethod
    def from_endpoints(cls, endpoints: List[NormalizedEndpoint]) -> "WorkflowDAG":
        """Build a DAG from normalized endpoints with auto-detected dependencies."""
        dag = cls()
        for ep in endpoints:
            dag.add_node(WorkflowNode(endpoint_id=ep.canonical_key, endpoint=ep))
        dag.detect_dependencies(endpoints)
        return dag

    def to_workflow_steps(self) -> List[WorkflowStep]:
        """
        Flatten DAG into WorkflowStep objects preserving parallel group info.

        Steps in the same parallel group share the same `order` value.
        `parallel_group` is stored in metadata for the executor.
        """
        groups = self.topological_sort()
        steps: List[WorkflowStep] = []

        for group_index, group in enumerate(groups):
            for node_id in sorted(group):  # deterministic ordering within group
                node = self._nodes[node_id]
                ep = node.endpoint
                steps.append(WorkflowStep(
                    order=group_index + 1,
                    method=ep.method,
                    path=ep.normalized_path,
                    canonical_key=ep.canonical_key,
                    action=ep.metadata.get("business_action"),
                    status=ep.status,
                    depends_on=sorted(node.dependencies),
                    metadata={
                        "business_domain": ep.metadata.get("business_domain"),
                        "source_count": ep.source_count,
                        "original_path": ep.original_path,
                        "parallel_group": group_index,
                    },
                ))

        return steps
