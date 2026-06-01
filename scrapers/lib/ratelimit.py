from __future__ import annotations

import time
from dataclasses import dataclass


SOURCE_LIMITS_PER_MINUTE = {
    "linkedin": 30,
    "indeed": 30,
    "glassdoor": 20,
    "ziprecruiter": 30,
    "naukri": 30,
    "hirist": 30,
    "yc": 30,
    "wellfound": 20,
    "instahyre": 30,
    "cutshort": 30,
    "foundit": 30,
    "ambitionbox": 20,
    "iimjobs": 30,
    "google_jobs": 20,
}


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float
    tokens: float | None = None
    updated_at: float | None = None

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = self.capacity
        if self.updated_at is None:
            self.updated_at = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - (self.updated_at or now)
        self.tokens = min(self.capacity, (self.tokens or 0) + elapsed * self.refill_rate)
        self.updated_at = now

    def consume(self, tokens: float = 1, *, wait: bool = True, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            self._refill()
            if (self.tokens or 0) >= tokens:
                self.tokens = (self.tokens or 0) - tokens
                return True
            if not wait:
                return False
            if deadline is not None and time.monotonic() >= deadline:
                return False
            needed = tokens - (self.tokens or 0)
            sleep_for = min(max(needed / self.refill_rate, 0.05), 2.0)
            time.sleep(sleep_for)


_BUCKETS: dict[str, TokenBucket] = {}


def bucket_for_source(source: str) -> TokenBucket:
    normalized = source.lower().replace("_", "")
    per_minute = SOURCE_LIMITS_PER_MINUTE.get(source.lower(), SOURCE_LIMITS_PER_MINUTE.get(normalized, 30))
    capacity = max(1, per_minute)
    return _BUCKETS.setdefault(source.lower(), TokenBucket(capacity=capacity, refill_rate=per_minute / 60))


def rate_limit(source: str, tokens: float = 1) -> None:
    bucket_for_source(source).consume(tokens)

