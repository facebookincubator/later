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

import asyncio
import functools
import logging
import sys
import time

from typing import Any, Callable, Coroutine, Literal, overload, ParamSpec, TypeVar

if sys.version_info >= (3, 11):  # pragma: no cover
    from asyncio import timeout as timeout_context
else:  # pragma: no cover
    from async_timeout import timeout as timeout_context

_T1 = TypeVar("_T1")
_T2 = TypeVar("_T2")
_T3 = TypeVar("_T3")
_T4 = TypeVar("_T4")
_T5 = TypeVar("_T5")
_T6 = TypeVar("_T6")
T = TypeVar("T")
P = ParamSpec("P")

logger: logging.Logger = logging.getLogger(__name__)


def coroutine_timer(
    func: Callable[P, Coroutine[object, object, T]],
) -> Callable[P, Coroutine[object, object, T]]:
    """
    A decorator that logs the execution time of an async function.
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start_time = time.monotonic()
        try:
            return await func(*args, **kwargs)
        finally:
            end_time = time.monotonic()
            execution_time_ms = (end_time - start_time) * 1000
            logger.debug(
                "CoroutineTimer: '%s' took %.2f ms to execute.",
                func.__name__,
                execution_time_ms,
            )

    return wrapper


# All this typing mess was stolen from TypeShed and adapted to our needs
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    /,
    *,
    return_exceptions: Literal[False] = False,
    timeout: float = ...,
) -> tuple[_T1]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    /,
    *,
    timeout: float = ...,
) -> tuple[_T1, _T2]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    /,
    *,
    timeout: float = ...,
) -> tuple[_T1, _T2, _T3]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    coro4: Coroutine[Any, Any, _T4],
    /,
    *,
    timeout: float = ...,
) -> tuple[_T1, _T2, _T3, _T4]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    coro4: Coroutine[Any, Any, _T4],
    coro5: Coroutine[Any, Any, _T5],
    /,
    *,
    timeout: float = ...,
) -> tuple[_T1, _T2, _T3, _T4, _T5]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    coro4: Coroutine[Any, Any, _T4],
    coro5: Coroutine[Any, Any, _T5],
    coro6: Coroutine[Any, Any, _T6],
    /,
    *,
    timeout: float = ...,
) -> tuple[_T1, _T2, _T3, _T4, _T5, _T6]:  # pragma: no cover
    ...
@overload
async def gather(
    *coros: Coroutine[Any, Any, T],
    timeout: float = ...,
) -> list[T]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    /,
    *,
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> tuple[_T1 | BaseException]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    /,
    *,
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> tuple[_T1 | BaseException, _T2 | BaseException]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    /,
    *,
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> tuple[
    _T1 | BaseException, _T2 | BaseException, _T3 | BaseException
]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    coro4: Coroutine[Any, Any, _T4],
    /,
    *,
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> tuple[
    _T1 | BaseException,
    _T2 | BaseException,
    _T3 | BaseException,
    _T4 | BaseException,
]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    coro4: Coroutine[Any, Any, _T4],
    coro5: Coroutine[Any, Any, _T5],
    /,
    *,
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> tuple[
    _T1 | BaseException,
    _T2 | BaseException,
    _T3 | BaseException,
    _T4 | BaseException,
    _T5 | BaseException,
]:  # pragma: no cover
    ...
@overload
async def gather(
    coro1: Coroutine[Any, Any, _T1],
    coro2: Coroutine[Any, Any, _T2],
    coro3: Coroutine[Any, Any, _T3],
    coro4: Coroutine[Any, Any, _T4],
    coro5: Coroutine[Any, Any, _T5],
    coro6: Coroutine[Any, Any, _T6],
    /,
    *,
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> tuple[
    _T1 | BaseException,
    _T2 | BaseException,
    _T3 | BaseException,
    _T4 | BaseException,
    _T5 | BaseException,
    _T6 | BaseException,
]:  # pragma: no cover
    ...
@overload
async def gather(
    *coros: Coroutine[Any, Any, T],
    return_exceptions: Literal[True] = True,
    timeout: float = ...,
) -> list[T | BaseException]:  # pragma: no cover
    ...
# pyre-ignore[3]: Removing this return type makes the overloads work better until pyrefly
async def gather(
    # pyre-ignore[2]: Removing this type makes the overloads work better until pyrefly
    *coros,
    return_exceptions: bool = False,
    timeout: float | None = None,
):
    """
    This is a wrapper around asyncio.gather that is safe to use outside of a running event loop.
    Since its a coroutine, it can be awaited from any loop after its called, unlike asyncio.gather
    """
    if timeout is None:
        return await asyncio.gather(*coros, return_exceptions=return_exceptions)

    async with timeout_context(timeout):
        return await asyncio.gather(*coros, return_exceptions=return_exceptions)
