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
from unittest import mock

import later
from later import coroutine_timer
from later.unittest import TestCase


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


class TestGather(unittest.TestCase):
    def test_gather_simple(self) -> None:
        coro = later.gather(
            asyncio.sleep(0, result=1),
            asyncio.sleep(0, result=True),
            asyncio.sleep(0, result="foo"),
        )
        self.assertEqual(asyncio.run(coro), [1, True, "foo"])

    def test_gather_return_exceptions(self) -> None:
        async def inner() -> None:
            raise RuntimeError

        coro = later.gather(inner(), return_exceptions=True)
        self.assertIsInstance(asyncio.run(coro)[0], RuntimeError)

    def test_gather_exception(self) -> None:
        async def inner() -> None:
            raise RuntimeError

        coro = later.gather(inner())
        with self.assertRaises(RuntimeError):
            asyncio.run(coro)

    def test_timeout(self) -> None:
        async def inner() -> None:
            await asyncio.sleep(9999)

        coro = later.gather(inner(), timeout=0.01)
        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
