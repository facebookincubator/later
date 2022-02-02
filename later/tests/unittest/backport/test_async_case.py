# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
# This file was copied from python 3.8 test suite, for use in python 3.7
# It is licensed as python itself see https://github.com/python/cpython/LICENSE
# Any changes made for 3.7 were done under that license.

import asyncio
import unittest

from later.unittest.backport.async_case import IsolatedAsyncioTestCase


def tearDownModule() -> None:
    asyncio.set_event_loop_policy(None)


class TestHangsForever(IsolatedAsyncioTestCase):
    @unittest.expectedFailure
    async def test_base_exception_from_async_method(self):
        raise BaseException("Hangs forever")


class TestAsyncCase(unittest.TestCase):
    def test_full_cycle(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            def setUp(self):
                self.assertEqual(events, [])
                events.append("setUp")

            async def asyncSetUp(self):
                self.assertEqual(events, ["setUp"])
                events.append("asyncSetUp")

            async def test_func(self):
                self.assertEqual(events, ["setUp", "asyncSetUp"])
                events.append("test")
                self.addAsyncCleanup(self.on_cleanup)

            async def asyncTearDown(self):
                self.assertEqual(events, ["setUp", "asyncSetUp", "test"])
                events.append("asyncTearDown")

            def tearDown(self):
                self.assertEqual(
                    events, ["setUp", "asyncSetUp", "test", "asyncTearDown"]
                )
                events.append("tearDown")

            async def on_cleanup(self):
                self.assertEqual(
                    events, ["setUp", "asyncSetUp", "test", "asyncTearDown", "tearDown"]
                )
                events.append("cleanup")

        test = Test("test_func")
        test.run()
        self.assertEqual(
            events,
            ["setUp", "asyncSetUp", "test", "asyncTearDown", "tearDown", "cleanup"],
        )

    def test_exception_in_setup(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            async def asyncSetUp(self):
                events.append("asyncSetUp")
                raise Exception()

            async def test_func(self):
                events.append("test")
                self.addAsyncCleanup(self.on_cleanup)

            async def asyncTearDown(self):
                events.append("asyncTearDown")

            async def on_cleanup(self):
                events.append("cleanup")

        test = Test("test_func")
        test.run()
        self.assertEqual(events, ["asyncSetUp"])

    def test_exception_in_test(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            async def asyncSetUp(self):
                events.append("asyncSetUp")

            async def test_func(self):
                events.append("test")
                raise Exception()
                self.addAsyncCleanup(self.on_cleanup)

            async def asyncTearDown(self):
                events.append("asyncTearDown")

            async def on_cleanup(self):
                events.append("cleanup")

        test = Test("test_func")
        test.run()
        self.assertEqual(events, ["asyncSetUp", "test", "asyncTearDown"])

    def test_exception_in_test_after_adding_cleanup(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            async def asyncSetUp(self):
                events.append("asyncSetUp")

            async def test_func(self):
                events.append("test")
                self.addAsyncCleanup(self.on_cleanup)
                raise Exception()

            async def asyncTearDown(self):
                events.append("asyncTearDown")

            async def on_cleanup(self):
                events.append("cleanup")

        test = Test("test_func")
        test.run()
        self.assertEqual(events, ["asyncSetUp", "test", "asyncTearDown", "cleanup"])

    def test_exception_in_tear_down(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            async def asyncSetUp(self):
                events.append("asyncSetUp")

            async def test_func(self):
                events.append("test")
                self.addAsyncCleanup(self.on_cleanup)

            async def asyncTearDown(self):
                events.append("asyncTearDown")
                raise Exception()

            async def on_cleanup(self):
                events.append("cleanup")

        test = Test("test_func")
        test.run()
        self.assertEqual(events, ["asyncSetUp", "test", "asyncTearDown", "cleanup"])

    def test_exception_in_tear_clean_up(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            async def asyncSetUp(self):
                events.append("asyncSetUp")

            async def test_func(self):
                events.append("test")
                self.addAsyncCleanup(self.on_cleanup)

            async def asyncTearDown(self):
                events.append("asyncTearDown")

            async def on_cleanup(self):
                events.append("cleanup")
                raise Exception()

        test = Test("test_func")
        test.run()
        self.assertEqual(events, ["asyncSetUp", "test", "asyncTearDown", "cleanup"])

    def test_cleanups_interleave_order(self) -> None:
        events = []

        class Test(IsolatedAsyncioTestCase):
            async def test_func(self):
                self.addAsyncCleanup(self.on_sync_cleanup, 1)
                self.addAsyncCleanup(self.on_async_cleanup, 2)
                self.addAsyncCleanup(self.on_sync_cleanup, 3)
                self.addAsyncCleanup(self.on_async_cleanup, 4)

            async def on_sync_cleanup(self, val):
                events.append(f"sync_cleanup {val}")

            async def on_async_cleanup(self, val):
                events.append(f"async_cleanup {val}")

        test = Test("test_func")
        test.run()
        self.assertEqual(
            events,
            ["async_cleanup 4", "sync_cleanup 3", "async_cleanup 2", "sync_cleanup 1"],
        )


if __name__ == "__main__":
    unittest.main()
