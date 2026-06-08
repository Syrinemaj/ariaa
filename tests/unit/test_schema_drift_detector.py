"""
Unit tests — SchemaDriftDetector (Section 10.2).

Happy paths: no drift, non-breaking drift (optional field removed).
Unhappy paths: breaking drifts (required field removed, type changed,
               new required field, endpoint missing).
"""
from __future__ import annotations

import pytest

from app.models.endpoint import Endpoint
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
from app.workflows.schema_drift_detector import (
    SchemaDriftWarning,
    build_schema_snapshot,
    check_schema_drift,
)


def _make_plan(steps: list[PlanStep], snapshot: dict) -> AutomationPlan:
    return AutomationPlan(
        run_id="run-1",
        instruction="test",
        intent=BusinessIntent(
            instruction="test",
            intent="test",
            action="create",
            confidence=0.9,
        ),
        workflow_name="wf",
        steps=steps,
        metadata={"schema_snapshot": snapshot},
    )


def _make_step(key: str) -> PlanStep:
    return PlanStep(
        order=1,
        endpoint_id="ep-1",
        method="POST",
        path="/test",
        canonical_key=key,
    )


def _make_endpoint(key: str, metadata: dict) -> Endpoint:
    ep = Endpoint.__new__(Endpoint)
    ep.canonical_key = key
    ep.metadata_json = metadata
    return ep


# ── Happy paths ───────────────────────────────────────────────────────────────

class TestNoSnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot_returns_no_warnings(self):
        plan = _make_plan([_make_step("POST /users")], snapshot={})
        warnings = await check_schema_drift(plan, [])
        assert warnings == []


class TestNoDrift:
    @pytest.mark.asyncio
    async def test_identical_schemas_return_no_warnings(self):
        schema = {"fields": {"name": "str", "email": "str"}, "required": ["name"]}
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": schema})
        ep = _make_endpoint("ep1", schema)
        warnings = await check_schema_drift(plan, [ep])
        assert warnings == []


class TestNonBreakingDrift:
    @pytest.mark.asyncio
    async def test_optional_field_removed_is_non_breaking(self):
        old_schema = {
            "fields": {"name": "str", "nickname": "str"},
            "required": ["name"],
        }
        new_schema = {
            "fields": {"name": "str"},  # nickname removed (was optional)
            "required": ["name"],
        }
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": old_schema})
        ep = _make_endpoint("ep1", new_schema)
        warnings = await check_schema_drift(plan, [ep])
        assert len(warnings) == 1
        assert warnings[0].is_breaking is False
        assert warnings[0].drift_type == "field_removed"
        assert warnings[0].field_name == "nickname"


# ── Breaking drifts ───────────────────────────────────────────────────────────

class TestBreakingDrift:
    @pytest.mark.asyncio
    async def test_required_field_removed_is_breaking(self):
        old_schema = {
            "fields": {"name": "str", "email": "str"},
            "required": ["name", "email"],
        }
        new_schema = {"fields": {"name": "str"}, "required": ["name"]}
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": old_schema})
        ep = _make_endpoint("ep1", new_schema)
        warnings = await check_schema_drift(plan, [ep])
        breaking = [w for w in warnings if w.is_breaking]
        assert any(w.field_name == "email" for w in breaking)

    @pytest.mark.asyncio
    async def test_type_changed_is_breaking(self):
        old_schema = {"fields": {"age": "int"}, "required": []}
        new_schema = {"fields": {"age": "str"}, "required": []}
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": old_schema})
        ep = _make_endpoint("ep1", new_schema)
        warnings = await check_schema_drift(plan, [ep])
        assert any(
            w.drift_type == "type_changed" and w.field_name == "age"
            for w in warnings
        )
        assert all(w.is_breaking for w in warnings)

    @pytest.mark.asyncio
    async def test_new_required_field_is_breaking(self):
        old_schema = {"fields": {"name": "str"}, "required": ["name"]}
        new_schema = {
            "fields": {"name": "str", "org_id": "str"},
            "required": ["name", "org_id"],
        }
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": old_schema})
        ep = _make_endpoint("ep1", new_schema)
        warnings = await check_schema_drift(plan, [ep])
        new_req = [w for w in warnings if w.drift_type == "new_required_field"]
        assert any(w.field_name == "org_id" for w in new_req)
        assert all(w.is_breaking for w in new_req)

    @pytest.mark.asyncio
    async def test_endpoint_missing_entirely_is_breaking(self):
        old_schema = {"fields": {"name": "str"}, "required": ["name"]}
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": old_schema})
        warnings = await check_schema_drift(plan, [])  # no current endpoints
        assert len(warnings) == 1
        assert warnings[0].is_breaking is True
        assert warnings[0].field_name == "*"

    @pytest.mark.asyncio
    async def test_breaking_warnings_sorted_first(self):
        old_schema = {
            "fields": {"a": "str", "b": "str"},
            "required": ["a"],
        }
        new_schema = {"fields": {"b": "str"}, "required": []}
        plan = _make_plan([_make_step("ep1")], snapshot={"ep1": old_schema})
        ep = _make_endpoint("ep1", new_schema)
        warnings = await check_schema_drift(plan, [ep])
        assert warnings[0].is_breaking is True


# ── Snapshot builder ──────────────────────────────────────────────────────────

class TestBuildSnapshot:
    def test_snapshot_keys_match_canonical_keys(self):
        ep1 = _make_endpoint("POST /users", {"fields": {"name": "str"}, "required": []})
        ep2 = _make_endpoint("GET /users/{id}", {"fields": {"id": "int"}, "required": []})
        snapshot = build_schema_snapshot([ep1, ep2])
        assert "POST /users" in snapshot
        assert "GET /users/{id}" in snapshot

    def test_snapshot_stores_metadata_json(self):
        meta = {"fields": {"x": "int"}, "required": ["x"]}
        ep = _make_endpoint("ep1", meta)
        snapshot = build_schema_snapshot([ep])
        assert snapshot["ep1"] == meta
