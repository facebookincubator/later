# This file was copied from typeshed and modified to expose types for IsolatedAsyncioTestCase
# It is licensed as typeshed see https://github.com/python/typeshed/blob/master/LICENSE
import sys
from typing import Any, Awaitable, Callable
from unittest import TestCase

class IsolatedAsyncioTestCase(TestCase):
    async def asyncSetUp(self) -> None: ...
    async def asyncTearDown(self) -> None: ...
    def addAsyncCleanup(
        self, __func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> None: ...
