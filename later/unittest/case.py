# Copyright 2019 Facebook
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
# under the License.
"""
This TestCase attempts to track all tasks so that they are ensured to have
been awaited. Any time asyncio calls logger.error() it is considered a
test failure.
"""
from __future__ import annotations

import asyncio
import asyncio.futures
import asyncio.log
import asyncio.tasks
import unittest.mock as mock
from functools import wraps

from .backport.async_case import IsolatedAsyncioTestCase as AsyncioTestCase


class TestTask(asyncio.Task):
    _managed: bool = False

    def __await__(self):
        self._managed = True
        return super().__await__()

    def result(self):
        if self.done():
            self._managed = True
        return super().result()

    def exception(self):
        if self.done():
            self._managed = True
        return super().exception()

    def add_done_callback(self, fn, *, context=None):
        @wraps(fn)
        def mark_managed(fut):
            self._managed = True
            return fn(fut)

        super().add_done_callback(mark_managed, context=context)

    def was_managed(self):
        return self._managed

    def __del__(self):
        context = {"task": self, "message": "Task was destroyed but never awaited!"}
        if not self.was_managed():
            self._loop.call_exception_handler(context)
        super().__del__()


def task_factory(loop, coro):
    return TestTask(coro, loop=loop)


def all_tasks(loop):
    # This is a copy of asyncio.all_task but returns even done tasks
    # so we can see if they were awaited instead of ignored

    # This is copied from the guts of asyncio.all_tasks
    # Looping the WeakSet since it is possible it fails during iteration
    _all_tasks = asyncio.tasks._all_tasks
    _get_loop = asyncio.futures._get_loop
    i = 0
    while True:
        try:
            tasks = list(_all_tasks)
        except RuntimeError:  # pragma: nocover
            i += 1
            if i >= 1000:
                raise
            else:
                break
        return {t for t in tasks if _get_loop(t) is loop}


class TestCase(AsyncioTestCase):
    def _callTestMethod(self, testMethod):
        loop = self._asyncioTestLoop
        # install our own task factory for monitoring usage
        loop.set_task_factory(task_factory)
        # Track existing tasks
        start_tasks = all_tasks(loop)
        # Setup a patch for the asyncio logger
        real_logger = asyncio.log.logger.error
        with mock.patch.object(
            asyncio.log.logger, "error", side_effect=real_logger
        ) as error:
            super()._callTestMethod(testMethod)
            if error.called:
                self.fail(f"asyncio logger.error() was called!\n{error.call_args_list}")

        # Lets join the queue to insure all the tasks created by this case
        # are cleaned up
        loop.run_until_complete(self._asyncioCallsQueue.join())
        left_over_tasks = set(all_tasks(loop)) - set(start_tasks)
        for task in list(left_over_tasks):
            if isinstance(task, TestTask) and task.was_managed():
                left_over_tasks.remove(task)
        if left_over_tasks:
            self.assertEqual(set(), left_over_tasks, "left over un-awaited tasks!")
