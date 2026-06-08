"""
Unit tests — WorkflowDAG (Section 10.1).

Happy paths: no deps, linear chain, parallel groups.
Unhappy paths: cycle detection, missing node reference.
"""
from __future__ import annotations

import pytest

from app.normalization.models import NormalizedEndpoint
from app.workflows.dag_builder import WorkflowDAG, WorkflowNode


def _make_ep(canonical_key: str, method: str = "GET", path: str = "/x") -> NormalizedEndpoint:
    return NormalizedEndpoint(
        method=method,
        original_url=f"https://api.example.com{path}",
        original_path=path,
        normalized_path=path,
        canonical_key=canonical_key,
        status=200,
    )


# ── Topology ──────────────────────────────────────────────────────────────────

class TestTopologicalSort:
    def test_single_node_yields_one_group(self):
        dag = WorkflowDAG()
        dag.add_node(WorkflowNode("A", _make_ep("A")))
        groups = dag.topological_sort()
        assert groups == [["A"]]

    def test_independent_nodes_form_one_parallel_group(self):
        dag = WorkflowDAG()
        for key in ["A", "B", "C"]:
            dag.add_node(WorkflowNode(key, _make_ep(key)))
        groups = dag.topological_sort()
        assert len(groups) == 1
        assert sorted(groups[0]) == ["A", "B", "C"]

    def test_linear_chain_yields_sequential_groups(self):
        dag = WorkflowDAG()
        for key in ["A", "B", "C"]:
            dag.add_node(WorkflowNode(key, _make_ep(key)))
        dag.add_dependency("B", "A")
        dag.add_dependency("C", "B")
        groups = dag.topological_sort()
        assert len(groups) == 3
        assert groups[0] == ["A"]
        assert groups[1] == ["B"]
        assert groups[2] == ["C"]

    def test_diamond_dependency(self):
        """A → [B, C] → D should produce three groups."""
        dag = WorkflowDAG()
        for key in ["A", "B", "C", "D"]:
            dag.add_node(WorkflowNode(key, _make_ep(key)))
        dag.add_dependency("B", "A")
        dag.add_dependency("C", "A")
        dag.add_dependency("D", "B")
        dag.add_dependency("D", "C")
        groups = dag.topological_sort()
        assert len(groups) == 3
        assert groups[0] == ["A"]
        assert sorted(groups[1]) == ["B", "C"]
        assert groups[2] == ["D"]

    def test_cycle_raises_value_error(self):
        dag = WorkflowDAG()
        dag.add_node(WorkflowNode("A", _make_ep("A")))
        dag.add_node(WorkflowNode("B", _make_ep("B")))
        dag.add_dependency("A", "B")
        dag.add_dependency("B", "A")
        with pytest.raises(ValueError, match="cycle"):
            dag.topological_sort()

    def test_dependency_to_unknown_node_is_ignored(self):
        """External dependency not in the DAG must not crash."""
        dag = WorkflowDAG()
        dag.add_node(WorkflowNode("A", _make_ep("A")))
        dag.add_dependency("A", "NONEXISTENT")
        groups = dag.topological_sort()
        # The missing dep is not tracked → A still has in_degree 0
        assert groups == [["A"]]


# ── Dependency detection ──────────────────────────────────────────────────────

class TestDetectDependencies:
    def test_post_then_get_with_param_creates_dependency(self):
        ep_post = _make_ep("post_users", "POST", "/users")
        ep_get = _make_ep("get_user", "GET", "/users/{user_id}")
        dag = WorkflowDAG.from_endpoints([ep_post, ep_get])
        node_get = dag._nodes["get_user"]
        assert "post_users" in node_get.dependencies

    def test_independent_endpoints_have_no_deps(self):
        ep1 = _make_ep("a", "GET", "/products")
        ep2 = _make_ep("b", "GET", "/orders")
        dag = WorkflowDAG.from_endpoints([ep1, ep2])
        assert not dag._nodes["a"].dependencies
        assert not dag._nodes["b"].dependencies


# ── Workflow step conversion ───────────────────────────────────────────────────

class TestToWorkflowSteps:
    def test_parallel_group_same_order(self):
        dag = WorkflowDAG()
        for key in ["A", "B"]:
            dag.add_node(WorkflowNode(key, _make_ep(key)))
        steps = dag.to_workflow_steps()
        orders = [s.order for s in steps]
        assert orders[0] == orders[1] == 1

    def test_sequential_steps_increment_order(self):
        dag = WorkflowDAG()
        for key in ["A", "B"]:
            dag.add_node(WorkflowNode(key, _make_ep(key)))
        dag.add_dependency("B", "A")
        steps = dag.to_workflow_steps()
        step_a = next(s for s in steps if s.canonical_key == "A")
        step_b = next(s for s in steps if s.canonical_key == "B")
        assert step_a.order == 1
        assert step_b.order == 2

    def test_depends_on_populated(self):
        dag = WorkflowDAG()
        for key in ["A", "B"]:
            dag.add_node(WorkflowNode(key, _make_ep(key)))
        dag.add_dependency("B", "A")
        steps = dag.to_workflow_steps()
        step_b = next(s for s in steps if s.canonical_key == "B")
        assert "A" in step_b.depends_on
