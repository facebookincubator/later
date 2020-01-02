from unittest.mock import call

from later.unittest import TestCase
from later.unittest.mock import AsyncContextManager


class TestAsyncContextManagerMock(TestCase):
    async def test_return_value(self) -> None:

        mock = AsyncContextManager(return_value=10)

        async with mock() as val:
            self.assertEqual(val, 10)
            mock.assert_awaited()
            mock.assert_called()

    async def test_call_args(self) -> None:
        c = call(expire=True)
        mock = AsyncContextManager()

        async with mock(expire=True):
            mock.assert_awaited()
            self.assertEqual(mock.call_args, c)

    async def test_as_instance(self) -> None:
        mock = AsyncContextManager(return_value=10, instance=True)

        async with mock as val:
            mock.assert_awaited()
            self.assertEqual(val, 10)

    async def test_created_but_not_aentered(self) -> None:

        mock = AsyncContextManager()

        m = mock()

        mock.assert_called()
        mock.assert_not_awaited()

        async with m:
            pass

        mock.assert_awaited()