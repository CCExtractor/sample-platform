import datetime

from flask import g

from mod_api.services.status import (derive_output_status, derive_run_status,
                                     derive_sample_status, get_run_timestamps,
                                     is_dummy_row)
from mod_regression.models import RegressionTestOutput
from mod_regression.models import \
    RegressionTestOutputFiles as RegressionTestMultipleFiles
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)
from tests.api.base import ApiTestCase


class TestServicesStatus(ApiTestCase):
    def setUp(self):
        super().setUp()
        fork = Fork('https://github.com/test/test.git')
        g.db.add(fork)
        g.db.commit()
        self.test_obj = Test(TestPlatform.linux,
                             TestType.commit, fork.id, 'master', 'commit_hash')
        g.db.add(self.test_obj)
        g.db.commit()

    def test_derive_run_status_queued(self):
        self.assertEqual(derive_run_status(self.test_obj), 'queued')

    def test_derive_run_status_running(self):
        tp = TestProgress(self.test_obj.id, TestStatus.testing, 'testing')
        g.db.add(tp)
        g.db.commit()
        self.assertEqual(derive_run_status(self.test_obj), 'running')

    def test_derive_run_status_pass(self):
        tp = TestProgress(self.test_obj.id, TestStatus.completed, 'done')
        # A passing result: exit code matches and the expected output for
        # regression test 1 was produced and matched (got=None).
        tr = TestResult(self.test_obj.id, 1, 100, 0, 0)
        rf = TestResultFile(self.test_obj.id, 1, 1, 'sample_out1')
        g.db.add_all([tp, tr, rf])
        g.db.commit()
        self.assertEqual(derive_run_status(self.test_obj), 'pass')

    def test_derive_run_status_completed_without_results_is_error(self):
        # A run marked completed that reported zero TestResult rows must
        # not show green — the worker finished without reporting anything.
        tp = TestProgress(self.test_obj.id, TestStatus.completed, 'done')
        g.db.add(tp)
        g.db.commit()
        self.assertEqual(derive_run_status(self.test_obj), 'error')

    def test_derive_run_status_fail(self):
        tp = TestProgress(self.test_obj.id, TestStatus.completed, 'done')
        # runtime 100, exit_code 1, expected 0
        tr = TestResult(self.test_obj.id, 1, 100, 1, 0)
        g.db.add(tp)
        g.db.add(tr)
        g.db.commit()
        self.assertEqual(derive_run_status(self.test_obj), 'fail')

    def test_derive_run_status_canceled_covers_infra_error(self):
        tp = TestProgress(self.test_obj.id,
                          TestStatus.canceled, 'canceled by admin')
        g.db.add(tp)
        g.db.commit()
        self.assertEqual(derive_run_status(self.test_obj), 'canceled')

    def test_derive_run_status_incomplete(self):
        from unittest.mock import MagicMock

        from mod_api.services.status import _compute_run_status
        mock_prog = MagicMock()
        mock_prog.status = "some_unknown_status"
        res = _compute_run_status([mock_prog], {}, {}, self.test_obj.id)
        self.assertEqual(res, 'incomplete')

    def test_is_dummy_row(self):
        rf = TestResultFile(1, 1, -1, '', 'error')
        self.assertTrue(is_dummy_row(rf))
        rf2 = TestResultFile(1, 1, 1, 'expected', 'got')
        self.assertFalse(is_dummy_row(rf2))

    def test_derive_sample_status_not_started(self):
        self.assertEqual(derive_sample_status(None, []), 'not_started')

    def test_derive_sample_status_missing_output(self):
        tr = TestResult(1, 1, 100, 0, 0)
        rf = TestResultFile(1, 1, -1, '', 'error')
        self.assertEqual(derive_sample_status(tr, [rf]), 'missing_output')

    def test_derive_sample_status_fail_rc(self):
        tr = TestResult(1, 1, 100, 1, 0)
        self.assertEqual(derive_sample_status(tr, []), 'fail')

    def test_derive_sample_status_fail_diff(self):
        tr = TestResult(1, 1, 100, 0, 0)
        rf = TestResultFile(1, 1, 1, 'expected_hash', 'got_hash')
        self.assertEqual(derive_sample_status(tr, [rf]), 'fail')

    def test_derive_sample_status_pass(self):
        tr = TestResult(1, 1, 100, 0, 0)
        rf = TestResultFile(1, 1, 1, 'expected_hash', None)
        self.assertEqual(derive_sample_status(tr, [rf]), 'pass')

    def test_derive_sample_status_pass_multi(self):
        tr = TestResult(1, 1, 100, 0, 0)
        rf = TestResultFile(1, 1, 1, 'expected_hash', 'got_hash')
        rto = RegressionTestOutput(1, 1, 'expected_hash', 'output.txt')
        multi = RegressionTestMultipleFiles('got_hash', 1)
        multi.file_hashes = 'got_hash'
        rto.multiple_files = [multi]
        rf.regression_test_output = rto
        self.assertEqual(derive_sample_status(tr, [rf]), 'pass')

    def test_derive_sample_status_missing_output_expected(self):
        """Missing output detected when expected non-ignored output has no result file."""
        tr = TestResult(1, 1, 100, 0, 0)
        rto = RegressionTestOutput(1, 'hash', '.txt', 'out')
        g.db.add(rto)
        g.db.commit()
        self.assertEqual(derive_sample_status(tr, [], expected_outputs=[rto]), 'missing_output')

    def test_derive_sample_status_pass_with_expected_outputs(self):
        """Pass when all expected outputs have matching result files."""
        tr = TestResult(1, 1, 100, 0, 0)
        rto = RegressionTestOutput(1, 'hash', '.txt', 'out')
        g.db.add(rto)
        g.db.commit()
        rf = TestResultFile(1, 1, rto.id, 'hash', None)
        self.assertEqual(derive_sample_status(tr, [rf], expected_outputs=[rto]), 'pass')

    def test_derive_sample_status_ignored_output_not_missing(self):
        """Ignored expected outputs should not trigger missing_output."""
        tr = TestResult(1, 1, 100, 0, 0)
        rto = RegressionTestOutput(1, 'hash', '.txt', 'out', ignore=True)
        g.db.add(rto)
        g.db.commit()
        self.assertEqual(derive_sample_status(tr, [], expected_outputs=[rto]), 'pass')

    def test_derive_output_status(self):
        rf_dummy = TestResultFile(-1, -1, -1, '', 'error')
        self.assertEqual(derive_output_status(rf_dummy), 'missing_output')

        rf_match = TestResultFile(1, 1, 1, 'exp', None)
        self.assertEqual(derive_output_status(rf_match), 'pass')

        rf_diff = TestResultFile(1, 1, 1, 'exp', 'got')
        self.assertEqual(derive_output_status(rf_diff), 'fail')

    def test_get_run_timestamps(self):
        ts = get_run_timestamps(self.test_obj)
        self.assertIsNone(ts['created_at'])

        tp1 = TestProgress(self.test_obj.id, TestStatus.preparation, 'queued')
        tp1.timestamp = datetime.datetime(2023, 1, 1, 10, 0, 0)
        g.db.add(tp1)

        tp2 = TestProgress(self.test_obj.id, TestStatus.testing, 'testing')
        tp2.timestamp = datetime.datetime(2023, 1, 1, 10, 5, 0)
        g.db.add(tp2)

        tp3 = TestProgress(self.test_obj.id, TestStatus.completed, 'done')
        tp3.timestamp = datetime.datetime(2023, 1, 1, 10, 10, 0)
        g.db.add(tp3)
        g.db.commit()

        ts2 = get_run_timestamps(self.test_obj)
        self.assertEqual(ts2['created_at'], tp1.timestamp)
        self.assertEqual(ts2['queued_at'], tp1.timestamp)
        self.assertEqual(ts2['started_at'], tp2.timestamp)
        self.assertEqual(ts2['completed_at'], tp3.timestamp)
