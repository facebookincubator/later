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
import contextvars
import functools
import logging
import threading
from collections.abc import Awaitable, Callable, Coroutine, Hashable, Mapping, Sequence

from functools import partial, wraps
from inspect import isawaitable
from types import TracebackType
from typing import (
    AbstractSet,
    Any,
    cast,
    NewType,
    overload,
    ParamSpec,
    Protocol,
    TypeVar,
    Union,
)
from unittest.mock import Mock

from .event import BiDirectionalEvent


FixerType = Callable[[asyncio.Task], Union[asyncio.Task, Awaitable[asyncio.Task]]]
logger: logging.Logger = logging.getLogger(__name__)
T = TypeVar("T")
TParams = ParamSpec("TParams")

__all__: Sequence[str] = [
    "Watcher",
    "START_TASK",
    "TaskSentinel",
    "cancel",
    "as_task",
    "herd",
]


class TaskSentinel(asyncio.Task):
    """When you need a done task for typing"""

    def __init__(self) -> None:
        fake = Mock()
        asyncio.Future.__init__(self, loop=fake)
        asyncio.Future.set_result(self, None)


async def cancel(fut: asyncio.Future) -> None:
    """
    Cancel a future/task and await for it to cancel.
    If the fut is already done() this is a no-op
    If everything goes well this returns None.

    If this coroutine is cancelled, we wait for the passed in argument to cancel
    but we will raise the CancelledError as per Cancellation Contract, Unless the task
    doesn't cancel correctly then we could raise other exceptions.

    If the task raises an exception during cancellation we re-raise it
    if the task completes instead of cancelling we raise a InvalidStateError
    """
    if fut.done():
        return  # nothing to do
    fut.cancel()
    exc: asyncio.CancelledError | None = None
    while not fut.done():
        shielded = asyncio.shield(fut)
        try:
            await asyncio.wait([shielded])
        except asyncio.CancelledError as ex:
            exc = ex
        finally:
            # Insure we handle the exception/value that may exist on the shielded task
            # This will prevent errors logged to the asyncio logger
            if (
                shielded.done()
                and not shielded.cancelled()
                and not shielded.exception()
            ):
                shielded.result()
    if fut.cancelled():
        if exc is None:
            return
        # we were cancelled also so honor the contract
        raise exc from None
    # Some exception thrown during cancellation
    ex = fut.exception()
    if ex is not None:
        raise ex from None
    # fut finished instead of cancelled, wat?
    raise asyncio.InvalidStateError(
        f"task didn't raise CancelledError on cancel: {fut} had result {fut.result()}"
    )


def as_task(
    func: Callable[TParams, Coroutine[object, object, T]],
) -> Callable[TParams, asyncio.Task[T]]:
    """
    Decorate a function, So that when called it is wrapped in a task
    on the running loop.
    """

    @wraps(func)
    def create_task(*args: TParams.args, **kws: TParams.kwargs) -> asyncio.Task[T]:
        loop = asyncio.get_running_loop()
        return loop.create_task(func(*args, **kws))

    return create_task


# Sentinel Task
START_TASK: asyncio.Task = TaskSentinel()

# ContextVar for Finding an existing Task Watcher
WATCHER_CONTEXT: contextvars.ContextVar[Watcher] = contextvars.ContextVar(
    "WATCHER_CONTEXT"
)


class WatcherError(RuntimeError):
    pass


