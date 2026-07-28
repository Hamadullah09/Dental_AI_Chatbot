from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from app.core.logging import get_logger

logger = get_logger(__name__)


class ServiceBusyError(RuntimeError):
    """Raised when a bounded resource could not be acquired within its wait budget."""

    def __init__(self, name: str, waited_seconds: float) -> None:
        super().__init__(f"'{name}' is at capacity (waited {waited_seconds:.1f}s); please retry shortly.")
        self.name = name
        self.waited_seconds = waited_seconds


class ConcurrencyGate:
    """Bounds concurrent access to a scarce resource (single-GPU Ollama inference) and
    exposes queue depth so callers can surface an explicit 'queued' state to the user
    instead of blocking silently or overwhelming the backend with concurrent requests."""

    def __init__(self, name: str, max_concurrent: int, max_wait_seconds: float) -> None:
        self.name = name
        self.max_concurrent = max(1, max_concurrent)
        self.max_wait_seconds = max_wait_seconds
        self._sync_sema = threading.Semaphore(self.max_concurrent)
        self._async_sema = asyncio.Semaphore(self.max_concurrent)
        self._waiting = 0
        self._active = 0
        self._lock = threading.Lock()

    def _set_gauges(self) -> None:
        try:
            from app.middleware.metrics import GATE_ACTIVE, GATE_QUEUE_DEPTH

            GATE_QUEUE_DEPTH.labels(name=self.name).set(self._waiting)
            GATE_ACTIVE.labels(name=self.name).set(self._active)
        except Exception:
            pass

    @property
    def queue_depth(self) -> int:
        return self._waiting

    @property
    def is_saturated(self) -> bool:
        with self._lock:
            return self._active >= self.max_concurrent

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._lock:
            self._waiting += 1
            self._set_gauges()
        acquired = self._sync_sema.acquire(timeout=self.max_wait_seconds)
        with self._lock:
            self._waiting -= 1
            if acquired:
                self._active += 1
            self._set_gauges()
        if not acquired:
            logger.warning(f"concurrency_gate.busy name={self.name} max_wait={self.max_wait_seconds}")
            raise ServiceBusyError(self.name, self.max_wait_seconds)
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                self._set_gauges()
            self._sync_sema.release()

    @asynccontextmanager
    async def acquire_async(self) -> AsyncIterator[None]:
        with self._lock:
            self._waiting += 1
            self._set_gauges()
        acquired = True
        try:
            await asyncio.wait_for(self._async_sema.acquire(), timeout=self.max_wait_seconds)
        except TimeoutError:
            acquired = False
        with self._lock:
            self._waiting -= 1
            if acquired:
                self._active += 1
            self._set_gauges()
        if not acquired:
            logger.warning(f"concurrency_gate.busy name={self.name} max_wait={self.max_wait_seconds}")
            raise ServiceBusyError(self.name, self.max_wait_seconds)
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                self._set_gauges()
            self._async_sema.release()


_gate: ConcurrencyGate | None = None


def get_ollama_gate() -> ConcurrencyGate:
    global _gate
    if _gate is None:
        from app.core.config import get_settings

        settings = get_settings()
        _gate = ConcurrencyGate(
            name="ollama",
            max_concurrent=settings.ollama_max_concurrent_requests,
            max_wait_seconds=settings.ollama_queue_max_wait_seconds,
        )
    return _gate
