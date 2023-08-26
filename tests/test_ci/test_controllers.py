import json
from importlib import reload
from unittest import mock
from unittest.mock import MagicMock

from flask import g

from mod_auth.models import Role
from mod_ci.controllers import (Workflow_builds, get_info_for_pr_comment,
                                progress_type_request, start_platforms)
from mod_ci.models import BlockedUsers
from mod_customized.models import CustomizedTest
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import (RegressionTest, RegressionTestOutput,
                                   RegressionTestOutputFiles)
from mod_test.models import Test, TestPlatform, TestResultFile, TestType
from tests.base import (BaseTestCase, MockResponse, generate_git_api_header,
                        generate_signature, mock_api_request_github)


class MockGcpInstance:
    """Mock GcpInstance object."""

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

    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.delete_expired_instances')
    @mock.patch('mod_ci.controllers.Process')
    @mock.patch('run.log')
    def test_start_platform_none_specified(self, mock_log, mock_process,
                                           mock_delete_expired_instances, mock_get_compute_service_object):
        """Test that both platforms run when no platform value is passed."""
        start_platforms(mock.ANY, 1)

        mock_delete_expired_instances.assert_called_once()
        mock_get_compute_service_object.assert_called_once()
        self.assertEqual(2, mock_process.call_count)
        self.assertEqual(4, mock_log.info.call_count)

    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.delete_expired_instances')
    @mock.patch('mod_ci.controllers.Process')
    @mock.patch('run.log')
    def test_start_platform_linux_specified(self, mock_log, mock_process,
                                            mock_delete_expired_instances, mock_get_compute_service_object):
        """Test that only Linux platform runs when platform is specified as Linux."""
        start_platforms(mock.ANY, platform=TestPlatform.linux)

        self.assertEqual(1, mock_process.call_count)
        self.assertEqual(2, mock_log.info.call_count)
        mock_log.info.assert_called_with("Linux GCP instances process kicked off")
        mock_delete_expired_instances.assert_called_once()
        mock_get_compute_service_object.assert_called_once()

    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.delete_expired_instances')
    @mock.patch('mod_ci.controllers.Process')
    @mock.patch('run.log')
    def test_start_platform_windows_specified(self, mock_log, mock_process,
                                              mock_delete_expired_instances, mock_get_compute_service_object):
        """Test that only Windows platform runs when platform is specified as Windows."""
        start_platforms(mock.ANY, platform=TestPlatform.windows)

        self.assertEqual(1, mock_process.call_count)
        self.assertEqual(2, mock_log.info.call_count)
        mock_log.info.assert_called_with("Windows GCP instances process kicked off")
        mock_delete_expired_instances.assert_called_once()
        mock_get_compute_service_object.assert_called_once()

    @mock.patch('run.log')
    @mock.patch('mod_ci.controllers.MaintenanceMode')
    def test_gcp_instance_maintenance_mode(self, mock_maintenance, mock_log):
        """Test that gcp instance does not run when in maintainenace."""
        from mod_ci.controllers import gcp_instance

        class MockMaintenance:
            def __init__(self):
                self.disabled = True

        mock_maintenance.query.filter.return_value.first.return_value = MockMaintenance()

        resp = gcp_instance(mock.ANY, mock.ANY, "test", mock.ANY, 1)

        self.assertIsNone(resp)
        mock_log.info.assert_called_once()
        mock_log.critical.assert_not_called()
        self.assertEqual(mock_log.debug.call_count, 2)

    @mock.patch('github.Github')
    @mock.patch('mod_ci.controllers.delete_expired_instances')
    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.gcp_instance')
    def test_cron_job_testing_false(self, mock_gcp_instance, mock_get_compute_service_object,
                                    mock_delete_expired_instances, mock_github):
        """Test working of cron function when testing is disabled."""
        from mod_ci.cron import cron
        mock_delete_expired_instances.reset_mock()
        mock_get_compute_service_object.reset_mock()
        cron()
        self.assertEqual(mock_delete_expired_instances.call_count, 1)
        self.assertEqual(mock_get_compute_service_object.call_count, 1)

    @mock.patch('github.Github')
    @mock.patch('mod_ci.controllers.delete_expired_instances')
    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.gcp_instance')
    def test_cron_job_testing_true(self, mock_gcp_instance, mock_get_compute_service_object,
                                   mock_delete_expired_instances, mock_github):
        """Test working of cron function when testing is enabled."""
        from mod_ci.cron import cron
        mock_delete_expired_instances.reset_mock()
        mock_get_compute_service_object.reset_mock()
        cron(testing=True)
        mock_delete_expired_instances.assert_not_called()
        mock_get_compute_service_object.assert_not_called()

    @mock.patch('mod_ci.controllers.wait_for_operation')
    @mock.patch('mod_ci.controllers.create_instance')
    @mock.patch('builtins.open', new_callable=mock.mock_open())
    @mock.patch('mod_ci.controllers.g')
    def test_start_test(self, mock_g, mock_open_file, mock_create_instance, mock_wait_for_operation):
        """Test start_test function."""
        import zipfile

        import requests
        from github.Artifact import Artifact

        from mod_ci.controllers import Artifact_names, start_test
        test = Test.query.first()
        repository = MagicMock()

        artifact1 = MagicMock(Artifact)
        artifact1.name = Artifact_names.windows
        artifact1.workflow_run.head_sha = '1978060bf7d2edd119736ba3ba88341f3bec3322'

        artifact2 = MagicMock(Artifact)
        artifact2.name = Artifact_names.linux
        artifact2.workflow_run.head_sha = '1978060bf7d2edd119736ba3ba88341f3bec3323'

        class mock_zip:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extractall(*args, **kwargs):
                return None
        repository.get_artifacts.return_value = [artifact1, artifact2]
        response = requests.models.Response()
        response.status_code = 200
        requests.get = MagicMock(return_value=response)
        zipfile.ZipFile = MagicMock(return_value=mock_zip())
        customized_test = CustomizedTest(1, 1)
        g.db.add(customized_test)
        g.db.commit()
        start_test(mock.ANY, self.app, mock_g.db, repository, test, mock.ANY)
        mock_create_instance.assert_called_once()
        mock_wait_for_operation.assert_called_once()

    @mock.patch('mod_ci.controllers.start_test')
    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.g')
    def test_gcp_instance(self, mock_g, mock_get_compute_service_object, mock_start_test):
        """Test gcp_instance function."""
        from mod_ci.controllers import gcp_instance

        # Making a sample test invalid
        test = Test.query.get(1)
        test.pr_nr = 0
        g.db.commit()
        gcp_instance(self.app, mock_g.db, TestPlatform.linux, mock.ANY, None)

        mock_start_test.assert_called_once()
        mock_get_compute_service_object.assert_called_once()

    def test_get_compute_service_object(self):
        """Test get_compute_service_object function."""
        import googleapiclient
        from google.oauth2 import service_account

        from mod_ci.controllers import get_compute_service_object
        service_account.Credentials.from_service_account_file = MagicMock()
        compute = get_compute_service_object()
        self.assertEqual(type(compute), googleapiclient.discovery.Resource)

    @mock.patch('builtins.open', new_callable=mock.mock_open())
    def test_create_instance_linux(self, mock_open_file):
        """Test create_instance function for linux platform."""
        from mod_ci.controllers import create_instance
        compute = MagicMock()
        instance = create_instance(compute, "test", "test", Test.query.get(1), "")

        mock_open_file.assert_called()
        self.assertEqual(str(type(instance)), str(MagicMock))

    @mock.patch('builtins.open', new_callable=mock.mock_open())
    def test_create_instance_windows(self, mock_open_file):
        """Test create_instance function for windows platform."""
        from mod_ci.controllers import create_instance
        compute = MagicMock()
        new_test = Test(TestPlatform.windows, TestType.commit, 1, "test", "test")
        g.db.add(new_test)
        g.db.commit()
        instance = create_instance(compute, "test", "test", new_test, "")

        mock_open_file.assert_called()
        self.assertEqual(str(type(instance)), str(MagicMock))

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

    @mock.patch('github.Github')
    def test_comments_successfully_in_passed_pr_test(self, mock_github):
        """Check comments in passed PR test."""
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from github.IssueComment import IssueComment

        from mod_ci.controllers import Status, comment_pr

        repository = mock_github(g.github['bot_token']).get_repo(
            f"{g.github['repository_owner']}/{g.github['repository']}")
        pull_request = repository.get_pull(number=1)
        mock_github(g.github['bot_token']).get_user().login = 'test-bot'

        comment1 = MagicMock(IssueComment)
        comment1.user.login = 'invalid'

        comment2 = MagicMock(IssueComment)
        comment2.user.login = 'test-bot'
        comment2.body = 'linux test passed'

        # Delete old bot comments and create a new comment
        pull_request.get_issue_comments.return_value = [comment1, comment2]
        comment_pr(1, Status.SUCCESS, 1, 'linux')
        mock_github.assert_called_with(g.github['bot_token'])
        mock_github(g.github['bot_token']).get_repo.assert_called_with(
            f"{g.github['repository_owner']}/{g.github['repository']}")

        repository.get_pull.assert_called_with(number=1)
        pull_request.get_issue_comments.assert_called_once()
        comment1.delete.assert_not_called()
        comment2.delete.assert_called_once()

        args, kwargs = pull_request.create_issue_comment.call_args
        message = kwargs['body']
        if "passed" not in message:
            assert False, "Message not Correct"

    @mock.patch('github.Github')
    def test_comments_successfuly_in_failed_pr_test(self, mock_github):
        """Check comments in failed PR test."""
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from github.IssueComment import IssueComment

        from mod_ci.controllers import Status, comment_pr
        pull_request = mock_github.return_value.get_repo.return_value.get_pull(number=1)
        message = ("<b>CCExtractor CI platform</b> finished running the "
                   "test files on <b>linux</b>. Below is a summary of the test results")
        pull_request.get_issue_comments.return_value = [MagicMock(IssueComment)]
        # Comment on test that fails some/all regression tests
        comment_pr(2, Status.FAILURE, 1, 'linux')
        pull_request.get_issue_comments.assert_called_with()
        args, kwargs = pull_request.create_issue_comment.call_args
        message = kwargs['body']
        reg_tests = RegressionTest.query.all()
        flag = False
        for reg_test in reg_tests:
            if reg_test.command not in message:
                flag = True
        if flag:
            assert False, "Message not Correct"

    def test_get_running_instances(self):
        """Test get_running_instances function."""
        from mod_ci.controllers import get_running_instances
        result = get_running_instances(MagicMock(), "test", "test")
        self.assertEqual(result, [])

    def test_check_main_repo_returns_in_false_url(self):
        """Test main repo checking."""
        from mod_ci.controllers import is_main_repo
        assert is_main_repo('random_user/random_repo') is False
        assert is_main_repo('test_owner/test_repo') is True

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.update_status_on_github')
    @mock.patch('mod_ci.controllers.get_running_instances')
    def test_delete_expired_instances(self, mock_get_running_instances, mock_update_github_status, mock_repo):
        """Test working of delete_expired_instances function."""
        from datetime import datetime, timedelta, timezone

        from mod_ci.controllers import delete_expired_instances

        current_timestamp = datetime.now(timezone.utc)
        expired_instance_time = current_timestamp - timedelta(minutes=150)
        mock_get_running_instances.return_value = [{
            'name': 'windows-1',
            'creationTimestamp': current_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
        }, {
            'name': 'linux-2',
            'creationTimestamp': expired_instance_time.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
        }, {
            'name': 'osx-3',
            'creationTimestamp': current_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
        }]
        compute = MagicMock()
        pendingOperations = [
            {'status': "DONE"},
            {'status': "PENDING"}
        ]
        compute.zoneOperations.return_value.get.return_value.execute = pendingOperations.pop
        delete_expired_instances(compute, 120, 'a', 'a')
        mock_get_running_instances.assert_called_once()
        mock_update_github_status.assert_called_once()

    def test_customizedtest_added_to_queue(self):
        """Test queue with a customized test addition."""
        regression_test = RegressionTest.query.filter(RegressionTest.id == 1).first()
        regression_test.active = False
        g.db.add(regression_test)
        g.db.commit()
        import mod_ci.controllers
        reload(mod_ci.controllers)
        from mod_ci.controllers import add_test_entry, queue_test
        add_test_entry(g.db, 'customizedcommitcheck', TestType.commit)
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

    def test_add_blocked_users(self):
        """Check adding a user to block list."""
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            c.post("/blocked_users", data=dict(user_id=1, comment="Bad user", add=True))
            self.assertNotEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 1).first(), None)
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "User blocked successfully.")

    def test_add_blocked_users_wrong_id(self):
        """Check adding invalid user id to block list."""
        self.create_user_with_role(self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post("/blocked_users", data=dict(user_id=0, comment="Bad user", add=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id == 0).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    def test_add_blocked_users_empty_id(self):
        """Check adding blank user id to block list."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.post("/blocked_users", data=dict(comment="Bad user", add=True))
            self.assertEqual(BlockedUsers.query.filter(BlockedUsers.user_id.is_(None)).first(), None)
            self.assertIn("GitHub User ID not filled in", str(response.data))

    @mock.patch('requests.get', return_value=MockResponse({"login": "test"}, 200))
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

    def test_remove_blocked_users(self):
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

    def test_remove_blocked_users_wrong_id(self):
        """Check removing non existing id from block list."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.admin)
        with self.app.test_client() as c:
            c.post("/account/login", data=self.create_login_form_data(self.user.email, self.user.password))
            c.post("/blocked_users/7355608", data=dict(remove=True))
            with c.session_transaction() as session:
                flash_message = dict(session['_flashes']).get('message')
            self.assertEqual(flash_message, "No such user in Blacklist")

    def test_remove_blocked_users_invalid_id(self):
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

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release(self, mock_request, mock_repo):
        """Check webhook release update CCExtractor Version for release."""
        last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
        # abcdefgh is the new commit after previous version defined in base.py
        last_commit.value = 'abcdefgh'
        g.db.commit()
        with self.app.test_client() as c:
            # Full Release with version with 2.1
            data = {'action': 'published',
                    'release': {'prerelease': False, 'published_at': '2018-05-30T20:18:44Z', 'tag_name': 'v2.1'}}
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'release'))
            last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
            self.assertEqual(last_release.version, '2.1')

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release_edited(self, mock_request, mock_repo):
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

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_release_deleted(self, mock_request, mock_repo):
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

    def test_webhook_prerelease(self):
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

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    @mock.patch('run.log')
    def test_webhook_push_no_after(self, mock_log, mock_request, mock_repo):
        """Test webhook triggered with push event without 'after' in payload."""
        data = {'no_after': 'test'}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'push'))

        mock_log.debug.assert_called_with("push event detected")
        mock_log.warning.assert_any_call("Unknown push type! Dumping payload for analysis")

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('mod_ci.controllers.GeneralData')
    def test_webhook_push_valid(self, mock_gd, mock_add_test_entry, mock_request, mock_repo):
        """Test webhook triggered with push event with valid data."""
        data = {'after': 'abcdefgh', 'ref': 'refs/heads/master'}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'push'))

        mock_gd.query.filter.assert_called()
        mock_add_test_entry.assert_called_once()

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_closed(self, mock_requests, mock_test, mock_repo):
        """Test webhook triggered with pull_request event with closed action."""
        platform_name = "platform"

        class MockTest:
            def __init__(self):
                self.id = 1
                self.progress = []
                self.platform = MockPlatform(platform_name)
                self.commit = "test"

        mock_test.query.filter.return_value.all.return_value = [MockTest()]
        mock_repo.return_value.get_commit.return_value.get_statuses.return_value = [
            {"context": f"CI - {platform_name}"}]

        data = {'action': 'closed',
                'pull_request': {'number': 1234, 'draft': False}}
        # one of ip address from GitHub web hook
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        mock_test.query.filter.assert_called_once()

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.Test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_converted_to_draft(self, mock_requests, mock_test, mock_repo):
        """Test webhook triggered with pull_request event with converted_to_draft action."""
        platform_name = "platform"

        class MockTest:
            def __init__(self):
                self.id = 1
                self.progress = []
                self.platform = MockPlatform(platform_name)
                self.commit = "test"

        mock_test.query.filter.return_value.all.return_value = [MockTest()]
        mock_repo.return_value.get_commit.return_value.get_statuses.return_value = [
            {"context": f"CI - {platform_name}"}]

        data = {'action': 'converted_to_draft',
                'pull_request': {'number': 1234, 'draft': False}}
        # one of ip address from GitHub web hook
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        mock_test.query.filter.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_opened_blocked(self, mock_request, mock_repo, mock_blocked):
        """Test webhook triggered with pull_request event with opened action for blocked user."""
        data = {'action': 'opened',
                'pull_request': {'number': '1234', 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}, 'draft': False}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'ERROR')
        mock_blocked.query.filter.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_opened(self, mock_request, mock_add_test_entry, mock_repo, mock_blocked):
        """Test webhook triggered with pull_request event with opened action."""
        mock_blocked.query.filter.return_value.first.return_value = None

        data = {'action': 'opened',
                'pull_request': {'number': 1234, 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}, 'draft': False}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_blocked.query.filter.assert_called_once_with(mock_blocked.user_id == 'test')
        mock_add_test_entry.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_ready_for_review(self, mock_request, mock_add_test_entry, mock_repo, mock_blocked):
        """Test webhook triggered with pull_request event with ready_for_review action."""
        mock_blocked.query.filter.return_value.first.return_value = None

        data = {'action': 'ready_for_review',
                'pull_request': {'number': 1234, 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}, 'draft': False}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_blocked.query.filter.assert_called_once_with(mock_blocked.user_id == 'test')
        mock_add_test_entry.assert_called_once()

    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_invalid_action(self, mock_request, mock_repo, mock_blocked):
        """Test webhook triggered with pull_request event with an invalid action."""
        data = {'action': 'invalid',
                'pull_request': {'number': 1234, 'draft': False, 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_blocked.query.filter.assert_not_called()

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_opened_draft(self, mock_request, mock_repo):
        """Test webhook triggered with pull_request event with open action, marked as draft."""
        data = {'action': 'opened',
                'pull_request': {'number': 1234, 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}, 'draft': True}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_pr_synchronize_draft(self, mock_request, mock_repo):
        """Test webhook triggered with pull_request event with synchronize action, marked as draft."""
        data = {'action': 'synchronize',
                'pull_request': {'number': 1234, 'head': {'sha': 'abcd1234'}, 'user': {'id': 'test'}, 'draft': True}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'pull_request'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_requested_valid_workflow_name(self, mock_requests, mock_schedule_test, mock_repo):
        """Test webhook triggered with workflow run event with action requested with a valid workflow name."""
        data = {'action': 'requested', 'workflow_run': {
            'name': Workflow_builds.LINUX, 'head_sha': 'abcd1234'}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_schedule_test.assert_called_once()

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_linux(self, mock_request, mock_queue_test, mock_repo):
        """Test webhook triggered with workflow run event with action completed and status success on linux."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.LINUX, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.LINUX
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'completed'
        workflow_run1.conclusion = 'success'
        workflow_run1.name = Workflow_builds.LINUX

        workflow_run2 = MagicMock(WorkflowRun)
        workflow_run2.head_sha = '2'

        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run2, workflow_run1]

        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_called_once()

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_windows(self, mock_request, mock_queue_test, mock_repo):
        """Test webhook triggered with workflow run event with action completed and status success on windows."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'completed'
        workflow_run1.conclusion = 'success'
        workflow_run1.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run1]

        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_called_once()

    @mock.patch('requests.get', side_effect=mock_api_request_github)
    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.deschedule_test')
    def test_webhook_workflow_run_completed_failure(self, mock_deschedule_test, mock_repo, mock_request):
        """Test webhook triggered with workflow run event with action completed and status failure."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}

        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'completed'
        workflow_run1.conclusion = 'failure'
        workflow_run1.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run1]

        from github.PullRequest import PullRequest
        pr = MagicMock(PullRequest)
        pr.head.sha = '1'
        pr.user.id = 1
        pr.number = 1
        mock_repo.return_value.get_pulls.return_value = [pr]

        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
        mock_deschedule_test.assert_called()

    @mock.patch('mod_ci.controllers.deschedule_test')
    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_running(self, mock_request, mock_repo, mock_schedule_test, mock_deschedule_test):
        """Test webhook triggered with workflow run event where github actions is still in progress."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'push',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}

        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'not_completed_yet'
        workflow_run1.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run1]

        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))

        mock_schedule_test.assert_not_called()
        mock_deschedule_test.assert_not_called()

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_requested_invalid_workflow_name(self, mock_request, mock_schedule_test, mock_repo):
        """Test webhook triggered with workflow run event with an invalid action."""
        data = {'action': 'requested', 'workflow_run': {
            'name': 'Invalid', 'head_sha': 'abcdef'}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
        mock_schedule_test.assert_not_called()
        self.assertEqual(response.data, b'{"msg": "EOL"}')

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.schedule_test')
    @mock.patch('mod_ci.controllers.deschedule_test')
    @mock.patch('mod_ci.controllers.add_test_entry')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_with_unrecognized_event(self, mock_requests, mock_schedule_test,
                                             mock_deschedule_test, mock_add_test_entry, mock_repo):
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

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_pr_linux(self, mock_request, mock_queue_test,
                                                                mock_blocked, mock_repo):
        """Test webhook triggered - workflow run event, action completed, status success for pull request on linux."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'pull_request',
                                 'name': Workflow_builds.LINUX, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.LINUX
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'completed'
        workflow_run1.conclusion = 'success'
        workflow_run1.name = Workflow_builds.LINUX
        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run1]

        from github.PullRequest import PullRequest
        pr = MagicMock(PullRequest)
        pr.head.sha = '1'
        pr.user.id = 1
        pr.number = 1
        mock_repo.return_value.get_pulls.return_value = [pr]
        with self.app.test_client() as c:
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

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_pr_windows(self, mock_request,
                                                                  mock_queue_test, mock_blocked, mock_repo):
        """Test webhook triggered - workflow run event, action completed, status success for pull request on windows."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'pull_request',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}
        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'completed'
        workflow_run1.conclusion = 'success'
        workflow_run1.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run1]

        from github.PullRequest import PullRequest
        pr = MagicMock(PullRequest)
        pr.head.sha = '1'
        pr.user.id = 1
        pr.number = 1
        mock_repo.return_value.get_pulls.return_value = [pr]

        with self.app.test_client() as c:
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

    @mock.patch('github.Github.get_repo')
    @mock.patch('mod_ci.controllers.deschedule_test')
    @mock.patch('mod_ci.controllers.BlockedUsers')
    @mock.patch('mod_ci.controllers.queue_test')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    def test_webhook_workflow_run_completed_successful_pr_updated(self, mock_request, mock_queue_test,
                                                                  mock_blocked, mock_deschedule_test, mock_repo):
        """Test webhook triggered - workflow run event, action completed, for a pull request whose head was updated."""
        data = {'action': 'completed',
                'workflow_run': {'event': 'pull_request',
                                 'name': Workflow_builds.WINDOWS, 'head_sha': '1',
                                 'head_branch': 'master'}, 'sender': {'login': 'test_owner'}}

        from github.Workflow import Workflow
        workflow = MagicMock(Workflow)
        workflow.id = 1
        workflow.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflows.return_value = [workflow]

        from github.WorkflowRun import WorkflowRun
        workflow_run1 = MagicMock(WorkflowRun)
        workflow_run1.head_sha = '1'
        workflow_run1.workflow_id = 1
        workflow_run1.status = 'completed'
        workflow_run1.conclusion = 'success'
        workflow_run1.name = Workflow_builds.WINDOWS
        mock_repo.return_value.get_workflow_runs.return_value = [workflow_run1]

        from github.PullRequest import PullRequest
        pr = MagicMock(PullRequest)
        pr.head.sha = '2'
        pr.user.id = 1
        pr.number = 1
        mock_repo.return_value.get_pulls.return_value = [pr]

        with self.app.test_client() as c:
            mock_blocked.query.filter.return_value.first.return_value = None
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'workflow_run'))
            mock_queue_test.assert_not_called()
            mock_deschedule_test.assert_called()

    def test_start_ci_with_a_get_request(self):
        """Test start_ci function with a request method other than post."""
        with self.app.test_client() as c:
            response = c.get('/start-ci', environ_overrides=WSGI_ENVIRONMENT, headers=self.generate_header({}, 'test'))
            self.assertEqual(response.data, b'OK')

    @mock.patch('github.Github')
    @mock.patch('run.log.debug')
    def test_queue_test_with_pull_request(self, mock_debug, mock_github):
        """Check queue_test function with pull request as test type."""
        from mod_ci.controllers import add_test_entry, queue_test
        repository = mock_github(g.github['bot_token']).get_repo(
            f"{g.github['repository_owner']}/{g.github['repository']}")
        add_test_entry(g.db, 'customizedcommitcheck', TestType.pull_request)
        mock_debug.assert_called_once_with('pull request test type detected')
        queue_test(repository.get_commit("1"), 'customizedcommitcheck', TestType.pull_request, TestPlatform.linux)
        mock_debug.assert_called_with('Created tests, waiting for cron...')

    @mock.patch('run.log.critical')
    @mock.patch('github.Github.get_repo')
    @mock.patch('run.log.debug')
    def test_queue_test_github_failure(self, mock_debug, mock_repo, mock_critical):
        """Check queue_test function when updating GitHub status fails."""
        from github import GithubException

        from mod_ci.controllers import add_test_entry, queue_test
        add_test_entry(g.db, 'customizedcommitcheck', TestType.pull_request)
        mock_debug.assert_called_once_with('pull request test type detected')
        mock_commit = mock_repo.get_commit("1")
        response_data = "mock 400 response"
        mock_commit.create_status = mock.MagicMock(
            side_effect=GithubException(status=400, data=response_data, headers={}))
        queue_test(mock_commit, 'customizedcommitcheck', TestType.pull_request, TestPlatform.linux)
        mock_debug.assert_called_with('Created tests, waiting for cron...')
        mock_critical.assert_called_with(f"Could not post to GitHub! Response: {response_data}")

    @mock.patch('run.log')
    @mock.patch('github.Github')
    def test_schedule_test_function(self, git_mock, mock_log):
        """Check the functioning of schedule_test function."""
        from mod_ci.controllers import schedule_test
        repository = git_mock(g.github['bot_token']).get_repo(
            f"{g.github['repository_owner']}/{g.github['repository']}")
        schedule_test(repository.get_commit(1))
        mock_log.debug.assert_not_called()
        mock_log.critical.assert_not_called()

        mock_log.reset_mock()
        schedule_test(None)
        mock_log.debug.assert_not_called()
        mock_log.critical.assert_not_called()

    @mock.patch('run.log')
    @mock.patch('github.Github')
    def test_deschedule_test_function(self, git_mock, mock_log):
        """Check the functioning of deschedule_test function on linux platform."""
        from mod_ci.controllers import deschedule_test
        repository = git_mock(g.github['bot_token']).get_repo(
            f"{g.github['repository_owner']}/{g.github['repository']}")
        commit = Test.query.filter(Test.platform == TestPlatform.linux).first().commit
        deschedule_test(repository.get_commit(commit), commit, TestType.pull_request, TestPlatform.linux)
        mock_log.debug.assert_called_once_with("pull request test type detected")
        mock_log.critical.assert_not_called()

        # Test deschedule function with github commit None
        mock_log.reset_mock()
        deschedule_test(None, 1, TestType.commit, TestPlatform.linux)
        mock_log.debug.assert_not_called()
        mock_log.critical.assert_not_called()

    @mock.patch('github.Github.get_repo')
    @mock.patch('requests.get', side_effect=mock_api_request_github)
    @mock.patch('mod_ci.controllers.inform_mailing_list')
    @mock.patch('mod_sample.models.Issue.query')
    def test_webhook_issue_opened(self, mock_issue, mock_mailing, mock_request, mock_github):
        """Test webhook triggered with issues event with opened action."""
        from mod_sample.models import Issue
        data = {'action': 'opened',
                'issue': {'number': '1234', 'title': 'testTitle', 'body': 'testing', 'state': 'opened',
                          'user': {'login': 'testAuthor'}}}
        with self.app.test_client() as c:
            response = c.post(
                '/start-ci', environ_overrides=WSGI_ENVIRONMENT,
                data=json.dumps(data), headers=self.generate_header(data, 'issues'))

        self.assertEqual(response.data, b'{"msg": "EOL"}')
        mock_mailing.assert_called_once_with(mock.ANY, '1234', 'testTitle', 'testAuthor', 'testing')

    @mock.patch('github.Github')
    @mock.patch('run.log.critical')
    def test_github_api_error(self, mock_critical, mock_github):
        """Test functions with GitHub API error."""
        from github import Github, GithubException

        from mod_ci.controllers import deschedule_test, schedule_test
        github_status = Github('1').get_repo(
            f"{g.github['repository_owner']}/{g.github['repository']}").get_commit('abcdef')
        github_status.create_status.side_effect = GithubException(status=500, data="", headers={})
        schedule_test(github_status)
        mock_critical.assert_called()
        mock_critical.reset_mock()
        deschedule_test(github_status, 1, TestType.commit, TestPlatform.linux)
        mock_critical.assert_called()
        mock_critical.reset_mock()
        deschedule_test(github_status, 1, TestType.commit, TestPlatform.windows)
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

    @mock.patch('mod_ci.controllers.wait_for_operation')
    @mock.patch('mod_ci.controllers.delete_instance')
    @mock.patch('mod_ci.controllers.get_compute_service_object')
    @mock.patch('mod_ci.controllers.update_build_badge')
    @mock.patch('github.Github.get_repo')
    def test_progress_type_request(self, mock_repo, mock_update_build_badge, mock_get_compute_service_object,
                                   mock_delete_instance, mock_wait_for_operation):
        """Test progress_type_request function."""
        from mod_ci.models import GcpInstance
        from run import log

        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        request = MagicMock()
        request.form = {'status': 'completed', 'message': 'Ran all tests'}
        gcp_instance = GcpInstance(name='test_instance', test_id=3)
        g.db.add(gcp_instance)
        g.db.commit()

        test = Test.query.filter(Test.id == 3).first()

        response = progress_type_request(log, test, test.id, request)
        mock_update_build_badge.assert_called_once()
        mock_get_compute_service_object.assert_called()
        self.assertTrue(response)

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

    @mock.patch('run.log')
    @mock.patch('run.config')
    def test_start_platforms_with_empty_zone(self, mock_config, mock_log):
        """Test start_platforms function if GCP zone is not provided in config."""
        def config_get(key, *args, **kwargs):
            if key == "ZONE":
                return ""
            return "test"
        mock_config.get.side_effect = config_get
        start_platforms(mock.ANY)

        mock_log.critical.assert_called_with('GCP zone name is empty!')

    @mock.patch('run.log')
    @mock.patch('run.config')
    def test_start_platforms_with_empty_project_name(self, mock_config, mock_log):
        """Test start_platforms function if GCP project name is not provided in config."""
        def config_get(key, *args, **kwargs):
            if key == "PROJECT_NAME":
                return ""
            return "test"
        mock_config.get.side_effect = config_get
        start_platforms(mock.ANY)

        mock_log.critical.assert_called_with('GCP project name is empty!')

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
