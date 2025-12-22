from importlib import reload
from unittest import mock

from flask import g
from sqlalchemy import and_

from mod_auth.models import Role
from mod_customized.models import TestFork
from mod_regression.models import RegressionTest
from mod_test.models import Fork, Test, TestPlatform
from tests.base import BaseTestCase, MockResponse, empty_github_token


def return_git_user():
    """Get git username."""
    return "test"


@mock.patch('github.Github.get_repo')
@mock.patch('mod_auth.controllers.fetch_username_from_token', side_effect=return_git_user)
class TestControllers(BaseTestCase):
    """Test customize test pages."""

    def test_customize_test_page_fails_with_no_permission(self, mock_user, mock_repo):
        """Test access to the customize test page without permission."""
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.user)

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.get('/custom/')
            self.assertEqual(response.status_code, 403)

    def test_customize_test_page_loads_with_permission(self, mock_user, mock_repo):
        """Test access to the customize test page with permission."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.get('/custom/')
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            self.assertIn('submit', str(response.data))

    def test_customize_test_fails_with_wrong_commit_hash(self, mock_user, mock_repo):
        """Test customize test creation with wrong commit hash."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            from github import GithubException
            mock_repo.return_value.get_commit = mock.MagicMock(
                side_effect=GithubException(status=404, data="", headers={}))
            response = c.post('/custom/', data=self.create_customize_form('', ['linux']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            self.assertIn('Commit hash is not filled in', str(response.data))
            response = c.post('/custom/', data=self.create_customize_form('test-url', ['linux']))
            self.assertIn('Wrong Commit Hash', str(response.data))

    def test_customize_test_creates_with_right_test_commit(self, mock_user, mock_repo):
        """Test customize test creation with correct commit."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        commit_hash = 'abcdef'

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.post(
                '/custom/', data=self.create_customize_form(commit_hash, ['linux']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            custom_test = TestFork.query.filter(TestFork.user_id == g.user.id).first()
            self.assertNotEqual(custom_test, None)

    def test_customize_test_creates_fork_if_not_exists(self, mock_user, mock_repo):
        """Test fork creation if it isn't existed."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.post('/custom/', data=self.create_customize_form('abcdef', ['linux']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            fork = Fork.query.filter(Fork.github.like("%/test/test_repo.git")).first()
            self.assertNotEqual(fork, None)

    def test_customize_test_creates_with_multiple_platforms(self, mock_user, mock_repo):
        """Test customize test creation with several platforms."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.post(
                '/custom/', data=self.create_customize_form('abcdef', ['linux', 'windows']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            test_linux = g.db.query(Test.id).filter(
                and_(TestFork.test_id == Test.id, Test.platform == TestPlatform.linux)).first()
            test_windows = g.db.query(Test.id).filter(
                and_(TestFork.test_id == Test.id, Test.platform == TestPlatform.windows)).first()
            self.assertNotEqual(test_linux, None)
            self.assertNotEqual(test_windows, None)

    def test_customize_test_creates_with_select_arr(self, mock_user, mock_repo):
        """Test customize test creation with commits list."""
        from flask import g
        from github.Commit import Commit

        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        commits = []
        num_commits = 4
        for i in range(num_commits):
            commit_hash = self.create_random_string()
            url = f"https://github.com/{return_git_user()}/{g.github['repository']}/commit/{commit_hash}"
            new_commit = mock.MagicMock(Commit)
            new_commit.sha = commit_hash
            new_commit.html_url = url
            commits.append(new_commit)
        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            mock_repo.return_value.get_commits.return_value = commits
            response = c.get('/custom/')
            for commit in commits:
                self.assertIn(commit.sha, str(response.data))

    def test_customize_regression_tests_load(self, mock_user, mock_repo):
        """Test loading of the regression tests."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/custom/')
            self.assertEqual(response.status_code, 200)
            regression_tests = RegressionTest.query.all()
            for regression_test in regression_tests:
                self.assertIn(regression_test.command, str(response.data))

    def test_error_on_no_regression_test(self, mock_user, mock_repo):
        """Test case when there isn't any regression test."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post('/custom/', data=self.create_customize_form('abcdef', ['linux'], regression_test=[]),
                              follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Please add one or more Regression Tests', str(response.data))

    def test_customize_test_creates_with_customize_regression_tests(self, mock_user, mock_repo):
        """Test customize test creation with regression tests."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.post('/custom/', data=self.create_customize_form('abcdef', ['linux'], regression_test=[2]),
                              follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            test = Test.query.filter(Test.id == 3).first()
            regression_tests = test.get_customized_regressiontests()
            self.assertIn(2, regression_tests)
            self.assertNotIn(1, regression_tests)

    @mock.patch('requests.get', return_value=MockResponse({}, 500))
    def test_customize_test_github_server_error(self, mock_requests, mock_user, mock_repo):
        """Test in case GitHub ever returns a 500 error."""
        import mod_customized.controllers
        reload(mod_customized.controllers)

        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            from github import GithubException
            mock_repo.return_value.get_commit = mock.MagicMock(
                side_effect=GithubException(status=500, data="", headers={}))
            response = c.post(
                '/custom/', data=self.create_customize_form('mockWillReturn500', ['linux'], regression_test=[2]),
                follow_redirects=True
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("Error contacting GitHub", str(response.data))

    def test_customize_test_wrong_commit_hash(self, mock_user, mock_repo):
        """Test in case if a wrong hash is submitted."""
        import mod_customized.controllers
        reload(mod_customized.controllers)

        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            from github import GithubException
            mock_repo.return_value.get_commit = mock.MagicMock(
                side_effect=GithubException(status=404, data="", headers={}))
            response = c.post(
                '/custom/',
                data=self.create_customize_form('not-found', ['linux'], regression_test=[2]),
                follow_redirects=True
            )

            # Validate if View Works
            self.assertEqual(response.status_code, 200)
            self.assertIn("Wrong Commit Hash", str(response.data))

    @mock.patch('run.get_github_config')
    @mock.patch('mod_auth.controllers.github_token_validity')
    def test_customize_test_page_without_github_token(
            self, mock_token_validity, mock_get_github_config, mock_user, mock_repo):
        """Test customize test page loads when GitHub bot token is not configured."""
        import mod_customized.controllers
        reload(mod_customized.controllers)
        # Create user WITH github_token so fetch_username_from_token returns a username
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester,
            github_token='user_github_token')
        # Mock token validity to return a valid username
        mock_token_validity.return_value = 'testuser'
        # Mock get_github_config to return empty bot_token
        mock_get_github_config.return_value = {
            'ci_key': g.github['ci_key'],
            'bot_token': '',
            'repository_owner': g.github['repository_owner'],
            'repository': g.github['repository']
        }

        with self.app.test_client() as c:
            c.post('/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/custom/')
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
