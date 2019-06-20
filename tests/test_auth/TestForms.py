from flask import g
from wtforms.validators import ValidationError

from mod_auth.forms import unique_username, valid_password
from mod_auth.models import User
from tests.base import BaseTestCase


class Field:
    def __init__(self, data):
        self.data = data


class TestForm(BaseTestCase):

    def test_unique_username(self):
        """
        Test that username is always unique.
        """
        user = User(name="thealphadollar")
        g.db.add(user)
        g.db.commit()

        user_field = Field("thealphadollar")

        with self.assertRaises(ValidationError):
            unique_username(None, user_field)

    def test_empty_invalid_password(self):
        """
        Test validation fail for zero length password.
        """
        pass_field = Field("")

        with self.assertRaises(ValidationError):
            valid_password(None, pass_field)

    def test_less_than_min_lenght_invalid_password(self):
        """
        Test validation fail for password of length less than min length.
        """
        pass_field = Field("".join(['x' * (int(self.app.config['MIN_PWD_LEN']) - 1)]))

        with self.assertRaises(ValidationError):
            valid_password(None, pass_field)

    def test_more_than_max_lenght_invalid_password(self):
        """
        Test validation fail for password of length more than max length.
        """
        pass_field = Field("".join(['x' * (int(self.app.config['MAX_PWD_LEN']) + 1)]))

        with self.assertRaises(ValidationError):
            valid_password(None, pass_field)

    def test_valid_password(self):
        """
        Test validation pass for valid password.
        """
        pass_field = Field("".join(['x' * (int(self.app.config['MAX_PWD_LEN']))]))

        valid_password(None, pass_field)
