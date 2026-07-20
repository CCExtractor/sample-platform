"""Shared base class for the API test package."""

from unittest.mock import patch

from tests.base import BaseTestCase


def _mock_generate_hash(password):
    return f"mock_hash_{password}"


def _mock_is_password_valid(self, password):
    return self.password == f"mock_hash_{password}"


class ApiTestCase(BaseTestCase):
    """BaseTestCase with password hashing stubbed out.

    sha512_crypt is deliberately slow, and almost every API test creates a
    user and requests a token. Stubbing the hash cuts the package runtime
    from minutes to seconds. A test that needs real hashing can call
    cls._hash_patchers[i].stop() locally (none do today).
    """

    @classmethod
    def setUpClass(cls):
        """Patch User hashing for the whole test class."""
        cls._hash_patchers = [
            patch('mod_auth.models.User.generate_hash',
                  staticmethod(_mock_generate_hash)),
            patch('mod_auth.models.User.is_password_valid',
                  _mock_is_password_valid),
        ]
        for patcher in cls._hash_patchers:
            patcher.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Restore the real hashing implementations."""
        super().tearDownClass()
        for patcher in cls._hash_patchers:
            patcher.stop()
