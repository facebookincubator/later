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

"""Forked child cleanup must not mutate a parent pool's kernel I/O state."""

from __future__ import annotations

import asyncio
import gc
import os
import selectors
import socket
import subprocess
import sys
import threading
import unittest
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import later.runner as runner


async def io() -> None:
    assert await asyncio.to_thread(lambda: b"executor wakeup") == b"executor wakeup"
    reader, writer = socket.socketpair()
    reader.setblocking(False)
    writer.setblocking(False)
    try:
        loop = asyncio.get_running_loop()
        await loop.sock_sendall(writer, b"parent bytes")
        assert await loop.sock_recv(reader, 12) == b"parent bytes"
    finally:
        reader.close()
        writer.close()


def loop_factory(variant: str) -> Callable[[], asyncio.AbstractEventLoop]:
    if variant == "select":

        def select_loop() -> asyncio.AbstractEventLoop:
            return asyncio.SelectorEventLoop(selectors.SelectSelector())

        return select_loop
    if variant == "poll":

        def poll_loop() -> asyncio.AbstractEventLoop:
            return asyncio.SelectorEventLoop(selectors.PollSelector())

        return poll_loop
    if variant in ("uvloop", "ig_uvloop"):

        def optional_loop() -> asyncio.AbstractEventLoop:
            loop = getattr(runner, variant)()
            assert isinstance(loop, asyncio.AbstractEventLoop), (
                "loop variant unavailable"
            )
            return loop

        return optional_loop
    return asyncio.new_event_loop


def check_io(refs: list[weakref.ReferenceType[asyncio.AbstractEventLoop]]) -> None:
    for ref in refs:
        loop = ref()
        assert loop is not None and not loop.is_closed(), "parent loop was lost"
        selector = getattr(loop, "_selector", None)
        if hasattr(selectors, "EpollSelector") and isinstance(
            selector, selectors.EpollSelector
        ):
            fdinfo = Path(f"/proc/self/fdinfo/{selector.fileno()}").read_text()
            registered = {
                int(line.split()[1])
                for line in fdinfo.splitlines()
                if line.startswith("tfd:")
            }
            assert set(selector.get_map()).issubset(registered), (
                "child cleanup mutated parent kernel I/O registrations",
                list(selector.get_map()),
                fdinfo,
            )
        loop.run_until_complete(asyncio.wait_for(io(), 3))


def check_grandchild() -> None:
    grandchild = os.fork()
    if grandchild == 0:
        gc.collect()
        runner.run_nested(asyncio.wait_for(io(), 3))
        os._exit(0)
    _, grandchild_status = os.waitpid(grandchild, 0)
    assert grandchild_status == 0, "grandchild I/O failed"
    runner.run_nested(asyncio.wait_for(io(), 3))


