import asyncio

import pytest

from app.core.concurrency import ConcurrencyGate, ServiceBusyError


def test_gate_allows_up_to_max_concurrent():
    gate = ConcurrencyGate(name="test", max_concurrent=2, max_wait_seconds=1.0)
    with gate.acquire():
        with gate.acquire():
            assert gate.queue_depth == 0


def test_gate_raises_when_wait_budget_exhausted():
    gate = ConcurrencyGate(name="test-busy", max_concurrent=1, max_wait_seconds=0.1)
    with gate.acquire():
        with pytest.raises(ServiceBusyError):
            with gate.acquire():
                pass


def test_gate_releases_slot_after_context_exits():
    gate = ConcurrencyGate(name="test-release", max_concurrent=1, max_wait_seconds=0.5)
    with gate.acquire():
        pass
    with gate.acquire():
        assert gate._active == 1


@pytest.mark.asyncio
async def test_async_gate_raises_when_saturated():
    gate = ConcurrencyGate(name="test-async-busy", max_concurrent=1, max_wait_seconds=0.1)
    async with gate.acquire_async():
        with pytest.raises(ServiceBusyError):
            async with gate.acquire_async():
                pass


@pytest.mark.asyncio
async def test_async_gate_allows_sequential_acquisition():
    gate = ConcurrencyGate(name="test-async-sequential", max_concurrent=1, max_wait_seconds=1.0)
    async with gate.acquire_async():
        pass
    async with gate.acquire_async():
        assert gate._active == 1
