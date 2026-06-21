"""Tests for the CLI's HTTP client, mocking the requests session."""

import unittest
from unittest import mock

import requests  # type: ignore[import-untyped]

from sp_cli.client import ApiClient, ApiError


class FakeResponse:
    """Minimal stand-in for a requests Response."""

    def __init__(self, status_code, json_data=None, raise_json=False):
        """Store the canned status and body."""
        self.status_code = status_code
        self._json = json_data
        self._raise_json = raise_json

    def json(self):
        """Return the canned JSON body or raise like requests does on non-JSON."""
        if self._raise_json:
            raise ValueError('No JSON could be decoded')
        return self._json


class ApiClientTests(unittest.TestCase):
    """Exercise request building and error mapping in the client."""

    @mock.patch('requests.Session.request')
    def test_get_returns_payload_and_builds_url(self, mock_request):
        """A 2xx response is returned and the API prefix is applied."""
        mock_request.return_value = FakeResponse(200, {'data': []})
        client = ApiClient('https://host/api/v1')

        self.assertEqual(client.get('/runs'), {'data': []})
        args, _ = mock_request.call_args
        self.assertEqual(args[0], 'GET')
        self.assertEqual(args[1], 'https://host/api/v1/runs')

    @mock.patch('requests.Session.request')
    def test_204_returns_none(self, mock_request):
        """A 204 (e.g. token revoke) returns None, not a parse error."""
        mock_request.return_value = FakeResponse(204)
        self.assertIsNone(ApiClient('https://host').request('DELETE', '/auth/tokens/current'))

    @mock.patch('requests.Session.request')
    def test_error_codes_map_to_exit_codes(self, mock_request):
        """Each HTTP error maps to its documented exit code."""
        cases = {404: 4, 422: 5, 400: 5, 401: 6, 403: 6, 429: 7}
        client = ApiClient('https://host')
        for status, expected_exit in cases.items():
            mock_request.return_value = FakeResponse(status, {'code': 'x', 'message': 'm'})
            with self.assertRaises(ApiError) as caught:
                client.get('/runs/9')
            self.assertEqual(caught.exception.exit_code, expected_exit, f'status {status}')

    @mock.patch('requests.Session.request')
    def test_token_is_sent_as_bearer_header(self, mock_request):
        """A configured token is sent as an Authorization header."""
        mock_request.return_value = FakeResponse(200, {})
        ApiClient('https://host', token='secret').get('/runs')
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret')

    @mock.patch('requests.Session.request', side_effect=requests.RequestException('boom'))
    def test_connection_failure(self, mock_request):
        """A transport failure maps to a connection_error with exit code 3."""
        with self.assertRaises(ApiError) as caught:
            ApiClient('https://host').get('/runs')
        self.assertEqual(caught.exception.code, 'connection_error')
        self.assertEqual(caught.exception.exit_code, 3)

    @mock.patch('requests.Session.request')
    def test_non_json_body_raises_invalid_response(self, mock_request):
        """A non-JSON body raises invalid_response rather than crashing."""
        mock_request.return_value = FakeResponse(500, raise_json=True)
        with self.assertRaises(ApiError) as caught:
            ApiClient('https://host').get('/runs')
        self.assertEqual(caught.exception.code, 'invalid_response')

    @mock.patch('requests.Session.request')
    def test_get_paginated_follows_offset(self, mock_request):
        """Pagination is followed across pages until next_offset is null."""
        mock_request.side_effect = [
            FakeResponse(200, {'data': [1, 2, 3], 'pagination': {'next_offset': 3}}),
            FakeResponse(200, {'data': [4, 5], 'pagination': {'next_offset': None}}),
        ]
        items = ApiClient('https://host').get_paginated('/runs/9/samples')
        self.assertEqual(items, [1, 2, 3, 4, 5])
