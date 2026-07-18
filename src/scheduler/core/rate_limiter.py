"""Token Bucket Rate-Limiter implementation for multi-tenant isolation."""

import asyncio
import time


class TokenBucketLimiter:
    """Asynchronous Token Bucket rate-limiter using an in-memory lock."""

    def __init__(self, capacity: int = 5, refill_rate: float = 0.5) -> None:
        """Initialize the TokenBucketLimiter.

        Args:
            capacity: Max number of tokens (burst capacity). Defaults to 5.
            refill_rate: Refill rate in tokens per second. Defaults to 0.5 (1 token every 2s).
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.buckets: dict[str, float] = {}
        self.last_updated: dict[str, float] = {}
        self.lock = asyncio.Lock()

    async def acquire(self, tenant_id: str) -> bool:
        """Attempt to acquire 1 token for a given tenant.

        Refills the tenant's bucket dynamically based on elapsed time.

        Args:
            tenant_id: Unique identifier for the tenant.

        Returns:
            True if a token was successfully acquired, False otherwise.
        """
        async with self.lock:
            now = time.time()
            if tenant_id not in self.buckets:
                self.buckets[tenant_id] = float(self.capacity)
                self.last_updated[tenant_id] = now

            # Calculate refilled tokens based on elapsed time
            elapsed = now - self.last_updated[tenant_id]
            refilled = elapsed * self.refill_rate
            self.buckets[tenant_id] = min(float(self.capacity), self.buckets[tenant_id] + refilled)
            self.last_updated[tenant_id] = now

            if self.buckets[tenant_id] >= 1.0:
                self.buckets[tenant_id] -= 1.0
                return True
            return False
