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
Task tracking utilities for async test cases.

This module provides :class:`TestTask`, an instrumented asyncio Task subclass
that tracks whether tasks have been properly awaited or otherwise managed.
It is used by :class:`later.unittest.TestCase` to detect task leaks in tests.
"""

from __future__ import annotations

import asyncio
import asyncio.base_tasks
import asyncio.coroutines
import asyncio.futures
import asyncio.log
import asyncio.tasks
import os.path
import reprlib
import traceback
from collections.abc import Callable, Coroutine, Generator, Iterator
from contextvars import Context
from functools import wraps
from typing import TypeVar

_T = TypeVar("_T")


class _BaseTask(asyncio.Task[_T]):
    """Base class for generic Task typing. Uses subscripted Task (Python 3.9+)."""

    pass


class TestTask(_BaseTask[_T]):
    """
    An instrumented asyncio Task that tracks whether it has been managed.

    This class wraps a coroutine as an asyncio Task while tracking whether
    the task result was properly consumed. A task is considered "managed" when:

    - It is awaited (via ``await task``)
    - Its result is retrieved (via ``task.result()``)
    - Its exception is retrieved (via ``task.exception()``)
    - A done callback is added (via ``task.add_done_callback()``)
    - It completes with ``None`` result (fire-and-forget pattern)

    When a TestTask is garbage collected without being managed, it logs
    an error through the event loop's exception handler, which can be
    used by test frameworks to fail tests that leak tasks.

    Attributes:
        _managed: Whether the task has been properly managed.
        _coro_repr: String representation of the wrapped coroutine.
        _creation_stack: Stack trace from where the task was created,
            with asyncio internals filtered out for readability.
    """

    _managed: bool = False
    _coro_repr: str
    _creation_stack: list[traceback.FrameSummary]

    # pyre-ignore[2]: We don't cast *args and **kws as they are passed through
    def __init__(self, coro: Coroutine[object, object, _T], *args, **kws) -> None:
        # pyre-fixme[16]: Module `coroutines` has no attribute `_format_coroutine`.
        self._coro_repr = asyncio.coroutines._format_coroutine(coro)
        super().__init__(coro, *args, **kws)
        self._creation_stack = list(TestTask._filter_creation_stack())
        self._creation_stack.reverse()

    @staticmethod
    def _filter_creation_stack() -> Iterator[traceback.FrameSummary]:
        """
        This removes all the asyncio internal frames since they are not helpful
        """
        asyncio_package = os.path.dirname(asyncio.__file__)
        # Remove all the frames from later
        summary = traceback.extract_stack()[:-3]
        # Filter all frames until we hit a frame not in asyncio, then yield them all.
        filter = True
        for frame in reversed(summary):
            if filter and not frame.filename.startswith(asyncio_package):
                filter = False
            if filter:
                continue
            yield frame

    @reprlib.recursive_repr()
    def __repr__(self) -> str:
        repr_info = asyncio.base_tasks._task_repr_info(self)
        coro = f"coro={self._coro_repr}"
        # Index 2 is the coro slot (after name= which was added in Python 3.8)
        repr_info[2] = coro

        if self._creation_stack:
            frame = self._creation_stack[-1]
            repr_info.append(f"Task Created at: {frame.filename}:{frame.lineno}")

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