class Watcher:
    _tasks: dict[asyncio.Future, FixerType | None]
    _scheduled: list[FixerType]
    _tasks_changed: BiDirectionalEvent
    _cancelled: asyncio.Event
    _cancel_timeout: float
    _preexit_callbacks: list[Callable[[], None]]
    _shielded_tasks: dict[asyncio.Task, asyncio.Future]
    # pyre-ignore[13]: loop is initialized in __aenter__
    loop: asyncio.AbstractEventLoop
    running: bool
    done_ok: bool

    @staticmethod
    def get() -> Watcher:
        return WATCHER_CONTEXT.get()

    def __init__(
        self,
        *,
        cancel_timeout: float = 300,
        context: bool = False,
        done_ok: bool = True,
    ) -> None:
        """
        cancel_timeout is the time in seconds we will wait after cancelling all
        the tasks watched by this watcher.

        context is wether to expose this Watcher via contextvars now or at __aenter__
        """
        if context:
            WATCHER_CONTEXT.set(self)
        self._cancel_timeout = cancel_timeout
        self._tasks: dict[asyncio.Future, FixerType | None] = {}
        self._scheduled: list[FixerType] = []
        self._tasks_changed = BiDirectionalEvent()
        self._cancelled = asyncio.Event()
        self._preexit_callbacks = []
        self._shielded_tasks: dict[asyncio.Task, asyncio.Future] = {}
        self.running = False
        self.done_ok = done_ok

    async def _run_scheduled(self) -> None:
        scheduled = self._scheduled
        while scheduled:
            fixer = scheduled.pop()
            task = fixer(START_TASK)
            if not isinstance(task, asyncio.Task) and isawaitable(task):
                task = await task

            if isinstance(task, asyncio.Task):
                self._tasks[task] = fixer
            else:
                raise TypeError(f"{fixer}(START_TASK) failed to return a task.")

    async def unwatch(
        self,
        task: asyncio.Task = START_TASK,
        fixer: FixerType | None = None,
        *,
        shield: bool = False,
    ) -> bool:
        """
        The ability to unwatch a task, by task or fixer
        This is a coroutine to insure the watcher has re-watched the tasks list

        If the task was shielded then you need to specify here so we can find
        the shield and remove it from the watch list.

        When unwatching a fixer, if the returned task is not the same
        as the one passed in we will cancel it, and await it.
        """

        async def tasks_changed() -> None:
            if self.running:
                await self._tasks_changed.set()

        if shield:
            if task in self._shielded_tasks:
                shield_task = self._shielded_tasks.pop(task)
                # no task left behind, lets cancel it for safety
                await cancel(shield_task)
                del self._tasks[shield_task]
                await tasks_changed()
                return True
        elif fixer is not None:
            for t, fix in tuple(self._tasks.items()):
                if fix is fixer:
                    del self._tasks[t]
                    await tasks_changed()
                    if t is not task:
                        await cancel(t)
                    return True
        elif task is not START_TASK:
            if task in self._tasks:
                del self._tasks[task]
                await tasks_changed()
                return True
        return False

    def watch(
        self,
        task: asyncio.Task = START_TASK,
        fixer: FixerType | None = None,
        *,
        shield: bool = False,
    ) -> None:
        """
        Add a task to be watched by the watcher
        You can also attach a fixer co-routine or function to be used to fix a
        task that has died.

        The fixer will be passed the failed task, and is expected to return a working
        task, or raise if that is impossible.

        You can also just pass in the fixer and we will use it to create the task
        to be watched.  The fixer will be passed a dummy task singleton:
        `later.task.START_TASK`

        shield argument lets you watch a task, but not cancel it in this watcher.
        Useful for triggering on task failures, but not managing said task.
        """
        # Watching a coro, leads to a confusing error deep in watcher
        # so use runtime checks not just static types.
        if not isinstance(task, asyncio.Task):
            raise TypeError("only asyncio.Task objects can be watched.")

        if task is START_TASK:
            if not fixer:
                raise ValueError("fixer must be specified when using START_TASK.")
            self._scheduled.append(fixer)
        elif shield:
            if fixer:
                raise ValueError("`fixer` can not be used with shield=True")
            # pyre-fixme[1001]: Awaitable assigned to `self._shielded_tasks` is
            #  never awaited.
            self._shielded_tasks[task] = asyncio.shield(task)
            self._tasks[self._shielded_tasks[task]] = None
        else:
            self._tasks[task] = fixer
        self._tasks_changed.set_nowait()

    def create_task(
        self,
        coro: Coroutine[object, object, T],
        **kws: Any,
    ) -> asyncio.Task[T]:
        t = asyncio.create_task(coro, **kws)
        self.watch(t)
        return t

    def cancel(self) -> None:
        """
        Stop the watcher and cause it to cancel all the tasks in its care.
        """
        self._cancelled.set()

    def add_preexit_callback(
        self, callback: Callable[..., None], *args: Any, **kws: Any
    ) -> None:
        self._preexit_callbacks.append(partial(callback, *args, **kws))

    def _run_preexit_callbacks(self) -> None:
        for callback in self._preexit_callbacks:
            try:
                callback()
            except Exception as e:
                logger.exception(
                    f"ignoring exception from pre-exit callback {callback}: {e}"
                )

    async def __aenter__(self) -> Watcher:
        WATCHER_CONTEXT.set(self)
        self.loop = asyncio.get_running_loop()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        cancel_task: asyncio.Task = self.loop.create_task(self._cancelled.wait())
        changed_task: asyncio.Task = START_TASK
        try:
            # an exception was raised in the body of the watcher.
            # just return, cancel any tasks.
            if exc is not None:
                return False
            self.running = True
            while not self._cancelled.is_set():
                if self._scheduled:
                    await self._run_scheduled()
                if changed_task is START_TASK or changed_task.done():
                    changed_task = self.loop.create_task(self._tasks_changed.wait())
                if not self._tasks:
                    return False  # There are no tasks just exit.
                done, pending = await asyncio.wait(
                    [cancel_task, changed_task, *self._tasks.keys()],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_task in done:
                    break  # Don't bother doing fixes just break out
                for task in done:
                    task = cast(asyncio.Task, task)
                    if task is changed_task:
                        continue
                    else:
                        await self._fix_task(task)
        finally:
            self.running = False
            self._run_preexit_callbacks()
            await self._event_task_cleanup(cancel_task, changed_task)
            await self._handle_cancel()
            self._tasks.clear()
            self._shielded_tasks.clear()
        return False

    async def _event_task_cleanup(self, *tasks: asyncio.Task) -> None:
        for task in tasks:
            if task is not START_TASK:
                await cancel(task)

    async def _fix_task(self, task: asyncio.Task) -> None:
        # Insure we "retrieve" the result of failed tasks
        exc = task.exception()
        if exc is None:
            task.result()
            if self.done_ok:
                # clean up the task is done. And thats okay.
                del self._tasks[task]
                return
        fixer = self._tasks[task]
        if fixer is None:
            raise RuntimeError(f"{task} finished and there is no fixer!") from exc
        new_task = fixer(task)
        if not isinstance(new_task, asyncio.Task) and isawaitable(new_task):
            new_task = await new_task

        if isinstance(new_task, asyncio.Task):
            del self._tasks[task]
            self._tasks[new_task] = fixer
        else:
            raise TypeError(
                f"{fixer}(task) failed to return a task, returned:" f"{new_task}!"
            ) from exc

    async def _handle_cancel(self) -> None:
        tasks = [task for task in self._tasks if not task.done()]
        if not tasks:
            return

        # pyre-fixme[1001]: Awaitable assigned to `task` is never awaited.
        for task in tasks:
            task.cancel()

        done, pending = await asyncio.wait(tasks, timeout=self._cancel_timeout)
        bad_tasks: list[asyncio.Future] = []
        for task in done:
            if task.cancelled():
                continue
            if task.exception() is not None:
                bad_tasks.append(task)

        bad_tasks.extend(pending)

        if bad_tasks:
            raise WatcherError(
                "The following tasks didn't cancel cleanly or at all!", bad_tasks
            )


CacheKey = NewType("CacheKey", tuple[Hashable, ...])
ArgID = Union[int, str]


class _CountTask:
    """So herd can track herd size and task together for cancellation"""

    task: asyncio.Task | None = None
    count: int = 0


def _get_local(local: threading.local, field: str) -> dict[CacheKey, object]:
    """
    helper for attempting to fetch a named attr from a threading.local
    """
    try:
        return cast(dict[CacheKey, object], getattr(local, field))
    except AttributeError:
        container: dict[CacheKey, object] = {}
        setattr(local, field, container)
        return container


def _build_key(
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    ignored_args: AbstractSet[ArgID] | None = None,
) -> CacheKey:
    """
    Build a key for caching Hashable args and kwargs.
    Allow for not including certain fields from args or kwargs
    """
    if not ignored_args:
        return CacheKey((args, tuple(sorted(kwargs.items()))))

    # If we do want to ignore something then do so
    return CacheKey(
        (
            tuple((value for idx, value in enumerate(args) if idx not in ignored_args)),
            tuple(
                item for item in sorted(kwargs.items()) if item[0] not in ignored_args
            ),
        )
    )


class AsyncCallable(Protocol):
    def __call__(
        self, fn: Callable[TParams, Coroutine[object, object, T]]
    ) -> Callable[TParams, Coroutine[object, object, T]]:  # pragma: nocover
        ...


@overload
def herd(
    fn: Callable[TParams, Coroutine[object, object, T]],
    *,
    ignored_args: AbstractSet[ArgID] | None = None,
) -> Callable[TParams, Coroutine[object, object, T]]:  # pragma: nocover
    ...


@overload
def herd(
    fn: None = None,
    *,
    ignored_args: AbstractSet[ArgID] | None = None,
) -> AsyncCallable:  # pragma: nocover
    ...


def herd(
    fn: Callable[TParams, Coroutine[object, object, T]] | None = None,
    *,
    ignored_args: AbstractSet[ArgID] | None = None,
) -> (
    Callable[TParams, Coroutine[object, object, T]]
    | Callable[
        [Callable[TParams, Coroutine[object, object, T]]],
        Callable[TParams, Coroutine[object, object, T]],
    ]
):
    """
    Provide a simple thundering herd protection as a decorator.
    if requests comes in while and existing request with those same args is pending,
    wait for the pending request and return its results.

    ignored_args are arguments that should be ignored for matching with
    existing requests. Use arg position or kwargs name.
    Example: a client arg for when multiple clients exists but the request hits the same
    backend.

    Each member of the herd is "shielded" from cancellation effecting other herd members
    """

    def decorator(
        fn: Callable[TParams, Coroutine[object, object, T]],
    ) -> Callable[TParams, Coroutine[object, object, T]]:
        local: threading.local = threading.local()

        @functools.wraps(fn)
        async def wrapped(*args: TParams.args, **kwargs: TParams.kwargs) -> T:
            pending = cast(dict[CacheKey, _CountTask], _get_local(local, "pending"))
            request = _build_key(tuple(args), kwargs, ignored_args)
            count_task = pending.setdefault(request, _CountTask())
            count_task.count += 1
            task = count_task.task  # thanks pyre
            if task is None:
                count_task.task = task = asyncio.create_task(fn(*args, **kwargs))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                if count_task.count == 1:
                    await cancel(task)
                raise  # always re-raise CancelledError
            finally:
                count_task.count -= 1
                # Lets destroy the herd on last member exit or
                # First success member exit. This is to mirror the original
                # herd behavior that tore down the herd after the original call exited
                if count_task.count == 0 or not task.cancelled():
                    if request in pending and pending[request] is count_task:
                        del pending[request]

        return wrapped

    if fn and callable(fn):
        return decorator(fn)

    return decorator
