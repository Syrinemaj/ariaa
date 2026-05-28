import asyncio
import random
from typing import Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    retries: int = 3,
    base_delay: float = 0.5,
    jitter: float = 0.5,
) -> T:
    last_error: Optional[Exception] = None

    for attempt in range(retries):
        try:
            return await operation()
        except Exception as error:
            last_error = error

            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
                await asyncio.sleep(delay)

    raise last_error  # type: ignore
