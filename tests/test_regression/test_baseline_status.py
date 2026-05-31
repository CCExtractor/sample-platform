"""Tests for the BaselineStatus feature on RegressionTest.

Verifies the state-machine transitions in RegressionTest.update_baseline_status
and the is_regression property.
"""

from flask import g

from mod_regression.models import BaselineStatus, RegressionTest
from tests.base import BaseTestCase


class TestBaselineStatus(BaseTestCase):
    """Tests for the BaselineStatus state machine."""

    def _get_regression_test(self, test_id: int = 1) -> RegressionTest:
        """Fetch a RegressionTest from the test database."""
        return RegressionTest.query.filter(RegressionTest.id == test_id).first()

    # ------------------------------------------------------------------
    # Initial state
    # ------------------------------------------------------------------

    def test_new_regression_test_has_unknown_baseline(self):
        """A freshly created regression test must have baseline_status = unknown."""
        rt = self._get_regression_test()
        self.assertEqual(rt.baseline_status, BaselineStatus.unknown)

    # ------------------------------------------------------------------
    # unknown -> established (first run passes)
    # ------------------------------------------------------------------

    def test_unknown_pass_transitions_to_established(self):
        """unknown + pass -> established."""
        rt = self._get_regression_test()
        self.assertEqual(rt.baseline_status, BaselineStatus.unknown)

        changed = rt.update_baseline_status(passed=True)

        self.assertTrue(changed)
        self.assertEqual(rt.baseline_status, BaselineStatus.established)

    # ------------------------------------------------------------------
    # unknown -> never_worked (first run fails)
    # ------------------------------------------------------------------

    def test_unknown_fail_transitions_to_never_worked(self):
        """unknown + fail -> never_worked."""
        rt = self._get_regression_test()
        self.assertEqual(rt.baseline_status, BaselineStatus.unknown)

        changed = rt.update_baseline_status(passed=False)

        self.assertTrue(changed)
        self.assertEqual(rt.baseline_status, BaselineStatus.never_worked)

    # ------------------------------------------------------------------
    # never_worked -> established (first pass after never working)
    # ------------------------------------------------------------------

    def test_never_worked_pass_transitions_to_established(self):
        """never_worked + pass -> established."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=False)  # unknown -> never_worked
        self.assertEqual(rt.baseline_status, BaselineStatus.never_worked)

        changed = rt.update_baseline_status(passed=True)

        self.assertTrue(changed)
        self.assertEqual(rt.baseline_status, BaselineStatus.established)

    # ------------------------------------------------------------------
    # never_worked + fail -> never_worked (no change)
    # ------------------------------------------------------------------

    def test_never_worked_fail_stays_never_worked(self):
        """never_worked + fail -> never_worked (no transition)."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=False)  # unknown -> never_worked

        changed = rt.update_baseline_status(passed=False)

        self.assertFalse(changed)
        self.assertEqual(rt.baseline_status, BaselineStatus.never_worked)

    # ------------------------------------------------------------------
    # established + pass -> established (no change)
    # ------------------------------------------------------------------

    def test_established_pass_stays_established(self):
        """established + pass -> established (no transition)."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=True)  # unknown -> established

        changed = rt.update_baseline_status(passed=True)

        self.assertFalse(changed)
        self.assertEqual(rt.baseline_status, BaselineStatus.established)

    # ------------------------------------------------------------------
    # established + fail -> established (regression, not never_worked)
    # ------------------------------------------------------------------

    def test_established_fail_stays_established(self):
        """established + fail -> established (it is a regression, not never_worked)."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=True)  # unknown -> established

        changed = rt.update_baseline_status(passed=False)

        self.assertFalse(changed)
        self.assertEqual(rt.baseline_status, BaselineStatus.established)

    # ------------------------------------------------------------------
    # is_regression property
    # ------------------------------------------------------------------

    def test_is_regression_false_when_unknown(self):
        """A test with unknown baseline cannot be a regression."""
        rt = self._get_regression_test()
        self.assertFalse(rt.is_regression)

    def test_is_regression_false_when_never_worked(self):
        """A test that never worked is not a regression when it fails."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=False)
        self.assertFalse(rt.is_regression)

    def test_is_regression_true_when_established(self):
        """An established test that fails is a true regression."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=True)
        self.assertTrue(rt.is_regression)

    # ------------------------------------------------------------------
    # Persistence: changes survive a database round-trip
    # ------------------------------------------------------------------

    def test_baseline_status_persists_to_database(self):
        """Verify baseline_status is actually saved and reloaded from DB."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=False)  # unknown -> never_worked
        g.db.add(rt)
        g.db.commit()

        reloaded = RegressionTest.query.filter(RegressionTest.id == 1).first()
        self.assertEqual(reloaded.baseline_status, BaselineStatus.never_worked)

    def test_established_status_persists_to_database(self):
        """Verify established status is saved and reloaded from DB."""
        rt = self._get_regression_test()
        rt.update_baseline_status(passed=True)  # unknown -> established
        g.db.add(rt)
        g.db.commit()

        reloaded = RegressionTest.query.filter(RegressionTest.id == 1).first()
        self.assertEqual(reloaded.baseline_status, BaselineStatus.established)
