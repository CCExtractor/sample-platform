import json
from unittest.mock import patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_test.models import Fork, Test, TestPlatform, TestType
from tests.api.base import ApiTestCase


class TestRoutesSystem(ApiTestCase):
    def setUp(self):
        super().setUp()

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

    @patch('mod_api.routes.system.text')
    def test_system_health_db_down(self, mock_text):
        mock_text.side_effect = Exception('DB Down')
        res = self.client.get('/api/v1/system/health')
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json['status'], 'down')
        db_dep = next(d for d in res.json['dependencies'] if d['name'] == 'database')
        self.assertEqual(db_dep['status'], 'down')

    def test_safe_resolve_path_traversal(self):
        from mod_api.utils import safe_resolve
        base = '/safe/base/path'
        # Should return None for path traversal attempts
        self.assertIsNone(safe_resolve(base, '../../../etc/passwd'))
        self.assertIsNone(safe_resolve(base, '/etc/passwd'))
