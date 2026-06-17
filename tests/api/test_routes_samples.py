import datetime
import json
from unittest.mock import patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput)
from mod_sample.models import Sample
from mod_test.models import (Fork, Test, TestPlatform, TestResult,
                             TestResultFile, TestType)
from tests.base import BaseTestCase


class TestRoutesSamples(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User('testadmin_samp', Role.admin,
                          'samp_admin@local.com', User.generate_hash('adminpass123'))
        self.user = User('testuser_samp', Role.user,
                         'samp_user@local.com', User.generate_hash('userpass123'))
        g.db.add_all([self.admin, self.user])
        g.db.commit()

        self.fork = Fork('https://github.com/test/test.git')
        g.db.add(self.fork)
        g.db.commit()

        self.test_obj = Test(TestPlatform.linux, TestType.commit,
                             self.fork.id, 'master', 'commit_hash')
        g.db.add(self.test_obj)
        g.db.commit()
        self.test_id = self.test_obj.id

        self.sample = Sample('test_sha', 'txt', 'test_sample')
        g.db.add(self.sample)
        g.db.commit()
        self.sample_id = self.sample.id

        self.category = Category('Test Category', 'Description')
        g.db.add(self.category)
        g.db.commit()

        self.reg_test = RegressionTest(
            self.sample_id, 'command', InputType.file, OutputType.file, self.category.id, 0)
        g.db.add(self.reg_test)
        g.db.commit()
        self.reg_test_id = self.reg_test.id

        self.reg_out = RegressionTestOutput(
            self.reg_test_id, 'expected_hash', '.txt', 'exp')
        g.db.add(self.reg_out)
        g.db.commit()
        self.reg_out_id = self.reg_out.id

        self.test_result = TestResult(self.test_id, self.reg_test_id, 0, 0, 0)
        g.db.add(self.test_result)
        g.db.commit()

        self.result_file = TestResultFile(
            self.test_id, self.reg_test_id, self.reg_out_id, 'expected_hash', None)
        g.db.add(self.result_file)
        g.db.commit()

        _rate_limit_store.clear()

    def get_token(self, email, password, token_name='test_token', scopes=None):
        payload = {'email': email, 'password': password,
                   'token_name': token_name}
        if scopes:
            payload['scopes'] = scopes
        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
        return res.json['token']

    def test_list_run_samples(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't1', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]
                         ['regression_test_id'], self.reg_test_id)

    def test_get_run_sample(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't2', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples/{self.reg_test_id}', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['regression_test_id'], self.reg_test_id)

    def test_list_samples(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't3', scopes=['runs:read'])
        res = self.client.get(
            '/api/v1/samples', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 3)
        self.assertTrue(
            any(s['sample_id'] == self.sample_id for s in res.json['data']))

    def test_get_sample(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't4', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['sample_id'], self.sample_id)

    def test_get_sample_history(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't5', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertTrue(
            any(h['run_id'] == self.test_id for h in res.json['data']))

    def test_list_regression_tests(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't6', scopes=['runs:read'])
        res = self.client.get('/api/v1/regression-tests',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 3)
        self.assertTrue(any(rt['regression_test_id'] == self.reg_test_id
                            for rt in res.json['data']))

    def test_list_regression_tests_active_filter(self):
        # Create an inactive regression test
        rt_inactive = RegressionTest(
            self.sample_id, 'cmd_inactive', InputType.file, OutputType.file, self.category.id, 0)
        rt_inactive.active = False
        g.db.add(rt_inactive)
        g.db.commit()
        rt_inactive_id = rt_inactive.id

        token = self.get_token(
            'samp_user@local.com', 'userpass123', 't_active_filter', scopes=['runs:read'])

        # Default active=true
        res = self.client.get('/api/v1/regression-tests',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(rt['regression_test_id'] == self.reg_test_id
                            for rt in res.json['data']))
        self.assertFalse(any(rt['regression_test_id'] == rt_inactive_id
                             for rt in res.json['data']))

        res_false = self.client.get(
            '/api/v1/regression-tests?active=false', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res_false.status_code, 200)
        self.assertFalse(any(rt['regression_test_id'] == self.reg_test_id
                             for rt in res_false.json['data']))
        self.assertTrue(any(rt['regression_test_id'] == rt_inactive_id
                            for rt in res_false.json['data']))

    def test_baseline_verification_success(self):
        # We must set got to a non-None value so that we can approve it
        self.result_file.got = 'new_hash'
        g.db.commit()

        token = self.get_token(
            'samp_admin@local.com', 'adminpass123', 't_base1', scopes=['baselines:write'])
        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id,
            'remove_variants': False
        }
        res = self.client.post(f'/api/v1/runs/{self.test_id}/samples/{self.sample_id}/baseline-approval',
                               data=json.dumps(payload),
                               content_type='application/json',
                               headers={'Authorization': f'Bearer {token}'})
        # Wait, what does it return? 200 OK.
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['status'], 'approved')

    def test_baseline_verification_rejected(self):
        # Without setting got (so got is None), it should return 422
        token = self.get_token(
            'samp_admin@local.com', 'adminpass123', 't_base2', scopes=['baselines:write'])
        payload = {
            'regression_id': self.reg_test_id,
            'output_id': self.reg_out_id
        }
        res = self.client.post(f'/api/v1/runs/{self.test_id}/samples/{self.sample_id}/baseline-approval',
                               data=json.dumps(payload),
                               content_type='application/json',
                               headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 422)
        self.assertIn('matches expected', res.json['message'])
