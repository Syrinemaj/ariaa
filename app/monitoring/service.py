from app.monitoring.events import EventName
from app.monitoring.logger import log_event


def log_har_uploaded(file_name: str, file_id: str) -> None:
    log_event(EventName.HAR_UPLOADED, {"file_name": file_name, "file_id": file_id})


def log_registry_saved(run_id: str, endpoints_count: int) -> None:
    log_event(EventName.REGISTRY_SAVED, {"run_id": run_id, "endpoints_count": endpoints_count})


def log_rag_indexed(run_id: str, indexed_count: int) -> None:
    log_event(EventName.RAG_INDEXED, {"run_id": run_id, "indexed_count": indexed_count})


def log_rag_searched(query: str, results_count: int) -> None:
    log_event(EventName.RAG_SEARCHED, {"query": query, "results_count": results_count})


def log_plan_generated(run_id: str, instruction: str, steps_count: int) -> None:
    log_event(EventName.PLAN_GENERATED, {"run_id": run_id, "instruction": instruction, "steps_count": steps_count})


def log_plan_validated(is_valid: bool, issues_count: int) -> None:
    log_event(EventName.PLAN_VALIDATED, {"is_valid": is_valid, "issues_count": issues_count})


def log_execution_started(automation_run_id: str, dry_run: bool) -> None:
    log_event(EventName.EXECUTION_STARTED, {"automation_run_id": automation_run_id, "dry_run": dry_run})


def log_execution_completed(
    automation_run_id: str,
    status: str,
    success_count: int,
    failed_count: int,
) -> None:
    log_event(EventName.EXECUTION_COMPLETED, {
        "automation_run_id": automation_run_id,
        "status": status,
        "success_count": success_count,
        "failed_count": failed_count,
    })
