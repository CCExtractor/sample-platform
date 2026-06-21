"""Tests for the triage helpers that adapt RunSample results into failure rows."""

import unittest

from sp_cli import triage


class IsFailureTests(unittest.TestCase):
    """``is_failure`` keys off the RunSample status."""

    def test_fail_status_is_failure(self):
        """A 'fail' status counts as a failure worth triaging."""
        self.assertTrue(triage.is_failure({"status": "fail"}))

    def test_missing_output_is_failure(self):
        """A 'missing_output' status counts as a failure."""
        self.assertTrue(triage.is_failure({"status": "missing_output"}))

    def test_pass_status_is_not_failure(self):
        """A 'pass' status is not a failure."""
        self.assertFalse(triage.is_failure({"status": "pass"}))

    def test_missing_status_is_not_failure(self):
        """A result with no status is not treated as a failure."""
        self.assertFalse(triage.is_failure({}))


class HasOutputDiffTests(unittest.TestCase):
    """``has_output_diff`` prefers per-output status, matching the API's 'pass'."""

    def test_passing_output_is_not_a_diff(self):
        """A per-output status of 'pass' must not be reported as a diff."""
        sample = {"status": "fail", "outputs": [{"status": "pass"}]}
        self.assertFalse(triage.has_output_diff(sample))

    def test_failing_output_is_a_diff(self):
        """A per-output status other than 'pass' is a differing output."""
        sample = {"status": "fail", "outputs": [{"status": "fail"}]}
        self.assertTrue(triage.has_output_diff(sample))

    def test_mixed_outputs_report_a_diff(self):
        """If any output differs, the sample has an output diff."""
        sample = {"status": "fail",
                  "outputs": [{"status": "pass"}, {"status": "fail"}]}
        self.assertTrue(triage.has_output_diff(sample))

    def test_no_outputs_falls_back_to_matching_exit_code(self):
        """Without per-output data, a fail whose exit code matched is a diff."""
        sample = {"status": "fail", "exit_code": 0, "expected_rc": 0}
        self.assertTrue(triage.has_output_diff(sample))

    def test_no_outputs_and_exit_mismatch_is_not_a_diff(self):
        """Without per-output data, a fail with a mismatched exit code is not a diff."""
        sample = {"status": "fail", "exit_code": 1, "expected_rc": 0}
        self.assertFalse(triage.has_output_diff(sample))


class ClassifySampleTests(unittest.TestCase):
    """``classify_sample`` flattens a RunSample into an agent-friendly row."""

    def test_carries_ids_and_classification(self):
        """The row carries the result ids plus the classification code."""
        sample = {
            "regression_test_id": 42,
            "sample_id": 7,
            "sample_name": "dvb_subtitles",
            "categories": ["DVB"],
            "exit_code": 10,
            "expected_rc": 0,
            "status": "fail",
            "outputs": [{"status": "pass"}],
        }
        row = triage.classify_sample(sample)
        self.assertEqual(row["regression_test_id"], 42)
        self.assertEqual(row["sample_id"], 7)
        self.assertEqual(row["sample_name"], "dvb_subtitles")
        self.assertEqual(row["categories"], ["DVB"])
        self.assertIn("code", row)
        self.assertIn("confidence", row)
        self.assertIn("reason", row)


class GroupByCodeTests(unittest.TestCase):
    """``group_by_code`` counts failures by code, highest first."""

    def test_counts_sorted_descending(self):
        """Codes are returned ordered by frequency, most common first."""
        failures = [
            {"code": "EXIT_CODE_MISMATCH"},
            {"code": "SEGFAULT"},
            {"code": "EXIT_CODE_MISMATCH"},
        ]
        counts = triage.group_by_code(failures)
        self.assertEqual(counts, {"EXIT_CODE_MISMATCH": 2, "SEGFAULT": 1})
        self.assertEqual(next(iter(counts)), "EXIT_CODE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
