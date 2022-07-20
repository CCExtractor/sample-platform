import json
import time
from unittest import mock

from flask import url_for
from werkzeug.exceptions import Forbidden, NotFound

from mod_auth import controllers
from mod_auth.controllers import (fetch_username_from_token,
                                  generate_hmac_hash, github_token_validity,
                                  send_reset_email)
from mod_auth.models import Role, User
from tests.base import BaseTestCase, mock_decorator, signup_information


class MockUser:
    """Mock user object to avoid interacting with database."""

    def __init__(self, id=None, name=None, email=None, password=None, github_token=None, role=None):
        self.id = id
        self.name = name
        self.email = email
        self.password = password
        self.github_token = github_token
        self.role = role


class TestSignUp(BaseTestCase):
    """Test sign up process."""

    def test_if_email_signup_form_renders(self):
        """Test email signup form rendering."""
        response = self.app.test_client().get(url_for('auth.signup'))
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('auth/signup.html')

    def test_blank_email(self):
        """Test case with blank email."""
        response = self.signup(email='')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Email address is not filled in', response.data)

    def test_invalid_email_address(self):
        """Test case with invalid email."""
        invalid_email_address = ['plainaddress',
                                 '#@%^%#$@#$@#.com',
                                 '@domain.com',
                                 'Joe Smith <email@domain.com>',
                                 'email.domain.com',
                                 'email@domain.com (Joe Smith)',
                                 'email@-domain.com',
                                 'email@111.222.333.44444']

        for email in invalid_email_address:
            with self.subTest():
                response = self.signup(email)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Entered value is not a valid email address', response.data)

    @mock.patch('requests.post')
    def test_existing_email_signup(self, mock_post):
        """Test case with existed email."""
        response = self.signup(email=signup_information['existing_user_email'])
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Email sent for verification purposes. Please check your mailbox', response.data)
        mock_post.assert_called_once()

    @mock.patch('requests.post')
    def test_valid_email_signup(self, mock_post):
        """Test case with valid email."""
        response = self.signup(email=signup_information['valid_email'])
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Email sent for verification purposes. Please check your mailbox', response.data)
        mock_post.assert_called_once()

    def signup(self, email):
        """Finish signup with specific email."""
        return self.app.test_client().post(url_for('auth.signup'), data=dict(email=email), follow_redirects=True)


