import os
import tempfile

from mock import mock

from tests.base import BaseTestCase, provide_file_at_root


class mock_application:

    def __init__(self):
        self.config = {}
        self.root_path = ''


class TestRun(BaseTestCase):

    def test_install_secret_keys_files_present(self):
        secrets = tempfile.NamedTemporaryFile()
        csrf = tempfile.NamedTemporaryFile()
        application = mock_application()

        with open(secrets.name, 'w') as f:
            f.write('secret')
        with open(csrf.name, 'w') as f:
            f.write('csrf')

        with provide_file_at_root('config.py'):
            from run import install_secret_keys
            install_secret_keys(application, secrets.name, csrf.name)

        secrets.close()
        csrf.close()

        self.assertEqual(application.config['SECRET_KEY'], b'secret', 'secret key not loaded properly')
        self.assertEqual(application.config['CSRF_SESSION_KEY'], b'csrf', 'csrf session key not loaded properly')

    def test_install_secret_keys_secrets_not_present(self):
        secrets = tempfile.NamedTemporaryFile()
        csrf = "notAvailable"
        application = mock_application()

        with open(secrets.name, 'w') as f:
            f.write('secret')

        with provide_file_at_root('config.py'):
            from run import install_secret_keys
            with self.assertRaises(SystemExit) as cmd:
                install_secret_keys(application, secrets.name, csrf)

        secrets.close()

        self.assertEqual(application.config['SECRET_KEY'], b'secret', 'secret key not loaded properly')
        self.assertEquals(cmd.exception.code, 1, 'function exited with a wrong code')

    def test_install_secret_keys_csrf_not_present(self):
        secrets = "notAvailable"
        csrf = tempfile.NamedTemporaryFile()
        application = mock_application()

        with open(csrf.name, 'w') as f:
            f.write('csrf')

        with provide_file_at_root('config.py'):
            from run import install_secret_keys
            with self.assertRaises(SystemExit) as cmd:
                install_secret_keys(application, secrets, csrf.name)

        csrf.close()

        self.assertEquals(cmd.exception.code, 1, 'function exited with a wrong code')
        self.assertEqual(application.config['CSRF_SESSION_KEY'], b'csrf', 'csrf session key not loaded properly')
