"""Unit tests for the approval module (service + guard), DB mocked."""
from unittest.mock import MagicMock

import pytest

from app.approval.approval_guard import (
    ApprovalRequiredError,
    assert_approval_for_real_execution,
)
from app.approval.approval_service import (
    ApprovalAlreadyProcessedError,
    approve_automation,
    create_approval_request,
)
from app.models.approval import AutomationApproval


def _db_returning(existing):
    """Mock Session whose query(...).filter(...).with_for_update().first() returns `existing`."""
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = existing
    return db


class TestApprovalGuard:
    def test_dry_run_never_requires_approval(self):
        assert_approval_for_real_execution(dry_run=True, approval_granted=False)

    def test_real_run_with_approval_passes(self):
        assert_approval_for_real_execution(dry_run=False, approval_granted=True)

    def test_real_run_without_approval_raises(self):
        with pytest.raises(ApprovalRequiredError):
            assert_approval_for_real_execution(dry_run=False, approval_granted=False)


class TestCreateApprovalRequest:
    def test_creates_pending_request(self):
        db = MagicMock()
        approval = create_approval_request(db, "run-1")

        assert isinstance(approval, AutomationApproval)
        assert approval.automation_run_id == "run-1"
        assert approval.status == "pending"
        db.add.assert_called_once_with(approval)
        db.commit.assert_called_once()


class TestApproveAutomation:
    def test_pending_request_becomes_approved(self):
        pending = AutomationApproval(automation_run_id="run-1", status="pending")
        db = _db_returning(pending)

        result = approve_automation(db, "run-1", approved_by="admin-1", comment="ok")

        assert result is pending
        assert result.status == "approved"
        assert result.approved_by == "admin-1"
        assert result.comment == "ok"
        assert result.approved_at is not None
        db.commit.assert_called_once()

    def test_missing_request_is_created_then_approved(self):
        db = _db_returning(None)

        result = approve_automation(db, "run-2", approved_by="admin-1")

        assert result.automation_run_id == "run-2"
        assert result.status == "approved"
        db.add.assert_called_once()

    @pytest.mark.parametrize("status", ["approved", "rejected"])
    def test_already_processed_request_cannot_be_approved_again(self, status):
        processed = AutomationApproval(automation_run_id="run-3", status=status)
        db = _db_returning(processed)

        with pytest.raises(ApprovalAlreadyProcessedError):
            approve_automation(db, "run-3", approved_by="admin-1")

        assert processed.status == status
        db.commit.assert_not_called()
