import unittest

import later


class VersionTests(unittest.TestCase):
    def test_version(self) -> None:
        self.assertIsInstance(later.__version__, str)
        self.assertEqual(later.__version__.count('.'), 2)