class TestLogin(BaseTestCase):
    """Test login process."""

    @mock.patch('mod_auth.controllers.flash')
    def test_not_show_login_user_logged_in(self, mock_flash):
        """Do not show login page if the user is already logged in."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/account/login')

        self.assertStatus(response, 302)
        mock_flash.assert_called_once_with('You are already logged in!', 'alert')


class CompleteSignUp(BaseTestCase):
    """Test cases to complete signup."""

    def setUp(self):
        """Set up hashes for the signup links."""
        self.time_of_hash = int(time.time())
        # if this test somehow manages to run for more than a year, we probably have bigger problems
        SECONDS_PER_YEAR = 31_536_000
        self.expiry_time = self.time_of_hash + SECONDS_PER_YEAR
        # time in the past - used to test how we handle expired HMACs
        self.past_time = self.time_of_hash - 3600

        content_to_hash = f"{signup_information['valid_email']}|{self.expiry_time}"
        self.hash = generate_hmac_hash(self.app.config.get('HMAC_KEY', ''), content_to_hash)
        content_to_hash = f"{signup_information['existing_user_email']}|{self.time_of_hash}"
        self.existing_user_hash = generate_hmac_hash(self.app.config.get('HMAC_KEY', ''), content_to_hash)
        content_to_hash = f"{signup_information['valid_email']}|{self.past_time}"
        self.expired_hash = generate_hmac_hash(self.app.config.get('HMAC_KEY', ''), content_to_hash)

    def test_if_link_expired(self):
        """Test signup with an expired signup link."""
        response = self.complete_signup(signup_information['valid_email'], self.past_time, self.expired_hash)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"The request to complete the registration was invalid.", response.data)

    def test_if_wrong_link(self):
        """Test signup with a wrong signup link."""
        response = self.complete_signup(signup_information['existing_user_email'], self.expiry_time, self.hash)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"The request to complete the registration was invalid.", response.data)

    def test_if_valid_link(self):
        """Test signup with a valid signup link."""
        response = self.complete_signup(signup_information['valid_email'], self.expiry_time, self.hash)
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('auth/complete_signup.html')

    def test_if_password_is_blank(self):
        """Test case when password is empty."""
        response = self.complete_signup(signup_information['valid_email'], self.expiry_time, self.hash,
                                        name=signup_information['existing_user_name'], password='', password_repeat='')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('auth/complete_signup.html')
        self.assertIn(b"Password is not filled in", response.data)

    def test_if_password_length_is_invalid(self):
        """Test case when password has incorrect length."""
        response = self.complete_signup(signup_information['valid_email'], self.expiry_time, self.hash,
                                        name=signup_information['existing_user_name'], password='small',
                                        password_repeat='small')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('auth/complete_signup.html')
        self.assertIn(b"Password needs to be between", response.data)

    def test_if_passwords_dont_match(self):
        """Test case when fields with passwords don't contain the same content."""
        response = self.complete_signup(signup_information['valid_email'], self.expiry_time, self.hash,
                                        name=signup_information['existing_user_name'], password='some_password',
                                        password_repeat='another_password')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('auth/complete_signup.html')
        self.assertIn(b"The password needs to match the new password", response.data)

    def complete_signup(self, email, expires, mac, name='', password='', password_repeat=''):
        """Finish signup with user data."""
        return self.app.test_client().post(url_for('auth.complete_signup', email=email, expires=expires, mac=mac),
                                           data=dict(name=name, password=password, password_repeat=password_repeat),
                                           follow_redirects=True)


