import time

import pytest

from app.core.resilience import CircuitBreaker, CircuitBreakerOpenError, retry_with_backoff


def test_circuit_breaker_opens_after_threshold_and_rejects_fast():
    breaker = CircuitBreaker(name="test", failure_threshold=3, reset_timeout_seconds=10.0)

    def failing():
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(failing)

    assert breaker.state == "open"
    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(failing)


def test_circuit_breaker_half_open_recovers_on_success():
    breaker = CircuitBreaker(name="test-recover", failure_threshold=1, reset_timeout_seconds=0.05)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert breaker.state == "open"

    time.sleep(0.1)

    result = breaker.call(lambda: "ok")
    assert result == "ok"
    assert breaker.state == "closed"


def test_circuit_breaker_half_open_reopens_on_failure():
    breaker = CircuitBreaker(name="test-reopen", failure_threshold=1, reset_timeout_seconds=0.05)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    time.sleep(0.1)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("still down")))
    assert breaker.state == "open"


def test_retry_with_backoff_retries_transient_then_succeeds():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("transient")
        return "done"

    result = retry_with_backoff(flaky, max_attempts=5, base_delay=0.01, max_delay=0.02, name="test")
    assert result == "done"
    assert attempts["count"] == 3


def test_retry_with_backoff_stops_at_max_attempts():
    attempts = {"count": 0}

    def always_fails():
        attempts["count"] += 1
        raise ConnectionError("still failing")

    with pytest.raises(ConnectionError):
        retry_with_backoff(always_fails, max_attempts=3, base_delay=0.01, max_delay=0.02, name="test")
    assert attempts["count"] == 3


def test_retry_with_backoff_does_not_retry_non_transient_errors():
    attempts = {"count": 0}

    def bad_request():
        attempts["count"] += 1
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        retry_with_backoff(
            bad_request,
            max_attempts=5,
            base_delay=0.01,
            should_retry=lambda exc: isinstance(exc, ConnectionError),
            name="test",
        )
    assert attempts["count"] == 1
