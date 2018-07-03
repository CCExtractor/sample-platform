from tests.base import BaseTestCase, MockRequests
from mod_auth.models import User, Role
from mock import mock
from flask import g


class TestAuth(BaseTestCase):

    @mock.patch('requests.Session')
    def test_fetch_username(self, mock_requests):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            g.user = User.query.filter(User.id == 1).first()
            g.user.github_token = self.user.github_token
            g.db.add(g.user)
            g.db.commit()
            session = mock_requests()
            session.auth = (self.user.email, self.user.github_token)
            session.get.side_effect = MockRequests
            from mod_auth.controllers import fetch_username_from_token
            username = fetch_username_from_token()
            self.assertEqual(session.auth, (self.user.email, self.user.github_token))
            session.get.assert_called_with('https://api.github.com/user')
            self.assertIn("test", username)
