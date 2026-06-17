import datetime
from unittest.mock import MagicMock, PropertyMock

from flask import g

from mod_api.services.error_service import (_classify_infra_error,
                                            _get_sample_id,
                                            derive_error_summary,
                                            derive_errors_for_run,
                                            derive_infrastructure_errors)
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput)
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)
from tests.base import BaseTestCase


class TestServicesErrorService(BaseTestCase):
    def setUp(self):
        super().setUp()
        fork = Fork('https://github.com/test/test.git')
        g.db.add(fork)
        g.db.commit()
        self.test_obj = Test(TestPlatform.linux,
                             TestType.commit, fork.id, 'master', 'commit_hash')
        g.db.add(self.test_obj)
        g.db.commit()

        self.category = Category('Test Category', 'Description')
        g.db.add(self.category)
        g.db.commit()

        self.reg_test1 = RegressionTest(
            1, 'cmd1', InputType.file, OutputType.file, self.category.id, 0)
        self.reg_test2 = RegressionTest(
            1, 'cmd2', InputType.file, OutputType.file, self.category.id, 0)
        g.db.add_all([self.reg_test1, self.reg_test2])
        g.db.commit()

        self.reg_out1 = RegressionTestOutput(
            self.reg_test1.id, 'sample1_out', '.txt', 'exp1')
        self.reg_out2 = RegressionTestOutput(
            self.reg_test2.id, 'sample2_out', '.txt', 'exp2')
        g.db.add_all([self.reg_out1, self.reg_out2])

        dummy_out = RegressionTestOutput(
            self.reg_test1.id, 'dummy', '', 'dummy')
        dummy_out.id = -1
        g.db.merge(dummy_out)

        g.db.commit()

    def test_derive_errors_for_run_rc_mismatch(self):
        tr = TestResult(self.test_obj.id, self.reg_test1.id,
                        100, 1, 0)  # runtime, exit_code, expected_rc
        g.db.add(tr)
        g.db.commit()

        errors = derive_errors_for_run(self.test_obj.id)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['type'], 'exit_code_mismatch')
        self.assertEqual(errors[0]['severity'], 'error')

    def test_derive_errors_for_run_missing_output(self):
        tr = TestResult(self.test_obj.id, self.reg_test1.id, 100, 0, 0)
        rf = TestResultFile(
            self.test_obj.id, self.reg_test1.id, -1, '', 'error')
        g.db.add_all([tr, rf])
        g.db.commit()

        errors = derive_errors_for_run(self.test_obj.id)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['type'], 'missing_output')

    def test_derive_errors_for_run_diff_mismatch(self):
        tr = TestResult(self.test_obj.id, self.reg_test1.id, 100, 0, 0)
        rf = TestResultFile(self.test_obj.id, self.reg_test1.id,
                            self.reg_out1.id, 'expected_hash', 'got_hash')
        g.db.add_all([tr, rf])
        g.db.commit()

        errors = derive_errors_for_run(self.test_obj.id)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['type'], 'diff_mismatch')
        self.assertEqual(errors[0]['severity'], 'warning')

    def test_derive_error_summary(self):
        tr1 = TestResult(self.test_obj.id, self.reg_test1.id,
                         100, 1, 0)  # rc mismatch
        tr2 = TestResult(self.test_obj.id, self.reg_test2.id, 100, 0, 0)
        rf2 = TestResultFile(self.test_obj.id, self.reg_test2.id,
                             self.reg_out2.id, 'exp', 'got')  # diff mismatch
        g.db.add_all([tr1, tr2, rf2])
        g.db.commit()

        summary = derive_error_summary(self.test_obj.id)
        self.assertEqual(len(summary), 2)

        # summary is a list of buckets
        summary_dict = {b['key']: b for b in summary}

        self.assertEqual(summary_dict['exit_code_mismatch']['count'], 1)
        self.assertEqual(
            summary_dict['exit_code_mismatch']['severity'], 'error')

        self.assertEqual(summary_dict['diff_mismatch']['count'], 1)
        self.assertEqual(summary_dict['diff_mismatch']['severity'], 'warning')

    def test_aggregate_error_severity_escalation(self):
        # Create an error with severity 'warning' and another with 'error' in the same bucket
        from mod_api.services.error_service import _aggregate_error_into_bucket
        bucket = {
            'count': 1,
            'severity': 'warning',
            'sample_ids': [],
            'first_seen_at': None,
            'last_seen_at': None
        }

        # New error with higher severity
        err_error = {'severity': 'error', 'sample_id': 1}
        _aggregate_error_into_bucket(err_error, bucket)
        self.assertEqual(bucket['severity'], 'error')
        self.assertEqual(bucket['count'], 2)

        # New error with lower severity should not downgrade
        err_info = {'severity': 'info', 'sample_id': 2}
        _aggregate_error_into_bucket(err_info, bucket)
        self.assertEqual(bucket['severity'], 'error')
        self.assertEqual(bucket['count'], 3)

    def test_derive_infrastructure_errors(self):
        tp1 = TestProgress(
            self.test_obj.id, TestStatus.canceled, 'provisioning VM failed')
        tp1.timestamp = datetime.datetime(2023, 1, 1, 10, 0, 0)

        tp2 = TestProgress(
            self.test_obj.id, TestStatus.canceled, 'merge conflict')
        tp2.timestamp = datetime.datetime(2023, 1, 1, 10, 5, 0)

        g.db.add(tp1)
        g.db.add(tp2)
        g.db.commit()

        errors = derive_infrastructure_errors(self.test_obj.id)
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0]['type'], 'vm_provisioning')
        self.assertEqual(errors[1]['type'], 'merge')

    def test_classify_infra_error(self):
        self.assertEqual(_classify_infra_error(
            'timeout connecting to worker'), 'worker')
        self.assertEqual(_classify_infra_error('failed to build'), 'build')
        self.assertEqual(_classify_infra_error('storage is full'), 'storage')
        self.assertEqual(_classify_infra_error(
            'fetch remote repository'), 'checkout')
        self.assertEqual(_classify_infra_error('merge conflict'), 'merge')
        self.assertEqual(_classify_infra_error(
            'random error string'), 'worker')

    def test_get_sample_id(self):
        tr = TestResult(self.test_obj.id, 1, 100, 0, 0)
        self.assertIsNone(_get_sample_id(tr))

        tr.regression_test = MagicMock()
        tr.regression_test.sample_id = 42
        self.assertEqual(_get_sample_id(tr), 42)

        # Test exception catching
        mock_reg = MagicMock()
        type(mock_reg).sample_id = PropertyMock(side_effect=RuntimeError('Mock exception'))
        tr.regression_test = mock_reg
        self.assertIsNone(_get_sample_id(tr))
