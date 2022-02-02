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
# under the License.
from asyncio import Event


class BiDirectionalEvent:
    """
    Events can be set and cleared multiple times, but this one has backchannel
    information for the setter to ensure the waiter has called wait() a second time.
    Both the wait and the set are coroutines
    """

    _sevent: Event
    _cevent: Event
    _first_wait: Event

    def __init__(self) -> None:
        self._cevent = Event()
        self._sevent = Event()
        self._first_wait = Event()

    async def wait(self) -> None:
        if self._first_wait.is_set():
            self._cevent.set()
        else:
            self._first_wait.set()
        await self._sevent.wait()
        self._sevent.clear()

    def is_set(self) -> bool:
        return self._sevent.is_set()

    async def set(self) -> None:
        if not self._first_wait.is_set():
            await self._first_wait.wait()
        self._sevent.set()
        await self._cevent.wait()
        self._cevent.clear()

    def set_nowait(self) -> None:
        self._sevent.set()
