"""Phase 6 — create_plan_from_instruction() (app/planner/service.py) forwards
existing_workflow/csv_columns through to build_automation_plan(). Both are
passthrough-only here: the automatic WorkflowModel lookup itself (Phase 4)
lives inside build_automation_plan(), not in service.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.workflow import WorkflowModel
from app.planner.models import AutomationPlan, BusinessIntent
from app.planner.service import create_plan_from_instruction


def _make_db():
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.all.return_value = []
    db.execute = AsyncMock(return_value=execute_result)
    return db


def _make_plan():
    intent = BusinessIntent(
        instruction="Crée un employé", intent="create employee",
        action="create", entities=["employee"], confidence=0.9,
    )
    return AutomationPlan(
        run_id="run-1", instruction="Crée un employé", intent=intent,
        workflow_name="wf", steps=[],
    )


class TestCreatePlanFromInstructionForwarding:
    @pytest.mark.asyncio
    async def test_existing_workflow_and_csv_columns_forwarded(self):
        db = _make_db()
        workflow = MagicMock(spec=WorkflowModel)
        plan = _make_plan()

        with patch(
            "app.planner.service.analyze_business_intent", return_value=plan.intent,
        ), patch(
            "app.planner.service.build_automation_plan", new=AsyncMock(return_value=plan),
        ) as mock_build, patch(
            "app.planner.service.validate_plan",
            new=AsyncMock(return_value=MagicMock(is_valid=True, issues=[])),
        ):
            await create_plan_from_instruction(
                db=db, run_id="run-1", instruction="Crée un employé",
                existing_workflow=workflow, csv_columns=["prénom", "nom"],
            )

        _, kwargs = mock_build.call_args
        assert kwargs["existing_workflow"] is workflow
        assert kwargs["csv_columns"] == ["prénom", "nom"]

    @pytest.mark.asyncio
    async def test_defaults_to_none_when_not_provided(self):
        db = _make_db()
        plan = _make_plan()

        with patch(
            "app.planner.service.analyze_business_intent", return_value=plan.intent,
        ), patch(
            "app.planner.service.build_automation_plan", new=AsyncMock(return_value=plan),
        ) as mock_build, patch(
            "app.planner.service.validate_plan",
            new=AsyncMock(return_value=MagicMock(is_valid=True, issues=[])),
        ):
            await create_plan_from_instruction(
                db=db, run_id="run-1", instruction="Crée un employé",
            )

        _, kwargs = mock_build.call_args
        assert kwargs["existing_workflow"] is None
        assert kwargs["csv_columns"] is None
