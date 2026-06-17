import json
from unittest import mock

from flask import g, request
from sqlalchemy.exc import SQLAlchemyError

from mod_api.middleware.error_handler import (handle_500,
                                              handle_sqlalchemy_error)
from tests.base import BaseTestCase


class TestMiddlewareErrorHandler(BaseTestCase):
    def setUp(self):
        super().setUp()
        from mod_api.middleware.rate_limit import _rate_limit_store
        _rate_limit_store.clear()

    def test_handle_400(self):
        # Trigger 400 with invalid json data format
        res = self.client.post('/api/v1/auth/tokens',
                               data="not json", content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_handle_401(self):
        # Missing auth
        res = self.client.get('/api/v1/system/queue')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json['code'], 'unauthorized')

    def test_handle_404(self):
        res = self.client.get('/api/v1/this_route_does_not_exist')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json['code'], 'not_found')

    def test_handle_405(self):
        # GET is allowed on /api/v1/system/health, POST is not
        res = self.client.post('/api/v1/system/health')
        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json['code'], 'method_not_allowed')

    def test_handle_429(self):
        # POST to /auth/tokens allows 5 requests per 15 min. We'll hit it 6 times.
        payload = {'email': 'test@example.com',
                   'password': 'pwd', 'token_name': 'test'}
        for _ in range(5):
            self.client.post('/api/v1/auth/tokens', json=payload)
        res = self.client.post('/api/v1/auth/tokens', json=payload)
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json['code'], 'rate_limited')
        self.assertIn('retry_after', res.json['details'])

    def test_marshmallow_error(self):
        # Missing required 'password' field
        payload = {'email': 'test@example.com', 'token_name': 'test'}
        res = self.client.post('/api/v1/auth/tokens', json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')
        self.assertIn('password', res.json['details']['fields'])

    @mock.patch('mod_api.routes.auth.User.query')
    def test_sqlalchemy_error(self, mock_query):
        # Mock database query to raise SQLAlchemyError
        mock_query.filter_by.side_effect = SQLAlchemyError("Database down")

        payload = {'email': 'test@example.com',
                   'password': 'password123', 'token_name': 'test'}
        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')

        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json['code'], 'internal_error')

    def test_handle_500(self):
        with self.app.test_request_context('/api/v1/system/health'):
            res = handle_500(ValueError("Something went wrong"))
            self.assertEqual(res.status_code, 500)
            self.assertEqual(res.json['code'], 'internal_error')

    def test_non_api_request_error(self):
        # Standard error handler for non-API route
        res = self.client.get('/not_an_api_route')
        self.assertEqual(res.status_code, 404)

    def test_non_api_request_500(self):
        from werkzeug.exceptions import InternalServerError

        from run import internal_error
        with self.app.test_request_context('/not_an_api_route_500'):
            res = internal_error(InternalServerError("Boom"))
            # @template_renderer wrapper returns rendered template (str) or tuple
            if isinstance(res, tuple):
                self.assertEqual(res[1], 500)
            else:
                self.assertTrue(isinstance(res, str))
