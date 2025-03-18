# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pyre-strict
from __future__ import annotations

import asyncio
import unittest
from typing import Any, List

from later.unittest import ignoreAsyncioErrors, ignoreTaskLeaks, TestCase


# This is a place to purposefully produce leaked tasks
saved_tasks: list[asyncio.Task] = []


class TestTestCase(TestCase):
    @unittest.expectedFailure
    async def test_unmanaged_task_created_in_testmethod(self) -> None:
        saved_tasks.append(asyncio.get_running_loop().create_task(asyncio.sleep(10)))

    async def test_managed_task_done(self) -> None:
        task = asyncio.get_running_loop().create_task(asyncio.sleep(0.5, "test"))
        saved_tasks.append(task)
        await task

    async def test_unmanaged_task_done_none(self) -> None:
        """None value Done tasks are ignored"""

        async def coro(e: asyncio.Event) -> None:
            e.set()

        event = asyncio.Event()
        saved_tasks.append(asyncio.get_running_loop().create_task(coro(event)))
        await event.wait()

    @unittest.expectedFailure
    async def dtest_unmanaged_task_done_value(self) -> None:
        async def coro(e: asyncio.Event) -> bool:
            e.set()
            return False

        event = asyncio.Event()
        saved_tasks.append(asyncio.get_running_loop().create_task(coro(event)))
        await event.wait()

    @unittest.expectedFailure
    async def test_garbage_collected_task_during_testmethod(self) -> None:
        t = asyncio.get_running_loop().create_task(asyncio.sleep(10))
        t.cancel()
        del t

    async def test_tasks_add_callback(self) -> None:
        # If we add a callback and it is run then thats good enough
        # to say the task was managed
        t = asyncio.get_running_loop().create_task(asyncio.sleep(10))
        x = False

        def callback(fut: asyncio.Task) -> None:
            nonlocal x
            x = True

        t.add_done_callback(callback)
        t.cancel()
        await asyncio.sleep(0.1)  # callbacks are scheduled
        self.assertTrue(x, "callback was executed")

    async def test_task_exception(self) -> None:
        async def coro() -> None:
            raise RuntimeError

        t = asyncio.get_running_loop().create_task(coro())
        # Letting the task move to done, without awaiting it
        while not t.done():
            await asyncio.sleep(0)
        t.exception()
        # pyre-fixme[16]: `Task` has no attribute `was_managed`.
        self.assertTrue(t.was_managed())
        self.assertIsInstance(t.exception(), RuntimeError)
        self.assertTrue(t.done())

    @ignoreAsyncioErrors
    async def test_ignore_asyncio_error(self) -> None:
        async def sub() -> int:
            return 5

        # pyre-ignore[1001]: This is fine we don't await on purpose
        sub()  # don't await

    @ignoreTaskLeaks
    async def test_ignore_task_leaks(self) -> None:
        async def coro() -> None:
            raise RuntimeError

        saved_tasks.append(asyncio.get_running_loop().create_task(coro()))

    async def test_forgotten_tasks_done_no_value(self) -> None:
        asyncio.get_running_loop().create_task(asyncio.sleep(0))
        await asyncio.sleep(0)


@ignoreAsyncioErrors
class IgnoreAsyncioErrorsTestCase(TestCase):
    async def test_ignore_asyncio_error_on_case_class(self) -> None:
        async def sub() -> int:
            return 5

        # pyre-ignore[1001]: This is fine we don't await on purpose
        sub()  # don't await


@ignoreTaskLeaks
class IgnoreTaskLeaksTestCase(TestCase):
    async def test_ignore_task_leaks_on_case_class(self) -> None:
        async def coro() -> None:
            raise RuntimeError

        saved_tasks.append(asyncio.get_running_loop().create_task(coro()))


if __name__ == "__main__":
    unittest.main()
