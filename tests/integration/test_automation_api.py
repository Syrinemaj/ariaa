from unittest.mock import AsyncMock, MagicMock, patch

from app.automation.models import AutomationExecutionResult, StepExecutionResult
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep


def make_plan_payload(requires_approval=True, method="GET"):
    return {
        "run_id": "run-test-123",
        "instruction": "list all users",
        "intent": {
            "instruction": "list all users",
            "intent": "list",
            "action": "list",
            "confidence": 0.95,
        },
        "workflow_name": "user-listing",
        "steps": [
            {
                "order": 1,
                "endpoint_id": "ep-1",
                "method": method,
                "path": "/api/users",
                "canonical_key": f"{method} /api/users",
                "risk_level": "low",
            }
        ],
        "requires_approval": requires_approval,
        "dry_run_default": True,
    }


def make_execution_result(dry_run=True, status="completed"):
    return AutomationExecutionResult(
        status=status,
        dry_run=dry_run,
        success_count=1,
        failed_count=0,
        total_steps=1,
        results=[
            StepExecutionResult(
                step_order=1,
                method="GET",
                path="/api/users",
                status="success",
                status_code=200 if not dry_run else None,
                request_payload={},
                response_payload={"users": []},
            )
        ],
        metadata={"duration_seconds": 0.1},
    )


class TestCreatePlan:
    def test_returns_404_for_unknown_run(self, client):
        with patch("app.api.automation.get_run_by_id", return_value=None):
            response = client.post(
                "/automation/plan",
                json={"run_id": "nonexistent", "instruction": "do something"},
            )
        assert response.status_code == 404

    def test_creates_plan_for_valid_run(self, client):
        mock_run = MagicMock()
        mock_plan = AutomationPlan(
            run_id="run-123",
            instruction="list users",
            intent=BusinessIntent(
                instruction="list users",
                intent="list",
                action="list",
                confidence=0.9,
            ),
            workflow_name="user-flow",
            steps=[],
        )
        mock_validation = MagicMock()
        mock_validation.is_valid = True
        mock_validation.issues = []
        mock_validation.model_dump.return_value = {"is_valid": True, "issues": []}

        with patch("app.api.automation.get_run_by_id", return_value=mock_run), \
             patch("app.api.automation.create_plan_from_instruction",
                   return_value=(mock_plan, mock_validation)):
            response = client.post(
                "/automation/plan",
                json={"run_id": "run-123", "instruction": "list users"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert "validation" in data


class TestExecutePlan:
    def test_dry_run_succeeds(self, client):
        mock_run = MagicMock()
        mock_run.id = "automation-run-1"
        mock_result = make_execution_result(dry_run=True)

        with patch("app.api.automation.execute_automation",
                   new_callable=AsyncMock,
                   return_value=(mock_run, mock_result)):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(requires_approval=True),
                    "dry_run": True,
                    "approval_granted": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["status"] == "completed"
        assert data["success_count"] == 1

    def test_real_execution_without_approval_returns_403(self, client):
        from app.security.execution_guard import ExecutionGuardError

        with patch("app.api.automation.execute_automation",
                   new_callable=AsyncMock,
                   side_effect=ExecutionGuardError("Real execution requires explicit approval.")):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(requires_approval=True),
                    "dry_run": False,
                    "approval_granted": False,
                },
            )

        assert response.status_code == 403
        assert "approval" in response.json()["detail"].lower()

    def test_delete_without_allow_returns_403(self, client):
        from app.security.execution_guard import ExecutionGuardError

        with patch("app.api.automation.execute_automation",
                   new_callable=AsyncMock,
                   side_effect=ExecutionGuardError("Method DELETE is forbidden by default.")):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(requires_approval=False, method="DELETE"),
                    "dry_run": False,
                    "approval_granted": True,
                },
            )

        assert response.status_code == 403
