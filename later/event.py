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

"""
Synchronization primitives for asyncio services.

This module provides specialized event classes for coordinating between
asynchronous tasks.
"""

from asyncio import Event


class BiDirectionalEvent:
    """
    A bidirectional event for coordinating between a setter and a waiter.

    Unlike a standard :class:`asyncio.Event`, this class provides a backchannel
    mechanism that allows the setter to know when the waiter has acknowledged
    the signal and is ready to receive another one.

    This is useful for implementing patterns where:

    1. A producer sets an event to signal data availability
    2. The producer needs to wait until the consumer has processed the data
       and is ready for more before signaling again

    Example::

        event = BiDirectionalEvent()

        async def consumer():
            while True:
                await event.wait()  # Wait for producer to signal
                process_data()      # Process the signaled data

        async def producer():
            while True:
                prepare_data()
                await event.set()   # Signal consumer and wait for acknowledgment

    Attributes:
        _sevent: The "set" event that waiters block on.
        _cevent: The "clear/ack" event that signals waiter acknowledgment.
        _first_wait: Event to track if wait() has been called at least once.
    """

    _sevent: Event
    _cevent: Event
    _first_wait: Event

    def __init__(self) -> None:
        self._cevent = Event()
        self._sevent = Event()
        self._first_wait = Event()

    async def wait(self) -> None:
        """
        Wait for the event to be set, then automatically clear it.

        On subsequent calls (after the first), this method also signals
        to the setter that the waiter is ready to receive again.

        This method should be called in a loop by the consumer.
        """
        if self._first_wait.is_set():
            self._cevent.set()
        else:
            self._first_wait.set()
        await self._sevent.wait()
        self._sevent.clear()

    def is_set(self) -> bool:
        """Return True if the event is currently set."""
        return self._sevent.is_set()

    async def set(self) -> None:
        """
        Set the event and wait for the waiter to acknowledge.

        This method blocks until the waiter has called :meth:`wait` after
        this set operation, providing backpressure to the producer.

        If :meth:`wait` has never been called, this method will block until
        the first call to :meth:`wait` occurs.
        """
        if not self._first_wait.is_set():
            await self._first_wait.wait()
        self._sevent.set()
        await self._cevent.wait()
        self._cevent.clear()

    def set_nowait(self) -> None:
        """
        Set the event without waiting for acknowledgment.

        This is a non-blocking version of :meth:`set` that does not wait
        for the waiter to acknowledge. Useful for signaling without
        backpressure.
        """
        self._sevent.set()
