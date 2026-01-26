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
Mock utilities for async testing.

This module re-exports common mocking utilities from :mod:`unittest.mock` and
provides additional helpers for testing asynchronous context managers.

Re-exports:
    - :class:`AsyncMock`: Mock for async callables
    - :class:`MagicMock`: Mock with sensible defaults for magic methods
    - :class:`Mock`: Basic mock object
    - :func:`call`: Helper for making assertions about mock calls
    - :func:`create_autospec`: Create a mock with the spec of another object
    - :func:`patch`: Context manager/decorator for mocking

Custom helpers:
    - :func:`AsyncContextManager`: Create a mock for async context managers
"""

from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    call,
    create_autospec,
    DEFAULT,
    MagicMock,
    Mock,
    patch,
)


__all__ = [
    "AsyncContextManager",
    "AsyncMock",
    "MagicMock",
    "Mock",
    "call",
    "create_autospec",
    "patch",
]


def AsyncContextManager(return_value: object = DEFAULT, instance: bool = False) -> Mock:
    """
    Create a mock for an async context manager.

    This helper sets up a mock tree to properly mock out an async context
    manager class or instance. It handles the ``__aenter__`` and ``__aexit__``
    protocol automatically.

    Args:
        return_value: The value returned by ``__aenter__`` when entering
            the context. Defaults to :data:`unittest.mock.DEFAULT`.
        instance: If ``True``, the returned mock represents an instance
            of a context manager. If ``False`` (default), it represents
            a class that must be instantiated.

    Returns:
        A :class:`Mock` with additional helper methods:
        - ``assert_awaited()``: Assert the context manager was entered
        - ``assert_not_awaited()``: Assert the context manager was not entered

    Example::

        # Mocking a context manager class
        mock_cm = AsyncContextManager(return_value="data")
        with patch("module.SomeAsyncCM", mock_cm):
            async with SomeAsyncCM() as result:
                assert result == "data"
        mock_cm.assert_awaited()

        # Mocking an instance directly
        mock_instance = AsyncContextManager(return_value="data", instance=True)
        with patch("module.cm_instance", mock_instance):
            async with cm_instance as result:
                assert result == "data"
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
