from importlib import reload

from flask import g
from mock import MagicMock, mock
from werkzeug.datastructures import Headers

from mod_auth.models import Role
from mod_ci.controllers import start_new_test, start_platform
from mod_ci.models import BlockedUsers
from mod_customized.models import CustomizedTest
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import RegressionTest
from mod_test.models import Test, TestPlatform, TestType
from tests.base import (BaseTestCase, generate_git_api_header,
                        generate_signature, mock_api_request_github)


class MockKVM:

    def __init__(self, name):
        self.name = name


class MockPlatform:

    def __init__(self, platform):
        self.platform = platform


class TestControllers(BaseTestCase):

    @mock.patch('mod_ci.controllers.Kvm')
    @mock.patch('run.log')
    def test_start_platform_no_match(self, mock_log, mock_kvm):
        """
        Test that error is logged when started with wrong KVM name.
        """
        mock_kvm.query.first.return_value = MockKVM("test")

        start_platform(mock.ANY, mock.ANY)

        mock_kvm.query.first.assert_called_once()
        mock_log.error.assert_called_once()

    @mock.patch('mod_ci.controllers.kvm_processor_linux')
    @mock.patch('mod_ci.controllers.Kvm')
    @mock.patch('run.log')
    def test_start_platform_linux_match(self, mock_log, mock_kvm, mock_linux_processor):
        """
        Test that linux processor is invoked when started with linux KVM name.
        """
        mock_kvm.query.first.return_value = MockKVM(self.app.config.get('KVM_LINUX_NAME', ''))

        start_platform(mock.ANY, mock.ANY)

        mock_kvm.query.first.assert_called_once()
        mock_linux_processor.assert_called_once_with(mock.ANY, mock.ANY, None)
        mock_log.error.assert_not_called()

    @mock.patch('mod_ci.controllers.kvm_processor_windows')
    @mock.patch('mod_ci.controllers.Kvm')
    @mock.patch('run.log')
    def test_start_platform_windows_match(self, mock_log, mock_kvm, mock_windows_processor):
        """
        Test that windows processor is invoked when started with windows KVM name.
        """
        mock_kvm.query.first.return_value = MockKVM(self.app.config.get('KVM_WINDOWS_NAME', ''))

        start_platform(mock.ANY, mock.ANY)

        mock_kvm.query.first.assert_called_once()
        mock_windows_processor.assert_called_once_with(mock.ANY, mock.ANY, None)
        mock_log.error.assert_not_called()

    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.and_')
    def test_start_new_test_none(self, mock_and, mock_test):
        """
        Test starting a new test when the test is None.
        """
        mock_test.query.filter.return_value.order_by.return_value.first.return_value = None
        mock_db = MagicMock()

        response = start_new_test(mock_db, mock.ANY, 0)

        mock_and.assert_called_once()
        self.assertEqual(response, None)

    @mock.patch('run.log')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.and_')
    def test_start_new_test_unsupported(self, mock_and, mock_test, mock_log):
        """
        Test starting a new test when the test is unsupported.
        """
        mock_test.query.filter.return_value.order_by.return_value.first.return_value = MagicMock()
        mock_db = MagicMock()

        response = start_new_test(mock_db, mock.ANY, 0)

        mock_and.assert_called_once()
        self.assertEqual(response, None)
        mock_log.error.assert_called_once()

    @mock.patch('run.log')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.and_')
    @mock.patch('mod_ci.controllers.kvm_processor_linux')
    def test_start_new_test_linux(self, mock_processor, mock_and, mock_test, mock_log):
        """
        Test starting a new test when the test is linux test.
        """
        mock_test.query.filter.return_value.order_by.return_value.first.return_value = MockPlatform(TestPlatform.linux)
        mock_db = MagicMock()

        response = start_new_test(mock_db, mock.ANY, 0)

        mock_and.assert_called_once()
        self.assertEqual(response, None)
        mock_processor.assert_called_once_with(mock_db, mock.ANY, 0)
        mock_log.error.assert_not_called()

    @mock.patch('run.log')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.and_')
    @mock.patch('mod_ci.controllers.kvm_processor_windows')
    def test_start_new_test_windows(self, mock_processor, mock_and, mock_test, mock_log):
        """
        Test starting a new test when the test is windows test.
        """
        mock_test.query.filter.return_value.order_by.return_value.first.return_value = MockPlatform(
            TestPlatform.windows)
        mock_db = MagicMock()

        response = start_new_test(mock_db, mock.ANY, 0)

        mock_and.assert_called_once()
        self.assertEqual(response, None)
        mock_processor.assert_called_once_with(mock_db, mock.ANY, 0)
        mock_log.error.assert_not_called()

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
        fork_url = 'https://github.com/{user}/{repo}.git'.format(user=self.user.name, repo=g.github['repository'])
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
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.tester)
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
    @mock.patch('mod_ci.controllers.get_html_issue_body')
    def test_inform_mailing_list(self, mock_get_html_issue_body, mock_email):
        """
        Test the inform_mailing_list function
        """
        from mod_ci.controllers import inform_mailing_list

        mock_get_html_issue_body.return_value = """2430 - Some random string\n\n
                     Link to Issue: https://www.github.com/test_owner/test_repo/issues/matejmecka\n\n
                     Some random string(https://github.com/Some random string)\n\n\n
                     Lorem Ipsum sit dolor amet...\n        """
        email = inform_mailing_list(mock_email, "matejmecka", "2430", "Some random string",
                                    "Lorem Ipsum sit dolor amet...")

        mock_email.send_simple_message.assert_called_once_with(
            {
                'to': 'ccextractor-dev@googlegroups.com',
                'subject': 'GitHub Issue #matejmecka',
                'html': """2430 - Some random string\n\n
                     Link to Issue: https://www.github.com/test_owner/test_repo/issues/matejmecka\n\n
                     Some random string(https://github.com/Some random string)\n\n\n
                     Lorem Ipsum sit dolor amet...\n        """
            }
        )
        mock_get_html_issue_body.assert_called_once()

    @staticmethod
    @mock.patch('mod_ci.controllers.markdown')
    def test_get_html_issue_body(mock_markdown):
        """
        Test the get_html_issue_body for correct email formatting
        """
        from mod_ci.controllers import get_html_issue_body

        title = "[BUG] Test Title"
        author = "abcxyz"
        body = "i'm issue body"
        issue_number = 1
        url = "www.example.com"

        get_html_issue_body(title, author, body, issue_number, url)

        mock_markdown.assert_called_once_with(body, extras=["target-blank-links", "task_list", "code-friendly"])

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id.is_(None)).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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

    @mock.patch('requests.get', side_effect=mock_api_request_github)
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

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_wrong_url(self, mock_request):
        """
        Check webhook fails when ping with wrong url
        """
        import json
        with self.app.test_client() as c:
            data = {'action': 'published',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': '0.0.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('ping', sig)
            # non github ip address
            wsgi_environment = {'REMOTE_ADDR': '0.0.0.0'}
            response = c.post(
                '/start-ci', environ_overrides=wsgi_environment,
                data=json.dumps(data), headers=headers)
            self.assertNotEqual(response.status_code, 200)

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_ping(self, mock_request):
        """
        Check webhook release update CCExtractor Version
        """
        import json
        with self.app.test_client() as c:
            data = {'action': 'published',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': '0.0.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('ping', sig)
            # one of ip address from github webhook
            wsgi_environment = {'REMOTE_ADDR': '192.30.252.0'}
            response = c.post(
                '/start-ci', environ_overrides=wsgi_environment,
                data=json.dumps(data), headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'{"msg": "Hi!"}')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release(self, mock_request):
        """
        Check webhook release update CCExtractor Version
        """
        import json
        with self.app.test_client() as c:
            # Full Release with version with 2.1
            data = {'action': 'published',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('release', sig)
            # one of ip address from github webhook
            wsgi_environment = {'REMOTE_ADDR': '192.30.252.0'}
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=wsgi_environment,
                data=json.dumps(data), headers=headers)
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertEqual(last_release.version, '2.1')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release_edited(self, mock_request):
        """
        Check webhook action "edited" updates the specified version.
        """
        import json
        from datetime import datetime
        with self.app.test_client() as c:
            release = CCExtractorVersion('2.1', '2018-05-30T20:18:44Z', 'abcdefgh')
            g.db.add(release)
            g.db.commit()
            # Full Release with version with 2.1
            data = {'action': 'edited',
                    'release': {'prerelease': False, 'published_at': '2018-06-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('release', sig)
            # one of ip address from github webhook
            wsgi_environment = {'REMOTE_ADDR': '192.30.252.0'}
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=wsgi_environment,
                data=json.dumps(data), headers=headers)
            last_release = CCExtractorVersion.query.filter_by(version='2.1').first()
            self.assertEqual(last_release.released,
                             datetime.strptime('2018-06-30T20:18:44Z', '%Y-%m-%dT%H:%M:%SZ').date())

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release_deleted(self, mock_request):
        """
        Check    def add_CCExversion(self, c, version='v2.1', commit='abcdefgh', released='2018-05-30T20:18:44Z'):
        """
        import json
        with self.app.test_client() as c:
            release = CCExtractorVersion('2.1', '2018-05-30T20:18:44Z', 'abcdefgh')
            g.db.add(release)
            g.db.commit()
            # Delete full release with version with 2.1
            data = {'action': 'deleted',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('release', sig)
            # one of ip address from github webhook
            wsgi_environment = {'REMOTE_ADDR': '192.30.252.0'}
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=wsgi_environment,
                data=json.dumps(data), headers=headers)
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertNotEqual(last_release.version, '2.1')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_prerelease(self, mock_request):
        """
        Check webhook release update CCExtractor Version
        """
        import json
        with self.app.test_client() as c:
            # Full Release with version with 2.1
            data = {'action': 'prereleased',
                    'release': {'prerelease': True, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('release', sig)
            # one of ip address from github webhook
            wsgi_environment = {'REMOTE_ADDR': '192.30.252.0'}
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=wsgi_environment,
                data=json.dumps(data), headers=headers)
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertNotEqual(last_release.version, '2.1')
