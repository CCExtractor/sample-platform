import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_regression.models import RegressionTestOutput
from mod_test.models import Fork, Test, TestPlatform, TestResultFile, TestType
from tests.api.base import ApiTestCase


class TestRoutesSystem(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.test_dir.name

        # Create users
        admin2 = User('admin2', Role.admin, 'admin2@local.com',
                      User.generate_hash('adminpass123'))
        user2 = User('user2', Role.user, 'user2@local.com',
                     User.generate_hash('userpass123'))
        g.db.add_all([admin2, user2])
        g.db.commit()

        # Create a test run
        fork = Fork('https://github.com/test/test.git')
        g.db.add(fork)
        g.db.commit()

        self.test_obj = Test(TestPlatform.linux,
                             TestType.commit, fork.id, 'master', 'commit_hash')
        g.db.add(self.test_obj)
        g.db.commit()
        self.test_id = self.test_obj.id

        _rate_limit_store.clear()

    def tearDown(self):
        self.test_dir.cleanup()
        super().tearDown()

    def generate_system_token(self, email, password, scopes=None):
        payload = {
            'email': email,
            'password': password,
            'token_name': 'test_token_' + self.create_random_string(8)
        }
        if scopes:
            payload['scopes'] = scopes

        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
        if res.status_code != 201:
            raise RuntimeError(
                f"Failed to get token: {res.status_code} - {res.json}")
        return res.json['token']

    def test_health_check_unauthenticated(self):
        res = self.client.get('/api/v1/system/health')
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.json['status'], ['ok', 'degraded'])
        self.assertIn('dependencies', res.json)

    def test_system_queue_requires_scope(self):
        token = self.generate_system_token('user2@local.com', 'userpass123', ['runs:read'])
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {token}'})
        # Forbidden due to missing scope
        self.assertEqual(res.status_code, 403)

    def test_system_queue_with_scope(self):
        # A test with no progress is "queued"
        token = self.generate_system_token(
            'user2@local.com', 'userpass123', ['system:read'])
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('data', res.json)
        self.assertEqual(res.json['meta']['queue_depth'], 1)
        self.assertEqual(res.json['meta']['running_count'], 0)
        self.assertEqual(res.json['data'][0]['run_id'], self.test_id)
        self.assertEqual(res.json['data'][0]['status'], 'queued')

    def test_system_queue_platform_filter(self):
        token = self.generate_system_token(
            'user2@local.com', 'userpass123', ['system:read'])
        res = self.client.get('/api/v1/system/queue?platform=windows',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['meta']['queue_depth'], 0)

    @patch('run.storage_client_bucket')
    def test_list_artifacts(self, mock_bucket):
        # Setup mock behavior for GCS
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = 'https://signed.url'
        mock_bucket.blob.return_value = mock_blob

        # Create real files
        os.makedirs(os.path.join(self.dir_path, 'LogFiles'), exist_ok=True)
        log_path = os.path.join(
            self.dir_path, 'LogFiles', f'{self.test_id}.txt')
        with open(log_path, 'w') as f:
            f.write('log content')

        os.makedirs(os.path.join(self.dir_path, 'TestResults'), exist_ok=True)
        with open(os.path.join(self.dir_path, 'TestResults', 'got.srt'), 'w') as f:
            f.write('actual content')

        # Add test result files
        rf = TestResultFile(self.test_id, 1, 1, 'expected', 'got')
        rto = RegressionTestOutput(1, 1, 'expected', 'out.txt')
        rf.regression_test_output = rto
        g.db.add(rf)
        g.db.commit()

        # Create local file for actual to pass isfile check (already done above)

        original_sample_repo = self.app.config.get('SAMPLE_REPOSITORY')
        self.app.config['SAMPLE_REPOSITORY'] = self.dir_path
        try:
            token = self.generate_system_token(
                'user2@local.com', 'userpass123', ['results:read'])
            res = self.client.get(
                f'/api/v1/runs/{self.test_id}/artifacts', headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(res.status_code, 200)
        finally:
            if original_sample_repo is not None:
                self.app.config['SAMPLE_REPOSITORY'] = original_sample_repo
            else:
                del self.app.config['SAMPLE_REPOSITORY']

        items = res.json['data']
        # We expect: binary, coredump, combined_stdout, build_log, expected_output, actual_output
        self.assertEqual(len(items), 6)

        types = [item['type'] for item in items]
        self.assertIn('binary', types)
        self.assertIn('build_log', types)
        self.assertIn('expected_output', types)
        self.assertIn('actual_output', types)

    def test_list_artifacts_not_found(self):
        token = self.generate_system_token(
            'user2@local.com', 'userpass123', ['results:read'])
        res = self.client.get('/api/v1/runs/9999/artifacts',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 404)

    def test_list_artifacts_missing_storage(self):
        # When files do not exist, verify storage_status='missing' and download_url=None
        token = self.generate_system_token(
            'user2@local.com', 'userpass123', ['results:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/artifacts', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)

        # Verify the build log artifact has storage_status 'missing' since we didn't create the log file
        build_log = next(
            a for a in res.json['data'] if a['type'] == 'build_log')
        self.assertEqual(build_log['storage_status'], 'missing')
        self.assertIsNone(build_log['download_url'])

    @patch('mod_api.routes.system.text')
    def test_system_health_db_down(self, mock_text):
        mock_text.side_effect = Exception('DB Down')
        res = self.client.get('/api/v1/system/health')
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json['status'], 'down')
        db_dep = next(d for d in res.json['dependencies'] if d['name'] == 'database')
        self.assertEqual(db_dep['status'], 'down')

    def test_list_artifacts_type_filter(self):
        token = self.generate_system_token(
            'user2@local.com', 'userpass123', ['results:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/artifacts?type=build_log', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]['type'], 'build_log')

    def test_safe_resolve_path_traversal(self):
        from mod_api.utils import safe_resolve
        base = '/safe/base/path'
        # Should return None for path traversal attempts
        self.assertIsNone(safe_resolve(base, '../../../etc/passwd'))
        self.assertIsNone(safe_resolve(base, '/etc/passwd'))
