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
    async def test_patch_classmethods(self, patched):
        await Helper.async_class_method()

    @patch("later.tests.unittest.backport.test_mock.Helper.async_static_method")
    async def test_patch_staticmethods(self, patched):
        await Helper.async_static_method()

    @patch("later.tests.unittest.backport.test_mock.Helper.async_method")
    async def test_patch_methods(self, patched):
        await Helper().async_method()


if __name__ == "__main__":
    unittest.main()
