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
This module provides a pool of event loops like IG does so we create the least number of loops.
And provides some primatives for supporting nested loops.
"""

from __future__ import annotations

import asyncio
import asyncio.events
import asyncio.events as asyncio_events
import logging
import os
import threading
from asyncio import AbstractEventLoop
from asyncio.events import (
    _get_running_loop as get_running_loop,
    _set_running_loop,
    new_event_loop,
)
from collections import deque
from contextlib import contextmanager
from os import getpid
from typing import Awaitable, Iterator, TypeVar

__all__: list[str] = ["run_nested"]

T = TypeVar("T")
ALLOW_NESTED_LOOPS: bool = os.environ.get("ALLOW_NESTED_LOOPS", "1") == "1"
logger: logging.Logger = logging.getLogger(__name__)
PID: int = getpid()

try:  # pragma: no cover
    # pyre-ignore[21]: Suppress error that type checker can't import these
    from uvloop import Loop as uvloop  # @manual
except ImportError:
    uvloop = type(None)

try:  # pragma: no cover
    # pyre-ignore[21]: Suppress error that type checker can't import these
    from ig_uvloop.loop import Loop as ig_uvloop  # @manual
except ImportError:
    ig_uvloop = type(None)


def cancel_all_tasks(
    loop: AbstractEventLoop,
    timeout: float = 0.1,  # 100ms should be enough
) -> None:
    to_cancel = asyncio.all_tasks(loop)
    if not to_cancel:
        return

    for task in to_cancel:
        task.cancel()

    loop.run_until_complete(
        asyncio.wait(
            to_cancel,
            timeout=timeout,
        )
    )

    for task in to_cancel:
        if task.cancelled():
            continue

        if task.done():
            if task.exception() is not None:
                loop.call_exception_handler(
                    {
                        "message": "unhandled exception during task cancellation in runner.cancel_all_tasks()",
                        "exception": task.exception(),
                        "task": task,
                    }
                )

            else:
                loop.call_exception_handler(
                    {
                        "message": "failed to raise a asyncio.CancelledError when cancelled in runner.cancel_all_tasks()",
                        "task": task,
                    }
                )
        else:
            loop.call_exception_handler(
                {
                    "message": "task did not cancel after runner.cancel_all_tasks()",
                    "task": task,
                }
            )


class _ThreadLocalPool(threading.local):
    stack: deque[AbstractEventLoop]
    dirty_loop: AbstractEventLoop | None = None

    def __init__(self) -> None:
        self.stack = deque()
        self.dirty_loop = None

    def atFork(self) -> None:  # pragma: no cover
        # Fork, all kids out of the pool
        self.stack.clear()
        self.dirty_loop = None
        global PID
        PID = getpid()

    @staticmethod
    def cleanup_loop(loop: AbstractEventLoop) -> None:
        # Clean the loop
        if not isinstance(loop, (ig_uvloop, uvloop)):
            # If its not uvloop we can cleanup asyncgens
            loop.run_until_complete(loop.shutdown_asyncgens())
            # pyre-ignore[16]: Suppress error that shutdown_asyncgens was called
            loop._asyncgens_shutdown_called = False
            cancel_all_tasks(loop)
            # Lets throw away the default executor if it exists
            # pyrefly: ignore [missing-attribute]
            if (executor := loop._default_executor) is not None:
                executor.shutdown(wait=False, cancel_futures=True)
                # pyrefly: ignore [bad-assignment]
                loop._default_executor = None
        else:  # pragma: no cover
            cancel_all_tasks(loop)

    def return_loop(self, loop: AbstractEventLoop) -> None:
        "Give a loop back to the pool"
        # a dirty loop is getting burried in the stack, clean it up.
        if dirty_loop := self.dirty_loop:
            if not (dirty_loop.is_closed() or dirty_loop.is_running()):
                # This takes place inside run_nested, so we never need to pause the existing loop
                _ThreadLocalPool.cleanup_loop(dirty_loop)
                self.dirty_loop = None
        self.stack.append(loop)
        # This loop is "dirty" and needs to be cleaned up if burried in the stack
        self.dirty_loop = loop

    def borrow_loop(self) -> AbstractEventLoop:
        "Returns a loop 'borrowed' from the pool, order LIFO"
        loop: AbstractEventLoop
        stack = self.stack
        # Any loop that is not "ready" is considered borked and discarded
        while stack:
            loop = stack.pop()
            if loop is self.dirty_loop:
                # We can clean this up when loop is returned.
                self.dirty_loop = None
            if loop.is_running():
                logger.error("Running eventloop in pool, discarding")
                continue
            if loop.is_closed():
                logger.error("Closed eventloop in pool, discarding")
                continue
            return loop
        # We need to create a loop since the pool is empty of ready loops
        loop = new_event_loop()
        return loop

    def __len__(self) -> int:
        """This is mostly for unittest to quickly see the loop count"""
        return len(self.stack)


_thread_local_pool: _ThreadLocalPool = _ThreadLocalPool()


# At fork, reinitialize the `_thread_local_pool` so it is useable in the child
if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_thread_local_pool.atFork)


def _get_event_loop() -> AbstractEventLoop | None:
    """
    Return the set event loop or None, will not return the running loop
    """
    # This uses implementation details of asyncio, that could change in python 3.16
    # But it prevents the warning messages about not having a set event loop
    # pyre-ignore[16]: Suppress error about asyncio.events._event_loop_policy
    if (policy := getattr(asyncio_events, "_event_loop_policy", False)) is not False:
        if policy is None:  # pragma: no cover
            return None
        try:
            # pyrefly: ignore [missing-attribute]
            return policy._local._loop
        except AttributeError:  # pragma: no cover
            # https://fburl.com/code/llqrtjvq
            # This is some custom policy, lets call its get_event_loop
            # pyrefly: ignore [missing-attribute]
            return policy.get_event_loop()
    else:  # pragma: no cover
        # This is 3.16 and we are cooked.
        # TODO(T192006199): fried fix this for 3.16 which has different set_event_loop/get_event_loop behaviors
        return None


@contextmanager
def pause_existing_loop() -> Iterator[None]:
    # We need to clear out the running event loop so we can start a new one
    # _get_running_loop() will return the current event loop if it exists without raising an exception
    running_loop = get_running_loop()
    if not running_loop:
        # No running loop to pause; nothing to leave or restore.
        yield
        return
    if not ALLOW_NESTED_LOOPS:
        raise RuntimeError(
            "Nested event loops are not allowed by ENV variable ALLOW_NESTED_LOOPS"
        )

    current_task = asyncio.current_task()

    # Python 3.14+ tracks task execution state separately; we must leave the
    # current task before running a nested loop
    if current_task is not None:
        # pyrefly: ignore [bad-argument-type]
        asyncio._leave_task(running_loop, current_task)
    # _set_running_loop() will set the current event loop
    _set_running_loop(None)
    try:
        yield
    finally:
        # Restore the previously running event loop
        _set_running_loop(running_loop)
        if current_task is not None:
            # pyrefly: ignore [bad-argument-type]
            asyncio._enter_task(running_loop, current_task)


def run_nested(awaitable: Awaitable[T]) -> T:
    """
    This will execute an awaitable using either the current loop if its not running/closed or a loop
    from a "freelist" of eventloops.  This idea came from IG's wait_for
    """
    # Track what the pid was when we started
    pid: int = PID
    rloop: AbstractEventLoop | None = get_running_loop()

    # Check the legacy "set" event loop for a "default" loop for the thread
    if (loop := _get_event_loop()) is not None and (
        loop.is_running() or loop.is_closed()
    ):
        loop = None

    if rloop is None:
        # Fast path: nothing is running on this thread, so there is no running
        # loop or task to pause, and run_until_complete manages the running-loop
        # state itself.
        if loop is not None:
            return loop.run_until_complete(awaitable)
        loop = _thread_local_pool.borrow_loop()
        # Do not inherit a previous borrower's task factory.
        loop.set_task_factory(None)
        try:
            return loop.run_until_complete(awaitable)
        finally:
            # The worst case we get a fork in the run_until_complete and try to put the parent
            # loop into the child pool. This global is updated in child after fork
            if pid == PID:
                _thread_local_pool.return_loop(loop)

    # A loop is already running on this thread, so we must pause it (and the
    # current task) before driving the inner loop.
    borrowed: bool = False
    if loop is None:
        loop = _thread_local_pool.borrow_loop()
        borrowed = True
        # This is the old carve out for request context. Copy the running loop's
        # task factory (which may be None) so we never inherit a stale one.
        loop.set_task_factory(rloop.get_task_factory())

    with pause_existing_loop():
        try:
            return loop.run_until_complete(awaitable)
        finally:
            # return_loop (and its lazy cleanup) must run while the outer loop is
            # still paused, so any cleanup run_until_complete sees no running loop.
            if borrowed and pid == PID:
                _thread_local_pool.return_loop(loop)