class TestLogOut(BaseTestCase):
    """Test logout process."""

    def test_if_logout_redirects_to_login(self):
        """Test redirect to the login page after logout."""
        response = self.app.test_client().get(url_for('auth.logout'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You have been logged out", response.data)
        self.assert_template_used('auth/login.html')


class TestGitHubFunctions(BaseTestCase):
    """Test github-related functions."""

    @mock.patch('requests.Session')
    @mock.patch('mod_auth.controllers.g')
    @mock.patch('mod_auth.controllers.User')
    def test_fetch_username_from_none_token(self, mock_user_model, mock_g, mock_session):
        """Test the Token to username function with None as user's token."""
        mock_user_model.query.filter.return_value.first.return_value = MockUser()

        return_value = fetch_username_from_token()

        mock_user_model.query.filter.assert_called_once_with(mock_user_model.id == mock_g.user.id)
        self.assertIsNone(return_value)
        mock_session.assert_not_called()
        mock_g.log.error.assert_not_called()

    @mock.patch('requests.Session')
    @mock.patch('mod_auth.controllers.g')
    @mock.patch('mod_auth.controllers.User')
    def test_fetch_username_from_valid_token(self, mock_user_model, mock_g, mock_session):
        """Test the Token to username function with dummy token value."""
        mock_user_model.query.filter.return_value.first.return_value = MockUser(github_token='token')
        mock_session.return_value.get.return_value.json.return_value = {'login': 'username'}

        return_value = fetch_username_from_token()

        mock_user_model.query.filter.assert_called_once_with(mock_user_model.id == mock_g.user.id)
        mock_session.assert_called_once()
        self.assertEqual(return_value, 'username', "unexpected return value")
        mock_g.log.error.assert_not_called()

    @mock.patch('requests.Session')
    @mock.patch('mod_auth.controllers.g')
    @mock.patch('mod_auth.controllers.User')
    def test_fetch_username_from_token_exception(self, mock_user_model, mock_g, mock_session):
        """Test the Token to username function with requests throwing exception."""
        mock_user_model.query.filter.return_value.first.return_value = MockUser(github_token='token')
        mock_session.return_value.get.side_effect = Exception

        return_value = fetch_username_from_token()

        mock_user_model.query.filter.assert_called_once_with(mock_user_model.id == mock_g.user.id)
        mock_session.assert_called_once()
        self.assertIsNone(return_value)
        mock_g.log.error.assert_called_once_with("Failed to fetch the user token")

    @mock.patch('requests.post')
    def test_github_callback_empty_post(self, mock_post):
        """Send empty post request to github_callback."""
        with self.app.test_client() as client:
            response = client.post("/account/github_callback")

        self.assertEqual(response.status_code, 404)
        mock_post.assert_not_called()

    @mock.patch('requests.post')
    def test_github_callback_empty_get(self, mock_post):
        """Send empty get request to github_callback."""
        with self.app.test_client() as client:
            response = client.get("/account/github_callback")

        self.assertEqual(response.status_code, 404)
        mock_post.assert_not_called()

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('mod_auth.controllers.g')
    @mock.patch('requests.post')
    def test_github_callback_incomplete_get(self, mock_post, mock_g, mock_user_model):
        """Send valid get request to github_callback and receive no access_token."""
        mock_post.return_value.json.return_value = {}

        with self.app.test_client() as client:
            response = client.get("/account/github_callback", query_string={'code': 'secret'})

        self.assertEqual(response.status_code, 302)
        mock_post.assert_called_once()
        mock_user_model.query.filter.assert_called_once()
        mock_g.db.commit.assert_not_called()
        mock_g.log.error.assert_called_once_with("GitHub didn't return an access token")

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('mod_auth.controllers.g')
    @mock.patch('requests.post')
    def test_github_callback_valid_get(self, mock_post, mock_g, mock_user_model):
        """Send valid get request to github_callback and receive access_token."""
        mock_post.return_value.json.return_value = {'access_token': 'test'}

        with self.app.test_client() as client:
            response = client.get("/account/github_callback", query_string={'code': 'secret'})

        self.assertEqual(response.status_code, 302)
        mock_post.assert_called_once()
        self.assertEqual(2, mock_user_model.query.filter.call_count)
        mock_user_model.query.filter.assert_called_with(mock_user_model.id == mock_g.user.id)
        mock_g.db.commit.assert_called_once()
        mock_g.log.error.assert_not_called()

    def test_github_redirect(self):
        """Test editing account where GitHub token is not null."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin, self.user.github_token)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                "/account/manage", data=dict(
                    current_password=self.user.password,
                    name="T1duS",
                    email=self.user.email
                ))
            user = User.query.filter(User.name == "T1duS").first()
            self.assertNotEqual(user, None)
            self.assertIn("Settings saved", str(response.data))


class Miscellaneous(BaseTestCase):
    """Test utils."""

    def test_github_token_validity(self):
        """Test the GitHub Token Validity Function."""
        res = github_token_validity('token')
        self.assertEqual(res, False)


class ManageAccount(BaseTestCase):
    """Test account management operations."""

    def test_edit_username(self):
        """Test editing user's name."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            new_user_name = "T1duS"
            response = c.post(
                "/account/manage", data=dict(
                    current_password=self.user.password,
                    name=new_user_name,
                    email=self.user.email
                ))
            user = User.query.filter(User.name == new_user_name).first()
            self.assertNotEqual(user, None)
            self.assertIn("Settings saved", str(response.data))

    def test_edit_email(self):
        """Test editing user's email address."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            new_user_email = "valid@gmail.com"
            response = c.post(
                "/account/manage", data=dict(
                    current_password=self.user.password,
                    name=self.user.name,
                    email=new_user_email
                ))
            user = User.query.filter(User.email == new_user_email).first()
            self.assertNotEqual(user, None)
            self.assertIn("Settings saved", str(response.data))

    def test_edit_invalid_email(self):
        """Test editing user's email with invalid email address."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            invalid_new_email = "invalid@gg"
            response = c.post(
                "/account/manage", data=dict(
                    current_password=self.user.password,
                    name=self.user.name,
                    email=invalid_new_email
                ))
            user = User.query.filter(User.email == invalid_new_email).first()
            self.assertEqual(user, None)
            self.assertNotIn("Settings saved", str(response.data))
            self.assertIn("entered value is not a valid email address", str(response.data))

    @mock.patch('mod_auth.controllers.url_for')
    @mock.patch('mod_auth.controllers.generate_hmac_hash')
    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('mod_auth.controllers.g.mailer')
    @mock.patch('run.app')
    def test_send_reset_email(self, mock_app, mock_mailer, mock_flash, mock_hash, mock_url_for):
        """Test sending recovery email to user."""
        user = MockUser(1, "testuser", "dummy@test.org", "dummy")
        mock_mailer.send_simple_message.return_value = True

        send_reset_email(user)

        mock_hash.assert_called_once()
        mock_app.jinja_env.get_or_select_template.assert_called_once_with("email/recovery_link.txt")
        mock_url_for.assert_called_once()
        mock_mailer.send_simple_message.assert_called_once()
        mock_flash.assert_not_called()

    @mock.patch('mod_auth.controllers.url_for')
    @mock.patch('mod_auth.controllers.generate_hmac_hash')
    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('mod_auth.controllers.g.mailer')
    @mock.patch('run.app')
    def test_send_reset_email_fail(self, mock_app, mock_mailer, mock_flash, mock_hash, mock_url_for):
        """Test sending recovery email to user."""
        user = MockUser(1, "testuser", "dummy@test.org", "dummy")
        mock_mailer.send_simple_message.return_value = False

        send_reset_email(user)

        mock_hash.assert_called_once()
        mock_app.jinja_env.get_or_select_template.assert_called_once_with("email/recovery_link.txt")
        mock_url_for.assert_called_once()
        mock_mailer.send_simple_message.assert_called_once()
        mock_flash.assert_called_once_with("Could not send an email. Please get in touch", "error-message")

    def test_account_reset_get(self):
        """Test account reset endpoint with GET."""
        with self.app.test_client() as client:
            response = client.get("/account/reset")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recover password", str(response.data))

    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('mod_auth.controllers.send_reset_email')
    @mock.patch('mod_auth.controllers.User')
    def test_account_reset_post_user_none(self, mock_user_model, mock_mail, mock_flash):
        """Test account reset endpoint with POST where user doesn't exist."""
        mock_user_model.query.filter_by.return_value.first.return_value = None
        email_to_test = "example@test.org"
        form_data = {'email': email_to_test}

        with self.app.test_client() as client:
            response = client.post("/account/reset", data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recover password", str(response.data))
        mock_user_model.query.filter_by.assert_called_once_with(email=email_to_test)
        mock_mail.assert_not_called()
        mock_flash.assert_called_once()

    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('mod_auth.controllers.send_reset_email')
    @mock.patch('mod_auth.controllers.User')
    def test_account_reset_post_user(self, mock_user_model, mock_mail, mock_flash):
        """Test account reset endpoint with POST where user does exist."""
        mock_user_model.query.filter_by.return_value.first.return_value = "user"
        email_to_test = "example@test.org"
        form_data = {'email': email_to_test}

        with self.app.test_client() as client:
            response = client.post("/account/reset", data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recover password", str(response.data))
        mock_user_model.query.filter_by.assert_called_once_with(email=email_to_test)
        mock_mail.assert_called_once_with("user")
        mock_flash.assert_called_once()

    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('time.time')
    def test_complete_reset_expired(self, mock_time, mock_flash):
        """Test complete reset endpoint expired."""
        time_now = 100
        mock_time.return_value = time_now
        time_expired = 100

        with self.app.test_client() as client:
            response = client.post(f"/account/reset/1/{time_expired}/some_mac")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Redirecting...", str(response.data))
        mock_flash.assert_called_once()

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('hmac.compare_digest', return_value=True)
    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('time.time')
    def test_complete_reset_get(self, mock_time, mock_flash, mock_hmac, mock_user):
        """Test complete reset get form."""
        time_now = 100
        mock_time.return_value = time_now
        mock_user.query.filter_by.return_value.first.return_value = MockUser(email="mock",
                                                                             name="dummy",
                                                                             password="psswd")

        with self.app.test_client() as client:
            response = client.get(f"/account/reset/1/{time_now}/some_mac")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Please enter your new password below", str(response.data))
        mock_user.query.filter_by.assert_called_once_with(id=1)
        mock_hmac.assert_called_once()
        mock_flash.assert_not_called()

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('hmac.compare_digest', return_value=True)
    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('time.time')
    @mock.patch('mod_auth.controllers.CompleteResetForm')
    @mock.patch('mod_auth.controllers.g')
    def test_complete_reset_post_valid(self, mock_g, mock_form, mock_time, mock_flash, mock_hmac, mock_user):
        """Test complete reset valid new password post."""
        time_now = 100
        mock_time.return_value = time_now
        mock_user.query.filter_by.return_value.first.return_value = MockUser(email="mock",
                                                                             name="dummy",
                                                                             password="psswd")

        with self.app.test_client() as client:
            new_password = "abcdEFGH@1234"
            response = client.post(f"/account/reset/1/{time_now}/some_mac", data={
                'Password': new_password,
                'Repeat password': new_password,
                'Reset password': True
            })

        self.assertEqual(response.status_code, 302)
        mock_user.query.filter_by.assert_called_once_with(id=1)
        mock_hmac.assert_called_once()
        mock_user.generate_hash.assert_called_once()
        mock_g.db.commit.assert_called_once()
        mock_g.mailer.send_simple_message.assert_called_once()
        mock_flash.assert_not_called()

    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('time.time')
    def test_complete_signup_expired(self, mock_time, mock_flash):
        """Test complete signup endpoint expired."""
        time_now = 100
        mock_time.return_value = time_now
        time_expired = 100

        with self.app.test_client() as client:
            response = client.post(f"/account/complete_signup/email/{time_expired}/some_mac")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Redirecting...", str(response.data))
        mock_flash.assert_called_once()

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('hmac.compare_digest', return_value=True)
    @mock.patch('time.time')
    def test_complete_signup_user_already_exists(self, mock_time, mock_hmac, mock_flash, mock_user):
        """Test complete signup when user already exists."""
        time_now = 100
        mock_time.return_value = time_now
        mock_user.query.filter_by.return_value.first.return_value = MockUser(email="mock",
                                                                             name="dummy",
                                                                             password="psswd")

        with self.app.test_client() as client:
            response = client.post(f"/account/complete_signup/email/{time_now}/some_mac")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Redirecting...", str(response.data))
        mock_hmac.assert_called_once()
        mock_user.query.filter_by.assert_called_once_with(email='email')
        mock_flash.assert_called_once_with(mock.ANY, "error-message")

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('mod_auth.controllers.flash')
    @mock.patch('hmac.compare_digest', return_value=True)
    @mock.patch('time.time')
    @mock.patch('mod_auth.controllers.CompleteSignupForm')
    @mock.patch('mod_auth.controllers.g')
    def test_complete_signup(self, mock_g, mock_form, mock_time, mock_hmac, mock_flash, mock_user):
        """Test complete signup with valid response."""
        time_now = 100
        mock_time.return_value = time_now
        mock_form.return_value.validate_on_submit.return_value = True
        mock_user.query.filter_by.return_value.first.return_value = None
        mock_user.return_value = MockUser(id=1)

        with self.app.test_client() as client:
            response = client.post(f"/account/complete_signup/email/{time_now}/some_mac")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Redirecting...", str(response.data))
        mock_hmac.assert_called_once()
        mock_user.query.filter_by.assert_called_once_with(email='email')
        mock_form.assert_called_once_with()
        mock_user.assert_called_once()
        mock_g.db.add.assert_called_once()
        mock_g.mailer.send_simple_message.assert_called_once()
        mock_flash.assert_not_called()


class ManageUsers(BaseTestCase):
    """Test users management operations."""

    @mock.patch('mod_auth.controllers.g')
    def test_user_view_not_loggen_in(self, mock_g):
        """
        Test accessing user view when not logged in.

        This test accounts for all other methods which are decorated by login_required
        """
        with self.app.test_client() as client:
            response = client.get("/account/user/2")

        self.assertEqual(response.status_code, 302)

    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    def test_user_view_wrong_user(self, mock_g, mock_login):
        """Test accessing different user from user id."""
        from mod_auth.controllers import user

        mock_g.user = MockUser(id=1, role="None")

        with self.assertRaises(Forbidden):
            user(2)

    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    @mock.patch('mod_auth.controllers.User')
    def test_user_view_non_existent_user(self, mock_user, mock_g, mock_login):
        """Test accessing for user not existent."""
        from mod_auth.controllers import user

        mock_user.query.filter_by.return_value.first.return_value = None
        mock_g.user = MockUser(id=1, role="None")

        with self.assertRaises(NotFound):
            user(1)

        mock_user.query.filter_by.assert_called_once_with(id=1)

    # NOTE: Not able to mock template_renderer decorator
    # @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    # @mock.patch('mod_auth.controllers.template_renderer', return_value=mock_decorator)
    # @mock.patch('mod_auth.controllers.g')
    # @mock.patch('mod_auth.controllers.User')
    # @mock.patch('mod_upload.models.Upload')
    # def test_user_view_success(self, mock_upload, mock_user, mock_g, mock_renderer, mock_login):
    #     """
    #     Test accessing for user successfully.
    #     """
    #     from mod_auth.controllers import user

    #     mock_user.query.filter_by.return_value.first.return_value = MockUser(id=1, role="None")
    #     mock_g.user = MockUser(id=1, role="None")

    #     response = user(1)

    #     mock_user.query.filter_by.assert_called_once_with(id=1)
    #     mock_upload.query.filter.assert_called_once_with(mock_upload.user_id == 1)

    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    def test_user_reset_wrong_user(self, mock_g, mock_login):
        """Test accessing reset user from different non-admin user id."""
        from mod_auth.controllers import reset_user

        mock_g.user = MockUser(id=1, role="None")

        with self.assertRaises(Forbidden):
            reset_user(2)

    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    def test_user_role_wrong_user(self, mock_g, mock_login):
        """Test accessing role change from non-admin user id."""
        from mod_auth.controllers import role

        mock_g.user = MockUser(id=1, role="None")

        with self.assertRaises(Forbidden):
            role(2)

    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    def test_user_deactivate_wrong_user(self, mock_g, mock_login):
        """Test deactivating user from different user id."""
        from mod_auth.controllers import deactivate

        mock_g.user = MockUser(id=1, role="None")

        with self.assertRaises(Forbidden):
            deactivate(2)

    @mock.patch('mod_auth.controllers.User')
    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    def test_user_deactivate_non_existent_user(self, mock_g, mock_login, mock_user):
        """Test deactivating user from non-existent user id."""
        from mod_auth.controllers import deactivate

        mock_g.user = MockUser(id=1, role="None")
        mock_user.query.filter_by.return_value.first.return_value = None

        with self.assertRaises(NotFound):
            deactivate(1)

    @mock.patch('mod_auth.controllers.url_for')
    @mock.patch('mod_auth.controllers.DeactivationForm')
    @mock.patch('mod_auth.controllers.User')
    @mock.patch('mod_auth.controllers.login_required', side_effect=mock_decorator)
    @mock.patch('mod_auth.controllers.g')
    def test_user_deactivate_existent_user(self, mock_g, mock_login, mock_user, mock_form, mock_url_for):
        """Test deactivating user."""
        from mod_auth.controllers import deactivate

        mock_user.query.filter_by.return_value.first.return_value = MockUser(id=1, role=None)
        mock_g.user = MockUser(id=1, role="None")

        deactivate(1)

        mock_user.query.filter_by.assert_called_once_with(id=1)
        mock_form.assert_called_once()
        mock_form.return_value.validate_on_submit.assert_called_once()
        mock_g.db.commit.assert_called_once()
        mock_url_for.assert_called_once_with('.login')
