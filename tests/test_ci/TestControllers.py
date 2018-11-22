from mock import mock
from tests.base import BaseTestCase, MockRequests
from mod_test.models import Test, TestPlatform, TestType
from mod_regression.models import RegressionTest
from mod_customized.models import CustomizedTest
from mod_ci.models import BlockedUsers
from mod_auth.models import Role
from importlib import reload
from flask import g

class TestControllers(BaseTestCase):
    @mock.patch('github.GitHub')
    def test_comments_successfully_in_passed_pr_test(self, git_mock):
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import comment_pr, Status
        # Comment on test that passes all regression tests
        comment_pr(1, Status.SUCCESS, 1, 'linux')
        git_mock.assert_called_with(access_token=g.github['bot_token'])
        git_mock(access_token=g.github['bot_token']).repos.assert_called_with(g.github['repository_owner'])
        git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner']).assert_called_with(g.github['repository'])
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        repository.issues.assert_called_with(1)
        pull_request = repository.issues(1)
        pull_request.comments.assert_called_with()
        new_comment = pull_request.comments()
        args, kwargs = new_comment.post.call_args
        message = kwargs['body']
        if "passed" not in message:
            assert False, "Message not Correct"

    @mock.patch('github.GitHub')
    def test_comments_successfuly_in_failed_pr_test(self, git_mock):
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import comment_pr, Status
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        pull_request = repository.issues(1)
        message = ('<b>CCExtractor CI platform</b> finished running the '
                   'test files on <b>linux</b>. Below is a summary of the test results')
        pull_request.comments().get.return_value = [{'user': {'login': g.github['bot_name']},
                                                    'id': 1, 'body': message}]
        # Comment on test that fails some/all regression tests
        comment_pr(2, Status.FAILURE, 1, 'linux')
        pull_request = repository.issues(1)
        pull_request.comments.assert_called_with(1)
        new_comment = pull_request.comments(1)
        args, kwargs = new_comment.post.call_args
        message = kwargs['body']
        reg_tests = RegressionTest.query.all()
        flag = False
        for reg_test in reg_tests:
            if reg_test.command not in message:
                flag = True
        if flag:
            assert False, "Message not Correct"

    def test_check_main_repo_returns_in_false_url(self):
        from mod_ci.controllers import check_main_repo
        assert check_main_repo('random_user/random_repo') is False
        assert check_main_repo('test_owner/test_repo') is True

    @mock.patch('github.GitHub')
    @mock.patch('git.Repo')
    @mock.patch('libvirt.open')
    @mock.patch('shutil.rmtree')
    @mock.patch('mod_ci.controllers.open')
    @mock.patch('lxml.etree')
    def test_customize_tests_run_on_fork_if_no_remote(self, mock_etree, mock_open,
                                                      mock_rmtree, mock_libvirt, mock_repo, mock_git):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux)
        import mod_ci.cron
        import mod_ci.controllers
        reload(mod_ci.cron)
        reload(mod_ci.controllers)
        from mod_ci.cron import cron
        conn = mock_libvirt()
        vm = conn.lookupByName()
        import libvirt
        # mocking the libvirt kvm to shut down
        vm.info.return_value = [libvirt.VIR_DOMAIN_SHUTOFF]
        # Setting current snapshot of libvirt
        vm.hasCurrentSnapshot.return_value = 1
        repo = mock_repo()
        origin = repo.create_remote()
        from collections import namedtuple
        GitPullInfo = namedtuple('GitPullInfo', 'flags')
        pull_info = GitPullInfo(flags=0)
        origin.pull.return_value = [pull_info]
        cron()
        fork_url = ('https://github.com/{user}/{repo}.git').format(
                user=self.user.name, repo=g.github['repository'])
        repo.create_remote.assert_called_with('fork_2', url=fork_url)
        repo.create_head.assert_called_with('CI_Branch', origin.refs.master)

    @mock.patch('github.GitHub')
    @mock.patch('git.Repo')
    @mock.patch('libvirt.open')
    @mock.patch('shutil.rmtree')
    @mock.patch('mod_ci.controllers.open')
    @mock.patch('lxml.etree')
    def test_customize_tests_run_on_fork_if_remote_exist(self, mock_etree, mock_open,
                                                         mock_rmtree, mock_libvirt, mock_repo, mock_git):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux)
        import mod_ci.cron
        import mod_ci.controllers
        reload(mod_ci.cron)
        reload(mod_ci.controllers)
        from mod_ci.cron import cron
        conn = mock_libvirt()
        vm = conn.lookupByName()
        import libvirt
        # mocking the libvirt kvm to shut down
        vm.info.return_value = [libvirt.VIR_DOMAIN_SHUTOFF]
        # Setting current snapshot of libvirt
        vm.hasCurrentSnapshot.return_value = 1
        repo = mock_repo()
        origin = repo.remote()
        from collections import namedtuple
        Remotes = namedtuple('Remotes', 'name')
        repo.remotes = [Remotes(name='fork_2')]
        GitPullInfo = namedtuple('GitPullInfo', 'flags')
        pull_info = GitPullInfo(flags=0)
        origin.pull.return_value = [pull_info]
        cron()
        fork_url = ('https://github.com/{user}/{repo}.git').format(
                user=self.user.name, repo=g.github['repository'])
        repo.remote.assert_called_with('fork_2')

    @mock.patch('github.GitHub')
    @mock.patch('git.Repo')
    @mock.patch('libvirt.open')
    @mock.patch('shutil.rmtree')
    @mock.patch('mod_ci.controllers.open')
    @mock.patch('lxml.etree')
    def test_customize_tests_run_on_selected_regression_tests(self, mock_etree, mock_open,
                                                              mock_rmtree, mock_libvirt, mock_repo, mock_git):
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        import mod_ci.cron
        import mod_ci.controllers
        reload(mod_ci.cron)
        reload(mod_ci.controllers)
        from mod_ci.cron import cron
        conn = mock_libvirt()
        vm = conn.lookupByName()
        import libvirt
        vm.info.return_value = [libvirt.VIR_DOMAIN_SHUTOFF]
        vm.hasCurrentSnapshot.return_value = 1
        repo = mock_repo()
        origin = repo.remote()
        from collections import namedtuple
        Remotes = namedtuple('Remotes', 'name')
        repo.remotes = [Remotes(name='fork_2')]
        GitPullInfo = namedtuple('GitPullInfo', 'flags')
        pull_info = GitPullInfo(flags=0)
        origin.pull.return_value = [pull_info]
        single_test = mock_etree.Element('tests')
        mock_etree.Element.return_value = single_test
        cron()
        mock_etree.SubElement.assert_any_call(single_test, 'entry', id=str(2))
        assert (single_test, 'entry', str(1)) not in mock_etree.call_args_list

    def test_customizedtest_added_to_queue(self):
        regression_test = RegressionTest.query.filter(RegressionTest.id == 1).first()
        regression_test.active = False
        g.db.add(regression_test)
        g.db.commit()
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import queue_test
        queue_test(g.db, None, 'customizedcommitcheck', TestType.commit)
        test = Test.query.filter(Test.id == 3).first()
        customized_test = test.get_customized_regressiontests()
        self.assertIn(2, customized_test)
        self.assertNotIn(1, customized_test)

    @mock.patch('mailer.Mailer')
    def test_inform_mailing_list(self, mock_email):
        """
        Test the inform_mailing_list function
        """
        from mod_ci.controllers import inform_mailing_list
        from mailer import Mailer

        email = inform_mailing_list(mock_email, "matejmecka", "2430", "Some random string",
                                    "Lorem Ipsum sit dolor amet...")

        mock_email.send_simple_message.assert_called_once_with(
            {
                'text': '2430 - Some random string\n\n'
                '        Link to Issue: https://www.github.com/test_owner/test_repo/issues/matejmecka\n\n'
                '        Some random string(https://github.com/Some random string)\n\n\n'
                '        Lorem Ipsum sit dolor amet...\n        ',
                'subject': 'GitHub Issue #matejmecka', 'to': 'ccextractor-dev@googlegroups.com'
            }
        )

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_add_blocked_users(self, mock_request):
        """
        Check adding a user to block list.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/blocked_users', data=dict(user_id=1, comment="Bad user", add=True))
            self.assertNotEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 1).first(), None)
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User blocked successfully.")

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_add_blocked_users_wrong_id(self, mock_request):
        """
        Check adding invalid user id to block list.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/blocked_users', data=dict(user_id=0, comment="Bad user", add=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 0).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_add_blocked_users_empty_id(self, mock_request):
        """
        Check adding blank user id to block list.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/blocked_users', data=dict(comment="Bad user", add=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id == None).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_add_blocked_users_already_exists(self, mock_request):
        """
        Check adding existing blocked user again.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            blocked_user = BlockedUsers(1, "Bad user")
            g.db.add(blocked_user)
            g.db.commit()
            response = c.post(
                '/blocked_users', data=dict(user_id=1, comment="Bad user", add=True))
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User already blocked.")

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_remove_blocked_users(self, mock_request):
        """
        Check removing user from block list.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            blocked_user = BlockedUsers(1, "Bad user")
            g.db.add(blocked_user)
            g.db.commit()
            self.assertNotEqual(BlockedUsers.query.filter(BlockedUsers.comment == "Bad user").first(), None)
            response = c.post(
                '/blocked_users', data=dict(user_id=1, remove=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 1).first(), None)
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User removed successfully.")

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_remove_blocked_users_wrong_id(self, mock_request):
        """
        Check removing non existing id from block list.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/blocked_users', data=dict(user_id=7355608, remove=True))
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "No such user in Blacklist")

    @mock.patch('requests.get', side_effect=MockRequests)
    def test_remove_blocked_users_empty_id(self, mock_request):
        """
        Check removing blank user id from block list.
        """
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post(
                '/blocked_users', data=dict(remove=True))
            self.assertIn("GitHub User ID not filled in", str(response.data))
