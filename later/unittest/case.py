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
"""
This TestCase attempts to track all tasks so that they are ensured to have
been awaited. Any time asyncio calls logger.error() it is considered a
test failure.
"""

from __future__ import annotations

import asyncio
import asyncio.base_tasks
import asyncio.coroutines
import asyncio.futures
import asyncio.log
import asyncio.tasks
import sys
import traceback
import unittest.mock as mock
import weakref
from collections.abc import Callable, Coroutine
from typing import AbstractSet, TypeVar
from unittest import IsolatedAsyncioTestCase as AsyncioTestCase

from .test_task import TestTask

# Do not remove, even if Pyright complains about it.
# Setting global __unittest helps preserve proper tracebacks pointing to the specific error line when the test fails.
__unittest = True

_F = TypeVar("_F", bound=Callable[..., object])
_IGNORE_TASK_LEAKS_ATTR = "__later_testcase_ignore_tasks__"
_IGNORE_AIO_ERRS_ATTR = "__later_testcase_ignore_asyncio__"
atleastpy38: bool = sys.version_info[:2] >= (3, 8)
_unmanaged_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()


def task_factory(
    loop: asyncio.AbstractEventLoop,
    coro: Coroutine[object, object, object],
    **kws: object,
) -> TestTask[object]:
    task = TestTask(coro, loop=loop, **kws)
    _unmanaged_tasks.add(task)
    return task


def all_tasks(loop: asyncio.AbstractEventLoop) -> AbstractSet[asyncio.Task]:
    # This is a copy of asyncio.all_task but returns even done tasks
    # so we can see if they were awaited instead of ignored

    # This is copied from the guts of asyncio.all_tasks
    # Looping the WeakSet since it is possible it fails during iteration
    # pyre-ignore[16]: Module `asyncio.futures` has no attribute `_get_loop`
    _get_loop = asyncio.futures._get_loop
    i = 0
    while True:
        try:
            tasks = list(_unmanaged_tasks)
        except RuntimeError:  # pragma: nocover
            i += 1
            if i >= 1000:
                raise
        else:
            break
    return {t for t in tasks if _get_loop(t) is loop}


def ignoreAsyncioErrors(test_item: _F) -> _F:
    """Test is allowed to cause Asyncio Error Logs"""
    setattr(test_item, _IGNORE_AIO_ERRS_ATTR, True)
    return test_item


def ignoreTaskLeaks(test_item: _F) -> _F:
    """Test is allowed to leak tasks"""
    setattr(test_item, _IGNORE_TASK_LEAKS_ATTR, True)
    return test_item


class TestCase(AsyncioTestCase):
    def _callTestMethod(self, testMethod: Callable[..., None]) -> None:
        ignore_error = getattr(
            self,
            _IGNORE_AIO_ERRS_ATTR,
            getattr(testMethod, _IGNORE_AIO_ERRS_ATTR, False),
        )
        ignore_tasks = getattr(
            self,
            _IGNORE_TASK_LEAKS_ATTR,
            getattr(testMethod, _IGNORE_TASK_LEAKS_ATTR, False),
        )
        if sys.version_info >= (3, 11):  # pragma: nocover
            # pyre-fixme[16]: `TestCase` has no attribute `_asyncioRunner`.
            loop = self._asyncioRunner.get_loop()
        else:  # pragma: nocover
            loop = self._asyncioTestLoop
        if not ignore_tasks:
            # install our own task factory for monitoring usage
            loop.set_task_factory(task_factory)

        # Track existing tasks
        start_tasks = all_tasks(loop)
        # Setup a patch for the asyncio logger
        real_logger = asyncio.log.logger.error
        with mock.patch.object(
            asyncio.log.logger, "error", side_effect=real_logger
        ) as error:
            # pyre-fixme[16]: `AsyncioTestCase` has no attribute `_callTestMethod`.
            super()._callTestMethod(testMethod)

        if sys.version_info < (3, 11):  # pragma: nocover
            # Lets join the queue to insure all the tasks created by this case
            # are cleaned up
            loop.run_until_complete(self._asyncioCallsQueue.join())
        left_over_tasks = set(all_tasks(loop)) - set(start_tasks)
        for task in list(left_over_tasks):
            if isinstance(task, TestTask) and task.was_managed():
                left_over_tasks.remove(task)
        if left_over_tasks and not ignore_tasks:
            errors = "\n".join(
                [
                    f"{task!r}\nTraceback (most recent call last):\n{''.join(traceback.format_list(task._creation_stack))}\n"
                    for task in left_over_tasks
                    if isinstance(task, TestTask)
                ]
            )
            self.fail(
                f"left over un-awaited tasks:\n{errors if errors else left_over_tasks}"
            )

        if error.called and not ignore_error:
            errors = "\n\n".join(c[0][0] for c in error.call_args_list)
            self.fail(f"asyncio logger.error() was called!\n{errors}")
