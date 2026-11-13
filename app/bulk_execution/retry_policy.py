RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return True
    return status_code in RETRYABLE_STATUS_CODES


def is_retryable_step_result(result) -> bool:
    """
    Predicate for with_retries(is_retryable=...) — execute_step() never
    raises for an HTTP error status (see app/automation/executor.py): a
    4xx/5xx response, a path-traversal rejection, and a payload-validation
    failure all come back as a normal StepExecutionResult with
    status="failed", not an exception. A plain try/except retry loop (what
    with_retries used to be) therefore never triggers on any of these.

    Deliberately conservative: only retries when a real HTTP response was
    received (status_code is not None) and that status is transient
    (429/5xx) — status_code is None here means a pre-flight rejection
    (path-traversal/validation) or a raw network exception that execute_step
    already caught and stringified; both are non-transient by construction
    (validation) or already covered by execute_step's own error handling
    (network), so retrying them would just add 3x the delay for the same
    deterministic outcome.
    """
    return (
        getattr(result, "status", None) == "failed"
        and getattr(result, "status_code", None) is not None
        and is_retryable_status(result.status_code)
    )
