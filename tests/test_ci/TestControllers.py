from mock import mock
from tests.base import BaseTestCase
from mod_test.models import TestPlatform
from mod_regression.models import RegressionTest
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
    @mock.patch('lxml.etree.Element')
    def test_customize_tests_run_on_fork_if_no_remote(self, mock_etree, mock_open,
                                                      mock_rmtree, mock_libvirt, mock_repo, mock_git):
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
    @mock.patch('lxml.etree.Element')
    def test_customize_tests_run_on_fork_if_remote_exist(self, mock_etree, mock_open,
                                                         mock_rmtree, mock_libvirt, mock_repo, mock_git):
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
