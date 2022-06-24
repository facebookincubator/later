# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import cast
from unittest.mock import call, Mock

import later
from later.unittest import TestCase
from later.unittest.mock import AsyncMock


class TaskTests(TestCase):
    async def test_as_task(self) -> None:
        tsleep = later.as_task(asyncio.sleep)
        # pep484 is still limited on typing around decorators, best to cast
        task: asyncio.Task = cast(asyncio.Task, tsleep(500))
        self.assertIsInstance(task, asyncio.Task)
        await later.cancel(task)
        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())

    async def test_cancel_task(self) -> None:
        task: asyncio.Task = asyncio.get_running_loop().create_task(asyncio.sleep(500))
        await later.cancel(task)
        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())

    async def test_cancel_raises_other_exception(self) -> None:
        started = False

        @later.as_task
        async def _coro():
            nonlocal started
            started = True
            try:
                await asyncio.sleep(500)
            except asyncio.CancelledError:
                raise TypeError

        task: asyncio.Task = cast(asyncio.Task, _coro())
        await asyncio.sleep(0)
        self.assertTrue(started)
        with self.assertRaises(TypeError):
            await later.cancel(task)
        self.assertTrue(task.done())
        self.assertFalse(task.cancelled())

    async def test_cancel_already_done_task(self) -> None:
        started = False

        @later.as_task
        async def _coro():
            nonlocal started
            started = True

        task: asyncio.Task = cast(asyncio.Task, _coro())
        await asyncio.sleep(0)
        self.assertTrue(started)
        self.assertTrue(task.done())
        await later.cancel(task)

    async def test_cancel_task_completes(self) -> None:
        started = False

        @later.as_task
        async def _coro():
            nonlocal started
            started = True
            try:
                await asyncio.sleep(500)
            except asyncio.CancelledError:
                return 5

        task: asyncio.Task = cast(asyncio.Task, _coro())
        await asyncio.sleep(0)
        self.assertTrue(started)
        with self.assertRaises(asyncio.InvalidStateError):
            await later.cancel(task)
        self.assertTrue(task.done())
        self.assertFalse(task.cancelled())

    async def test_cancel_when_cancelled(self) -> None:
        started, cancelled = False, False

        @later.as_task
        async def test():
            nonlocal cancelled, started
            started = True
            try:
                await asyncio.sleep(500)
            except asyncio.CancelledError:
                cancelled = True
                await asyncio.sleep(0.5)
                raise

        # neat :P
        cancel_as_task = later.as_task(later.cancel)
        otask = cast(asyncio.Task, test())  # task created a scheduled.
        await asyncio.sleep(0)  # let test start
        self.assertTrue(started)
        ctask = cast(asyncio.Task, cancel_as_task(otask))
        await asyncio.sleep(0)  # let the cancel as task start
        self.assertFalse(otask.cancelled())
        ctask.cancel()
        await asyncio.sleep(0)  # Insure the cancel was raised in the ctask
        self.assertTrue(cancelled)
        # Not done yet since the orignal task is sleeping
        self.assertFalse(ctask.cancelled())
        # we are not cancelled yet, there is a 0.5 sleep in the cancellation flow
        with self.assertRaises(asyncio.CancelledError):
            # now our cancel must raise a CancelledError as per contract
            await ctask
        self.assertTrue(ctask.cancelled())
        self.assertTrue(otask.cancelled())


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

    async def test_add_task_and_remove_task(self) -> None:
        loop = asyncio.get_running_loop()

        def fixer(orig_task: asyncio.Task) -> asyncio.Task:
            return loop.create_task(asyncio.sleep(0.5))

        task: asyncio.Task = loop.create_task(asyncio.sleep(10))
        watcher = later.Watcher(context=True)
        watcher.watch(fixer=fixer)

        async def work() -> None:
            await asyncio.sleep(0.1)
            watcher.watch(task)
            await asyncio.sleep(0)
            self.assertTrue(await watcher.unwatch(task))
            self.assertTrue(await watcher.unwatch(fixer=fixer))
            await asyncio.sleep(10)

        async with watcher:
            watcher.watch(loop.create_task(work()))
            watcher.watch(task, shield=True)
            self.assertTrue(await watcher.unwatch(task, shield=True))
            self.assertFalse(await watcher.unwatch(task, shield=True))
            loop.call_later(0.2, watcher.cancel)

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

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
        fixer.assert_awaited()
        fixer.assert_has_awaits([call(task), call(replacement_task)])

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
        fixer.assert_awaited()
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
        fixer.assert_awaited()
        fixer.assert_has_awaits([call(later.START_TASK), call(task)])

    async def test_watcher_canceled_parent_aexit(self) -> None:
        loop = asyncio.get_running_loop()
        task: asyncio.Task = loop.create_task(asyncio.sleep(500))
        with self.assertRaises(asyncio.TimeoutError):
            async with later.timeout(0.2):
                async with later.Watcher() as watcher:
                    watcher.watch(task)
        self.assertTrue(task.cancelled())

    async def test_watcher_raise_in_body(self) -> None:
        loop = asyncio.get_running_loop()
        task: asyncio.Task = loop.create_task(asyncio.sleep(500))
        with self.assertRaises(RuntimeError):
            async with later.Watcher() as watcher:
                watcher.watch(task)
                await asyncio.sleep(0)
                raise RuntimeError
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

    def test_watch_non_task(self) -> None:
        watcher = later.Watcher()
        # Can't watch coros, or anything else
        with self.assertRaises(TypeError):
            # pyre-fixme[6]: Expected `Task[typing.Any]` for 1st param but got
            #  `Future[Variable[asyncio.tasks._T]]`.
            watcher.watch(asyncio.sleep(1))

    async def test_watcher_context(self) -> None:
        loop = asyncio.get_running_loop()

        def start_a_task():
            later.Watcher.get().watch(loop.create_task(asyncio.sleep(5)))

        async with later.Watcher() as watcher:
            loop.call_later(0.2, watcher.cancel)
            start_a_task()

    async def test_watcher_context_at_init(self) -> None:
        loop = asyncio.get_running_loop()

        def start_a_task():
            later.Watcher.get().watch(loop.create_task(asyncio.sleep(5)))

        watcher = later.Watcher(context=True)
        start_a_task()
        async with watcher:
            loop.call_later(0.2, watcher.cancel)

    def test_watcher_context_non_exist(self) -> None:
        with self.assertRaises(LookupError):
            later.Watcher.get()

    async def test_watch_with_shield(self) -> None:
        loop = asyncio.get_running_loop()
        task: asyncio.Task[None] = loop.create_task(asyncio.sleep(0.1))
        async with later.Watcher() as watcher:
            watcher.watch(task, shield=True)
            with self.assertRaises(ValueError):
                # This is not permitted
                watcher.watch(task, fixer=lambda x: task, shield=True)
            watcher.cancel()

        await task
