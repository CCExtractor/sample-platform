import os
import tempfile

from mod_api.services.diff_service import (_compute_hunks, compute_diff,
                                           file_sha256, read_lines)
from tests.api.base import ApiTestCase


class TestDiffService(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.test_dir.name
        from unittest.mock import patch
        patcher = patch(
            'mod_api.services.diff_service._enforce_safe_path', return_value=True)
        self.addCleanup(patcher.stop)
        self.mock_safe = patcher.start()

    def tearDown(self):
        self.test_dir.cleanup()
        super().tearDown()

    def create_file(self, filename, content, encoding='utf-8'):
        path = os.path.join(self.dir_path, filename)
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
        return path

    def test_compute_diff_identical(self):
        content = "line1\nline2\n"
        path1 = self.create_file("file1.txt", content)
        path2 = self.create_file("file2.txt", content)

        diff = compute_diff(path1, path2)
        self.assertEqual(diff['status'], 'identical')
        self.assertEqual(diff['summary']['added_lines'], 0)
        self.assertEqual(diff['summary']['removed_lines'], 0)
        self.assertEqual(len(diff['hunks']), 0)

    def test_compute_diff_missing_expected(self):
        path2 = self.create_file("file2.txt", "content")

        diff = compute_diff(os.path.join(self.dir_path, "missing.txt"), path2)
        self.assertEqual(diff['status'], 'missing_expected')

    def test_compute_diff_missing_actual(self):
        path1 = self.create_file("file1.txt", "content")

        diff = compute_diff(path1, os.path.join(self.dir_path, "missing.txt"))
        self.assertEqual(diff['status'], 'missing_actual')

    def test_compute_diff_different(self):
        content1 = "line1\nline2\nline3\n"
        content2 = "line1\nline_new\nline3\n"
        path1 = self.create_file("file1.txt", content1)
        path2 = self.create_file("file2.txt", content2)

        diff = compute_diff(path1, path2)
        self.assertEqual(diff['status'], 'different')
        self.assertEqual(diff['summary']['added_lines'], 1)
        self.assertEqual(diff['summary']['removed_lines'], 1)
        self.assertEqual(diff['summary']['changed_hunks'], 1)
        self.assertEqual(len(diff['hunks']), 1)

        hunk = diff['hunks'][0]
        self.assertEqual(hunk['expected_start'], 1)
        self.assertEqual(hunk['actual_start'], 1)

    def test_compute_diff_context_lines_clamped(self):
        content1 = "\n".join(str(i) for i in range(1, 201)) + "\n"
        content2 = content1.replace("\n100\n", "\n100_new\n")
        path1 = self.create_file("file1.txt", content1)
        path2 = self.create_file("file2.txt", content2)

        diff = compute_diff(path1, path2, context_lines=200)
        self.assertEqual(diff['status'], 'different')
        hunk = diff['hunks'][0]
        # max context is 50 before and 50 after, plus 1 removed and 1 added = 102 lines total
        self.assertEqual(len(hunk['lines']), 102)

    def test_compute_hunks_max_hunks(self):
        lines1 = ["1", "2", "3", "4", "5"]
        lines2 = ["1a", "2", "3a", "4", "5a"]
        # With context_lines=0 we should get 3 separate hunks
        hunks = _compute_hunks(lines1, lines2, context_lines=0, max_hunks=2)
        self.assertEqual(len(hunks), 2)  # bounded to 2

    def test_compute_hunks_parsing(self):
        lines1 = ["common", "remove_me", "common"]
        lines2 = ["common", "add_me", "common"]
        hunks = _compute_hunks(lines1, lines2, context_lines=1, max_hunks=10)
        self.assertEqual(len(hunks), 1)
        lines = hunks[0]['lines']
        self.assertEqual(lines[0]['kind'], 'context')
        self.assertEqual(lines[1]['kind'], 'removed')
        self.assertEqual(lines[2]['kind'], 'added')
        self.assertEqual(lines[3]['kind'], 'context')

    def test_read_lines_utf8(self):
        path = os.path.join(self.dir_path, "utf8.txt")
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write("line1\r\nline2\n")
        lines = read_lines(path)
        self.assertEqual(lines, ["line1", "line2"])

    def test_read_lines_cp1252(self):
        path = os.path.join(self.dir_path, "cp1252.txt")
        # Write bytes that are valid cp1252 but invalid utf-8
        with open(path, 'wb') as f:
            # \x80 is euro sign in cp1252, invalid start byte in utf-8
            f.write(b"line1\r\n\x80line2")

        lines = read_lines(path)
        # \x80 maps to \u20ac
        self.assertEqual(lines, ["line1", "\u20acline2"])

    def test_file_sha256(self):
        path = self.create_file("sha.txt", "hello")
        sha = file_sha256(path)
        # sha256("hello") = 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
        self.assertEqual(
            sha, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")

        self.assertIsNone(file_sha256(
            os.path.join(self.dir_path, "nonexistent.txt")))
