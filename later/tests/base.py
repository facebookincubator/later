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

import sys
import unittest

from later.tests.test_event import Test_BiDirectionalEvent  # noqa: F401
from later.tests.test_task import TaskTests, WatcherTests  # noqa: F401
from later.tests.test_version import VersionTests  # noqa: F401

from later.tests.unittest.test_case import (  # noqa: F401
    IgnoreAsyncioErrorsTestCase,
    IgnoreTaskLeaksTestCase,
    TestTestCase,
)
from later.tests.unittest.test_mock import TestAsyncContextManagerMock  # noqa: F401


if __name__ == "__main__":
    unittest.main()
