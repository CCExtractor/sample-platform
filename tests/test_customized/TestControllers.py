from mock import mock
from sqlalchemy import and_
from importlib import reload
from flask import g
from tests.base import BaseTestCase, MockRequests
from mod_auth.models import Role
from mod_test.models import Fork, Test, TestPlatform
from mod_regression.models import RegressionTest
from mod_customized.models import TestFork, CustomizedTest


def return_gituser():
    return "test"


@mock.patch('requests.get', side_effect=MockRequests)
@mock.patch('github.GitHub')
@mock.patch('mod_auth.controllers.fetch_username_from_token', side_effect=return_gituser)
class TestControllers(BaseTestCase):
    def test_customize_test_page_fails_with_no_permission(self, mock_user, mock_git, mock_requests):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/custom/')
            self.assertEqual(response.status_code, 403)

    def test_customize_test_page_loads_with_permission(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/custom/')
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            self.assertIn('submit', str(response.data))

    def test_customize_test_fails_with_wrong_commit_hash(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/custom/', data=self.create_customize_form('', ['linux']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            self.assertIn('Commit hash is not filled in', str(response.data))
            response = c.post(
                '/custom/', data=self.create_customize_form('test-url', ['linux']))
            self.assertIn('Wrong Commit Hash', str(response.data))

    def test_customize_test_creates_with_right_test_commit(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/custom/', data=self.create_customize_form('abcdef', ['linux']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            custom_test = TestFork.query.filter(
                TestFork.user_id == g.user.id).first()
            mock_requests.assert_called_with(('https://api.github.com/repos/{user}'
                                              '/{repo}/commits/{hash}').format(user=self.user.name,
                                                                               repo=g.github['repository'],
                                                                               hash='abcdef'))
            self.assertNotEqual(custom_test, None)

    def test_customize_test_creates_fork_if_not_exists(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/custom/', data=self.create_customize_form('abcdef', ['linux']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            fork = Fork.query.filter(Fork.github.like(
                "%/test/test_repo.git")).first()
            self.assertNotEqual(fork, None)

    def test_customize_test_creates_with_multiple_platforms(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            response = c.post('/custom/', data=self.create_customize_form(
                'abcdef', ['linux', 'windows']), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assert_template_used('custom/index.html')
            test_linux = g.db.query(Test.id).filter(
                and_(TestFork.test_id == Test.id, Test.platform == TestPlatform.linux)).first()
            test_windows = g.db.query(Test.id).filter(
                and_(TestFork.test_id == Test.id, Test.platform == TestPlatform.windows)).first()
            self.assertNotEqual(test_linux, None)
            self.assertNotEqual(test_windows, None)

    def test_customize_test_ccreates_with_select_arr(self, mock_user, mock_git, mock_requests):
        from flask import g
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        commits = []
        num_commits = 4
        for i in range(num_commits):
            commit_hash = self.create_random_string()
            url = ('https://github.com/{user}/{repo}/commit/{hash}').format(user=return_gituser(),
                                                                            repo=g.github['repository'],
                                                                            hash=commit_hash)
            commits.append({'html_url': url, 'sha': commit_hash})
        with self.app.test_client() as c:
            response = c.post('/account/login', data=self.create_login_form_data(
                self.user.email, self.user.password))
            repo = mock_git().repos()()
            repo.commits().get.return_value = commits
            response = c.get('/custom/')
            for commit in commits:
                self.assertIn(commit['sha'], str(response.data))

    def test_customize_regression_tests_load(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/custom/')
            self.assertEqual(response.status_code, 200)
            regression_tests = RegressionTest.query.all()
            for regression_test in regression_tests:
                self.assertIn(regression_test.command, str(response.data))

    def test_error_on_no_regression_test(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/custom/', data=self.create_customize_form('abcdef', ['linux'],
                                                            regression_test=[]), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Please add one or more Regression Tests', str(response.data))

    def test_customize_test_creates_with_customize_regression_tests(self, mock_user, mock_git, mock_requests):
        import mod_customized.controllers
        reload(mod_customized.controllers)
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/custom/', data=self.create_customize_form('abcdef', ['linux'],
                                                            regression_test=[2]), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            test = Test.query.filter(Test.id == 3).first()
            regression_tests = test.get_customized_regressiontests()
            self.assertIn(2, regression_tests)
            self.assertNotIn(1, regression_tests)

    def test_customize_test_github_server_error(self, mock_user, mock_git, mock_requests):
        """
        Test in case github ever returns a 500 error
        """

        import mod_customized.controllers
        reload(mod_customized.controllers)

        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            response_login = c.post('/account/login', 
                data=self.create_login_form_data(self.user.email, self.user.password))

            # Base.py: MockRequests
            response = c.post('/custom/', 
                data=self.create_customize_form('mockWillReturn500', ['linux'],
                                                            regression_test=[2]), follow_redirects=True) 

            # Validate if View Works
            self.assertEqual(response.status_code, 200)
            self.assertIn("Error contacting Github", str(response.data))

    def test_customize_test_wrong_commit_hash(self, mock_user, mock_git, mock_requests):
        """
        Test in case if a wrong hash is submitted
        """

        import mod_customized.controllers
        reload(mod_customized.controllers)

        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)

        with self.app.test_client() as c:
            response_login = c.post('/account/login', 
                data=self.create_login_form_data(self.user.email, self.user.password))

            response = c.post('/custom/', 
                data=self.create_customize_form('SomeoneSendMeCleanAirPlease', ['linux'],
                                                            regression_test=[2]), follow_redirects=True)

            # Validate if View Works
            self.assertEqual(response.status_code, 200)
            self.assertIn("Wrong Commit Hash", str(response.data))
