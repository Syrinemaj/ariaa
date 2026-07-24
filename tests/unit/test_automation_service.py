"""Regression test — real auth headers / row data must reach execute_plan_batch
unmodified. sanitize_payload() masks sensitive-looking fields (auth, tokens,
passwords) and is meant for persisted audit logs only; feeding its output into
the actual outbound call breaks auth and corrupts business data."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.automation.models import AutomationExecutionRequest, AutomationExecutionResult
from app.automation.service import execute_automation
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep


def _make_db() -> MagicMock:
    # execute_automation() takes an AsyncSession — commit/refresh must be awaitable.
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_plan() -> AutomationPlan:
    return AutomationPlan(
        run_id="run-1",
        instruction="list users",
        intent=BusinessIntent(instruction="list users", intent="read", action="list"),
        workflow_name="wf",
        steps=[
            PlanStep(
                order=0,
                endpoint_id="ep-1",
                method="GET",
                path="/users",
                canonical_key="GET /users",
            )
        ],
        requires_approval=False,
    )


class TestExecuteAutomationDoesNotSanitizeBeforeDispatch:
    @pytest.mark.asyncio
    async def test_real_auth_headers_and_rows_reach_execute_plan_batch(self, monkeypatch):
        captured = {}

        async def fake_execute_plan_batch(plan, input_rows, base_url=None, auth_headers=None, dry_run=True):
            captured["input_rows"] = input_rows
            captured["auth_headers"] = auth_headers
            return AutomationExecutionResult(
                status="completed",
                dry_run=dry_run,
                total_steps=1,
                success_count=1,
                failed_count=0,
                results=[],
            )

        monkeypatch.setattr("app.automation.service.execute_plan_batch", fake_execute_plan_batch)

        request = AutomationExecutionRequest(
            plan=_make_plan(),
            input_rows=[{"email": "a@b.com", "password": "hunter2"}],
            base_url="https://api.example.com",
            auth_headers={"Authorization": "Bearer real-token-123"},
            dry_run=True,
        )

        await execute_automation(
            db=_make_db(), request=request, approval_granted=True, org_id="org-1"
        )

        assert captured["auth_headers"] == {"Authorization": "Bearer real-token-123"}
        assert captured["input_rows"] == [{"email": "a@b.com", "password": "hunter2"}]
        assert "***MASKED***" not in str(captured["auth_headers"])
        assert "***MASKED***" not in str(captured["input_rows"])

    @pytest.mark.asyncio
    async def test_persisted_step_logs_are_still_sanitized(self, monkeypatch):
        # The masking must still happen somewhere — just not before dispatch.
        async def fake_execute_plan_batch(plan, input_rows, base_url=None, auth_headers=None, dry_run=True):
            from app.automation.models import StepExecutionResult

            return AutomationExecutionResult(
                status="completed",
                dry_run=dry_run,
                total_steps=1,
                success_count=1,
                failed_count=0,
                results=[
                    StepExecutionResult(
                        step_order=0,
                        method="GET",
                        path="/users",
                        status="success",
                        status_code=200,
                        request_payload={"password": "hunter2"},
                        response_payload={"token": "real-response-token"},
                    )
                ],
            )

        monkeypatch.setattr("app.automation.service.execute_plan_batch", fake_execute_plan_batch)

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        request = AutomationExecutionRequest(
            plan=_make_plan(),
            input_rows=[{"password": "hunter2"}],
            auth_headers={},
            dry_run=True,
        )

        await execute_automation(
            db=db, request=request, approval_granted=True, org_id="org-1"
        )

        step_logs = [obj for obj in added if type(obj).__name__ == "AutomationStepLog"]
        assert len(step_logs) == 1
        assert step_logs[0].request_payload["password"] == "***MASKED***"
        assert step_logs[0].response_payload["token"] == "***MASKED***"
