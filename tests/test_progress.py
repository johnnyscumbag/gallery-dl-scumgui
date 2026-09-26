import unittest

from src.progress import parse_progress


class ProgressParserTests(unittest.TestCase):
    def test_standard_progress(self):
        result = parse_progress("16%   1.01MB 337.19kB/s")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.percent, 16)
        self.assertEqual(result.downloaded, "1.01MB")
        self.assertEqual(result.speed, "337.19kB/s")

    def test_progress_with_whitespace(self):
        result = parse_progress("  100%   12.5MB 2.4MB/s  ")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.percent, 100)

    def test_non_progress_line(self):
        self.assertIsNone(parse_progress("Downloading image.jpg"))

    def test_invalid_percentage(self):
        self.assertIsNone(parse_progress("101% 1MB 1MB/s"))


if __name__ == "__main__":
    unittest.main()
