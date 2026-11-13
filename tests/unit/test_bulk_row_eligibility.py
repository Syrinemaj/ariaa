"""Which data rows a new real execution of a file picks up."""
from app.bulk_execution.service import ELIGIBLE_ROW_STATUSES


def test_failed_rows_can_be_relaunched():
    # Observed in a real run: after the target went down, the 100 failed
    # rows could not be relaunched at all.
    assert "failed" in ELIGIBLE_ROW_STATUSES


def test_never_executed_rows_are_eligible():
    assert "valid" in ELIGIBLE_ROW_STATUSES
    assert "dry_run_success" in ELIGIBLE_ROW_STATUSES


def test_succeeded_and_invalid_rows_are_not_picked_up_again():
    for status in ("success", "success_duplicate", "invalid"):
        assert status not in ELIGIBLE_ROW_STATUSES
