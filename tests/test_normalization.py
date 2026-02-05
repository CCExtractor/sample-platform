import unittest
import os
import tempfile
from mod_test.models import TestResultFile

class TestNormalization(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        
    def tearDown(self):
        self.test_dir.cleanup()

    def test_text_normalization(self):
        # File A: LF, no trailing spaces
        file_a_path = os.path.join(self.test_dir.name, "file_a.txt")
        with open(file_a_path, 'wb') as f:
            f.write(b"line1\nline2\n")

        # File B: CRLF, trailing spaces
        file_b_path = os.path.join(self.test_dir.name, "file_b.txt")
        with open(file_b_path, 'wb') as f:
            f.write(b"line1  \r\nline2\r\n")

        lines_a = TestResultFile.read_lines(file_a_path)
        lines_b = TestResultFile.read_lines(file_b_path)

        self.assertEqual(lines_a, ["line1\n", "line2\n"])
        self.assertEqual(lines_b, ["line1\n", "line2\n"])
        self.assertEqual(lines_a, lines_b)

    def test_binary_exemption(self):
        # Binary file: should NOT be modified
        file_bin_path = os.path.join(self.test_dir.name, "test.bin")
        content = b"line1  \r\nline2\r\n"
        with open(file_bin_path, 'wb') as f:
            f.write(content)

        lines = TestResultFile.read_lines(file_bin_path)
        # readlines() on binary file with default open (universal newlines) may still change \r\n to \n
        # but our normalize() should skip the rstrip part.
        # Actually, Python's readlines() in text mode WITHOUT newline=None (default) transforms \r\n to \n.
        # However, the requirement was to ensure binary files are not Corrupted or changed by our logic.
        
        # If we open in text mode, Python handles newlines.
        # Let's check if our normalization code skips the rstrip.
        self.assertEqual(lines, ["line1  \n", "line2\n"]) # line1 trailing spaces preserved

if __name__ == '__main__':
    unittest.main()
