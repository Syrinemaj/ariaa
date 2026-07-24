"""Regression test — a validation run must be marked "completed" (the process
finished) even when some rows are invalid. Per-row outcome belongs in
valid_rows/invalid_rows, not in status. Before this fix, any invalid row set
status="failed", which made real (non-dry) execution of the valid subset
unreachable downstream in bulk.py's `status == "completed"` gate — even when
the caller explicitly opted into allow_partial_execution."""
from unittest.mock import MagicMock

from app.bulk_validation import service as bulk_validation_service


class _FakeRow:
    def __init__(self, row_index, raw_data):
        self.row_index = row_index
        self.raw_data = raw_data
        self.normalized_data = None
        self.status = None
        self.error_message = None


def _make_db_with_rows(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    return db


class TestValidateBulkDataStatus:
    def test_status_is_completed_even_with_invalid_rows(self, monkeypatch):
        rows = [_FakeRow(0, {"email": "a@b.com"}), _FakeRow(1, {"email": "bad"})]
        db = _make_db_with_rows(rows)

        monkeypatch.setattr(bulk_validation_service, "get_approved_mappings", lambda **kw: {})
        monkeypatch.setattr(bulk_validation_service, "apply_mapping_to_row", lambda row, mappings: row)
        monkeypatch.setattr(bulk_validation_service, "resolve_row_references", lambda mapped: mapped)
        monkeypatch.setattr(bulk_validation_service, "validate_row_against_plan", lambda *a: [])
        monkeypatch.setattr(bulk_validation_service, "validate_contract_type", lambda *a: [])

        def fake_business_rules(resolved, row_index):
            if row_index == 1:
                return [{
                    "row_index": row_index,
                    "field_name": "email",
                    "error_code": "INVALID_EMAIL",
                    "message": "not a valid email",
                }]
            return []

        monkeypatch.setattr(bulk_validation_service, "validate_row_business_rules", fake_business_rules)

        result = bulk_validation_service.validate_bulk_data(
            db=db, analysis_run_id="run-1", data_file_id="file-1", plan={}
        )

        assert result["valid_rows"] == 1
        assert result["invalid_rows"] == 1
        # Regression guard: process completed, even though not every row is valid.
        assert db.add.call_args_list  # a BulkValidationRun was added
        validation_run = db.add.call_args_list[0].args[0]
        assert validation_run.status == "completed"
        assert result["ready_for_execution"] is False
        assert result["can_execute_partial"] is True

    def test_status_is_completed_when_all_rows_valid(self, monkeypatch):
        rows = [_FakeRow(0, {"email": "a@b.com"})]
        db = _make_db_with_rows(rows)

        monkeypatch.setattr(bulk_validation_service, "get_approved_mappings", lambda **kw: {})
        monkeypatch.setattr(bulk_validation_service, "apply_mapping_to_row", lambda row, mappings: row)
        monkeypatch.setattr(bulk_validation_service, "resolve_row_references", lambda mapped: mapped)
        monkeypatch.setattr(bulk_validation_service, "validate_row_against_plan", lambda *a: [])
        monkeypatch.setattr(bulk_validation_service, "validate_contract_type", lambda *a: [])
        monkeypatch.setattr(bulk_validation_service, "validate_row_business_rules", lambda *a: [])

        result = bulk_validation_service.validate_bulk_data(
            db=db, analysis_run_id="run-1", data_file_id="file-1", plan={}
        )

        validation_run = db.add.call_args_list[0].args[0]
        assert validation_run.status == "completed"
        assert result["ready_for_execution"] is True
