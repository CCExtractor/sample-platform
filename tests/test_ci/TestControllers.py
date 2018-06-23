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
