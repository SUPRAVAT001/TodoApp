"""In-memory rate limiter for authentication endpoints using a thread-safe sliding window."""

import os
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_rate_limited(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """Check if request exceeds rate limit in current sliding window."""
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Purge timestamps outside the active window
            timestamps = [ts for ts in self._requests[key] if ts > window_start]
            if len(timestamps) >= max_requests:
                self._requests[key] = timestamps
                return True

            timestamps.append(now)
            self._requests[key] = timestamps
            return False

    def clear(self) -> None:
        """Clear all stored rate limit entries (for testing)."""
        with self._lock:
            self._requests.clear()


limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP, prioritizing trusted reverse proxy headers."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def get_login_rate_limit() -> int:
    try:
        return int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
    except ValueError:
        return 10


def get_register_rate_limit() -> int:
    try:
        return int(os.getenv("RATE_LIMIT_REGISTER_PER_MINUTE", "5"))
    except ValueError:
        return 5


def is_rate_limiting_enabled() -> bool:
    env_override = os.getenv("RATE_LIMIT_ENABLED")
    if env_override is not None:
        return env_override.lower() in ("true", "1", "yes")
    # By default, rate limiting is active in all environments except unit/functional test runs.
    return os.getenv("ENVIRONMENT", "development").lower() != "test"


def check_rate_limit(
    request: Request,
    action: str,
    max_requests: Optional[int] = None,
    window_seconds: int = 60,
) -> None:
    """Enforce rate limit for an action per client IP; raises HTTP 429 if exceeded."""
    if not is_rate_limiting_enabled():
        return

    if max_requests is None:
        if action == "register":
            max_requests = get_register_rate_limit()
        else:
            max_requests = get_login_rate_limit()

    client_ip = get_client_ip(request)
    key = f"{action}:{client_ip}"
    if limiter.is_rate_limited(key, max_requests=max_requests, window_seconds=window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(window_seconds)},
        )
