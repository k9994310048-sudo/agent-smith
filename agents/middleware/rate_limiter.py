"""
Rate Limiter for LLM API calls.
Token bucket algorithm - lightweight, no external deps.
"""
import asyncio
import time
from collections import defaultdict


class TokenBucketRateLimiter:
    """Simple token bucket rate limiter for API calls."""

    def __init__(self, rate: float = 10, burst: int = 20):
        """
        rate: requests per second
        burst: max burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = defaultdict(lambda: float(burst))
        self.last_refill = defaultdict(time.time)

    async def acquire(self, key: str = "default") -> bool:
        """Acquire a token, wait if none available."""
        now = time.time()
        elapsed = now - self.last_refill[key]
        self.tokens[key] = min(
            self.burst,
            self.tokens[key] + elapsed * self.rate
        )
        self.last_refill[key] = now

        if self.tokens[key] >= 1.0:
            self.tokens[key] -= 1.0
            return True

        wait_time = (1.0 - self.tokens[key]) / self.rate
        await asyncio.sleep(wait_time)
        self.tokens[key] = 0.0
        self.last_refill[key] = time.time()
        return True

    def get_status(self, key: str = "default") -> dict:
        """Get current bucket status."""
        return {
            "tokens": round(self.tokens[key], 2),
            "burst": self.burst,
            "rate": self.rate,
        }


# Global instance for LLM API calls
_llm_rate_limiter = TokenBucketRateLimiter(rate=5, burst=15)


async def rate_llm_call(func, *args, **kwargs):
    """Wrap an LLM API call with rate limiting."""
    await _llm_rate_limiter.acquire("llm_api")
    return await func(*args, **kwargs)


def get_rate_limiter_status() -> dict:
    """Get rate limiter status for monitoring."""
    return _llm_rate_limiter.get_status("llm_api")
