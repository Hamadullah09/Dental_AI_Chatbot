from __future__ import annotations

import enum
import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(enum.StrEnum):
    closed = "closed"
    open = "open"
    half_open = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Raised instead of attempting a call when a breaker is open (dependency presumed down)."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit breaker '{name}' is open; failing fast instead of calling the dependency.")
        self.name = name


_STATE_VALUES = {"closed": 0, "half_open": 1, "open": 2}


class CircuitBreaker:
    """Per-dependency circuit breaker.

    Opens after `failure_threshold` consecutive failures so callers fail fast instead of
    piling up slow timeouts against a dependency that is already down. After
    `reset_timeout_seconds` it allows a single trial call (half-open); success closes it,
    failure re-opens it.
    """

    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout_seconds: float = 30.0) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._state = CircuitState.closed
        self._failure_count = 0
        self._opened_at = 0.0
        self._half_open_in_flight = False
        self._lock = threading.Lock()

    def _set_gauge(self) -> None:
        try:
            from app.middleware.metrics import CIRCUIT_BREAKER_STATE

            CIRCUIT_BREAKER_STATE.labels(name=self.name).set(_STATE_VALUES[self._state.value])
        except Exception:
            pass

    @property
    def state(self) -> str:
        return self._state.value

    def allow_request(self) -> bool:
        with self._lock:
            if self._state == CircuitState.closed:
                return True
            if self._state == CircuitState.open:
                if time.monotonic() - self._opened_at >= self.reset_timeout_seconds:
                    self._state = CircuitState.half_open
                    self._half_open_in_flight = False
                    self._set_gauge()
                    logger.warning(f"circuit_breaker.half_open name={self.name}")
                else:
                    return False
            if self._state == CircuitState.half_open:
                if self._half_open_in_flight:
                    return False
                self._half_open_in_flight = True
                return True
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state != CircuitState.closed:
                logger.info(f"circuit_breaker.closed name={self.name}")
            self._state = CircuitState.closed
            self._failure_count = 0
            self._half_open_in_flight = False
            self._set_gauge()

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.half_open:
                self._state = CircuitState.open
                self._opened_at = time.monotonic()
                self._half_open_in_flight = False
                logger.warning(f"circuit_breaker.reopened name={self.name}")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.open
                self._opened_at = time.monotonic()
                logger.warning(
                    f"circuit_breaker.opened name={self.name} consecutive_failures={self._failure_count}"
                )
            self._set_gauge()

    def reset(self) -> None:
        """Test-only helper: circuit breakers are process-wide singletons, so without an
        explicit reset, failure counts leak across otherwise-independent test cases running
        in the same pytest session (see tests/conftest.py's reset_circuit_breakers fixture)."""
        with self._lock:
            self._state = CircuitState.closed
            self._failure_count = 0
            self._opened_at = 0.0
            self._half_open_in_flight = False

    def call(self, fn: Callable[[], T]) -> T:
        if not self.allow_request():
            try:
                from app.middleware.metrics import CIRCUIT_BREAKER_REJECTIONS

                CIRCUIT_BREAKER_REJECTIONS.labels(name=self.name).inc()
            except Exception:
                pass
            raise CircuitBreakerOpenError(self.name)
        try:
            result = fn()
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 3.0,
    should_retry: Callable[[Exception], bool] | None = None,
    name: str = "operation",
) -> T:
    """Retry `fn` with exponential backoff + full jitter, bounded by `max_attempts`.

    `should_retry` decides whether a given exception is transient; anything else re-raises
    immediately so we don't burn the retry budget on errors a retry can't fix (bad request,
    auth failure, etc).
    """
    predicate = should_retry or (lambda _exc: True)
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except Exception as exc:
            if not predicate(exc) or attempt >= max_attempts:
                if attempt > 1:
                    logger.warning(f"retry.exhausted name={name} attempts={attempt} error={exc}")
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = delay * (0.5 + random.random() * 0.5)
            logger.info(f"retry.attempt name={name} attempt={attempt} next_delay_s={delay:.2f} error={exc}")
            time.sleep(delay)


def is_transient_network_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    try:
        import httpx

        if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
            return True
    except ImportError:
        pass
    return False


def is_transient_qdrant_error(exc: Exception) -> bool:
    if is_transient_network_error(exc):
        return True
    try:
        from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

        if isinstance(exc, ResponseHandlingException):
            return True
        if isinstance(exc, UnexpectedResponse):
            return getattr(exc, "status_code", 0) >= 500
    except ImportError:
        pass
    return False


def _build_default_breakers() -> tuple[CircuitBreaker, CircuitBreaker, CircuitBreaker]:
    """Breaker thresholds are configurable (see Settings) since production tuning for a
    single-instance GPU inference backend (Ollama) vs. a normally-fast local Qdrant will
    differ per deployment."""
    try:
        from app.core.config import get_settings

        settings = get_settings()
        return (
            CircuitBreaker(
                name="qdrant",
                failure_threshold=settings.qdrant_breaker_failure_threshold,
                reset_timeout_seconds=settings.qdrant_breaker_reset_seconds,
            ),
            CircuitBreaker(
                name="ollama",
                failure_threshold=settings.ollama_breaker_failure_threshold,
                reset_timeout_seconds=settings.ollama_breaker_reset_seconds,
            ),
            CircuitBreaker(
                name="embedding",
                failure_threshold=settings.embedding_breaker_failure_threshold,
                reset_timeout_seconds=settings.embedding_breaker_reset_seconds,
            ),
        )
    except Exception:
        return (
            CircuitBreaker(name="qdrant", failure_threshold=5, reset_timeout_seconds=20.0),
            CircuitBreaker(name="ollama", failure_threshold=3, reset_timeout_seconds=30.0),
            CircuitBreaker(name="embedding", failure_threshold=5, reset_timeout_seconds=15.0),
        )


# One breaker per external dependency, shared process-wide.
qdrant_breaker, ollama_breaker, embedding_breaker = _build_default_breakers()
