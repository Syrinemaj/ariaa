from unittest.mock import patch, MagicMock
from app.reports.models import AutomationExecutionReport, AnalysisRunReport


def make_execution_report(**kwargs):
    defaults = {
        "automation_run_id": "run-abc",
        "analysis_run_id": "analysis-1",
        "instruction": "list users",
        "workflow_name": "user-flow",
        "status": "completed",
        "dry_run": True,
        "total_steps": 3,
        "success_count": 3,
        "failed_count": 0,
        "duration_seconds": 1.5,
        "success_rate": 1.0,
        "error_rate": 0.0,
    }
    defaults.update(kwargs)
    return AutomationExecutionReport(**defaults)


class TestGetAutomationReport:
    def test_returns_report(self, client):
        report = make_execution_report()

        with patch("app.api.reports.get_automation_report", return_value=report):
            response = client.get("/reports/automation/run-abc")

        assert response.status_code == 200
        data = response.json()
        assert data["automation_run_id"] == "run-abc"
        assert data["success_rate"] == 1.0
        assert data["dry_run"] is True

    def test_returns_404_when_not_found(self, client):
        with patch("app.api.reports.get_automation_report", return_value=None):
            response = client.get("/reports/automation/nonexistent")

        assert response.status_code == 404


class TestGetAnalysisRunReport:
    def test_returns_summary(self, client):
        report = AnalysisRunReport(
            analysis_run_id="analysis-1",
            total_automation_runs=2,
            total_steps=10,
            total_success=8,
            total_failed=2,
            average_success_rate=0.8,
        )

        with patch("app.api.reports.get_reports_for_analysis_run", return_value=report):
            response = client.get("/reports/run/analysis-1")

        assert response.status_code == 200
        data = response.json()
        assert data["total_automation_runs"] == 2
        assert data["average_success_rate"] == 0.8


class TestGlobalSummary:
    def test_returns_summary(self, client):
        summary = {
            "total_automation_runs": 5,
            "dry_runs": 3,
            "real_runs": 2,
            "total_steps": 20,
            "total_success": 18,
            "total_failed": 2,
            "global_success_rate": 0.9,
            "status_breakdown": {"completed": 4, "failed": 1},
        }

        with patch("app.api.reports.get_global_summary", return_value=summary):
            response = client.get("/reports/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total_automation_runs"] == 5
        assert data["global_success_rate"] == 0.9
        assert data["status_breakdown"]["completed"] == 4

    def test_empty_db_returns_zeros(self, client):
        empty = {
            "total_automation_runs": 0,
            "dry_runs": 0,
            "real_runs": 0,
            "total_steps": 0,
            "total_success": 0,
            "total_failed": 0,
            "global_success_rate": 0.0,
            "status_breakdown": {},
        }

        with patch("app.api.reports.get_global_summary", return_value=empty):
            response = client.get("/reports/summary")

        assert response.status_code == 200
        assert response.json()["total_automation_runs"] == 0
