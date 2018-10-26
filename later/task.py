import asyncio
import logging
from functools import partial
from inspect import isawaitable
from types import TracebackType
from typing import (
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
    cast,
)


FixerType = Callable[[asyncio.Task], Union[asyncio.Task, Awaitable[asyncio.Task]]]
logger = logging.getLogger(__name__)

__all__: Sequence[str] = ["Watcher", "START_TASK"]

# Sentinel Task
START_TASK: asyncio.Task = asyncio.get_event_loop().create_task(asyncio.sleep(0))


class WatcherError(RuntimeError):
    pass


class Watcher:
    _tasks: Dict[asyncio.Task, Optional[FixerType]]
    _scheduled: List[FixerType]
    _tasks_changed: asyncio.Event
    _cancelled: asyncio.Event
    _cancel_timeout: float
    _preexit_callbacks: List[Callable[[], None]]
    loop: asyncio.AbstractEventLoop

    def __init__(self, cancel_timeout: float = 300) -> None:
        """
        cancel_timeout is the time in seconds we will wait after cancelling all
        the tasks watched by this watcher.
        """
        self._cancel_timeout = cancel_timeout
        self._tasks = {}
        self._scheduled = []
        self._tasks_changed = asyncio.Event()
        self._cancelled = asyncio.Event()
        self._preexit_callbacks = []

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

    def watch(
        self, task: asyncio.Task = START_TASK, fixer: Optional[FixerType] = None
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
        """
        if task is START_TASK:
            if not fixer:
                raise ValueError("fixer must be specified when using START_TASK.")
            self._scheduled.append(fixer)
        else:
            self._tasks[task] = fixer
        self._tasks_changed.set()

    def cancel(self) -> None:
        """
        Stop the watcher and cause it to cancel all the tasks in its care.
        """
        self._cancelled.set()

    def add_preexit_callback(self, callback: Callable[..., None], *args, **kws) -> None:
        self._preexit_callbacks.append(partial(callback, *args, **kws))

    def _run_preexit_callbacks(self) -> None:
        for callback in self._preexit_callbacks:
            try:
                callback()
            except Exception as e:
                logger.exception(
                    f"ignoring exception from pre-exit callback {callback}: {e}"
                )

    async def __aenter__(self) -> "Watcher":
        self.loop = asyncio.get_event_loop()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        cancel_task: asyncio.Task = self.loop.create_task(self._cancelled.wait())
        changed_task: asyncio.Task = START_TASK
        try:
            while not self._cancelled.is_set():
                if self._scheduled:
                    await self._run_scheduled()
                if changed_task is START_TASK or changed_task.done():
                    changed_task = self.loop.create_task(self._tasks_changed.wait())
                try:
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

                except asyncio.CancelledError:
                    self.cancel()
        finally:
            self._run_preexit_callbacks()
            cancel_task.cancel()
            changed_task.cancel()
            await self._handle_cancel()
        return False

    async def _fix_task(self, task: asyncio.Task) -> None:
        fixer = self._tasks[task]
        if fixer is None:
            raise RuntimeError(f"{task} finished and there is no fixer!")
        new_task = fixer(task)
        if not isinstance(new_task, asyncio.Task) and isawaitable(new_task):
            new_task = await new_task

        if isinstance(new_task, asyncio.Task):
            del self._tasks[task]
            self._tasks[new_task] = fixer
        else:
            raise TypeError(
                f"{fixer}(task) failed to return a task, returned:" f"{new_task}!"
            )

    async def _handle_cancel(self):
        if not self._tasks:
            return

        for task in self._tasks:
            task.cancel()

        done, pending = await asyncio.wait(
            self._tasks.keys(), timeout=self._cancel_timeout
        )
        bad_tasks: List[asyncio.Task] = []
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
