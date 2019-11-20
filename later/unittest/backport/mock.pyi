# fb has some local typeshed for unittest.mock with more than ANY for everything
# So we rely on what ever typehed is available to the end user.

from typing import Any, List, Optional, Sequence
from unittest.mock import (
    ANY as ANY,
    DEFAULT as DEFAULT,
    FILTER_DIR as FILTER_DIR,
    Base,
    MagicMock as MagicMock,
    Mock as Mock,
    NonCallableMagicMock as NonCallableMagicMock,
    NonCallableMock as NonCallableMock,
    PropertyMock as PropertyMock,
    call as call,
    create_autospec as create_autospec,
    mock_open as mock_open,
    patch as patch,
    seal as seal,
    sentinel as sentinel,
)

class AsyncMockMixin(Base):
    await_count: int
    await_args: Optional[call]
    await_args_list: List[call]
    def assert_awaited(self) -> None: ...
    def assert_awaited_once(self) -> None: ...
    def assert_awaited_with(self, *args: Any, **kws: Any) -> None: ...
    def assert_awaited_once_with(self, *args: Any, **kws: Any) -> None: ...
    def assert_any_await(self, *args: Any, **kws: Any) -> None: ...
    def assert_has_awaits(
        self, calls: Sequence[call], any_order: bool = ...
    ) -> None: ...
    def assert_not_awaited(self) -> None: ...

class AsyncMock(AsyncMockMixin, Mock): ...
