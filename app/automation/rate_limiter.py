import asyncio


class SimpleRateLimiter:
    def __init__(self, delay_seconds: float = 0.1) -> None:
        self.delay_seconds = delay_seconds

    async def wait(self) -> None:
        await asyncio.sleep(self.delay_seconds)
