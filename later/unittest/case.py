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
import reprlib
import sys
import unittest.mock as mock
import weakref
from collections.abc import Callable, Coroutine, Generator
from contextvars import Context
from functools import wraps
from typing import AbstractSet, Generic, TYPE_CHECKING, TypeVar
from unittest import IsolatedAsyncioTestCase as AsyncioTestCase

# Do not remove, even if Pyright complains about it.
# Setting global __unittest helps preserve proper tracebacks pointing to the specific error line when the test fails.
__unittest = True

_T = TypeVar("_T")
_F = TypeVar("_F", bound=Callable[..., object])
_IGNORE_TASK_LEAKS_ATTR = "__later_testcase_ignore_tasks__"
_IGNORE_AIO_ERRS_ATTR = "__later_testcase_ignore_asyncio__"
atleastpy38: bool = sys.version_info[:2] >= (3, 8)
_unmanaged_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()

# We can get rid of this when we drop support for 3.8
if TYPE_CHECKING:  # pragma: nocover

    class _BaseTask(asyncio.Task[_T]):
        pass

else:

    class _BaseTask(Generic[_T], asyncio.Task):
        pass


class TestTask(_BaseTask[_T]):
    _managed: bool = False
    _coro_repr: str

    # pyre-ignore[2]: We don't case *args and **kws has no type they are passed through
    def __init__(self, coro: Coroutine[object, object, _T], *args, **kws) -> None:
        # pyre-fixme[16]: Module `coroutines` has no attribute `_format_coroutine`.
        self._coro_repr = asyncio.coroutines._format_coroutine(coro)
        _unmanaged_tasks.add(self)
        super().__init__(coro, *args, **kws)

    @reprlib.recursive_repr()
    def __repr__(self) -> str:
        repr_info = asyncio.base_tasks._task_repr_info(self)
        coro = f"coro={self._coro_repr}"
        if atleastpy38:  # py3.8 added name=
            repr_info[2] = coro  # pragma: nocover
        else:
            repr_info[1] = coro  # pragma: nocover
        return f"<{self.__class__.__name__} {' '.join(repr_info)}>"

    def _mark_managed(self) -> None:
        self._managed = True

    def __await__(self) -> Generator[object, None, _T]:
        self._mark_managed()
        return super().__await__()

    def result(self) -> _T:
        if self.done():
            self._mark_managed()
        return super().result()

    def exception(self) -> BaseException | None:
        if self.done():
            self._mark_managed()
        return super().exception()

    # pyre-fixme[14]: `add_done_callback` overrides method defined in `Future`
    #  inconsistently.
    def add_done_callback(
        self, fn: Callable[[asyncio.Task], None], *, context: Context | None = None
    ) -> None:
        @wraps(fn)
        def mark_managed(fut: asyncio.Task) -> None:
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


def task_factory(
    loop: asyncio.AbstractEventLoop,
    coro: Coroutine[object, object, object],
    **kws: object,
) -> TestTask[object]:
    task = TestTask(coro, loop=loop, **kws)
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
            loop = self._asyncioRunner.get_loop()
        else:  # pragma: nocover
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

        if sys.version_info < (3, 11):  # pragma: nocover
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
