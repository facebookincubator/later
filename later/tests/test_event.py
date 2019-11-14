import asyncio
from contextlib import suppress

from later import BiDirectionalEvent
from later.unittest import TestCase


class Test_BiDirectionalEvent(TestCase):
    async def test_end_to_end(self) -> None:
        event = BiDirectionalEvent()
        woke = False

        async def waiter():
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
