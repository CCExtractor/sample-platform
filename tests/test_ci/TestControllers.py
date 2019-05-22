from mock import mock
from tests.base import BaseTestCase, mock_api_request_github
from mod_home.models import CCExtractorVersion, GeneralData
from mod_test.models import Test, TestPlatform, TestType
from mod_regression.models import RegressionTest
from mod_customized.models import CustomizedTest
from mod_ci.models import BlockedUsers
from mod_auth.models import Role
from werkzeug.datastructures import Headers
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
    def test_get_html_issue_body():
        """
        Test the get_html_issue_body for correct email formatting
        """
        from mod_ci.controllers import get_html_issue_body

        title = "[BUG] Test Title"
        author = "abcxyz"
        body = ("**strong_text**<br/>*em_text*\n\n"
                "- [list_with_link](www.example.com)\n"
                "- [X] checkbox_list with_code\n\n"
                "`code`\n\n"
                "> quote")
        issue_number = 1
        url = "www.example.com"

        expected_html_issue_body = ("[BUG] Test Title - abcxyz<br/>\n"
                                    "Link to Issue: www.example.com<br/>\n"
                                    """<a href="https://github.com/abcxyz">abcxyz</a><br/><br/>\n"""
                                    "<p><strong>strong_text</strong><br/><em>em_text</em></p>\n\n"
                                    "<ul>\n"
                                    """<li><a target="_blank" href="www.example.com">list_with_link</a></li>\n"""
                                    "<li>[X] checkbox_list with_code</li>\n"
                                    "</ul>\n\n"
                                    "<p><code>code</code></p>\n\n"
                                    "<blockquote>\n"
                                    "  <p>quote</p>\n"
                                    "</blockquote>\n")
        received_html_issue_body = get_html_issue_body(title, author, body, issue_number, url)

        assert received_html_issue_body == expected_html_issue_body, "wrong issue html [formatted] email returned"

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
            data = {'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': '0.0.1'}}
            sig = self.generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = self.generate_git_api_header('ping', sig)
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
            data = {'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': '0.0.1'}}
            sig = self.generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = self.generate_git_api_header('ping', sig)
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
            data = {'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = self.generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = self.generate_git_api_header('release', sig)
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
    def test_webhook_prerelease(self, mock_request):
        """
        Check webhook release update CCExtractor Version
        """
        import json
        with self.app.test_client() as c:
            # Full Release with version with 2.1
            data = {'release': {'prerelease': True, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = self.generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = self.generate_git_api_header('release', sig)
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

    @staticmethod
    def generate_signature(data, private_key):
        """
        Generate signature token of hook request

        :param data: Signature's data
        :param private_key: Signature's token
        """
        import hashlib
        import hmac
        algorithm = hashlib.__dict__.get('sha1')
        encoded_key = bytes(private_key, 'latin-1')
        mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
        return mac.hexdigest()

    @staticmethod
    def generate_git_api_header(event, sig):
        """
        Create header for Github API Request, based on header information from https://developer.github.com/webhooks/.

        :param event: Name of the event type that triggered the delivery.
        :param sig: The HMAC hex digest of the response body. The HMAC hex digest is generated
                    using the sha1 hash function and the secret as the HMAC key.
        """
        return Headers([
            ('X-GitHub-Event', event),
            ('X-Github-Delivery', '72d3162e-cc78-11e3-81ab-4c9367dc0958'),
            ('X-Hub-Signature', 'sha1={0}'.format(sig)),
            ('User-Agent', 'GitHub-Hookshot/044aadd'),
            ('Content-Type', 'application/json'),
            ('Content-Length', 6615)
        ])
