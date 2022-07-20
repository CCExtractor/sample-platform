import json
from importlib import reload
from unittest import mock
from unittest.mock import MagicMock, Mock

from flask import g
from werkzeug.datastructures import Headers

from mod_auth.models import Role
from mod_ci.controllers import (Workflow_builds, get_info_for_pr_comment,
                                start_platforms)
from mod_ci.models import BlockedUsers
from mod_customized.models import CustomizedTest
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import (RegressionTest, RegressionTestOutput,
                                   RegressionTestOutputFiles)
from mod_test.models import Test, TestPlatform, TestResultFile, TestType
from tests.base import (BaseTestCase, generate_git_api_header,
                        generate_signature, mock_api_request_github)


class MockKVM:
    """Mock KVM object."""

    def __init__(self, name):
        self.name = name


class MockPlatform:
    """Mock platform object."""

    def __init__(self, platform):
        self.platform = platform
        self.value = 'platform'


class MockFork:
    """Mock fork object."""

    def __init__(self, *args, **kwargs):
        self.github = None


class MockTest:
    """Mock test object."""

    def __init__(self):
        self.id = 1
        self.test_type = TestType.commit
        self.fork = MockFork()
        self.platform = MockPlatform(TestPlatform.linux)


WSGI_ENVIRONMENT = {'REMOTE_ADDR': "192.30.252.0"}


