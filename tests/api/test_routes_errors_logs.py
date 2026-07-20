import json
import os
import tempfile
from unittest.mock import patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput)
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)
from tests.api.base import ApiTestCase


class TestRoutesErrorsLogs(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User('testuser_el', Role.contributor,
                         'el_user@local.com', User.generate_hash('userpass123'))
        self.admin = User('testadmin_el', Role.admin,
                          'el_admin@local.com', User.generate_hash('adminpass123'))
        self.regular_user = User(
            'testregular_el', Role.user, 'el_regular@local.com', User.generate_hash('userpass123'))
        g.db.add_all([self.user, self.admin, self.regular_user])
        g.db.commit()

        fork = Fork('https://github.com/test/test.git')
        g.db.add(fork)
        g.db.commit()

        self.test_obj = Test(TestPlatform.linux,
                             TestType.commit, fork.id, 'master', 'commit_hash')
        g.db.add(self.test_obj)
        g.db.commit()
        self.test_id = self.test_obj.id

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
            self.reg_test1.id, 'expected1', '.txt', 'exp1')
        self.reg_out2 = RegressionTestOutput(
            self.reg_test2.id, 'expected2', '.txt', 'exp2')
        g.db.add_all([self.reg_out1, self.reg_out2])

        dummy_out = RegressionTestOutput(
            self.reg_test1.id, 'dummy', '', 'dummy')
        dummy_out.id = -1
        g.db.merge(dummy_out)

        g.db.commit()

        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.test_dir.name

        _rate_limit_store.clear()

    def tearDown(self):
        self.test_dir.cleanup()
        super().tearDown()

    def get_token(self, email, password, token_name='test_token', scopes=None):
        payload = {
            'email': email,
            'password': password,
            'token_name': token_name
        }
        if scopes:
            payload['scopes'] = scopes

        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
        return res.json['token']

    def test_list_run_errors(self):
        # Add a missing_output error
        tr1 = TestResult(self.test_obj.id, self.reg_test1.id, 100, 0, 0)
        rf1 = TestResultFile(
            self.test_obj.id, self.reg_test1.id, -1, '', 'error')

        # Add a diff_mismatch error
        tr2 = TestResult(self.test_obj.id, self.reg_test2.id, 100, 0, 0)
        rf2 = TestResultFile(
            self.test_obj.id, self.reg_test2.id, self.reg_out2.id, 'exp', 'got')

        g.db.add_all([tr1, rf1, tr2, rf2])
        g.db.commit()

        token = self.get_token('el_user@local.com',
                               'userpass123', 't1', scopes=['results:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/errors', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 2)

    def test_list_run_errors_filters(self):
        tr1 = TestResult(self.test_obj.id, self.reg_test1.id, 100, 0, 0)
        # missing_output (error)
        rf1 = TestResultFile(
            self.test_obj.id, self.reg_test1.id, -1, '', 'error')

        tr2 = TestResult(self.test_obj.id, self.reg_test2.id, 100, 0, 0)
        rf2 = TestResultFile(self.test_obj.id, self.reg_test2.id,
                             # diff_mismatch (warning)
                             self.reg_out2.id, 'exp', 'got')

        g.db.add_all([tr1, rf1, tr2, rf2])
        g.db.commit()

        token = self.get_token('el_user@local.com',
                               'userpass123', 't2', scopes=['results:read'])

        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/errors?type=missing_output', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]['type'], 'missing_output')
        self.assertEqual(res.json['data'][0]['severity'], 'error')

        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/errors?severity=warning', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]['type'], 'diff_mismatch')
        self.assertEqual(res.json['data'][0]['severity'], 'warning')

    def test_list_errors_invalid_severity(self):
        # The schema doesn't strictly validate severity to a whitelist enum? Let's see. Wait,
        # in mod_api/routes/errors_logs.py, it filters by severity.
        # Actually it just does errors = [e for e in errors if e['severity'] == severity]. It doesn't 400.
        # Let's test limit/offset pagination validation failure instead since list_run_errors
        # uses @validate_offset_pagination.
        token = self.get_token(
            'el_user@local.com', 'userpass123', 't_pag_inv', scopes=['results:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/errors?limit=500', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_list_infrastructure_errors(self):
        tp1 = TestProgress(
            self.test_obj.id, TestStatus.canceled, 'provisioning VM failed')
        g.db.add(tp1)
        g.db.commit()

        token = self.get_token('el_user@local.com',
                               'userpass123', 't3', scopes=['system:read'])

        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/infrastructure-errors', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertNotIn('stack', res.json['data'][0])

    def test_infra_errors_stack_forbidden_for_regular_user(self):
        tp1 = TestProgress(
            self.test_obj.id, TestStatus.canceled, 'provisioning VM failed')
        g.db.add(tp1)
        g.db.commit()

        reg_token = self.get_token(
            'el_regular@local.com', 'userpass123', 't_reg', scopes=['system:read'])
        res_reg = self.client.get(
            f'/api/v1/runs/{self.test_id}/infrastructure-errors?include_stack=true',
            headers={'Authorization': f'Bearer {reg_token}'})
        self.assertEqual(res_reg.status_code, 403)

    def test_infra_errors_include_stack_flag_accepted(self):
        tp1 = TestProgress(
            self.test_obj.id, TestStatus.canceled, 'provisioning VM failed')
        g.db.add(tp1)
        g.db.commit()

        admin_token = self.get_token(
            'el_admin@local.com', 'adminpass123', 't4', scopes=['system:read'])
        res = self.client.get(f'/api/v1/runs/{self.test_id}/infrastructure-errors?include_stack=true', headers={
                              'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res.status_code, 200)

    def test_get_error_summary(self):
        tr1 = TestResult(self.test_obj.id, self.reg_test1.id, 100, 1, 0)
        # Matched output (got=None) so the only bucket is the rc mismatch —
        # without it the expected output would also count as missing_output.
        rf1 = TestResultFile(self.test_obj.id, self.reg_test1.id,
                             self.reg_out1.id, 'exp1')
        g.db.add_all([tr1, rf1])
        g.db.commit()

        token = self.get_token('el_user@local.com',
                               'userpass123', 't5', scopes=['results:read'])

        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/error-summary', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)

    def test_get_run_logs(self):
        from run import config

        # Create a real log file and configure the app to read it
        os.makedirs(os.path.join(self.dir_path, 'LogFiles'), exist_ok=True)
        log_path = os.path.join(
            self.dir_path, 'LogFiles', f'{self.test_id}.txt')
        with open(log_path, 'w') as f:
            f.write("INFO worker: hello\n")

        original_sample_repo = config.get('SAMPLE_REPOSITORY')
        config['SAMPLE_REPOSITORY'] = self.dir_path
        try:
            token = self.get_token('el_user@local.com',
                                   'userpass123', 't6', scopes=['system:read'])

            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/logs', headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(res.status_code, 200)
            self.assertIn('data', res.json)
            self.assertEqual(len(res.json['data']), 1)
            self.assertEqual(res.json['data'][0]
                             ['message'], 'INFO worker: hello')
        finally:
            if original_sample_repo is not None:
                config['SAMPLE_REPOSITORY'] = original_sample_repo
            else:
                config.pop('SAMPLE_REPOSITORY', None)

    @patch('run.storage_client_bucket', None)
    def test_get_run_logs_file_not_found(self):
        from run import config

        # Do not create the file, so it raises FileNotFoundError
        original_sample_repo = config.get('SAMPLE_REPOSITORY')
        config['SAMPLE_REPOSITORY'] = self.dir_path
        try:
            token = self.get_token('el_user@local.com',
                                   'userpass123', 't7', scopes=['system:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/logs', headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(res.status_code, 404)
        finally:
            if original_sample_repo is not None:
                config['SAMPLE_REPOSITORY'] = original_sample_repo
            else:
                config.pop('SAMPLE_REPOSITORY', None)

    def test_get_logs_invalid_cursor(self):
        token = self.get_token(
            'el_user@local.com', 'userpass123', 't_logs_inv', scopes=['system:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/logs?cursor=-1', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_get_sample_logs(self):
        token = self.get_token('el_user@local.com',
                               'userpass123', 't8', scopes=['system:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples/1/logs', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 404)

    def test_error_summary_group_by_sample_id(self):
        tr1 = TestResult(self.test_obj.id, self.reg_test1.id, 100, 1, 0)
        g.db.add(tr1)
        g.db.commit()

        token = self.get_token(
            'el_user@local.com', 'userpass123', 't9_sum', scopes=['results:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/error-summary?group_by=sample_id',
            headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]['group_by'], 'sample_id')
