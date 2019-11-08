import asyncio
from typing import Callable
from unittest.mock import Mock, call

import later
from later.unittest import TestCase

from .helpers import AsyncMock


class WatcherTests(TestCase):
    async def test_empty_watcher(self) -> None:
        async with later.Watcher():
            pass

    async def test_preexit_callbacks(self) -> None:
        callback = Mock()
        callback.side_effect = Exception("DERP!")

        async with later.Watcher() as w:
            w.add_preexit_callback(callback, 1, 2)

        self.assertTrue(callback.called)
        callback.assert_has_calls([call(1, 2)])

    def test_bad_watch_call(self) -> None:
        w = later.Watcher()
        with self.assertRaises(ValueError):
            w.watch()

    async def test_watcher_fail_with_no_fix(self) -> None:
        loop = asyncio.get_running_loop()

        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        with self.assertRaises(RuntimeError):
            async with later.Watcher() as watcher:
                watcher.watch(task)

    async def test_watcher_cancel_timeout(self) -> None:
        async def coro() -> None:
            try:
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                pass
            await asyncio.sleep(2)  # take longer than 2 seconds to cancel

        loop = asyncio.get_running_loop()
        task = loop.create_task(coro())
        with self.assertRaises(later.WatcherError):
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)
                loop.call_later(0.2, watcher.cancel)
        # insure the task isn't still pending so we don't fail the later TestCase checks
        task.cancel()

    async def test_watcher_cancel(self) -> None:
        loop = asyncio.get_running_loop()

        async with later.Watcher(cancel_timeout=0.5) as watcher:
            watcher.watch(loop.create_task(asyncio.sleep(500)))
            loop.call_later(0.2, watcher.cancel)

    async def test_watcher_fail_with_callable_fixer(self) -> None:
        loop = asyncio.get_running_loop()
        fixer = Mock()
        replacement_task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        fixer.side_effect = [replacement_task, None]
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        with self.assertRaises(TypeError):  # from fixer returning None
            async with later.Watcher() as watcher:
                watcher.watch(task, fixer)

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(task), call(replacement_task)])

    async def test_watcher_fail_with_async_fixer(self) -> None:
        loop = asyncio.get_running_loop()
        fixer = AsyncMock()
        replacement_task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        fixer.side_effect = [replacement_task, None]
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        with self.assertRaises(TypeError):  # from fixer returning None
            async with later.Watcher() as watcher:
                watcher.watch(task, fixer)

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(task), call(replacement_task)])

    async def test_watcher_START_TASK_with_bad_callable_fixer(self) -> None:
        fixer = Mock()
        fixer.return_value = None

        with self.assertRaises(TypeError):
            async with later.Watcher() as watcher:
                watcher.watch(fixer=fixer)

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(later.START_TASK)])

    async def test_watcher_START_TASK_with_bad_async_fixer(self) -> None:
        fixer = AsyncMock()
        fixer.return_value = None

        with self.assertRaises(TypeError):
            async with later.Watcher() as watcher:
                watcher.watch(fixer=fixer)

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(later.START_TASK)])

    async def test_watcher_START_TASK_with_working_fixer(self) -> None:
        loop = asyncio.get_running_loop()
        fixer = AsyncMock()
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        fixer.side_effect = [task, None]

        with self.assertRaises(TypeError):  # from fixer returning None
            async with later.Watcher() as watcher:
                watcher.watch(fixer=fixer)

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(later.START_TASK), call(task)])

    async def test_watcher_canceled_parent_aexit(self) -> None:
        loop = asyncio.get_running_loop()
        task: asyncio.Task = loop.create_task(asyncio.sleep(500))

        async with later.timeout(0.2):
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)
        self.assertTrue(task.cancelled())

    async def test_watcher_cancel_task_badly(self) -> None:
        loop = asyncio.get_running_loop()

        async def coro() -> None:
            try:
                await asyncio.sleep(300)
                return None
            except asyncio.CancelledError:
                raise Exception("OMG!")

        task: asyncio.Task = loop.create_task(coro())
        with self.assertRaises(later.WatcherError):
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)
                loop.call_later(0.2, watcher.cancel)
