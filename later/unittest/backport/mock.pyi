# fb has some local typeshed for unittest.mock with more than ANY for everything
# So we rely on what ever typehed is available to the end user.

from typing import Any, List, Optional, Sequence
from unittest.mock import (
    ANY as ANY,
    Base,
    call as call,
    create_autospec as create_autospec,
    DEFAULT as DEFAULT,
    FILTER_DIR as FILTER_DIR,
    MagicMock as MagicMock,
    Mock as Mock,
    mock_open as mock_open,
    NonCallableMagicMock as NonCallableMagicMock,
    NonCallableMock as NonCallableMock,
    patch as patch,
    PropertyMock as PropertyMock,
    seal as seal,
    sentinel as sentinel,
)

class AsyncMockMixin(Base):
    await_count: int
    # pyre-fixme[11]: Annotation `call` is not defined as a type.
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
