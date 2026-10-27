import unittest

from utils import clamp, is_odd


class TestUtils(unittest.TestCase):
    def test_clamp(self) -> None:
        self.assertEqual(clamp(12, 0, 10), 10)

    def test_is_odd(self) -> None:
        self.assertTrue(is_odd(3))


if __name__ == "__main__":
    unittest.main()