class TestControllers(BaseTestCase):
    """Test CI-related controllers."""

    def test_comment_info_handles_variant_files_correctly(self):
        """Test that allowed variants of output files are handled correctly in PR comments.

        Make sure that the info used for the PR comment treats tests as successes if they got one of the allowed
        variants of the output file instead of the original version
        """
        VARIANT_HASH = 'abcdefgh_this_is_a_hash'
        TEST_RUN_ID = 1
        # Setting up the database
        # create regression test with an output file that has an allowed variant
        regression_test: RegressionTest = RegressionTest.query.filter(RegressionTest.id == 1).first()
        output_file: RegressionTestOutput = regression_test.output_files[0]
        variant_output_file = RegressionTestOutputFiles(VARIANT_HASH, output_file.id)
        output_file.multiple_files.append(variant_output_file)
        g.db.add(output_file)

        test_run_output_file: TestResultFile = TestResultFile.query.filter(
            TestResultFile.regression_test_output_id == output_file.id,
            TestResultFile.test_id == TEST_RUN_ID
        ).first()
        # mark the test as getting the variant as output, not the expected file
        test_run_output_file.got = VARIANT_HASH
        g.db.add(test_run_output_file)
        g.db.commit()

        # The actual test
        test: Test = Test.query.filter(Test.id == TEST_RUN_ID).first()
        comment_info = get_info_for_pr_comment(test.id)
        # we got a valid variant, so should still pass
        self.assertEqual(comment_info.failed_tests, [])
        for stats in comment_info.category_stats:
            # make sure the stats for the category confirm that everything passed too
            self.assertEqual(stats.success, stats.total)

    def test_comment_info_handles_invalid_variants_correctly(self):
        """Test that invalid variants of output files are handled correctly in PR comments.

        Make sure that regression tests are correctly marked as not passing when an invalid file hash is found
        """
        INVALID_VARIANT_HASH = 'this_is_an_invalid_hash'
        TEST_RUN_ID = 1
        test_result_file: TestResultFile = TestResultFile.query.filter(TestResultFile.test_id == TEST_RUN_ID).first()
        test_result_file.got = INVALID_VARIANT_HASH
        g.db.add(test_result_file)
        g.db.commit()

        test: Test = Test.query.filter(Test.id == TEST_RUN_ID).first()
        comment_info = get_info_for_pr_comment(test.id)
        # all categories that this regression test applies to should fail because of the invalid hash
        for category in test_result_file.regression_test.categories:
            stats = [stat for stat in comment_info.category_stats if stat.category == category.name]
            for stat in stats:
                self.assertEqual(stat.success, None)

    @mock.patch('mod_ci.controllers.Process')
    @mock.patch('run.log')
    def test_start_platform_none_specified(self, mock_log, mock_process):
        """Test that both platforms run with no platform value is passed."""
        start_platforms(mock.ANY, mock.ANY)

        self.assertEqual(2, mock_process.call_count)
        self.assertEqual(4, mock_log.info.call_count)

    @mock.patch('mod_ci.controllers.Process')
    @mock.patch('run.log')
    def test_start_platform_linux_specified(self, mock_log, mock_process):
        """Test that only linux platform runs."""
        start_platforms(mock.ANY, mock.ANY, platform=TestPlatform.linux)

        self.assertEqual(1, mock_process.call_count)
        self.assertEqual(2, mock_log.info.call_count)
        mock_log.info.assert_called_with("Linux VM process kicked off")

    @mock.patch('mod_ci.controllers.Process')
    @mock.patch('run.log')
    def test_start_platform_windows_specified(self, mock_log, mock_process):
        """Test that only windows platform runs."""
        start_platforms(mock.ANY, mock.ANY, platform=TestPlatform.windows)

        self.assertEqual(1, mock_process.call_count)
        self.assertEqual(2, mock_log.info.call_count)
        mock_log.info.assert_called_with("Windows VM process kicked off")

    @mock.patch('run.log')
    def test_kvm_processor_empty_kvm_name(self, mock_log):
        """Test that kvm processor fails with empty kvm name."""
        from mod_ci.controllers import kvm_processor

        resp = kvm_processor(mock.ANY, mock.ANY, "", mock.ANY, mock.ANY, mock.ANY)

        self.assertIsNone(resp)
        mock_log.info.assert_called_once()
        mock_log.critical.assert_called_once()

    @mock.patch('run.log')
    @mock.patch('mod_ci.controllers.MaintenanceMode')
    def test_kvm_processor_maintenance_mode(self, mock_maintenance, mock_log):
        """Test that kvm processor does not run when in mentainenace."""
        from mod_ci.controllers import kvm_processor

        class MockMaintence:
            def __init__(self):
                self.disabled = True

        mock_maintenance.query.filter.return_value.first.return_value = MockMaintence()

        resp = kvm_processor(mock.ANY, mock.ANY, "test", mock.ANY, mock.ANY, 1)

        self.assertIsNone(resp)
        mock_log.info.assert_called_once()
        mock_log.critical.assert_not_called()
        self.assertEqual(mock_log.debug.call_count, 2)

    @mock.patch('mod_ci.controllers.libvirt')
    @mock.patch('run.log')
    @mock.patch('mod_ci.controllers.MaintenanceMode')
    def test_kvm_processor_conn_fail(self, mock_maintenance, mock_log, mock_libvirt):
        """Test that kvm processor logs critically when conn cannot be established."""
        from mod_ci.controllers import kvm_processor

        mock_libvirt.open.return_value = None
        mock_maintenance.query.filter.return_value.first.return_value = None

        resp = kvm_processor(mock.ANY, mock.ANY, "test", mock.ANY, mock.ANY, 1)

        self.assertIsNone(resp)
        mock_log.info.assert_called_once()
        mock_log.critical.assert_called_once()
        self.assertEqual(mock_log.debug.call_count, 1)

    @mock.patch('run.log.critical')
    @mock.patch('mod_ci.controllers.save_xml_to_file')
    @mock.patch('builtins.open', new_callable=mock.mock_open())
    @mock.patch('mod_ci.controllers.g')
    def test_kvm_processor(self, mock_g, mock_open_file, mock_save_xml, mock_log_critical):
        """Test kvm_processor function."""
        import zipfile

        import libvirt
        import requests

        from mod_ci.controllers import Artifact_names, kvm_processor

        class mock_conn:
            def lookupByName(*args):
                class mock_vm:
                    def hasCurrentSnapshot(*args):
                        return 1

                    def info(*args):
                        return [libvirt.VIR_DOMAIN_SHUTOFF]

                    def snapshotCurrent(*args):
                        class snapshot:
                            def getName(*args):
                                return "test"
                        return snapshot

                    def revertToSnapshot(*args):
                        return 1

                    def create(*args):
                        return 1
                return mock_vm

            def close(*args):
                return

        def getFakeData(*args, **kwargs):
            if len(fakeData) == 0:
                return {'artifacts': []}
            r = fakeData[0]
            fakeData.pop(0)
            return r

        class mock_zip:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extractall(*args, **kwargs):
                return None

        libvirt.open = MagicMock(return_value=mock_conn)
        repo = MagicMock()
        zipfile.ZipFile = MagicMock(return_value=mock_zip())
        fakeData = [{'artifacts': [{'name': Artifact_names.windows,
                                    'archive_download_url': "test",
                                    'workflow_run': {'head_sha': '1978060bf7d2edd119736ba3ba88341f3bec3322'}}]},
                    {'artifacts': [{'name': Artifact_names.linux,
                                    'archive_download_url': "test",
                                    'workflow_run': {'head_sha': '1978060bf7d2edd119736ba3ba88341f3bec3323'}}]}]
        repo.actions.artifacts.return_value.get = getFakeData
        response = requests.models.Response()
        response.status_code = 200
        requests.get = MagicMock(return_value=response)
        kvm_processor(self.app, mock_g.db, "test", TestPlatform.linux, repo, None)
        mock_save_xml.assert_called()
        assert mock.call("Could not find an artifact for this commit") not in mock_log_critical.mock_calls

    @mock.patch('run.log.critical')
    @mock.patch('mod_ci.controllers.save_xml_to_file')
    @mock.patch('builtins.open', new_callable=mock.mock_open())
    @mock.patch('mod_ci.controllers.g')
    def test_kvm_processor_download_artifact_failed(self, mock_g, mock_open_file, mock_save_xml, mock_log_critical):
        """Test kvm_processor function when downloading the artifact fails."""
        import libvirt
        import requests

        from mod_ci.controllers import Artifact_names, kvm_processor

        class mock_conn:
            def lookupByName(*args):
                class mock_vm:
                    def hasCurrentSnapshot(*args):
                        return 1

                    def info(*args):
                        return [libvirt.VIR_DOMAIN_SHUTOFF]

                    def snapshotCurrent(*args):
                        class snapshot:
                            def getName(*args):
                                return "test"

                        return snapshot

                    def revertToSnapshot(*args):
                        return 1

                    def create(*args):
                        return 1

                return mock_vm

            def close(*args):
                return

        def getFakeData(*args, **kwargs):
            if len(fakeData) == 0:
                return {'artifacts': []}
            r = fakeData[0]
            fakeData.pop(0)
            return r

        libvirt.open = MagicMock(return_value=mock_conn)
        repo = MagicMock()
        fakeData = [{'artifacts': [{'name': Artifact_names.windows,
                                    'archive_download_url': "test",
                                    'workflow_run': {'head_sha': '1978060bf7d2edd119736ba3ba88341f3bec3322'}}]},
                    {'artifacts': [{'name': Artifact_names.windows,
                                    'archive_download_url': "test",
                                    'workflow_run': {'head_sha': '1978060bf7d2edd119736ba3ba88341f3bec3323'}}]}]
        repo.actions.artifacts.return_value.get = getFakeData
        response = requests.models.Response()
        response.status_code = 404
        requests.get = MagicMock(return_value=response)
        test = Test(TestPlatform.windows, TestType.commit, 1, "master", "1978060bf7d2edd119736ba3ba88341f3bec3323")
        g.db.add(test)
        g.db.commit()
        kvm_processor(self.app, mock_g.db, "test", TestPlatform.windows, repo, None)
        mock_save_xml.assert_called()
        mock_log_critical.assert_called_with(f"Could not fetch artifact, response code: {response.status_code}")

    @mock.patch('mod_ci.controllers.GeneralData')
    @mock.patch('mod_ci.controllers.g')
    def test_set_avg_time_first(self, mock_g, mock_gd):
        """Test setting average time for the first time."""
        from mod_ci.controllers import set_avg_time

        mock_gd.query.filter.return_value.first.return_value = None

        set_avg_time(TestPlatform.linux, "build", 100)

        mock_gd.query.filter.assert_called_once_with(mock_gd.key == 'avg_build_count_linux')
        self.assertEqual(mock_gd.call_count, 2)
        self.assertEqual(mock_g.db.add.call_count, 2)
        mock_g.db.commit.assert_called_once()

    @mock.patch('mod_ci.controllers.int')
    @mock.patch('mod_ci.controllers.GeneralData')
    @mock.patch('mod_ci.controllers.g')
    def test_set_avg_time(self, mock_g, mock_gd, mock_int):
        """Test setting average time for NOT first time."""
        from mod_ci.controllers import set_avg_time

        mock_int.return_value = 5

        set_avg_time(TestPlatform.windows, "prep", 100)

        mock_gd.query.filter.assert_called_with(mock_gd.key == 'avg_prep_count_windows')
        self.assertEqual(mock_gd.call_count, 0)
        self.assertEqual(mock_g.db.add.call_count, 0)
        mock_g.db.commit.assert_called_once()

    @mock.patch('github.GitHub')
    def test_comments_successfully_in_passed_pr_test(self, git_mock):
        """Check comments in passed PR test."""
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import Status, comment_pr

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
        """Check comments in failed PR test."""
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import Status, comment_pr
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        pull_request = repository.issues(1)
        message = ("<b>CCExtractor CI platform</b> finished running the "
                   "test files on <b>linux</b>. Below is a summary of the test results")
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
        """Test main repo checking."""
        from mod_ci.controllers import is_main_repo
        assert is_main_repo('random_user/random_repo') is False
        assert is_main_repo('test_owner/test_repo') is True

    @mock.patch('github.GitHub')
    @mock.patch('git.Repo')
    @mock.patch('libvirt.open')
    @mock.patch('shutil.rmtree')
    @mock.patch('mod_ci.controllers.open')
    @mock.patch('lxml.etree')
    def test_customize_tests_run_on_selected_regression_tests(self, mock_etree, mock_open,
                                                              mock_rmtree, mock_libvirt, mock_repo, mock_git):
        """Test customize tests running on the selected regression tests."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        import mod_ci.controllers
        import mod_ci.cron
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
        cron(testing=True)
        mock_etree.SubElement.assert_any_call(single_test, 'entry', id=str(2))
        assert (single_test, 'entry', str(1)) not in mock_etree.call_args_list

    def test_customizedtest_added_to_queue(self):
        """Test queue with a customized test addition."""
        regression_test = RegressionTest.query.filter(RegressionTest.id == 1).first()
        regression_test.active = False
        g.db.add(regression_test)
        g.db.commit()
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import add_test_entry, queue_test
        add_test_entry(g.db, None, 'customizedcommitcheck', TestType.commit)
        queue_test(None, 'customizedcommitcheck', TestType.commit, TestPlatform.linux)
        queue_test(None, 'customizedcommitcheck', TestType.commit, TestPlatform.windows)
        test = Test.query.filter(Test.id == 3).first()
        customized_test = test.get_customized_regressiontests()
        self.assertIn(2, customized_test)
        self.assertNotIn(1, customized_test)

    @mock.patch('mailer.Mailer')
    @mock.patch('mod_ci.controllers.get_html_issue_body')
    def test_inform_mailing_list(self, mock_get_html_issue_body, mock_email):
        """Test the inform_mailing_list function."""
        from mod_ci.controllers import inform_mailing_list

        mock_get_html_issue_body.return_value = """2430 - Some random string\n\n
                     Link to Issue: https://www.github.com/test_owner/test_repo/issues/matejmecka\n\n
                     Some random string(https://github.com/Some random string)\n\n\n
                     Lorem Ipsum sit dolor amet...\n        """
        inform_mailing_list(mock_email, "matejmecka", "2430", "Some random string", "Lorem Ipsum sit dolor amet...")

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
        """Test the get_html_issue_body for correct email formatting."""
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
        """Check adding a user to block list."""
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            c.post("/blocked_users", data=dict(user_id=1, comment="Bad user", add=True))
            self.assertNotEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 1).first(), None)
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User blocked successfully.")

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_add_blocked_users_wrong_id(self, mock_request):
        """Check adding invalid user id to block list."""
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post("/blocked_users", data=dict(user_id=0, comment="Bad user", add=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 0).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_add_blocked_users_empty_id(self, mock_request):
        """Check adding blank user id to block list."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post("/blocked_users", data=dict(comment="Bad user", add=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id.is_(None)).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_add_blocked_users_already_exists(self, mock_request):
        """Check adding existing blocked user again."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            blocked_user = BlockedUsers(1, "Bad user")
            g.db.add(blocked_user)
            g.db.commit()
            c.post("/blocked_users", data=dict(user_id=1, comment="Bad user", add=True))
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User already blocked.")

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_remove_blocked_users(self, mock_request):
        """Check removing user from block list."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            blocked_user = BlockedUsers(1, "Bad user")
            g.db.add(blocked_user)
            g.db.commit()
            self.assertNotEqual(BlockedUsers.query.filter(BlockedUsers.comment == "Bad user").first(), None)
            c.post("/blocked_users/1", data=dict(remove=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 1).first(), None)
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User removed successfully.")

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_remove_blocked_users_wrong_id(self, mock_request):
        """Check removing non existing id from block list."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            c.post("/blocked_users/7355608", data=dict(remove=True))
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "No such user in Blacklist")

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_remove_blocked_users_invalid_id(self, mock_request):
        """Check invalid id for the blocked_user url."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post("/blocked_users/hello", data=dict(remove=True))
            self.assertEqual(response.status_code, 404)

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_wrong_url(self, mock_request):
        """Check webhook fails when ping with wrong url."""
        with self.app.test_client() as c:
            # non GitHub ip address
            wsgi_environment = {'REMOTE_ADDR': '0.0.0.0'}
            data = {'action': "published",
                    'release': {'prerelease': False, 'published_at': "2018-05-30T20:18:44Z", 'tag_name': "0.0.1"}}
            response = c.post("/start-ci", environ_overrides=wsgi_environment,
                              data=json.dumps(data), headers=self.generate_header(data, "ping"))
            self.assertNotEqual(response.status_code, 200)

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_ping(self, mock_request):
        """Check webhook release update CCExtractor Version for ping."""
        with self.app.test_client() as c:
            data = {'action': 'published',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': '0.0.1'}}
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'ping'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'{"msg": "Hi!"}')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release(self, mock_request):
        """Check webhook release update CCExtractor Version for release."""
        with self.app.test_client() as c:
            # Full Release with version with 2.1
            data = {'action': 'published',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            # one of ip address from GitHub web hook
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'release'))
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertEqual(last_release.version, '2.1')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release_edited(self, mock_request):
        """Check webhook action "edited" updates the specified version."""
        from datetime import datetime
        with self.app.test_client() as c:
            release = CCExtractorVersion('2.1', '2018-05-30T20:18:44Z', 'abcdefgh')
            g.db.add(release)
            g.db.commit()
            # Full Release with version with 2.1
            data = {'action': 'edited',
                    'release': {'prerelease': False, 'published_at': '2018-06-30T20:18:44Z', 'tag_name': 'v2.1'}}
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'release'))
            last_release = CCExtractorVersion.query.filter_by(version='2.1').first()
            self.assertEqual(last_release.released,
                             datetime.strptime('2018-06-30T20:18:44Z', '%Y-%m-%dT%H:%M:%SZ').date())

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release_deleted(self, mock_request):
        """Check webhook action "delete" removes the specified version."""
        with self.app.test_client() as c:
            release = CCExtractorVersion('2.1', '2018-05-30T20:18:44Z', 'abcdefgh')
            g.db.add(release)
            g.db.commit()
            # Delete full release with version with 2.1
            data = {'action': 'deleted',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'release'))
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertNotEqual(last_release.version, '2.1')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_prerelease(self, mock_request):
        """Check webhook release update CCExtractor Version for prerelease."""
        with self.app.test_client() as c:
            # Full Release with version with 2.1
            data = {'action': 'prereleased',
                    'release': {'prerelease': True, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            sig = generate_signature(str(json.dumps(data)).encode('utf-8'), g.github['ci_key'])
            headers = generate_git_api_header('release', sig)
            last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
            # abcdefgh is the new commit after previous version defined in base.py
            last_commit.value = 'abcdefgh'
            g.db.commit()
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'ping'))
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertNotEqual(last_release.version, '2.1')

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_push_no_after(self, mock_request):
        """Test webhook triggered with push event without 'after' in payload."""
        data = {'no_after': 'test'}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'push'))

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('mod_ci.controllers.GitHub')
    @mock.patch('mod_ci.controllers.GeneralData')
    def test_webhook_push_valid(self, mock_gd, mock_github, mock_add_test_entry, mock_request):
        """Test webhook triggered with push event with valid data."""
        data = {'after': 'abcdefgh'}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'push'))

        mock_gd.query.filter.assert_called()
        mock_github.assert_called_once()
        mock_add_test_entry.assert_called_once()

    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_closed(self, mock_request, mock_test):
        """Test webhook triggered with pull_request event with closed action."""
        class MockTest:
            def __init__(self):
                self.id = 1
                self.progress = []

        mock_test.query.filter.return_value.all.return_value = [MockTest()]

        data = {'action': 'closed',
                'pull_request': {'number': '1234'}}
        # one of ip address from GitHub web hook
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        mock_test.query.filter.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.GitHub')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_opened_blocked(self, mock_request, mock_github, mock_blocked):
        """Test webhook triggered with pull_request event with opened action for blocked user."""
        class MockTest:
            def __init__(self):
                self.id = 1

        data = {'action': 'opened',
                'pull_request': {'number': '1234', 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'ERROR')
        mock_blocked.query.filter.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.GitHub')
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_opened(self, mock_request, mock_add_test_entry, mock_github, mock_blocked):
        """Test webhook triggered with pull_request event with opened action."""
        mock_blocked.query.filter.return_value.first.return_value = None

        data = {'action': 'opened',
                'pull_request': {'number': '1234', 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_blocked.query.filter.assert_called_once_with(mock_blocked.user_id == 'test')
        mock_add_test_entry.assert_called_once()

    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_requested_valid_workflow_name(self, mock_request, mock_schedule_test):
        """Test webhook triggered with workflow run event with action requested with a valid workflow name."""
        data = {'action': 'requested', 'workflow_run': {
            'name': 'Build CCExtractor on Linux', 'head_sha': 'abcd1234'}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_schedule_test.assert_called_once()

    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_linux(self, mock_request, mock_queue_test):
        """Test webhook triggered with workflow run event with action completed and status success on linux."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.LINUX, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        fakedata = {'workflow_runs': [
            {'head_sha': '1', 'status': 'completed',
                'conclusion': 'success', 'name': Workflow_builds.LINUX}
        ]}

        class MockedRepository:
            def statuses(self, *args):
                return None

            class actions:
                class runs:
                    def get(*args, **kwargs):
                        return fakedata

        class MockedGitHub:
            def repos(self, *args):
                return MockedRepository

        with self.app.test_client() as c:
            from github import GitHub
            GitHub.repos = Mock(return_value=MockedGitHub.repos)

            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_called_once()

    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_windows(self, mock_request, mock_queue_test):
        """Test webhook triggered with workflow run event with action completed and status success on windows."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        fakedata = {'workflow_runs': [
            {'head_sha': '1', 'status': 'completed',
                'conclusion': 'success', 'name': Workflow_builds.WINDOWS}
        ]}

        class MockedRepository:
            def statuses(self, *args):
                return None

            class actions:
                class runs:
                    def get(*args, **kwargs):
                        return fakedata

        class MockedGitHub:
            def repos(self, *args):
                return MockedRepository

        with self.app.test_client() as c:
            from github import GitHub
            GitHub.repos = Mock(return_value=MockedGitHub.repos)

            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_called_once()

    @mock.patch('mod_ci.controllers.deschedule_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_failure(self, mock_request, mock_deschedule_test):
        """Test webhook triggered with workflow run event with action completed and status failure."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.LINUX, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        fakedata = {'workflow_runs': [
            {'head_sha': '1', 'status': 'completed',
             'conclusion': 'failure', 'name': Workflow_builds.LINUX}
        ]}

        class MockedRepository:
            def statuses(self, *args):
                return None

            class actions:
                class runs:
                    def get(*args, **kwargs):
                        return fakedata

        class MockedGitHub:
            def repos(self, *args):
                return MockedRepository

        with self.app.test_client() as c:
            from github import GitHub
            GitHub.repos = Mock(return_value=MockedGitHub.repos)

            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
        mock_deschedule_test.assert_called()

    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_requested_invalid_workflow_name(self, mock_request, mock_schedule_test):
        """Test webhook triggered with workflow run event with an invalid action."""
        data = {'action': 'requested', 'workflow_run': {
            'name': 'Invalid', 'head_sha': 'abcd1234'}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
        mock_schedule_test.assert_not_called()
        self.assertEqual(response.data, b'{"msg": "EOL"}')

    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('mod_ci.controllers.deschedule_test')
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_with_unrecognized_event(self, mock_github, mock_schedule_test,
                                             mock_deschedule_test, mock_add_test_entry):
        """Test webhook with an unrecognised event triggered via GitHub Actions."""
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps({}), headers=self.generate_header({}, 'workflow_job'))
        mock_schedule_test.assert_not_called()
        mock_deschedule_test.assert_not_called()
        mock_add_test_entry.assert_not_called()
        self.assertEqual(response.data, b'{"msg": "EOL"}')

    @mock.patch('flask.g.log.warning')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_with_invalid_ci_signature(self, mock_github, mock_warning):
        """Test webhook if an invalid X-Hub-Signature is passed within headers."""
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps({}), headers=self.generate_header({}, 'workflow_run', "1"))
        mock_warning.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_pr_linux(self, mock_request, mock_queue_test, mock_blocked):
        """Test webhook triggered - workflow run event, action completed, status success for pull request on linux."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'pull_request',
                                 'name': Workflow_builds.LINUX, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        fakedata = {'workflow_runs': [
            {'head_sha': '1', 'status': 'completed',
             'conclusion': 'success', 'name': Workflow_builds.LINUX}
        ]}
        pull_requests = [{'head': {'sha': '1'}, 'user': {'id': 1}, 'number': '1'}]

        class MockedRepository:
            def statuses(self, *args):
                class gh_status:
                    def post(*args, **kwargs):
                        return None
                return gh_status

            class actions:
                class runs:
                    def get(*args, **kwargs):
                        return fakedata

            class pulls:
                def get(*args, **kwargs):
                    return pull_requests

        class MockedGitHub:
            def repos(self, *args):
                return MockedRepository
        with self.app.test_client() as c:
            from github import GitHub
            GitHub.repos = Mock(return_value=MockedGitHub.repos)
            mock_blocked.query.filter.return_value.first.return_value = None
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_called_once()
            mock_queue_test.reset_mock()

            mock_blocked.query.filter.return_value.first.return_value = 1
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_not_called()
            self.assertEqual(response.data, b'ERROR')

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_pr_windows(self, mock_request, mock_queue_test, mock_blocked):
        """Test webhook triggered - workflow run event, action completed, status success for pull request on windows."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'pull_request',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        fakedata = {'workflow_runs': [
            {'head_sha': '1', 'status': 'completed',
             'conclusion': 'success', 'name': Workflow_builds.WINDOWS}
        ]}
        pull_requests = [{'head': {'sha': '1'}, 'user': {'id': 1}, 'number': '1'}]

        class MockedRepository:
            def statuses(self, *args):
                class gh_status:
                    def post(*args, **kwargs):
                        return None
                return gh_status

            class actions:
                class runs:
                    def get(*args, **kwargs):
                        return fakedata

            class pulls:
                def get(*args, **kwargs):
                    return pull_requests

        class MockedGitHub:
            def repos(self, *args):
                return MockedRepository
        with self.app.test_client() as c:
            from github import GitHub
            GitHub.repos = Mock(return_value=MockedGitHub.repos)
            mock_blocked.query.filter.return_value.first.return_value = None
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_called_once()
            mock_queue_test.reset_mock()

            mock_blocked.query.filter.return_value.first.return_value = 1
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_not_called()
            self.assertEqual(response.data, b'ERROR')

    @mock.patch('mod_ci.controllers.deschedule_test')
    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_pr_updated(self, mock_request, mock_queue_test,
                                                                  mock_blocked, mock_deschedule_test):
        """Test webhook triggered - workflow run event, action completed, for a pull request whose head was updated."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'pull_request',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        fakedata = {'workflow_runs': [
            {'head_sha': '1', 'status': 'completed',
             'conclusion': 'success', 'name': Workflow_builds.WINDOWS}
        ]}
        pull_requests = [{'head': {'sha': '2'}, 'user': {'id': 1}, 'number': '1'}]

        class MockedRepository:
            def statuses(self, *args):
                class gh_status:
                    def post(*args, **kwargs):
                        return None
                return gh_status

            class actions:
                class runs:
                    def get(*args, **kwargs):
                        return fakedata

            class pulls:
                def get(*args, **kwargs):
                    return pull_requests

        class MockedGitHub:
            def repos(self, *args):
                return MockedRepository
        with self.app.test_client() as c:
            from github import GitHub
            GitHub.repos = Mock(return_value=MockedGitHub.repos)
            mock_blocked.query.filter.return_value.first.return_value = None
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_not_called()
            mock_deschedule_test.assert_called()

    def test_start_ci_with_a_get_request(self):
        """Test start_ci function with a request method other than post."""
        from mod_ci.controllers import start_ci
        response = start_ci()
        self.assertEqual(response, 'OK')

    @mock.patch('github.GitHub')
    @mock.patch('run.log.debug')
    def test_queue_test_with_pull_request(self, mock_debug, git_mock):
        """Check queue_test function with pull request as test type."""
        from mod_ci.controllers import add_test_entry, queue_test
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        add_test_entry(g.db, repository.statuses("1"), 'customizedcommitcheck', TestType.pull_request)
        mock_debug.assert_called_once_with('pull request test type detected')
        queue_test(repository.statuses("1"), 'customizedcommitcheck', TestType.pull_request, TestPlatform.linux)
        mock_debug.assert_called_with('Created tests, waiting for cron...')

    @mock.patch('run.log.critical')
    @mock.patch('run.log.debug')
    @mock.patch('github.GitHub')
    def test_schedule_test_function(self, git_mock, mock_debug, mock_critical):
        """Check the functioning of schedule_test function."""
        from mod_ci.controllers import schedule_test
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        schedule_test(repository.statuses(1), "1", TestType.commit)
        mock_debug.assert_not_called()
        schedule_test(None, None, TestType.commit)
        mock_debug.assert_not_called()
        schedule_test(repository.statuses(1), "1", TestType.pull_request)
        mock_debug.assert_called_once_with('pull request test type detected')

    @mock.patch('run.log.critical')
    @mock.patch('run.log.debug')
    @mock.patch('github.GitHub')
    def test_deschedule_test_function_linux(self, git_mock, mock_debug, mock_critical):
        """Check the functioning of deschedule_test function on linux platform."""
        from mod_ci.controllers import deschedule_test
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        deschedule_test(repository.statuses(1), TestPlatform.linux)
        mock_debug.assert_not_called()
        deschedule_test(None, TestPlatform.linux)
        mock_debug.assert_not_called()

    @mock.patch('run.log.critical')
    @mock.patch('run.log.debug')
    @mock.patch('github.GitHub')
    def test_deschedule_test_function_windows(self, git_mock, mock_debug, mock_critical):
        """Check the functioning of deschedule_test function on windows platform."""
        from mod_ci.controllers import deschedule_test
        repository = git_mock(access_token=g.github['bot_token']).repos(
            g.github['repository_owner'])(g.github['repository'])
        deschedule_test(repository.statuses(1), TestPlatform.windows)
        mock_debug.assert_not_called()
        deschedule_test(None, TestPlatform.windows)
        mock_debug.assert_not_called()

    @mock.patch('mod_ci.controllers.inform_mailing_list')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    @mock.patch('mod_ci.controllers.Issue')
    def test_webhook_issue_opened(self, mock_issue, mock_requests, mock_mailing):
        """Test webhook triggered with issues event with opened action."""
        data = {'action': 'opened',
                'issue': {'number': '1234', 'title': 'testTitle', 'body': 'testing', 'state': 'opened',
                          'user': {'login': 'testAuthor'}}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'issues'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_issue.query.filter(mock_issue.issue_id == '1234')
        mock_mailing.assert_called_once_with(mock.ANY, '1234', 'testTitle', 'testAuthor', 'testing')

    @mock.patch('run.log.critical')
    def test_github_api_error(self, mock_critical):
        """Test functions with GitHub API error."""
        from github import GitHub

        from mod_ci.controllers import deschedule_test, schedule_test
        schedule_test(GitHub('1').repos('1')('1').statuses('1'), 1, None)
        mock_critical.assert_called()
        mock_critical.reset_mock()
        deschedule_test(GitHub('1').repos('1')('1').statuses('1'), TestPlatform.linux)
        mock_critical.assert_called()

    @mock.patch('mod_ci.controllers.is_main_repo')
    @mock.patch('mod_ci.controllers.shutil')
    def test_update_build_badge(self, mock_shutil, mock_check_repo):
        """Test update_build_badge function."""
        from mod_ci.controllers import update_build_badge

        update_build_badge('pass', MockTest())

        mock_check_repo.assert_called_once_with(None)
        mock_shutil.copyfile.assert_called_once_with(mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    def test_progress_reporter_no_test(self, mock_test, mock_request):
        """Test progress_reporter with no test found."""
        from mod_ci.controllers import progress_reporter

        mock_test.query.filter.return_value.first.return_value = None

        expected_ret = "FAIL"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.progress_type_request')
    def test_progress_reporter_progress_type_fail(self, mock_progress_type, mock_test, mock_request):
        """Test progress_reporter with failing of request type progress."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'progress'}
        mock_progress_type.return_value = False

        expected_ret = "FAIL"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_progress_type.assert_called_once_with(mock.ANY, mock.ANY, 1, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.progress_type_request')
    def test_progress_reporter_progress_type(self, mock_progress_type, mock_test, mock_request):
        """Test progress_reporter with request type progress."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'progress'}
        mock_progress_type.return_value = "OK"

        expected_ret = "OK"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_progress_type.assert_called_once_with(mock.ANY, mock.ANY, 1, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.equality_type_request')
    def test_progress_reporter_equality_type(self, mock_equality_type, mock_test, mock_request):
        """Test progress_reporter with request type equality."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'equality'}
        mock_equality_type.return_value = "OK"

        expected_ret = "OK"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_equality_type.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.upload_log_type_request')
    def test_progress_reporter_logupload_type_empty(self, mock_logupload_type, mock_test, mock_request):
        """Test progress_reporter with request type logupload returning 'EMPTY'."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'logupload'}
        mock_logupload_type.return_value = False

        expected_ret = "EMPTY"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_logupload_type.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.upload_log_type_request')
    def test_progress_reporter_logupload_type(self, mock_logupload_type, mock_test, mock_request):
        """Test progress_reporter with request type logupload."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'logupload'}
        mock_logupload_type.return_value = "OK"

        expected_ret = "OK"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_logupload_type.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.upload_type_request')
    def test_progress_reporter_upload_type_empty(self, mock_upload_type, mock_test, mock_request):
        """Test progress_reporter with request type upload with returning 'EMPTY'."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'upload'}
        mock_upload_type.return_value = False

        expected_ret = "EMPTY"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_upload_type.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.upload_type_request')
    def test_progress_reporter_upload_type(self, mock_upload_type, mock_test, mock_request):
        """Test progress_reporter with request type upload."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'upload'}
        mock_upload_type.return_value = "OK"

        expected_ret = "OK"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_upload_type.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.request')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('mod_ci.controllers.finish_type_request')
    def test_progress_reporter_finish_type(self, mock_finish_type, mock_test, mock_request):
        """Test progress_reporter with request type finish."""
        from mod_ci.controllers import progress_reporter

        mock_test_obj = MagicMock()
        mock_test_obj.token = "token"
        mock_test.query.filter.return_value.first.return_value = mock_test_obj
        mock_request.form = {'type': 'finish'}
        mock_finish_type.return_value = "OK"

        expected_ret = "OK"

        ret_val = progress_reporter(1, "token")

        self.assertEqual(expected_ret, ret_val)
        mock_test.query.filter.assert_called_once()
        mock_request.assert_not_called()
        mock_finish_type.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY)

    @mock.patch('mod_ci.controllers.RegressionTestOutput')
    def test_equality_type_request_rto_none(self, mock_rto):
        """Test function equality_type_request when rto is None."""
        from mod_ci.controllers import equality_type_request

        mock_request = MagicMock()
        mock_request.form = {
            'test_id': 1,
            'test_file_id': 1
        }
        mock_rto.query.filter.return_value.first.return_value = None
        mock_log = MagicMock()

        equality_type_request(mock_log, 1, MagicMock(), mock_request)

        mock_log.debug.assert_called_once()
        mock_rto.query.filter.assert_called_once_with(mock_rto.id == 1)
        mock_log.info.assert_called_once()

    @mock.patch('mod_ci.controllers.g')
    @mock.patch('mod_ci.controllers.TestResultFile')
    @mock.patch('mod_ci.controllers.RegressionTestOutput')
    def test_equality_type_request_rto_exists(self, mock_rto, mock_result_file, mock_g):
        """Test function equality_type_request when rto exists."""
        from mod_ci.controllers import equality_type_request

        mock_request = MagicMock()
        mock_request.form = {
            'test_id': 1,
            'test_file_id': 1
        }
        mock_log = MagicMock()

        equality_type_request(mock_log, 1, MagicMock(), mock_request)

        mock_log.debug.assert_called_once()
        mock_rto.query.filter.assert_called_once_with(mock_rto.id == 1)
        mock_log.info.assert_not_called()
        mock_result_file.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY)
        mock_g.db.add.assert_called_once()
        mock_g.db.commit.assert_called_once()

    @mock.patch('mod_ci.controllers.secure_filename')
    def test_logupload_type_request_empty(self, mock_filename):
        """Test function logupload_type_request when filename is empty."""
        from mod_ci.controllers import upload_log_type_request

        mock_log = MagicMock()
        mock_request = MagicMock()
        mock_request.files = {'file': MagicMock()}
        mock_filename.return_value = ''

        self.assertFalse(upload_log_type_request(mock_log, 1, MagicMock(), MagicMock(), mock_request))

        mock_log.debug.assert_called_once()
        mock_filename.assert_called_once()

    @mock.patch('mod_ci.controllers.os')
    @mock.patch('mod_ci.controllers.secure_filename')
    def test_logupload_type_request(self, mock_filename, mock_os):
        """Test function logupload_type_request."""
        from mod_ci.controllers import upload_log_type_request

        mock_request = MagicMock()
        mock_log = MagicMock()
        mock_uploadfile = MagicMock()
        mock_request.files = {'file': mock_uploadfile}

        upload_log_type_request(mock_log, 1, MagicMock(), MagicMock(), mock_request)

        self.assertEqual(2, mock_log.debug.call_count)
        mock_filename.assert_called_once()
        self.assertEqual(2, mock_os.path.join.call_count)
        mock_uploadfile.save.assert_called_once()
        mock_os.rename.assert_called_once()

    @mock.patch('mod_ci.controllers.secure_filename')
    def test_upload_type_request_empty(self, mock_filename):
        """Test function upload_type_request when filename is empty."""
        from mod_ci.controllers import upload_type_request

        mock_request = MagicMock()
        mock_log = MagicMock()
        mock_request.files = {
            'file': MagicMock(),
            'test_id': 1,
            'test_file_id': 1
        }
        mock_filename.return_value = ''

        self.assertFalse(upload_type_request(mock_log, 1, MagicMock(), MagicMock(), mock_request))
        mock_log.debug.assert_called_once()
        mock_filename.assert_called_once()

    @mock.patch('mod_ci.controllers.hashlib')
    @mock.patch('mod_ci.controllers.TestResultFile')
    @mock.patch('mod_ci.controllers.RegressionTestOutput')
    @mock.patch('mod_ci.controllers.g')
    @mock.patch('mod_ci.controllers.iter')
    @mock.patch('mod_ci.controllers.open')
    @mock.patch('mod_ci.controllers.os')
    @mock.patch('mod_ci.controllers.secure_filename')
    def test_upload_type_request(self, mock_filename, mock_os, mock_open, mock_iter,
                                 mock_g, mock_rto, mock_result_file, mock_hashlib):
        """Test function upload_type_request."""
        from mod_ci.controllers import upload_type_request

        mock_upload_file = MagicMock()
        mock_log = MagicMock()
        mock_request = MagicMock()
        mock_request.files = {
            'file': mock_upload_file
        }
        mock_request.form = {
            'test_id': 1,
            'test_file_id': 1
        }
        mock_iter.return_value = ['chunk']
        mock_os.path.splitext.return_value = "a", "b"

        upload_type_request(mock_log, 1, MagicMock(), MagicMock(), mock_request)

        mock_log.debug.assert_called_once()
        mock_filename.assert_called_once()
        self.assertEqual(2, mock_os.path.join.call_count)
        mock_upload_file.save.assert_called_once()
        mock_open.assert_called_once_with(mock.ANY, "rb")
        mock_os.path.splitext.assert_called_once_with(mock.ANY)
        mock_os.rename.assert_called_once_with(mock.ANY, mock.ANY)
        mock_rto.query.filter.assert_called_once_with(mock_rto.id == 1)
        mock_result_file.assert_called_once_with(mock.ANY, 1, mock.ANY, mock.ANY, mock.ANY)
        mock_g.db.add.assert_called_once_with(mock.ANY)
        mock_g.db.commit.assert_called_once_with()
        mock_hashlib.sha256.assert_called_once_with()
        mock_iter.assert_called_once_with(mock.ANY, b"")

    @mock.patch('mod_ci.controllers.RegressionTest')
    @mock.patch('mod_ci.controllers.TestResult')
    @mock.patch('mod_ci.controllers.g')
    def test_finish_type_request(self, mock_g, mock_result, mock_rt):
        """Test function finish_type_request without exception occurring."""
        from mod_ci.controllers import finish_type_request

        mock_log = MagicMock()
        mock_request = MagicMock()
        mock_request.form = {
            'test_id': 1,
            'runTime': 1,
            'exitCode': 0
        }

        finish_type_request(mock_log, 1, MagicMock(), mock_request)

        mock_log.debug.assert_called_once()
        mock_rt.query.filter.assert_called_once_with(mock_rt.id == 1)
        mock_result.assert_called_once_with(mock.ANY, mock.ANY, 1, 0, mock.ANY)
        mock_g.db.add.assert_called_once_with(mock.ANY)
        mock_g.db.commit.assert_called_once_with()

    @mock.patch('mod_ci.controllers.RegressionTest')
    @mock.patch('mod_ci.controllers.TestResult')
    @mock.patch('mod_ci.controllers.g')
    def test_finish_type_request_with_error(self, mock_g, mock_result, mock_rt):
        """Test function finish_type_request with error in database commit."""
        from pymysql.err import IntegrityError

        from mod_ci.controllers import finish_type_request

        mock_log = MagicMock()
        mock_request = MagicMock()
        mock_request.form = {
            'test_id': 1,
            'runTime': 1,
            'exitCode': 0
        }
        mock_g.db.commit.side_effect = IntegrityError

        finish_type_request(mock_log, 1, MagicMock(), mock_request)

        mock_log.debug.assert_called_once()
        mock_rt.query.filter.assert_called_once_with(mock_rt.id == 1)
        mock_result.assert_called_once_with(mock.ANY, mock.ANY, 1, 0, mock.ANY)
        mock_g.db.add.assert_called_once_with(mock.ANY)
        mock_g.db.commit.assert_called_once_with()
        mock_log.error.assert_called_once()

    def test_in_maintenance_mode_ValueError(self):
        """Test in_maintenance_mode function with invalid platform."""
        with self.app.test_client() as c:
            response = c.post(
                '/maintenance/invalid')

        self.assertIsNotNone(response.data, b'ERROR')

    def test_in_maintenance_mode_linux(self):
        """Test in_maintenance_mode function with linux platform."""
        with self.app.test_client() as c:
            response = c.post(
                '/maintenance/linux')

        self.assertIsNotNone(response.data)

    def test_in_maintenance_mode_windows(self):
        """Test in_maintenance_mode function with windows platform."""
        with self.app.test_client() as c:
            response = c.post(
                '/maintenance/windows')

        self.assertIsNotNone(response.data)

    @staticmethod
    def generate_header(data, event, ci_key=None):
        """
        Generate headers for various REST methods.

        :param data: payload for the event
        :type data: dict
        :param event: the GitHub event to be triggered
        :type event: str
        """
        sig = generate_signature(str(json.dumps(data)).encode(
            'utf-8'), g.github['ci_key'] if ci_key is None else ci_key)
        headers = generate_git_api_header(event, sig)
        return headers
