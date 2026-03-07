"""Tests for REST API endpoints."""

from tests.base import BaseTestCase


class TestApiControllers(BaseTestCase):
    """API test coverage for v1 endpoints."""

    def test_summary_success(self):
        response = self.app.test_client().get('/api/v1/tests/1/summary')
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['data']['test_id'], 1)
        self.assertEqual(payload['data']['sample_progress']['current'], 2)

    def test_summary_not_found(self):
        response = self.app.test_client().get('/api/v1/tests/9999/summary')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['status'], 'failure')

    def test_results_success(self):
        response = self.app.test_client().get('/api/v1/tests/1/results')
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload['status'], 'success')
        self.assertGreaterEqual(len(payload['data']), 1)
        first_category = payload['data'][0]
        self.assertIn('tests', first_category)
        first_test = first_category['tests'][0]
        self.assertIn('expected_rc', first_test)
        self.assertIn('exit_code', first_test)
        if first_test['exit_code'] is not None:
            self.assertEqual(first_test['expected_rc'], first_test['exit_code'])

    def test_results_not_found(self):
        response = self.app.test_client().get('/api/v1/tests/9999/results')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['status'], 'failure')

    def test_files_success(self):
        response = self.app.test_client().get('/api/v1/tests/1/files')
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(len(payload['data']), 2)
        self.assertIn('expected_hash', payload['data'][0])
        self.assertIn('got_hash', payload['data'][0])

    def test_files_not_found(self):
        response = self.app.test_client().get('/api/v1/tests/9999/files')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['status'], 'failure')

    def test_progress_success(self):
        response = self.app.test_client().get('/api/v1/tests/1/progress')
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(len(payload['data']['events']), 3)
        self.assertIn('current_step', payload['data']['summary'])

    def test_progress_not_found(self):
        response = self.app.test_client().get('/api/v1/tests/9999/progress')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['status'], 'failure')

    def test_categories_success(self):
        response = self.app.test_client().get('/api/v1/categories')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'success')
        names = {item['name'] for item in response.json['data']}
        self.assertIn('Broken', names)
