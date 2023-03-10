import json
from tempfile import gettempdir
from unittest import mock

from flask import g

from mod_deploy.controllers import requests
from tests.base import (BaseTestCase, generate_git_api_header,
                        generate_signature)

WSGI_ENVIRONMENT = {'REMOTE_ADDR': '0.0.0.0'}


@mock.patch.object(requests, 'get')
class TestControllers(BaseTestCase):
    """Test deployment related operations."""

    def test_root(self, mock_request_get):
        """Test the Root of mod_deploy."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        response = self.app.test_client().get('/deploy', environ_overrides=WSGI_ENVIRONMENT)
        self.assertEqual(response.status_code, 200)
        self.assertIn("OK", str(response.data))

    def test_headers_ping(self, mock_request_get):
        """Test The View by sending a ping request."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('ping', sig)

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Hi", str(response.data))

    def test_headers_missing_X_GitHub_Event(self, mock_request_get):
        """Test missing X-GitHub-Event header."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)
        headers.remove('X-GitHub-Event')

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 418)

    def test_headers_missing_X_GitHub_Delivery(self, mock_request_get):
        """Test missing X-GitHub-Delivery header."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)
        headers.remove('X-GitHub-Delivery')

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 418)

    def test_headers_missing_X_Hub_Signature(self, mock_request_get):
        """Test missing X-Hub-Signature header."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)
        headers.remove('X-Hub-Signature')

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 418)

    def test_headers_missing_User_Agent(self, mock_request_get):
        """Test missing User-Agent header."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)
        headers.remove('User-Agent')

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 418)

    def test_headers_invalid_User_Agent(self, mock_request_get):
        """Test invalid user-agent beginning."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)
        headers['User-Agent'] = "invalid"

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 418)

    def test_headers_event_not_push(self, mock_request_get):
        """Test The View by sending an event other than push."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        sig = generate_signature(str(json.dumps({})).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('pull', sig)

        response = self.app.test_client().post('/deploy', headers=headers, environ_overrides=WSGI_ENVIRONMENT)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Wrong event", str(response.data))

    @mock.patch('mod_deploy.controllers.is_valid_signature', return_value=False)
    @mock.patch('mod_deploy.controllers.g')
    def test_headers_invalid_signature_event(self, mock_g, mock_valid_sign, mock_request_get):
        """Test the view by sending an event with invalid signature."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        self.app.config['INSTALL_FOLDER'] = gettempdir()
        data = {
            'ref': 'refs/heads/master'
        }
        sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)

        with self.app.test_client() as client:
            response = client.post(
                '/deploy', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=headers
            )

        self.assertEqual(response.status_code, 418)
        mock_valid_sign.assert_called_once()
        mock_g.log.warning.assert_called_once()
        mock_request_get.assert_called_once_with('https://api.github.com/meta', auth=('', ''))

    @mock.patch('mod_deploy.controllers.is_valid_signature', return_value=True)
    @mock.patch('mod_deploy.controllers.g')
    def test_headers_no_payload_event(self, mock_g, mock_valid_sign, mock_request_get):
        """Test the view by sending an event without payload."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        self.app.config['INSTALL_FOLDER'] = gettempdir()
        data = None
        sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)

        with self.app.test_client() as client:
            response = client.post(
                '/deploy', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=headers
            )

        self.assertEqual(response.status_code, 418)
        mock_valid_sign.assert_called_once()
        mock_g.log.warning.assert_called_once()
        mock_request_get.assert_called_once_with('https://api.github.com/meta', auth=('', ''))

    @mock.patch('mod_deploy.controllers.is_valid_signature', return_value=True)
    @mock.patch('mod_deploy.controllers.g')
    def test_headers_not_master_event(self, mock_g, mock_valid_sign, mock_request_get):
        """Test the view by sending a valid event with branch other than master."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        self.app.config['INSTALL_FOLDER'] = gettempdir()
        data = {
            'ref': 'refs/heads/not_master'
        }
        sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)

        with self.app.test_client() as client:
            response = client.post(
                '/deploy', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=headers
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Not master', str(response.data))
        mock_valid_sign.assert_called_once()
        mock_g.log.warning.assert_not_called()
        mock_request_get.assert_called_once_with('https://api.github.com/meta', auth=('', ''))

    @mock.patch('mod_deploy.controllers.Repo')
    @mock.patch('mod_deploy.controllers.is_valid_signature', return_value=True)
    @mock.patch('mod_deploy.controllers.subprocess.Popen')
    @mock.patch('mod_deploy.controllers.copyfile')
    @mock.patch('mod_deploy.controllers.open')
    def test_headers_valid_event(self, mock_open, mock_copy, mock_subprocess,
                                 mock_valid_sign, mock_repo, mock_request_get):
        """Test the view by sending a valid event."""
        mock_request_get.return_value.json.return_value = {"hooks": ['0.0.0.0']}
        self.app.config['INSTALL_FOLDER'] = gettempdir()
        data = {
            'ref': 'refs/heads/master'
        }
        sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
        headers = generate_git_api_header('push', sig)

        # set return for mock_repo
        class mock_pull:
            from collections import namedtuple
            flags = 128
            commit_obj = namedtuple('commit_obj', ['hexsha'])
            commit = commit_obj('somesha')
        mock_repo.return_value.remote.return_value.fetch.return_value = "valid fetch"
        mock_repo.return_value.remote.return_value.pull.return_value = [mock_pull]

        with self.app.test_client() as client:
            response = client.post(
                '/deploy', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=headers
            )
        self.assertEqual(response.status_code, 200)
        mock_repo.assert_called_once()
        mock_open.assert_called_once_with('build_commit.py', 'w')
        mock_copy.assert_called()
        mock_subprocess.assert_called_once_with(["sudo", "service", "platform", "reload"])
        self.assertIn("somesha", response.data.decode('utf-8'))
