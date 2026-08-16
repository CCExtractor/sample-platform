"""Tests for the run-to-run comparison behind the PR comment."""

import unittest
from types import SimpleNamespace

from mod_ci.comparison import (BROKEN_HERE, FAILING_DIFFERENTLY,
                               FAILING_IDENTICALLY, FIXED_HERE, NO_REFERENCE,
                               UNCHANGED_PASS, TestState, build_state,
                               classify, compare, summarise)


def entry(rt_id, error=False, files=()):
    """
    Build one ``get_test_results`` test entry.

    :param rt_id: Regression test id.
    :type rt_id: int
    :param error: The platform's verdict: True when the test failed.
    :type error: bool
    :param files: (output_id, got) pairs recorded for the test.
    :type files: Iterable[Tuple[int, Optional[str]]]
    :return: Entry shaped like the one get_test_results produces.
    :rtype: Dict[str, Any]
    """
    return {
        'test': SimpleNamespace(id=rt_id),
        'error': error,
        'files': [SimpleNamespace(regression_test_output_id=output_id, got=got)
                  for output_id, got in files],
    }


def category(entries):
    """
    Wrap test entries in a category, as get_test_results returns them.

    :param entries: The test entries in the category.
    :type entries: List[Dict[str, Any]]
    :return: Category structure.
    :rtype: Dict[str, Any]
    """
    return {'category': SimpleNamespace(name='Category'), 'tests': entries}


class BuildStateTests(unittest.TestCase):
    """A run summarised into one state per regression test."""

    def test_the_platform_verdict_is_taken_as_given(self):
        """passed mirrors get_test_results' own error flag, not a re-derivation.

        That flag already accounts for exit codes, missing outputs, and the
        alternative hashes an output may legitimately produce -- deciding it
        again here would create a second definition free to drift.
        """
        states = build_state([category([entry(1, error=False),
                                        entry(2, error=True, files=[(10, 'abc')])])])

        self.assertTrue(states[1].passed)
        self.assertFalse(states[2].passed)

    def test_a_variant_hash_that_the_platform_accepted_still_passes(self):
        """A recorded hash does not imply failure: outputs may have variants."""
        states = build_state([category([entry(1, error=False, files=[(10, 'a-known-variant')])])])

        self.assertTrue(states[1].passed)

    def test_signature_records_which_outputs_differed(self):
        """The signature is what distinguishes two failures of the same test."""
        states = build_state([category([entry(1, error=True, files=[(10, 'abc')])])])

        self.assertEqual(states[1].signature, ((10, 'abc'),))

    def test_signature_order_does_not_depend_on_row_order(self):
        """Two runs failing the same way must produce equal signatures."""
        one = build_state([category([entry(1, error=True, files=[(11, 'b'), (10, 'a')])])])
        other = build_state([category([entry(1, error=True, files=[(10, 'a'), (11, 'b')])])])

        self.assertEqual(one[1].signature, other[1].signature)

    def test_matching_outputs_leave_no_signature(self):
        """Rows without a recorded hash say nothing about how a test differed."""
        states = build_state([category([entry(1, error=False, files=[(10, None)])])])

        self.assertEqual(states[1].signature, ())


class ClassifyTests(unittest.TestCase):
    """How one test's behaviour reads against a reference run."""

    def setUp(self):
        """Name the two states every case is built from."""
        self.passing = TestState(passed=True, signature=())
        self.failing = TestState(passed=False, signature=((10, 'abc'),))
        self.failing_otherwise = TestState(passed=False, signature=((10, 'def'),))

    def test_broken_here(self):
        """Passing there and failing here is the finding worth surfacing."""
        self.assertEqual(classify(self.failing, self.passing), BROKEN_HERE)

    def test_fixed_here(self):
        """Failing there and passing here is the good news."""
        self.assertEqual(classify(self.passing, self.failing), FIXED_HERE)

    def test_identical_failure_is_not_this_change(self):
        """Same bytes on both sides: behaviour did not move, the baseline is stale."""
        self.assertEqual(classify(self.failing, self.failing), FAILING_IDENTICALLY)

    def test_different_failure_is_worth_a_look(self):
        """Both fail, but not the same way, so something did change."""
        self.assertEqual(classify(self.failing, self.failing_otherwise), FAILING_DIFFERENTLY)

    def test_unchanged_pass(self):
        """Passing on both sides."""
        self.assertEqual(classify(self.passing, self.passing), UNCHANGED_PASS)

    def test_absent_reference_is_not_good_news(self):
        """No record must never be reported as agreement."""
        self.assertEqual(classify(self.failing, None), NO_REFERENCE)
        self.assertEqual(classify(self.passing, None), NO_REFERENCE)


class CompareTests(unittest.TestCase):
    """Bucketing a whole run against a reference."""

    def test_buckets_every_test_exactly_once(self):
        """Nothing is dropped and nothing is double counted."""
        passing = TestState(passed=True, signature=())
        failing = TestState(passed=False, signature=((10, 'abc'),))
        current = {1: passing, 2: failing, 3: failing}
        reference = {1: passing, 2: passing, 3: failing}

        buckets = compare(current, reference)

        self.assertEqual(buckets[UNCHANGED_PASS], [1])
        self.assertEqual(buckets[BROKEN_HERE], [2])
        self.assertEqual(buckets[FAILING_IDENTICALLY], [3])
        self.assertEqual(sum(summarise(buckets).values()), len(current))

    def test_a_missing_reference_run_reports_no_reference(self):
        """A reference run we do not have is distinct from one that agreed."""
        current = {1: TestState(passed=False, signature=((10, 'abc'),))}

        buckets = compare(current, None)

        self.assertEqual(buckets[NO_REFERENCE], [1])
        self.assertEqual(buckets[FAILING_IDENTICALLY], [])

    def test_the_stale_baseline_case_reads_as_not_this_change(self):
        """The case this exists for: 45 tests failing identically to master.

        A branch that changed nothing relevant must not be described as
        breaking them, which is what the platform used to report.
        """
        drifted = TestState(passed=False, signature=((10, 'same-bytes'),))
        current = {rt: drifted for rt in range(1, 46)}
        reference = dict(current)

        buckets = compare(current, reference)

        self.assertEqual(len(buckets[FAILING_IDENTICALLY]), 45)
        self.assertEqual(buckets[BROKEN_HERE], [])
