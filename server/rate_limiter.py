"""Sliding window rate limiter for Power BI API calls."""

import time
from collections import deque


class RateLimiter:
    """Per-process sliding window rate limiter.

    Resets when MCP server restarts (each new Claude conversation).
    Scope: protect against runaway queries within a conversation.
    """

    def __init__(self, max_calls: int = 50, window_seconds: int = 300):
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def _evict_expired(self) -> None:
        cutoff = time.monotonic() - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def check(self) -> tuple[bool, int]:
        """Check if a call is allowed.

        Returns (allowed, seconds_until_available).
        If allowed, records the call timestamp.
        """
        self._evict_expired()
        if len(self._timestamps) < self._max_calls:
            self._timestamps.append(time.monotonic())
            return True, 0

        oldest = self._timestamps[0]
        wait = int(oldest + self._window_seconds - time.monotonic()) + 1
        return False, max(wait, 1)

    def remaining(self) -> int:
        self._evict_expired()
        return max(0, self._max_calls - len(self._timestamps))

    def status(self) -> dict:
        self._evict_expired()
        return {
            "max_calls": self._max_calls,
            "window_seconds": self._window_seconds,
            "calls_in_window": len(self._timestamps),
            "remaining": self.remaining(),
        }
