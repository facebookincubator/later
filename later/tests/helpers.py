from unittest.mock import Mock


__all__ = ["AsyncMock"]


class AsyncMock(Mock):
    """
    This mock is suitable to mock functions returning awaitable
    """

    def __call__(self, *args, **kwargs):
        async def coro():
            return super(AsyncMock, self).__call__(*args, **kwargs)

        return coro()
