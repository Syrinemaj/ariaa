RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return True
    return status_code in RETRYABLE_STATUS_CODES
