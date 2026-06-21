"""Tests for the rule-based failure classifier, using real examples from run #9299."""

import unittest

from sp_cli import classifier


class ClassifierTests(unittest.TestCase):
    """Each case is grounded in a real failure observed in the friction study."""

    def test_exit_code_mismatch(self):
        """`10 (Expected 0)` — the common CEA-708 failure in run #9299."""
        result = classifier.classify(10, 0)
        self.assertEqual(result["code"], classifier.CODE_EXIT_CODE_MISMATCH)
        self.assertEqual(result["confidence"], "high")
        self.assertIn("10", result["reason"])

    def test_windows_segfault_normalized(self):
        """`-1073741819` (0xC0000005) on Windows — the DVB failure in #9299."""
        result = classifier.classify(-1073741819, 0)
        self.assertEqual(result["code"], classifier.CODE_SEGFAULT)
        self.assertEqual(result["confidence"], "high")

    def test_linux_segfault_normalized(self):
        """`139` on Linux is the same crash — must map to the same code."""
        self.assertEqual(classifier.classify(139, 0)["code"], classifier.CODE_SEGFAULT)

    def test_abort(self):
        """`134` (SIGABRT) classifies as ABORT."""
        self.assertEqual(classifier.classify(134, 0)["code"], classifier.CODE_ABORT)

    def test_timeout(self):
        """`124` (timeout) classifies as TIMEOUT."""
        self.assertEqual(classifier.classify(124, 0)["code"], classifier.CODE_TIMEOUT)

    def test_missing_output(self):
        """'No output generated but there should be' — exit matches but output missing."""
        result = classifier.classify(0, 0, missing_output=True)
        self.assertEqual(result["code"], classifier.CODE_MISSING_OUTPUT)

    def test_output_diff(self):
        """Exit code matches but the output file differs."""
        result = classifier.classify(0, 0, has_output_diff=True)
        self.assertEqual(result["code"], classifier.CODE_OUTPUT_DIFF)
        self.assertEqual(result["confidence"], "medium")

    def test_pass(self):
        """Exit matches, no diff, nothing missing → PASS."""
        self.assertEqual(classifier.classify(0, 0)["code"], classifier.CODE_PASS)

    def test_crash_beats_exit_mismatch(self):
        """A segfault is reported as SEGFAULT, not a generic exit mismatch."""
        self.assertEqual(classifier.classify(139, 0)["code"], classifier.CODE_SEGFAULT)

    def test_regression_flag_true_when_previously_passed(self):
        """A failure on a test that has passed before is a real regression."""
        self.assertTrue(classifier.classify(10, 0, has_ever_passed=True)["regression"])

    def test_regression_flag_false_when_never_passed(self):
        """A failure on a test that never passed is pre-existing (never worked)."""
        self.assertFalse(classifier.classify(10, 0, has_ever_passed=False)["regression"])

    def test_regression_flag_none_when_unknown(self):
        """Without history, the regression flag is None (unknown)."""
        self.assertIsNone(classifier.classify(10, 0)["regression"])


if __name__ == "__main__":
    unittest.main()
