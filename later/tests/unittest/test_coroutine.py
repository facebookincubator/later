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
import unittest

from later import coroutine_timer

from later.unittest import mock, TestCase


class TestCoroutineTimer(TestCase):
    async def test_coroutine_timer(self) -> None:
        @coroutine_timer
        async def coro() -> None:
            await asyncio.sleep(0.1, "test")

        with mock.patch("logging.Logger.debug") as mock_debug:
            await coro()
            debug_format_str = mock_debug.call_args[0][0]
            debug_fn_name = mock_debug.call_args[0][1]
            assert debug_format_str == "CoroutineTimer: '%s' took %.2f ms to execute."
            assert debug_fn_name == "coro"


if __name__ == "__main__":
    unittest.main()
