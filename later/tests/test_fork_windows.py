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

"""Fork-child finalization must not mutate parent I/O across callback windows."""

from __future__ import annotations

import asyncio
import gc
import importlib
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
import unittest
import weakref
from collections.abc import Callable
from unittest.mock import patch

# Imported for its side effect alone: the module registers its fork lock with
# os.register_at_fork at import time, before later.runner registers its hooks.
importlib.import_module("concurrent.futures.thread")


def noop() -> None:
    pass


callback: Callable[[], None] = noop


def before_other() -> None:
    callback()


# Earlier registration means this callback runs after later's before hook.
# Each scenario runs in a fresh interpreter so callback order is deterministic.
if __name__ == "__main__":
    os.register_at_fork(before=before_other)


class _Window:
    def __init__(self, mode: str, retain: bool) -> None:
        import later.runner as runner

        self.runner = runner
        self.mode = mode
        self.retain = retain
        self.refs: list[weakref.ReferenceType[asyncio.AbstractEventLoop]] = []
        self.retained: list[asyncio.AbstractEventLoop] = []
        self.errors: list[Exception] = []
        self.paused = threading.Event()
        self.resume = threading.Event()
        self.created = threading.Event()
        self.release_worker = threading.Event()
        self.depth = 0

    async def warm(self) -> None:
        loop = asyncio.get_running_loop()
        self.refs.append(weakref.ref(loop))
        if self.retain:
            self.retained.append(loop)

    async def nested_warm(self) -> None:
        await self.warm()
        self.runner.run_nested(self.warm())

    async def parent_io(self) -> None:
        from later.tests.test_fork import io  # @manual - same test target

        def delayed() -> bytes:
            time.sleep(0.03)
            return b"parent wakeup"

        assert await asyncio.to_thread(delayed) == b"parent wakeup"
        await io()

    def fork_once(self, continue_child: bool = False) -> None:
        from later.tests.test_fork import io  # @manual - same test target

        pid = os.fork()
        if pid == 0:
            if continue_child:
                # References made before this fork belong to ancestors.
                self.refs = []
                self.runner.run_nested(self.warm())
                return
            # Failure, including SystemExit, must reach the waiting parent.
            status = 1
            try:
                gc.collect()
                self.runner.run_nested(asyncio.wait_for(io(), 1))
                status = 0
            finally:
                os._exit(status)
        waited, status = os.waitpid(pid, 0)
        print(f"child {pid} status={status}", flush=True)
        assert waited == pid and status == 0, ("child I/O failed", pid, status)

    def checked(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as error:
            self.errors.append(error)

    def worker(self) -> None:
        from later.tests.test_fork import check_io  # @manual - same test target

        assert self.paused.wait(5), "late-creation worker not started"
        self.runner.run_nested(self.warm())
        self.created.set()
        assert self.release_worker.wait(10), "late-creation worker not released"
        self.runner.run_nested(asyncio.wait_for(self.parent_io(), 1))
        check_io(self.refs)

    def collect_finalizer(self) -> None:
        window = self

        class Finalizer:
            def __del__(self) -> None:
                window.checked(lambda: window.runner.run_nested(window.warm()))

        cycle: list[object] = [Finalizer()]
        cycle.append(cycle)
        del cycle
        gc.collect()

    def before(self) -> None:
        if self.mode not in (
            "reentrant",
            "nested_child",
            "nested_children",
            "mixed_continuation",
        ):
            self.checked(self.before_action)
            return
        limit = 2 if self.mode in ("nested_children", "mixed_continuation") else 1
        if self.depth == limit:
            return
        self.depth += 1
        try:
            self.checked(self.before_action)
        finally:
            self.depth -= 1

    def before_action(self) -> None:
        if self.mode in ("nested_child", "nested_children", "mixed_continuation"):
            self.fork_once(
                continue_child=self.mode != "mixed_continuation" or self.depth == 1
            )
            self.runner.run_nested(self.warm())
        elif self.mode.startswith("overlap"):
            if threading.current_thread().name == "fork-A":
                self.paused.set()
                assert self.resume.wait(5), "overlapping fork did not finish"
            elif self.mode == "overlap_creation":
                self.runner.run_nested(self.nested_warm())
        elif self.mode == "thread_creation":
            self.paused.set()
            assert self.created.wait(5), "late-creation worker did not finish"
        elif self.mode == "gc_creation":
            self.collect_finalizer()
        else:
            self.runner.run_nested(self.warm())
            if self.mode == "reentrant":
                self.fork_once()

    def run(self) -> None:
        from later.tests.test_fork import check_io  # @manual - same test target

        thread = None
        if self.mode.startswith("overlap"):
            self.runner.run_nested(self.warm())
            thread = threading.Thread(
                target=lambda: self.checked(self.fork_once), name="fork-A"
            )
            thread.start()
            assert self.paused.wait(5), "first fork did not pause"
            self.fork_once()
            check_io(self.refs)
            self.resume.set()
        elif self.mode == "thread_creation":
            thread = threading.Thread(target=lambda: self.checked(self.worker))
            thread.start()
            self.fork_once()
            self.release_worker.set()
        else:
            self.fork_once()
        if thread is not None:
            thread.join(5)
            assert not thread.is_alive(), "worker stalled"
        assert not self.errors, self.errors
        assert self.refs, "scenario did not create a loop"
        if self.mode == "overlap_creation":
            assert len(self.refs) == 3, "overlapping fork did not create nested loops"
        if self.mode != "thread_creation":
            self.runner.run_nested(asyncio.wait_for(self.parent_io(), 1))
            check_io(self.refs)


def exercise_window(mode: str, variant: str, retain: bool) -> None:
    from later.tests.test_fork import loop_factory  # @manual - same test target

    global callback
    asyncio.set_event_loop(None)
    window = _Window(mode, retain)
    callback = window.before
    with patch.object(window.runner, "new_event_loop", loop_factory(variant)):
        window.run()
        callback = noop
        window.runner._close_pooled_loops()
        window.retained.clear()
        gc.collect()
        assert all(ref() is None for ref in window.refs), (
            "fork capture kept owner loops alive"
        )
    print(f"PASS {mode} {variant} retain={retain}", flush=True)


@unittest.skipUnless(hasattr(os, "fork"), "requires fork")
class TestForkLifetimeWindows(unittest.TestCase):
    def check_window(self, mode: str, retain: bool = False) -> None:
        import later.runner as runner

        variants = ["default", "select"]
        if hasattr(selectors, "PollSelector"):
            variants.append("poll")
        if runner.uvloop is not type(None):
            variants.append("uvloop")
        if runner.ig_uvloop is not type(None):
            variants.append("ig_uvloop")
        for variant in variants:
            with self.subTest(variant=variant):
                with subprocess.Popen(
                    [sys.executable, __file__, mode, variant, str(int(retain))],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                    env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
                ) as process:
                    try:
                        stdout, stderr = process.communicate(timeout=20)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        stdout, stderr = process.communicate()
                        self.fail("fork scenario timed out:\n" + stdout + stderr)
                    result = subprocess.CompletedProcess(
                        process.args, process.returncode, stdout, stderr
                    )
                self.assertEqual(
                    result.returncode,
                    0,
                    "fork-child finalization mutated parent I/O:\n"
                    + result.stdout
                    + result.stderr,
                )
                self.assertIn("PASS", result.stdout)
                self.assertNotIn("Exception ignored in", result.stderr)
                print(result.stdout, end="")

    def test_child_finalization_after_late_loop_creation(self) -> None:
        self.check_window("late_creation")

    def test_child_finalization_after_overlapping_forks(self) -> None:
        self.check_window("overlap")

    def test_child_finalization_after_overlapping_late_creation(self) -> None:
        self.check_window("overlap_creation")

    def test_child_finalization_after_other_thread_creation(self) -> None:
        self.check_window("thread_creation")

    def test_child_finalization_after_reentrant_fork(self) -> None:
        self.check_window("reentrant")

    def test_nested_child_continuation_preserves_enclosing_fork_capture(self) -> None:
        self.check_window("nested_child")

    def test_multilevel_child_continuation_preserves_enclosing_fork_captures(
        self,
    ) -> None:
        self.check_window("nested_children")

    def test_mixed_parent_child_continuation_preserves_enclosing_fork_captures(
        self,
    ) -> None:
        self.check_window("mixed_continuation")

    def test_nested_child_continuation_retained_reference_control(self) -> None:
        self.check_window("nested_child", retain=True)

    def test_child_finalization_after_gc_reentrant_creation(self) -> None:
        self.check_window("gc_creation")

    def test_late_creation_retained_reference_control(self) -> None:
        self.check_window("late_creation", retain=True)

    def test_overlapping_forks_retained_reference_control(self) -> None:
        self.check_window("overlap", retain=True)


if __name__ == "__main__":
    owner = os.getpid()
    status = 1
    try:
        exercise_window(sys.argv[1], sys.argv[2], bool(int(sys.argv[3])))
        status = 0
    finally:
        if os.getpid() != owner:
            os._exit(status)
