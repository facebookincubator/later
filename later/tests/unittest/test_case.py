from __future__ import annotations

import asyncio
import unittest
from typing import Any, Optional

from later.unittest import TestCase


saved_task: Optional[asyncio.Task[Any]] = None
saved_done_task: Optional[asyncio.Task[Any]] = None


class TestTestCase(TestCase):
    @unittest.expectedFailure
    async def test_unmanaged_task_created_in_testmethod(self):
        global saved_task
        saved_task = asyncio.get_running_loop().create_task(asyncio.sleep(10))

    async def test_managed_task_done(self):
        global saved_done_task
        saved_done_task = asyncio.get_running_loop().create_task(
            asyncio.sleep(0.5, "test")
        )
        await saved_done_task

    @unittest.expectedFailure
    async def test_garbage_collected_task_during_testmethod(self):
        t = asyncio.get_running_loop().create_task(asyncio.sleep(10))
        t.cancel()
        del t

    async def test_tasks_add_callback(self):
        # If we add a callback and it is run then thats good enough
        # to say the task was managed
        t = asyncio.get_running_loop().create_task(asyncio.sleep(10))
        x = False

        def callback(fut):
            nonlocal x
            x = True

        t.add_done_callback(callback)
        t.cancel()
        await asyncio.sleep(0.1)  # callbacks are scheduled
        self.assertTrue(x, "callback was executed")

    async def test_task_exception(self):
        async def coro():
            raise RuntimeError

        t = asyncio.get_running_loop().create_task(coro())
        # Letting the task move to done, without awaiting it
        while not t.done():
            await asyncio.sleep(0)
        t.exception()
        self.assertTrue(t.was_managed())
        self.assertIsInstance(t.exception(), RuntimeError)
        self.assertTrue(t.done())


if __name__ == "__main__":
    unittest.main()
