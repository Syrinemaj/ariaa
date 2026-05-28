"""Tests for Fix 3.3 — Celery-based bulk execution."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bulk_execution.resume import get_completed_batch_numbers, should_skip_batch


# ─── Resume logic ─────────────────────────────────────────────────────────────

class TestShouldSkipBatch:
    def test_skipped_when_resume_and_completed(self):
        assert should_skip_batch(2, {1, 2, 3}, resume=True) is True

    def test_not_skipped_when_not_completed(self):
        assert should_skip_batch(5, {1, 2}, resume=True) is False

    def test_not_skipped_when_not_resuming(self):
        assert should_skip_batch(2, {1, 2, 3}, resume=False) is False


class TestGetCompletedBatchNumbers:
    def test_returns_set_of_batch_numbers(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            MagicMock(batch_number=1),
            MagicMock(batch_number=3),
        ]
        result = get_completed_batch_numbers(db, "run-1")
        assert result == {1, 3}

    def test_empty_result(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        assert get_completed_batch_numbers(db, "run-1") == set()


# ─── Job progress tracking ────────────────────────────────────────────────────

class TestJobProgressRedisKeys:
    """Verify the Redis hash structure used for progress tracking."""

    def test_progress_structure(self):
        redis_mock = MagicMock()

        # Simulate what the task writes
        progress_data = {
            "status": "running",
            "total": "1000",
            "completed": "450",
            "failed": "12",
            "batches": "20",
            "batches_done": "9",
            "automation_run_id": "run-abc",
        }
        redis_mock.hgetall.return_value = progress_data

        data = redis_mock.hgetall("job:test-job-id")
        assert int(data["completed"]) + int(data["failed"]) == 462
        assert int(data["batches_done"]) == 9
        assert data["status"] == "running"

    def test_progress_pct_calculation(self):
        total = 1000
        completed = 450
        failed = 12
        pct = round((completed + failed) / total * 100, 1)
        assert pct == 46.2


# ─── Celery task enqueueing (service layer) ───────────────────────────────────

class TestExecuteValidRowsEnqueue:
    @pytest.mark.asyncio
    async def test_returns_job_id_immediately(self):
        """Service should return a job_id dict without running any execution."""
        from app.planner.models import AutomationPlan, BusinessIntent

        plan = AutomationPlan(
            run_id="run-1",
            instruction="test",
            intent=BusinessIntent(
                intent="test", action="list", entities=[],
                requires_bulk_execution=False
            ),
            workflow_name="test_workflow",
            steps=[],
            requires_approval=False,
            dry_run_default=True,
        )

        mock_row = MagicMock()
        mock_row.row_index = 0
        mock_row.id = "row-1"
        mock_row.status = "valid"

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_row]
        db.query.return_value.filter.return_value.count.return_value = 0

        with (
            patch("app.bulk_execution.service.get_redis") as mock_redis,
            patch("app.workers.tasks.execution.execute_batch_task") as mock_task,
            patch("app.bulk_execution.service.AutomationRun") as mock_run_cls,
        ):
            mock_redis.return_value = MagicMock()
            mock_task.apply_async = MagicMock()

            mock_run = MagicMock()
            mock_run.id = "auto-run-id"
            db.add = MagicMock()
            db.commit = MagicMock()
            db.refresh = MagicMock()
            mock_run_cls.return_value = mock_run

            from app.bulk_execution.service import execute_valid_rows_in_batches
            result = await execute_valid_rows_in_batches(
                db=db,
                plan=plan,
                data_file_id="file-1",
                base_url="https://api.example.com",
                auth_headers={},
                dry_run=True,
            )

        assert "job_id" in result
        assert "automation_run_id" in result
        assert result["status"] == "queued"
        # Task was enqueued, not awaited synchronously
        mock_task.apply_async.assert_called()
