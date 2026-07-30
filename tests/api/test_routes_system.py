import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_ci.models import BlockedUsers, MaintenanceMode
from mod_regression.models import RegressionTestOutput
from mod_sample.models import ForbiddenExtension
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


class TestRoutesPlatformConfig(ApiTestCase):
    """Maintenance mode, blocked CI users, and forbidden upload extensions."""

    def setUp(self):
        super().setUp()
        self.setup_run_data('adm')
        g.db.add(BlockedUsers(4242, 'repeated abusive uploads'))
        g.db.add(ForbiddenExtension('exe'))
        g.db.commit()
        _rate_limit_store.clear()

    def _admin(self, name='adm_tok', scopes=None):
        token = self.get_token(
            'adm_admin@local.com', 'adminpass123', name,
            scopes=scopes or ['system:read', 'system:write'])
        return {'Authorization': f'Bearer {token}'}

    def _reader(self, name='adm_read'):
        token = self.get_token('adm_user@local.com', 'userpass123', name,
                               scopes=['system:read'])
        return {'Authorization': f'Bearer {token}'}

    def _write(self, method, path, headers, body):
        return getattr(self.client, method)(
            f'/api/v1{path}', data=json.dumps(body),
            content_type='application/json', headers=headers)

    def test_plain_user_cannot_request_system_write(self):
        # system:write reconfigures CI itself, so it is admin-only at the
        # point a token is minted, not merely at the route.
        res = self._write('post', '/auth/tokens', {}, {
            'email': 'adm_user@local.com', 'password': 'userpass123',
            'token_name': 'nope', 'scopes': ['system:write']})
        self.assertEqual(res.status_code, 403)

    def test_admin_can_request_every_scope(self):
        # Guards the token schema's scope-count cap against the scope list.
        res = self._write('post', '/auth/tokens', {}, {
            'email': 'adm_admin@local.com', 'password': 'adminpass123',
            'token_name': 'allscopes',
            'scopes': ['runs:read', 'runs:write', 'results:read',
                       'baselines:write', 'system:read', 'system:write',
                       'tokens:manage']})
        self.assertEqual(res.status_code, 201)

    def test_platform_config_reads_refused_for_non_admin(self):
        # The blocklist names accounts and the rest is platform configuration,
        # so holding system:read is not on its own enough to read any of it.
        headers = self._reader()
        for path in ('/system/maintenance', '/system/blocked-users',
                     '/system/forbidden-extensions'):
            res = self.client.get(f'/api/v1{path}', headers=headers)
            self.assertEqual(res.status_code, 403, f'{path} was readable')

    def test_get_maintenance_reports_every_platform(self):
        res = self.client.get('/api/v1/system/maintenance',
                              headers=self._admin('adm_read_m'))

        self.assertEqual(res.status_code, 200)
        self.assertEqual({row['platform'] for row in res.json['platforms']},
                         set(TestPlatform.values()))
        # Nothing stored yet, so every platform reads as running.
        self.assertTrue(
            all(row['disabled'] is False for row in res.json['platforms']))

    def test_update_maintenance_creates_then_updates(self):
        res = self._write('patch', '/system/maintenance/linux',
                          self._admin(), {'disabled': True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json['disabled'])

        # Toggling back must reuse the row rather than add a second one.
        res = self._write('patch', '/system/maintenance/linux',
                          self._admin('adm_tok2'), {'disabled': False})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json['disabled'])
        self.assertEqual(MaintenanceMode.query.filter(
            MaintenanceMode.platform == TestPlatform.linux).count(), 1)

    def test_update_maintenance_invalid_platform(self):
        res = self._write('patch', '/system/maintenance/atari',
                          self._admin(), {'disabled': True})
        self.assertEqual(res.status_code, 400)

    def test_update_maintenance_requires_system_write(self):
        res = self._write('patch', '/system/maintenance/linux',
                          self._admin('adm_ro', scopes=['system:read']),
                          {'disabled': True})
        self.assertEqual(res.status_code, 403)

    def test_list_blocked_users(self):
        res = self.client.get('/api/v1/system/blocked-users',
                              headers=self._admin('adm_read_b'))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['data'][0]['user_id'], 4242)
        self.assertEqual(res.json['data'][0]['comment'],
                         'repeated abusive uploads')

    def test_block_user(self):
        res = self._write('post', '/system/blocked-users', self._admin(),
                          {'user_id': 99, 'comment': 'spam'})

        self.assertEqual(res.status_code, 201)
        self.assertIsNotNone(
            BlockedUsers.query.filter(BlockedUsers.user_id == 99).first())

    def test_block_user_twice(self):
        res = self._write('post', '/system/blocked-users', self._admin(),
                          {'user_id': 4242})
        self.assertEqual(res.status_code, 409)

    def test_block_user_rejects_login_instead_of_id(self):
        # The model keys on the numeric GitHub id; a login would silently
        # block nobody.
        res = self._write('post', '/system/blocked-users', self._admin(),
                          {'user_id': 'octocat'})
        self.assertEqual(res.status_code, 400)

    def test_block_user_forbidden_for_non_admin(self):
        res = self._write('post', '/system/blocked-users',
                          self._reader('adm_r2'), {'user_id': 7})
        self.assertEqual(res.status_code, 403)

    def test_unblock_user(self):
        res = self.client.delete('/api/v1/system/blocked-users/4242',
                                 headers=self._admin())

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(
            BlockedUsers.query.filter(BlockedUsers.user_id == 4242).first())

    def test_unblock_user_not_blocked(self):
        res = self.client.delete('/api/v1/system/blocked-users/1234',
                                 headers=self._admin())
        self.assertEqual(res.status_code, 404)

    def test_list_forbidden_extensions(self):
        res = self.client.get('/api/v1/system/forbidden-extensions',
                              headers=self._admin('adm_read_e'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('exe', res.json['data'])

    def test_forbid_extension(self):
        res = self._write('post', '/system/forbidden-extensions',
                          self._admin(), {'extension': 'BAT'})

        self.assertEqual(res.status_code, 201)
        # Stored lower-cased, since upload validation compares lower-cased.
        self.assertEqual(res.json['extension'], 'bat')
        self.assertIsNotNone(ForbiddenExtension.query.filter(
            ForbiddenExtension.extension == 'bat').first())

    def test_forbid_extension_rejects_dot_and_wildcards(self):
        headers = self._admin('adm_ext')
        for bad in ['.sh', '*', 'sh script']:
            res = self._write('post', '/system/forbidden-extensions',
                              headers, {'extension': bad})
            self.assertEqual(res.status_code, 400, f'accepted {bad!r}')

    def test_forbid_extension_twice(self):
        res = self._write('post', '/system/forbidden-extensions',
                          self._admin(), {'extension': 'exe'})
        self.assertEqual(res.status_code, 409)

    def test_allow_extension_again(self):
        res = self.client.delete('/api/v1/system/forbidden-extensions/exe',
                                 headers=self._admin())

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(ForbiddenExtension.query.filter(
            ForbiddenExtension.extension == 'exe').first())

    def test_allow_extension_tolerates_leading_dot(self):
        res = self.client.delete('/api/v1/system/forbidden-extensions/.exe',
                                 headers=self._admin())
        self.assertEqual(res.status_code, 200)

    def test_allow_extension_not_forbidden(self):
        res = self.client.delete('/api/v1/system/forbidden-extensions/mkv',
                                 headers=self._admin())
        self.assertEqual(res.status_code, 404)
