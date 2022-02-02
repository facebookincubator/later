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
# under the License
import unittest

from later.unittest.backport.async_case import IsolatedAsyncioTestCase
from later.unittest.backport.mock import patch


class Helper:
    @classmethod
    async def async_class_method(cls):
        raise Exception("Should never happen")

    @staticmethod
    async def async_static_method():
        raise Exception("Should never happen")

    async def async_method(self):
        raise Exception("Should never happen")


class TestPatch(IsolatedAsyncioTestCase):
    @patch("later.tests.unittest.backport.test_mock.Helper.async_class_method")
    async def test_patch_classmethods(self, patched) -> None:
        await Helper.async_class_method()

    @patch("later.tests.unittest.backport.test_mock.Helper.async_static_method")
    async def test_patch_staticmethods(self, patched) -> None:
        await Helper.async_static_method()

    @patch("later.tests.unittest.backport.test_mock.Helper.async_method")
    async def test_patch_methods(self, patched) -> None:
        await Helper().async_method()


if __name__ == "__main__":
    unittest.main()