class _Scenario:
    """The loops, events and sockets that one fork scenario shares across its steps."""

    def __init__(self, topology: str) -> None:
        self.topology = topology
        self.refs: list[weakref.ReferenceType[asyncio.AbstractEventLoop]] = []
        self.parked = threading.Event()
        self.resume = threading.Event()
        self.sockets: list[tuple[socket.socket, socket.socket]] = []
        self.thread: threading.Thread | None = None
        self.errors: list[Exception] = []

    async def warm(self) -> None:
        loop = asyncio.get_running_loop()
        self.refs.append(weakref.ref(loop))
        if self.topology == "resource":
            reader, writer = socket.socketpair()
            reader.setblocking(False)
            writer.setblocking(False)
            self.sockets.append((reader, writer))
            loop.add_reader(reader.fileno(), lambda: None)

    async def nested(self) -> None:
        await self.warm()
        runner.run_nested(self.warm())

    async def active(self) -> None:
        await self.warm()
        self.parked.set()
        if not self.resume.wait(10):
            raise TimeoutError("parent worker was not released")

    def worker(self) -> None:
        if self.topology == "thread_active":
            runner.run_nested(self.active())
        else:
            runner.run_nested(self.warm())
            self.parked.set()
            if not self.resume.wait(10):
                raise TimeoutError("parent worker was not released")
        check_io(self.refs)

    def checked_worker(self) -> None:
        try:
            self.worker()
        except Exception as error:
            self.errors.append(error)

    async def fork_while_borrowed(self) -> int:
        await self.warm()
        return os.fork()

    def start_parent(self) -> None:
        """Create the parent's loops the way the topology says, before the fork."""
        if self.topology.startswith("thread"):
            self.thread = threading.Thread(target=self.checked_worker)
            self.thread.start()
            assert self.parked.wait(5), "worker did not create its loop"
        elif self.topology != "borrowed":
            runner.run_nested(
                self.nested() if self.topology == "nested" else self.warm()
            )

    def fork(self) -> int:
        if self.topology == "borrowed":
            return runner.run_nested(self.fork_while_borrowed())
        return os.fork()

    def run_child(self, normal_exit: bool) -> NoReturn:
        gc.collect()
        assert not runner._thread_local_pool.stack, "child inherited the parent pool"
        runner.run_nested(asyncio.wait_for(io(), 3))
        if self.topology == "grandchild":
            check_grandchild()
        runner._close_pooled_loops()
        gc.collect()
        if normal_exit:
            raise SystemExit(0)
        os._exit(0)

    def check_parent(self, pid: int) -> None:
        _, status = os.waitpid(pid, 0)
        assert status == 0, ("child fresh loop failed", status)
        if self.thread is not None:
            self.resume.set()
            self.thread.join(5)
            assert not self.thread.is_alive(), "parent worker I/O stalled"
            assert not self.errors, self.errors
        else:
            check_io(self.refs)
        for reader, writer in self.sockets:
            writer.send(b"still registered")
            assert reader.recv(100) == b"still registered"
            reader.close()
            writer.close()
        assert not getattr(runner, "_fork_snapshot", ()), "parent kept a fork snapshot"


def exercise(topology: str, variant: str, normal_exit: bool) -> None:
    asyncio.set_event_loop(None)
    factory = loop_factory(variant)
    scenario = _Scenario(topology)
    with patch.object(runner, "new_event_loop", factory):
        scenario.start_parent()
        pid = scenario.fork()
        if pid == 0:
            scenario.run_child(normal_exit)
        scenario.check_parent(pid)
    print(f"PASS {topology} {variant} normal_exit={normal_exit}", flush=True)


@unittest.skipUnless(hasattr(os, "fork"), "requires fork")
class TestForkCleanup(unittest.TestCase):
    def test_live_tracking_is_weak(self) -> None:
        pool = runner._ThreadLocalPool()
        loop = pool.borrow_loop()
        ref = weakref.ref(loop)
        loop.close()
        del loop
        gc.collect()
        self.assertIsNone(ref(), "tracking retained an unpooled loop in its owner")

    def test_parent_capture_releases_new_loop(self) -> None:
        pool = runner._ThreadLocalPool()
        runner._before_fork()
        try:
            loop = pool.borrow_loop()
        finally:
            runner._after_fork_in_parent()
        try:
            loop.run_until_complete(asyncio.wait_for(io(), 3))
        finally:
            loop.close()
        ref = weakref.ref(loop)
        del loop
        gc.collect()
        self.assertIsNone(ref(), "parent capture retained a newly created loop")

    def test_child_cleanup_preserves_parent_io(self) -> None:
        """Inherited pooled-loop GC must not unregister the parent's I/O."""
        variants = ["default", "select"]
        if hasattr(selectors, "PollSelector"):
            variants.append("poll")
        if runner.uvloop is not type(None):
            variants.append("uvloop")
        if runner.ig_uvloop is not type(None):
            variants.append("ig_uvloop")
        for topology in (
            "idle",
            "nested",
            "resource",
            "borrowed",
            "thread_idle",
            "thread_active",
            "grandchild",
        ):
            for variant in variants:
                for normal_exit in (False, True):
                    with self.subTest(
                        topology=topology, variant=variant, normal_exit=normal_exit
                    ):
                        result = subprocess.run(
                            [
                                sys.executable,
                                __file__,
                                topology,
                                variant,
                                str(int(normal_exit)),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=20,
                            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
                        )
                        self.assertEqual(
                            result.returncode, 0, result.stdout + result.stderr
                        )
                        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    exercise(sys.argv[1], sys.argv[2], bool(int(sys.argv[3])))
