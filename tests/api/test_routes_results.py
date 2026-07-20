import base64
import json
import os
import tempfile
from unittest.mock import patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput)
from mod_test.models import TestResult, TestResultFile
from tests.api.base import ApiTestCase


class TestRoutesResults(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.setup_run_data('res')

        category = Category('Test Category', 'Description')
        g.db.add(category)
        g.db.commit()

        self.reg_test = RegressionTest(
            1, 'command', InputType.file, OutputType.file, category.id, 0)
        g.db.add(self.reg_test)
        g.db.commit()
        self.reg_test_id = self.reg_test.id

        self.reg_out = RegressionTestOutput(
            self.reg_test_id, 'expected_hash', '.txt', 'exp_file')
        g.db.add(self.reg_out)
        g.db.commit()
        self.reg_out_id = self.reg_out.id

        self.test_result = TestResult(self.test_id, self.reg_test_id, 0, 0, 0)
        g.db.add(self.test_result)
        g.db.commit()

        self.result_file = TestResultFile(
            self.test_id, self.reg_test_id, self.reg_out_id, 'expected_hash', 'actual_hash')
        g.db.add(self.result_file)
        g.db.commit()

        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.test_dir.name

        # Create TestResults directory
        self.test_results_dir = os.path.join(self.dir_path, 'TestResults')
        os.makedirs(self.test_results_dir, exist_ok=True)

        # Configure app to use our temp dir
        self.original_sample_repo = self.app.config.get('SAMPLE_REPOSITORY')
        self.app.config['SAMPLE_REPOSITORY'] = self.dir_path

        _rate_limit_store.clear()

    def tearDown(self):
        if self.original_sample_repo is not None:
            self.app.config['SAMPLE_REPOSITORY'] = self.original_sample_repo
        else:
            self.app.config.pop('SAMPLE_REPOSITORY', None)
        self.test_dir.cleanup()
        super().tearDown()

    def test_get_expected_output_base64(self):
        expected_file_path = os.path.join(
            self.test_results_dir, 'expected_hash.txt')
        with open(expected_file_path, 'wb') as f:
            f.write(b'expected data')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't1', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/expected', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['encoding'], 'base64')
            self.assertEqual(res.json['content'], base64.b64encode(
                b'expected data').decode('ascii'))
            self.assertEqual(res.json['filename'], 'expected_hash.txt')

    def test_get_expected_output_text(self):
        expected_file_path = os.path.join(
            self.test_results_dir, 'expected_hash.txt')
        with open(expected_file_path, 'wb') as f:
            f.write(b'line1\nline2')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't2', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/expected?format=text', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['encoding'], 'utf-8')
            self.assertEqual(res.json['content'], 'line1\nline2')

    def test_get_actual_output(self):
        actual_file_path = os.path.join(
            self.test_results_dir, 'actual_hash.txt')
        with open(actual_file_path, 'wb') as f:
            f.write(b'actual data')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't3', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/actual', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['filename'], 'actual_hash.txt')
            self.assertEqual(res.json['content'], base64.b64encode(
                b'actual data').decode('ascii'))

    def test_get_actual_output_matched_expected(self):
        # Set got = None
        self.result_file.got = None
        g.db.commit()

        expected_file_path = os.path.join(
            self.test_results_dir, 'expected_hash.txt')
        with open(expected_file_path, 'wb') as f:
            f.write(b'expected data')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't4', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/actual', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 303)
            redirect_url = res.headers['Location']
            res2 = self.client.get(redirect_url, headers={
                                   'Authorization': f'Bearer {token}'})
            self.assertEqual(res2.status_code, 200)

            import base64
            self.assertEqual(res2.json['content'], base64.b64encode(
                b'expected data').decode('ascii'))

    def test_get_diff(self):
        expected_file_path = os.path.join(
            self.test_results_dir, 'expected_hash.txt')
        with open(expected_file_path, 'wb') as f:
            f.write(b'line1\nline2\n')

        actual_file_path = os.path.join(
            self.test_results_dir, 'actual_hash.txt')
        with open(actual_file_path, 'wb') as f:
            f.write(b'line1\nline_new\n')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't5', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/diff', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['status'], 'different')
            self.assertEqual(res.json['summary']['added_lines'], 1)

    def test_get_diff_unified_format(self):
        expected_file_path = os.path.join(
            self.test_results_dir, 'expected_hash.txt')
        with open(expected_file_path, 'wb') as f:
            f.write(b'line1\nline2\n')

        actual_file_path = os.path.join(
            self.test_results_dir, 'actual_hash.txt')
        with open(actual_file_path, 'wb') as f:
            f.write(b'line1\nline_new\n')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't5_uni', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/diff?format=unified', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['format'], 'unified')
            self.assertIn('content', res.json)
            self.assertIsInstance(res.json['content'], str)

    def test_get_diff_identical_files(self):
        # When got is None, diff returns status 'identical'
        self.result_file.got = None
        g.db.commit()

        expected_file_path = os.path.join(
            self.test_results_dir, 'expected_hash.txt')
        with open(expected_file_path, 'wb') as f:
            f.write(b'expected data\n')

        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't5_id', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/diff', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['status'], 'identical')

    def test_create_baseline_approval(self):
        token = self.get_token('res_admin@local.com',
                               'adminpass123', 't6', scopes=['baselines:write'])

        actual_file_path = os.path.join(self.test_results_dir, 'actual_hash.txt')
        with open(actual_file_path, 'wb') as f:
            f.write(b'actual data')

        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id,
            'remove_variants': False
        }
        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            res = self.client.post(f'/api/v1/runs/{self.test_id}/samples/1/baseline-approval', data=json.dumps(
                payload), content_type='application/json', headers={'Authorization': f'Bearer {token}'})

        if res.status_code != 200:
            print("ERROR JSON:", res.json)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['status'], 'approved')

        # Verify db change
        reg_out_after = RegressionTestOutput.query.get(self.reg_out_id)
        self.assertEqual(reg_out_after.correct, 'actual_hash')

    def test_create_baseline_approval_forbidden_role(self):
        # Create token directly in DB to bypass token creation limitations
        from mod_api.models.api_token import ApiToken
        plaintext = ApiToken.generate_token()
        token = ApiToken(
            user_id=self.user.id,  # res_user has user role
            token_name='t7_forbidden',
            token_hash=ApiToken.hash_token(plaintext),
            token_prefix=ApiToken.extract_prefix(plaintext),
            scopes=['baselines:write'],
            expires_in_days=7
        )
        g.db.add(token)
        g.db.commit()

        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id
        }
        res = self.client.post(f'/api/v1/runs/{self.test_id}/samples/1/baseline-approval', data=json.dumps(
            payload), content_type='application/json', headers={'Authorization': f'Bearer {plaintext}'})

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json['code'], 'forbidden')

    def test_create_baseline_approval_contributor_forbidden(self):
        # Baseline approval is admin-only: a contributor must be rejected
        # even when holding a baselines:write token.
        from mod_api.models.api_token import ApiToken
        from mod_auth.models import Role, User
        contributor = User(
            'res_contrib', Role.contributor, 'res_contrib@local.com',
            User.generate_hash('contribpass123'))
        g.db.add(contributor)
        g.db.commit()

        plaintext = ApiToken.generate_token()
        token = ApiToken(
            user_id=contributor.id,
            token_name='t_contrib_forbidden',
            token_hash=ApiToken.hash_token(plaintext),
            token_prefix=ApiToken.extract_prefix(plaintext),
            scopes=['baselines:write'],
            expires_in_days=7,
        )
        g.db.add(token)
        g.db.commit()

        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id,
        }
        res = self.client.post(
            f'/api/v1/runs/{self.test_id}/samples/1/baseline-approval',
            data=json.dumps(payload), content_type='application/json',
            headers={'Authorization': f'Bearer {plaintext}'})

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json['code'], 'forbidden')

    def test_create_baseline_approval_remove_variants(self):
        token = self.get_token('res_admin@local.com',
                               'adminpass123', 't8', scopes=['baselines:write'])

        actual_file_path = os.path.join(self.test_results_dir, 'actual_hash.txt')
        with open(actual_file_path, 'wb') as f:
            f.write(b'actual data')

        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id,
            'remove_variants': True
        }
        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            res = self.client.post(f'/api/v1/runs/{self.test_id}/samples/1/baseline-approval', data=json.dumps(
                payload), content_type='application/json', headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['status'], 'approved')

        # Verify db change
        from mod_regression.models import RegressionTestOutputFiles
        variants = RegressionTestOutputFiles.query.filter_by(
            regression_test_output_id=self.reg_out_id).count()
        self.assertEqual(variants, 0)

    def test_create_baseline_approval_output_already_matches(self):
        # got=None means the actual output already matches the baseline,
        # so there is nothing to approve.
        self.result_file.got = None
        g.db.commit()

        token = self.get_token('res_admin@local.com',
                               'adminpass123', 't9', scopes=['baselines:write'])
        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id
        }
        res = self.client.post(
            f'/api/v1/runs/{self.test_id}/samples/1/baseline-approval',
            data=json.dumps(payload), content_type='application/json',
            headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 422)
        self.assertIn('matches expected', res.json['message'])

    def test_get_actual_output_missing_storage(self):
        # We don't write the file 'actual_hash.txt', so it will not be found on the filesystem
        with patch.dict('run.config', {'SAMPLE_REPOSITORY': self.dir_path}):
            token = self.get_token(
                'res_user@local.com', 'userpass123', 't9', scopes=['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/{self.reg_test_id}'
                f'/outputs/{self.reg_out_id}/actual', headers={'Authorization': f'Bearer {token}'})

            self.assertEqual(res.status_code, 404)
            self.assertIn('not found', res.json['message'].lower())

    def test_get_output_nonexistent_resource_404(self):
        token = self.get_token('res_user@local.com',
                               'userpass123', 't10', scopes=['results:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples/1/regression-tests/999999'
            f'/outputs/{self.reg_out_id}/expected', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json['code'], 'not_found')
