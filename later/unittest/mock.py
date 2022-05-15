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
from __future__ import annotations

from typing import Any
from unittest.mock import call, DEFAULT

from .backport.mock import AsyncMock, create_autospec, MagicMock, Mock, patch


__all__ = [
    "AsyncContextManager",
    "AsyncMock",
    "MagicMock",
    "Mock",
    "call",
    "create_autospec",
    "patch",
]


def AsyncContextManager(return_value: Any = DEFAULT, instance: bool = False) -> Mock:
    """
    This helper sets up a Mock Tree to mock out an AsyncContextManager class.
    return_value: The object returned by the context manager
    instance: Instead of a Class, this mock represents and instance


    mock.assert_awaited() -> The context manager was __aentered__
    mock.assert_not_awaited() -> the context manager was not __aentered__
    """
    mock = Mock()
    manager_instance = AsyncMock()

    if instance:
        mock = manager_instance
    else:
        mock.return_value = manager_instance

    if return_value is not DEFAULT:
        manager_instance.__aenter__.return_value = return_value

    mock.assert_awaited = manager_instance.__aenter__.assert_awaited
    mock.assert_not_awaited = manager_instance.__aenter__.assert_not_awaited
    return mock
