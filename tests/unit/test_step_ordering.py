"""Tests for app/planner/step_ordering.py — schema-based dependency
detection + topological sort, used by both plan generation paths
(RAG-based instruction plans and workflow-to-plan conversion) so execution
order always respects real create-then-reference dependencies instead of
RAG relevance rank or raw workflow-detection order."""
import pytest

from app.planner.step_ordering import (
    DependencyCycleError,
    detect_schema_dependencies,
    topological_sort_steps,
)


class TestDetectSchemaDependencies:
    def test_reference_step_depends_on_creator(self):
        steps = [
            {"canonical_key": "GET /employees/{id}", "method": "GET",
             "path": "/employees/{id}", "response_schema": {"properties": {"id": {}}}},
            {"canonical_key": "POST /employees", "method": "POST",
             "path": "/employees", "response_schema": {"properties": {"id": {}}}},
        ]
        detect_schema_dependencies(steps)
        assert steps[0]["depends_on"] == ["POST /employees"]
        assert steps[1]["depends_on"] == []

    def test_ignores_get_and_delete_as_producers(self):
        # Only POST/PUT are treated as producers — a GET returning an "id"
        # field doesn't mean a later step "depends on" that GET.
        steps = [
            {"canonical_key": "GET /employees/{id}", "method": "GET",
             "path": "/employees/{id}", "response_schema": {"properties": {"id": {}}}},
            {"canonical_key": "DELETE /employees/{id}", "method": "DELETE",
             "path": "/employees/{id}", "response_schema": {}},
        ]
        detect_schema_dependencies(steps)
        assert steps[1]["depends_on"] == []

    def test_no_dependency_when_no_matching_param(self):
        steps = [
            {"canonical_key": "GET /products", "method": "GET",
             "path": "/products", "response_schema": {"properties": {}}},
            {"canonical_key": "POST /employees", "method": "POST",
             "path": "/employees", "response_schema": {"properties": {"id": {}}}},
        ]
        detect_schema_dependencies(steps)
        assert steps[0]["depends_on"] == []

    def test_first_producer_wins_for_duplicate_field_names(self):
        steps = [
            {"canonical_key": "POST /a", "method": "POST", "path": "/a",
             "response_schema": {"properties": {"id": {}}}},
            {"canonical_key": "POST /b", "method": "POST", "path": "/b",
             "response_schema": {"properties": {"id": {}}}},
            {"canonical_key": "GET /x/{id}", "method": "GET", "path": "/x/{id}",
             "response_schema": {}},
        ]
        detect_schema_dependencies(steps)
        assert steps[2]["depends_on"] == ["POST /a"]


class TestTopologicalSortSteps:
    def test_creator_moved_before_dependent_despite_worse_rag_rank(self):
        # Mirrors the real bug: RAG can rank a step higher than the step it
        # actually depends on, since ranking is by semantic relevance score,
        # not execution order.
        steps = [
            {"canonical_key": "GET /employees/{id}", "order": 1, "depends_on": ["POST /employees"]},
            {"canonical_key": "PATCH /employees/{id}", "order": 2, "depends_on": ["POST /employees"]},
            {"canonical_key": "POST /employees", "order": 3, "depends_on": []},
        ]
        result = topological_sort_steps(steps)
        assert [s["canonical_key"] for s in result][0] == "POST /employees"
        # order field is renumbered to reflect the new, dependency-safe sequence
        assert [s["order"] for s in result] == [1, 2, 3]

    def test_stable_for_independent_steps(self):
        steps = [
            {"canonical_key": "A", "order": 1, "depends_on": []},
            {"canonical_key": "B", "order": 2, "depends_on": []},
            {"canonical_key": "C", "order": 3, "depends_on": []},
        ]
        result = topological_sort_steps(steps)
        assert [s["canonical_key"] for s in result] == ["A", "B", "C"]

    def test_cycle_raises(self):
        steps = [
            {"canonical_key": "A", "order": 1, "depends_on": ["B"]},
            {"canonical_key": "B", "order": 2, "depends_on": ["A"]},
        ]
        with pytest.raises(DependencyCycleError):
            topological_sort_steps(steps)

    def test_dangling_reference_does_not_crash(self):
        steps = [{"canonical_key": "A", "order": 1, "depends_on": ["DOES_NOT_EXIST"]}]
        result = topological_sort_steps(steps)
        assert [s["canonical_key"] for s in result] == ["A"]

    def test_self_reference_does_not_crash(self):
        steps = [{"canonical_key": "A", "order": 1, "depends_on": ["A"]}]
        result = topological_sort_steps(steps)
        assert [s["canonical_key"] for s in result] == ["A"]


class TestValidateDependencies:
    def test_dangling_dependency_flagged_as_error(self):
        from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
        from app.planner.plan_validator import _validate_dependencies

        plan = AutomationPlan(
            run_id="test-run",
            instruction="test",
            intent=BusinessIntent(instruction="test", intent="test", action="create", confidence=0.9),
            workflow_name="test",
            steps=[
                PlanStep(order=1, endpoint_id="ep1", method="GET", path="/x",
                         canonical_key="GET /x", depends_on=["GET /does-not-exist"]),
            ],
        )
        issues = _validate_dependencies(plan)
        assert any(i.level == "error" and "not part of this plan" in i.message for i in issues)

    def test_valid_dependency_produces_no_issues(self):
        from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
        from app.planner.plan_validator import _validate_dependencies

        plan = AutomationPlan(
            run_id="test-run",
            instruction="test",
            intent=BusinessIntent(instruction="test", intent="test", action="create", confidence=0.9),
            workflow_name="test",
            steps=[
                PlanStep(order=1, endpoint_id="ep1", method="POST", path="/employees",
                         canonical_key="POST /employees", depends_on=[]),
                PlanStep(order=2, endpoint_id="ep2", method="GET", path="/employees/{id}",
                         canonical_key="GET /employees/{id}", depends_on=["POST /employees"]),
            ],
        )
        issues = _validate_dependencies(plan)
        assert issues == []
