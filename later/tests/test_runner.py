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
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from unittest import TestCase

from later.runner import (
    _get_event_loop,
    _thread_local_pool,
    pause_existing_loop,
    run_nested,
)


class TestRunner(TestCase):
    def setUp(self) -> None:
        # Setup a default loop for the test
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.addCleanup(self.cleanup)

    def cleanup(self) -> None:
        # This cleans up the stack of nested loops
        for loop in _thread_local_pool.stack:
            loop.close()
        _thread_local_pool.stack.clear()
        _thread_local_pool.dirty_loop = None
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_simple_run_with_nesting(self) -> None:
        """
        This tests the expected behavior of the run_nested function.
        and proves its management of the event loops.
        """

        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        async def coro(val: int) -> int:
            return val

        async def nested(val: int) -> int:
            return run_nested(coro(val))

        set_loop = _get_event_loop()
        loop = run_nested(get_loop())
        if set_loop is not None:
            # While default loops are a thing, this should be true
            self.assertEqual(set_loop, loop)

        # we don't store existing loops only use them.
        self.assertEqual(len(_thread_local_pool), 0)

        self.assertEqual(run_nested(nested(4)), 4)
        self.assertEqual(len(_thread_local_pool), 1)

        self.assertNotIn(_get_event_loop(), _thread_local_pool.stack)
        # This should match, because the second loop was borrowed
        # from the pool and previous loop was restored.
        self.assertEqual(id(set_loop), id(_get_event_loop()))

        # Lets use the standard run method because it blows away the default loop
        self.assertEqual(asyncio.run(coro(5)), 5)
        self.assertEqual(len(_thread_local_pool), 1)
        loop = run_nested(get_loop())

        self.assertEqual(run_nested(coro(3)), 3)
        self.assertEqual(len(_thread_local_pool), 1)

        self.assertEqual(asyncio.run(nested(3)), 3)
        self.assertEqual(len(_thread_local_pool), 1)

        self.assertEqual(run_nested(coro(3)), 3)
        self.assertEqual(len(_thread_local_pool), 1)

        self.assertEqual(run_nested(nested(4)), 4)
        self.assertEqual(len(_thread_local_pool), 2)

        self.assertEqual(loop, run_nested(get_loop()))
        self.assertEqual(len(_thread_local_pool), 2)

        self.assertEqual(run_nested(nested(4)), 4)
        self.assertEqual(len(_thread_local_pool), 2)

        # Because we use asyncio.run the loop should be None
        self.assertEqual(None, _get_event_loop())

    def test_deep_nesting(self) -> None:
        """
        This shows that the nested system can go quite deep if need be
        """

        async def go_deep(depth: int) -> int:
            if depth < 10:
                return run_nested(go_deep(depth + 1))
            return 10

        self.assertEqual(run_nested(go_deep(1)), 10)
        # First loop already existed so we only have 9 in the freelist
        self.assertEqual(len(_thread_local_pool), 9)

    def test_get_event_loop_threads(self) -> None:
        """
        Loops are not portable across threads. Make sure we don't leak them.
        """
        self.loop.close()

        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        loop: asyncio.AbstractEventLoop = run_nested(get_loop())

        async def _check_loop() -> None:
            self.assertNotEqual(loop, asyncio.get_running_loop())

        def check() -> None:
            self.assertEqual(len(_thread_local_pool), 0)
            run_nested(_check_loop())
            self.assertEqual(len(_thread_local_pool), 1)

        futs: list[Future] = []
        self.assertEqual(len(_thread_local_pool), 1)
        with ThreadPoolExecutor(5) as executor:
            for _ in range(25):
                futs.append(executor.submit(check))
            wait(futs)
        self.assertEqual(len(_thread_local_pool), 1)
        self.assertEqual(loop, run_nested(get_loop()))

    def test_fork(self) -> None:
        """
        Loops are not portable across processes. Make sure we don't leak them.
        This tests the worst possible case where the fork happens in the yield
        statement of the _get_ready_loop context manager
        """

        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        async def nested() -> None:
            run_nested(get_loop())

        # Blow away the default loop
        asyncio.run(asyncio.sleep(0))

        self.assertEqual(len(_thread_local_pool), 0)
        loop: asyncio.AbstractEventLoop = run_nested(get_loop())
        self.assertEqual(len(_thread_local_pool), 1)
        run_nested(nested())
        self.assertEqual(len(_thread_local_pool), 2)

        async def _fork_in_running_loop() -> int:
            return os.fork()

        pid = run_nested(_fork_in_running_loop())
        if pid == 0:
            # Child, after the fork there should be no loops
            self.assertEqual(len(_thread_local_pool), 0)
            # So we don't write any testing output to confuse testx
            # If everything passes above this test case will pass.
            os._exit(0)
        else:
            # parent
            _, result = os.waitpid(pid, 0)
            self.assertEqual(result, 0)
            self.assertEqual(len(_thread_local_pool), 2)
            self.assertEqual(loop, run_nested(get_loop()))
            self.assertEqual(len(_thread_local_pool), 2)

    def test_is_already_running(self) -> None:
        """
        If for some reason a person takes a loop from run_nested and runs it
        it should be removed from the pool
        """

        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        async def coro() -> int:
            return 5

        async def nested() -> int:
            return run_nested(coro())

        loop: asyncio.AbstractEventLoop = run_nested(get_loop())
        run_nested(nested())
        self.assertEqual(len(_thread_local_pool), 1)
        self.assertEqual(5, loop.run_until_complete(nested()))
        self.assertEqual(len(_thread_local_pool), 1)
        loop.close()

    def test_is_closed(self) -> None:
        """
        What if somebody closes the loop
        """
        # Blow away the default loop if it exists
        asyncio.run(asyncio.sleep(0))

        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        async def coro() -> int:
            return 5

        loop: asyncio.AbstractEventLoop = run_nested(get_loop())
        loop.close()
        self.assertEqual(len(_thread_local_pool), 1)
        self.assertEqual(5, run_nested(coro()))
        self.assertEqual(len(_thread_local_pool), 1)
        self.assertIsNot(loop, run_nested(get_loop()))

    def test_task_factory_copy_from_running_loop(self) -> None:
        """
        This is a cut out for folly_context it uses task_factories to insure the folly context object is updated
        And there is an existing feature in `await_sync` that copies the task factory from a running loop.
        """

        async def coro() -> None:
            loop = asyncio.get_running_loop()
            self.assertIs(loop.get_task_factory(), asyncio.eager_task_factory)

        async def nested() -> None:
            loop = asyncio.get_running_loop()
            self.assertIsNone(loop.get_task_factory())
            loop.set_task_factory(asyncio.eager_task_factory)
            self.assertIsNotNone(loop.get_task_factory())
            return run_nested(coro())

        asyncio.run(nested())

    def test_set_loop_different_from_run_loop(self) -> None:
        """
        If a loop is set before calling run_nested, it should be used
        even if a different loop is running
        """
        # self.loop is the first loop we will run

        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        async def nested() -> None:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            self.assertEqual(id(run_nested(get_loop())), id(new_loop))
            new_loop.close()

        self.assertEqual(id(run_nested(get_loop())), id(self.loop))
        run_nested(nested())
        # We don't do anything with set loops anymore.
        # nested set a new loop and they closed it.
        self.assertNotEqual(id(_get_event_loop()), id(self.loop))
        loop = _get_event_loop()
        self.assertTrue(loop is not None and loop.is_closed())

        self.assertEqual(len(_thread_local_pool), 0)

    def test_use_existing_loop(self) -> None:
        """
        If a new loop is created by the caller of await_sync and set as the current loop, await_sync will use it
        """
        # Create a new loop and set it as the current loop
        loop = _get_event_loop()
        assert loop is not None

        async def loop_match() -> None:
            self.assertEqual(
                id(loop), id(asyncio.get_running_loop()), "Loop should match"
            )

        run_nested(loop_match())
        self.assertEqual(len(_thread_local_pool), 0)

    def test_created_loops_dont_leak_loops(self) -> None:
        """
        If a loop is barrowed from the pool, it doesn't stay set after run_nested returns
        """
        # Get rid of the existing loop if it exists
        self.loop.close()

        async def nested() -> None:
            self.assertEqual(len(_thread_local_pool), 0)
            running = asyncio.get_running_loop()
            run_nested(asyncio.sleep(0))
            self.assertEqual(len(_thread_local_pool), 1)
            # run_nested borrows a loop from the pool but must not leave it as
            # the running loop; we should still be on nested's own loop.
            self.assertEqual(running, asyncio.get_running_loop())

        run_nested(nested())
        self.assertEqual(len(_thread_local_pool), 2)
        self.assertNotIn(_get_event_loop(), _thread_local_pool.stack)

    def test_created_loops_get_cleaned_up(self) -> None:
        """
        If a loop are created in the pool, tasks are cleaned up after the loop is burried in the pool
        """
        # Get rid of the existing loop if it exists
        self.loop.close()

        async def bad_coro() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                raise TypeError("Bad Type")

        async def very_bad_coro(count: int) -> None:
            for i in range(count):
                try:
                    await asyncio.sleep(9999)
                except asyncio.CancelledError:
                    if i == count - 1:
                        return

        async def make_task() -> tuple[
            list[asyncio.Task[None]], asyncio.AbstractEventLoop
        ]:
            tasks = [
                # good cancellation citizen
                asyncio.create_task(asyncio.sleep(9999)),
                # Raises a different exception than Cancellation
                asyncio.create_task(bad_coro()),
                # returns instead of raising Cancellation
                asyncio.create_task(very_bad_coro(1)),
                # Never finishes
                asyncio.create_task(very_bad_coro(2)),
            ]
            loop = asyncio.get_running_loop()
            await asyncio.sleep(0)  # Insure it starts
            return tasks, loop

        async def nested() -> tuple[
            list[asyncio.Task[None]], asyncio.AbstractEventLoop
        ]:
            return run_nested(make_task())

        tasks, loop = run_nested(nested())

        self.assertEqual(len(asyncio.all_tasks(loop)), 1)
        self.assertTrue(tasks[0].cancelled())
        self.assertTrue(tasks[1].exception() is not None and not tasks[1].cancelled())
        # Will get cancelled again when the cleanup cancels
        self.assertTrue(tasks[2].done() and not tasks[2].cancelled())
        self.assertFalse(tasks[3].done())

        self.assertEqual(len(_thread_local_pool), 2)

    def test_pause_existing_loop_is_noop_without_running_loop(self) -> None:
        # run_nested only enters pause_existing_loop when a loop is running; with
        # nothing running the context manager must be a harmless no-op.
        ran = False
        with pause_existing_loop():
            ran = True
        self.assertTrue(ran)

    def test_running_loop_in_pool(self) -> None:
        async def get_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        async def nested() -> None:
            run_nested(asyncio.sleep(0))

        self.loop.close()
        # Lets get a loop from the pool
        loop = run_nested(get_loop())
        self.assertEqual(len(_thread_local_pool), 1)
        loop.run_until_complete(nested())
        self.assertNotIn(loop, _thread_local_pool.stack)
        self.assertEqual(len(_thread_local_pool), 1)
        self.assertIsNot(loop, run_nested(get_loop()))
        self.assertEqual(len(_thread_local_pool), 1)
        loop.close()

    def test_default_executor_still_works(self) -> None:
        async def use_executor() -> None:
            loop = asyncio.get_running_loop()
            f1 = loop.run_in_executor(None, time.sleep, 0.01)
            f2 = loop.run_in_executor(None, time.sleep, 0)
            await asyncio.gather(f1, f2)

        async def nested() -> None:
            # Since cleanup only happens when a loop is burried we to nest 1 level
            run_nested(use_executor())
            run_nested(use_executor())

        self.loop.close()
        run_nested(nested())
        run_nested(nested())
        run_nested(nested())

    def test_do_not_allow_nested_loops(self) -> None:
        """
        This tests that we don't allow nested loops, when asked
        """
        import later.runner as runner

        runner.ALLOW_NESTED_LOOPS = False
        self.addCleanup(setattr, runner, "ALLOW_NESTED_LOOPS", True)

        async def nested() -> None:
            run_nested(asyncio.sleep(0))

        with self.assertRaises(RuntimeError):
            run_nested(nested())

    def test_task_factory_not_inherited_across_borrows(self) -> None:
        """
        A loop returned to the pool must not carry a previous borrower's task
        factory into the next, unrelated run_nested call.
        """
        # Force every run to borrow from the pool.
        self.loop.close()

        # Seed the pool with loops while an eager task factory is set on the
        # running loop, so a borrowed loop picks it up and is returned dirty.
        async def seed() -> None:
            asyncio.get_running_loop().set_task_factory(asyncio.eager_task_factory)
            run_nested(asyncio.sleep(0))

        run_nested(seed())

        # A later run whose running loop has no factory must observe no factory,
        # both on the loop it runs on and on any loop it borrows.
        seen: list[object] = []

        async def record_inner() -> None:
            seen.append(asyncio.get_running_loop().get_task_factory())

        async def driver() -> None:
            self.assertIsNone(asyncio.get_running_loop().get_task_factory())
            run_nested(record_inner())

        run_nested(driver())
        self.assertEqual(seen, [None])
