import os
import tempfile

from tests.base import BaseTestCase, provide_file_at_root


class mock_application:
    """Mock object for application."""

    def __init__(self):
        self.config = {}
        self.root_path = ''


class TestRun(BaseTestCase):
    """Test application running."""

    def test_load_secret_keys_files_present(self):
        """Test csrf session and secret keys loading when they are presented."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = os.path.join(temp_dir, 'secret_key')
            csrf_path = os.path.join(temp_dir, 'secret_csrf')
            with open(secrets_path, 'wb') as f:
                f.write(b'secret')
            with open(csrf_path, 'wb') as f:
                f.write(b'csrf')

            application = mock_application()
            with provide_file_at_root('config.py'):
                from run import load_secret_keys
                load_secret_keys(application, secrets_path, csrf_path)

            self.assertEqual(application.config['SECRET_KEY'], b'secret', 'secret key not loaded properly')
            self.assertEqual(application.config['CSRF_SESSION_KEY'], b'csrf', 'csrf session key not loaded properly')

    def test_load_secret_keys_secrets_not_present(self):
        """Test csrf session and secret keys loading when csrf session key is not presented."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = os.path.join(temp_dir, 'secret_key')
            csrf = "notAvailable"
            with open(secrets_path, 'wb') as f:
                f.write(b'secret')

            application = mock_application()
            with provide_file_at_root('config.py'):
                from run import load_secret_keys
                with self.assertRaises(SystemExit) as cmd:
                    load_secret_keys(application, secrets_path, csrf)

            self.assertEqual(application.config['SECRET_KEY'], b'secret', 'secret key not loaded properly')
            self.assertEqual(cmd.exception.code, 1, 'function exited with a wrong code')

    def test_load_secret_keys_csrf_not_present(self):
        """Test csrf session and secret keys loading when secret key is not presented."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets = "notAvailable"
            csrf_path = os.path.join(temp_dir, 'secret_csrf')
            with open(csrf_path, 'wb') as f:
                f.write(b'csrf')

            application = mock_application()
            with provide_file_at_root('config.py'):
                from run import load_secret_keys
                with self.assertRaises(SystemExit) as cmd:
                    load_secret_keys(application, secrets, csrf_path)

            self.assertEqual(cmd.exception.code, 1, 'function exited with a wrong code')
            self.assertEqual(application.config['CSRF_SESSION_KEY'], b'csrf', 'csrf session key not loaded properly')
