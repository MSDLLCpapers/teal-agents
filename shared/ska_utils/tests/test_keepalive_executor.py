import asyncio
from unittest.mock import MagicMock, patch

import pytest

from ska_utils.keepalive_executor import (
    KeepaliveMessage,
    execute_with_keepalive,
)


@pytest.mark.asyncio
async def test_execute_with_keepalive_yields_keepalive_and_result():
    async def long_task():
        await asyncio.sleep(0.01)
        return "done"

    gen = execute_with_keepalive(
        long_task(),
        keepalive_interval_seconds=0.005,
        keepalive_poll_interval_seconds=0.002,
    )
    results = []
    async for value in gen:
        results.append(value)
    assert any(isinstance(v, KeepaliveMessage) for v in results)
    assert results[-1] == "done"


@pytest.mark.asyncio
async def test_execute_with_keepalive_task_exception():
    logger = MagicMock()

    async def failing_task():
        raise ValueError("fail!")

    gen = execute_with_keepalive(
        failing_task(),
        keepalive_interval_seconds=0.01,
        keepalive_poll_interval_seconds=0.005,
        logger=logger,
    )
    with pytest.raises(ValueError):
        async for _ in gen:
            pass
    assert logger.error.called
    assert "Task exception" in logger.error.call_args[0][0]


@pytest.mark.asyncio
async def test_execute_with_keepalive_keepalive_exception():
    logger = MagicMock()

    # Make the main task run long enough for keepalive to run twice
    async def task():
        await asyncio.sleep(0.02)
        return "done"

    with patch("asyncio.Queue.put_nowait", side_effect=RuntimeError("keepalive fail")):
        gen = execute_with_keepalive(
            task(),
            keepalive_interval_seconds=0.005,  # keepalive fires quickly
            keepalive_poll_interval_seconds=0.001,
            logger=logger,
        )
        results = []
        try:
            async for value in gen:
                results.append(value)
        except Exception:
            pass

    assert logger.error.called
    assert "Keepalive exception" in logger.error.call_args[0][0]


@pytest.mark.asyncio
async def test_execute_with_keepalive_cancel_keepalive():
    async def task():
        await asyncio.sleep(0.01)
        return "done"

    real_wait_for = asyncio.wait_for

    async def wait_for_side_effect(awaitable, timeout):
        if (
            isinstance(awaitable, asyncio.Task)
            and getattr(awaitable._coro, "__name__", "") == "run_keepalive"
        ):
            raise asyncio.CancelledError()
        return await real_wait_for(awaitable, timeout)

    with patch("asyncio.wait_for", side_effect=wait_for_side_effect):
        gen = execute_with_keepalive(
            task(),
            keepalive_interval_seconds=0.001,
            keepalive_poll_interval_seconds=0.001,
        )
        results = []
        async for value in gen:
            results.append(value)
        assert results[-1] == "done"
