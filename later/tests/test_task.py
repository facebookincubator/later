import asyncio
import unittest
from typing import Callable
from unittest.mock import Mock, call

import later

from .helpers import AsyncMock


class WatcherTests(unittest.TestCase):
    def test_empty_watcher(self) -> None:
        async def inner() -> None:
            async with later.Watcher():
                pass

        loop = asyncio.get_event_loop()
        loop.run_until_complete(inner())

    def test_preexit_callbacks(self) -> None:
        callback = Mock()
        callback.side_effect = Exception("DERP!")

        async def inner() -> None:
            async with later.Watcher() as w:
                w.add_preexit_callback(callback, 1, 2)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(inner())

        self.assertTrue(callback.called)
        callback.assert_has_calls([call(1, 2)])

    def test_bad_watch_call(self) -> None:
        w = later.Watcher()
        with self.assertRaises(ValueError):
            w.watch()

    def test_watcher_fail_with_no_fix(self) -> None:
        async def inner(task: asyncio.Task) -> None:
            async with later.Watcher() as watcher:
                watcher.watch(task)

        loop = asyncio.get_event_loop()
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        with self.assertRaises(RuntimeError):
            loop.run_until_complete(inner(task))

    def test_watcher_cancel_timeout(self) -> None:
        loop = asyncio.get_event_loop()

        async def coro() -> None:
            while True:
                try:
                    await asyncio.sleep(300)
                    return None
                except asyncio.CancelledError:
                    pass

        async def inner(task: asyncio.Task) -> None:
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)
                loop.call_later(0.2, watcher.cancel)

        task: asyncio.Task = loop.create_task(coro())
        with self.assertRaises(later.WatcherError):
            loop.run_until_complete(inner(task))

    def test_watcher_cancel(self) -> None:
        loop = asyncio.get_event_loop()

        async def inner(task: asyncio.Task) -> None:
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)
                loop.call_later(0.2, watcher.cancel)

        task: asyncio.Task = loop.create_task(asyncio.sleep(500))
        loop.run_until_complete(inner(task))

    def test_watcher_fail_with_callable_fixer(self) -> None:
        async def inner(task: asyncio.Task, fixer: Callable) -> None:
            async with later.Watcher() as watcher:
                watcher.watch(task, fixer)

        loop = asyncio.get_event_loop()
        fixer = Mock()
        replacement_task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        fixer.side_effect = [replacement_task, None]
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        with self.assertRaises(TypeError):  # from fixer returning None
            loop.run_until_complete(inner(task, fixer))

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(task), call(replacement_task)])

    def test_watcher_fail_with_async_fixer(self) -> None:
        async def inner(task: asyncio.Task, fixer: Callable) -> None:
            async with later.Watcher() as watcher:
                watcher.watch(task, fixer)

        loop = asyncio.get_event_loop()
        fixer = AsyncMock()
        replacement_task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        fixer.side_effect = [replacement_task, None]
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        with self.assertRaises(TypeError):  # from fixer returning None
            loop.run_until_complete(inner(task, fixer))

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(task), call(replacement_task)])

    def test_watcher_START_TASK_with_bad_callable_fixer(self) -> None:
        async def inner(fixer: Callable) -> None:
            async with later.Watcher() as watcher:
                watcher.watch(fixer=fixer)

        loop = asyncio.get_event_loop()
        fixer = Mock()
        fixer.return_value = None

        with self.assertRaises(TypeError):
            loop.run_until_complete(inner(fixer))

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(later.START_TASK)])

    def test_watcher_START_TASK_with_bad_async_fixer(self) -> None:
        async def inner(fixer: Callable) -> None:
            async with later.Watcher() as watcher:
                watcher.watch(fixer=fixer)

        loop = asyncio.get_event_loop()
        fixer = AsyncMock()
        fixer.return_value = None

        with self.assertRaises(TypeError):
            loop.run_until_complete(inner(fixer))

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(later.START_TASK)])

    def test_watcher_START_TASK_with_working_fixer(self) -> None:
        async def inner(fixer: Callable) -> None:
            async with later.Watcher() as watcher:
                watcher.watch(fixer=fixer)

        loop = asyncio.get_event_loop()
        fixer = AsyncMock()
        task: asyncio.Task = loop.create_task(asyncio.sleep(0.1))
        fixer.side_effect = [task, None]

        with self.assertRaises(TypeError):  # from fixer returning None
            loop.run_until_complete(inner(fixer))

        self.assertTrue(fixer.called)
        fixer.assert_has_calls([call(later.START_TASK), call(task)])

    def test_watcher_canceled_parent_aexit(self) -> None:
        async def inner(task: asyncio.Task) -> None:
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)

        loop = asyncio.get_event_loop()
        task: asyncio.Task = loop.create_task(asyncio.sleep(500))

        with self.assertRaises(asyncio.TimeoutError):
            loop.run_until_complete(asyncio.wait_for(inner(task), 0.2))

    def test_watcher_cancel_task_badly(self) -> None:
        loop = asyncio.get_event_loop()

        async def coro() -> None:
            try:
                await asyncio.sleep(300)
                return None
            except asyncio.CancelledError:
                raise Exception("OMG!")

        async def inner(task: asyncio.Task) -> None:
            async with later.Watcher(cancel_timeout=0.5) as watcher:
                watcher.watch(task)
                loop.call_later(0.2, watcher.cancel)

        task: asyncio.Task = loop.create_task(coro())
        with self.assertRaises(later.WatcherError):
            loop.run_until_complete(inner(task))
