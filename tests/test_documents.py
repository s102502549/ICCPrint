import unittest

from iccprint.documents import _valid_dpi


class DpiValidationTests(unittest.TestCase):
    def test_pair(self):
        self.assertEqual(_valid_dpi((300, 300)), (300.0, 300.0))

    def test_scalar(self):
        self.assertEqual(_valid_dpi(254), (254.0, 254.0))

    def test_invalid(self):
        self.assertIsNone(_valid_dpi((0, 300)))
        self.assertIsNone(_valid_dpi("not-a-dpi"))


if __name__ == "__main__":
    unittest.main()
