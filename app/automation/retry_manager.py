import asyncio
import random
from typing import Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    retries: int = 3,
    base_delay: float = 0.5,
    jitter: float = 0.5,
    is_retryable: Optional[Callable[[T], bool]] = None,
) -> T:
    """
    Retries `operation` up to `retries` times with exponential backoff + jitter.

    is_retryable(result): called on a SUCCESSFUL return value to decide
    whether it should be retried anyway. Needed because execute_step()
    (this function's main caller's operation) never raises for an HTTP error
    status — it always returns a StepExecutionResult, even for a 429 or a
    500 — so without this, nothing here ever actually retried an HTTP
    failure: the except-block only ever caught genuine Python exceptions
    (a bug found in production; see app/bulk_execution/retry_policy.py's
    is_retryable_step_result for the concrete predicate). Defaults to None,
    which preserves the original exception-only behavior for callers whose
    operation legitimately raises on failure.
    """
    last_error: Optional[Exception] = None
    last_result: Optional[T] = None

    for attempt in range(retries):
        try:
            result = await operation()
        except Exception as error:
            last_error = error
            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
                await asyncio.sleep(delay)
            continue

        if is_retryable is None or not is_retryable(result):
            return result

        last_result = result
        if attempt < retries - 1:
            delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
            await asyncio.sleep(delay)

    if last_result is not None:
        return last_result
    raise last_error  # type: ignore
