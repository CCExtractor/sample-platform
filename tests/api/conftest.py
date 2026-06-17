from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def mock_password_hashing():
    """
    Massively speed up pytest execution by mocking passlib hashing.

    This fixture is automatically applied to all tests in tests/api/
    but safely un-patches itself so it won't affect tests outside this package.
    """
    def mock_generate_hash(password):
        return f"mock_hash_{password}"

    def mock_is_password_valid(self, password):
        return self.password == f"mock_hash_{password}"

    with patch('mod_auth.models.User.generate_hash', staticmethod(mock_generate_hash)):
        with patch('mod_auth.models.User.is_password_valid', mock_is_password_valid):
            yield
