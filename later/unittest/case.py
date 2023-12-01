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
# under the License.
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
import reprlib
import sys
import unittest.mock as mock
import weakref
from functools import wraps
from typing import Any, Callable, TypeVar


if sys.version_info[:2] >= (3, 9):  # pragma: nocover
    from unittest import IsolatedAsyncioTestCase as AsyncioTestCase
else:  # pragma: nocover
    from .backport.async_case import IsolatedAsyncioTestCase as AsyncioTestCase


_F = TypeVar("_F", bound=Callable[..., Any])
_IGNORE_TASK_LEAKS_ATTR = "__later_testcase_ignore_tasks__"
_IGNORE_AIO_ERRS_ATTR = "__later_testcase_ignore_asyncio__"
atleastpy38: bool = sys.version_info[:2] >= (3, 8)
_unmanaged_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()


class TestTask(asyncio.Task):
    _managed: bool = False
    _coro_repr: str

    def __init__(self, coro, *args, **kws) -> None:
        # pyre-fixme[16]: Module `coroutines` has no attribute `_format_coroutine`.
        self._coro_repr = asyncio.coroutines._format_coroutine(coro)
        _unmanaged_tasks.add(self)
        super().__init__(coro, *args, **kws)

    @reprlib.recursive_repr()
    def __repr__(self) -> str:
        # pyre-fixme[16]: `TestTask` has no attribute `_repr_info`.
        repr_info = asyncio.base_tasks._task_repr_info(self)
        coro = f"coro={self._coro_repr}"
        if atleastpy38:  # py3.8 added name=
            repr_info[2] = coro  # pragma: nocover
        else:
            repr_info[1] = coro  # pragma: nocover
        return f"<{self.__class__.__name__} {' '.join(repr_info)}>"

    def _mark_managed(self):
        self._managed = True

    def __await__(self):
        self._mark_managed()
        return super().__await__()

    def result(self):
        if self.done():
            self._mark_managed()
        return super().result()

    def exception(self):
        if self.done():
            self._mark_managed()
        return super().exception()

    def add_done_callback(self, fn, *, context=None) -> None:
        @wraps(fn)
        def mark_managed(fut):
            self._mark_managed()
            return fn(fut)

        super().add_done_callback(mark_managed, context=context)

    def was_managed(self) -> bool:
        if self._managed:
            return True
        # If the task is done() and the result is None, let it pass as managed
        # We use super here so we don't manage ourselves.
        return (
            self.done()
            and not self.cancelled()
            and not super().exception()
            and super().result() is None
        )

    def __del__(self) -> None:
        # So a pattern is to create_task, and not save the results.
        # we accept that as long as there was no result other than None
        # thrift-py3 uses this pattern to call rpc methods in ServiceInterfaces
        # where any result/execption is returned to the remote client.
        if not self.was_managed():
            context = {
                "task": self,
                "message": (
                    "Task was destroyed but never awaited!, "
                    f"WrappedCoro: {self._coro_repr}"
                ),
            }
            # pyre-fixme[16]: `TestTask` has no attribute `_source_traceback`.
            if self._source_traceback:
                context["source_traceback"] = self._source_traceback
            self._loop.call_exception_handler(context)
        super().__del__()


def task_factory(loop, coro, **kws) -> TestTask:
    task = TestTask(coro, loop=loop, **kws)
    return task


def all_tasks(loop):
    # This is a copy of asyncio.all_task but returns even done tasks
    # so we can see if they were awaited instead of ignored

    # This is copied from the guts of asyncio.all_tasks
    # Looping the WeakSet since it is possible it fails during iteration
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
    def _callTestMethod(self, testMethod) -> None:
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
            loop = self._asyncioRunner.get_loop()
        else:
            # pyre-fixme[16]: `TestCase` has no attribute `_asyncioTestLoop`.
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

        if sys.version_info < (3, 11):
            # Lets join the queue to insure all the tasks created by this case
            # are cleaned up
            # pyre-fixme[16]: `TestCase` has no attribute `_asyncioCallsQueue`.
            loop.run_until_complete(self._asyncioCallsQueue.join())
        left_over_tasks = set(all_tasks(loop)) - set(start_tasks)
        for task in list(left_over_tasks):
            if isinstance(task, TestTask) and task.was_managed():
                left_over_tasks.remove(task)
        if left_over_tasks and not ignore_tasks:
            self.assertEqual(set(), left_over_tasks, "left over un-awaited tasks!")
        if error.called and not ignore_error:
            errors = "\n\n".join(c[0][0] for c in error.call_args_list)
            self.fail(f"asyncio logger.error() was called!\n{errors}")
