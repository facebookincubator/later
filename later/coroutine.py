# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-strict

import functools
import logging
import time

from typing import Callable, Coroutine, ParamSpec, TypeVar


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
