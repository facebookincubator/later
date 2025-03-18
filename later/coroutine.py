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
