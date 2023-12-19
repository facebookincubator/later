# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License
import asyncio
from contextlib import suppress

from later import BiDirectionalEvent
from later.unittest import TestCase


class Test_BiDirectionalEvent(TestCase):
    async def test_end_to_end(self) -> None:
        event: BiDirectionalEvent = BiDirectionalEvent()
        woke = False

        async def waiter() -> None:
            nonlocal woke
            while True:
                # do some work
                await event.wait()
                woke = True

        task = asyncio.get_running_loop().create_task(waiter())
        self.assertFalse(woke)
        await event.set()
        self.assertTrue(woke)
        woke = False
        await event.set()
        self.assertTrue(woke)
        self.assertFalse(event.is_set())
        event.set_nowait()
        self.assertTrue(event.is_set())
        # clean up the task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
