from unittest import mock

from werkzeug.exceptions import Forbidden, NotFound

from mod_auth.models import Role
from mod_regression.models import RegressionTest
from mod_test.models import (Test, TestPlatform, TestProgress, TestResult,
                             TestResultFile, TestStatus)
from tests.base import BaseTestCase


class TestControllers(BaseTestCase):
    """Test test page controllers."""

    @staticmethod
    def create_completed_regression_t_entries(test_id, regression_tests):
        """Create needed entries for completed regression."""
        from flask import g
        test_result_progress = [
            TestProgress(test_id, TestStatus.preparation, f"Test {test_id} preparation"),
            TestProgress(test_id, TestStatus.testing, f"Test {test_id} testing"),
            TestProgress(test_id, TestStatus.completed, f"Test {test_id} completed"),
        ]
        g.db.add_all(test_result_progress)
        test_results = [
            TestResult(test_id, regression_test, 200, 0, 0) for regression_test in regression_tests
        ]
        g.db.add_all(test_results)
        test_result_files = [
            TestResultFile(test_id, regression_test, regression_test, 'sample_output')
            for regression_test in regression_tests
        ]
        g.db.add_all(test_result_files)
        g.db.commit()

    def test_root(self):
        """Test the access of the test index page."""
        response = self.app.test_client().get('/test/')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/index.html')

    def test_specific_test_loads(self):
        """Test the access of the specific test page by test ID."""
        response = self.app.test_client().get('/test/1')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/by_id.html')

    def test_customize_test_loads(self):
        """Test loading of customize tests."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        self.create_completed_regression_t_entries(3, [2])
        response = self.app.test_client().get('/test/3')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('test/by_id.html')
        regression_tests = RegressionTest.query.all()
        self.assertIn(regression_tests[1].command, str(response.data))
        self.assertNotIn(regression_tests[0].command, str(response.data))

    def test_restart_with_permission(self):
        """Test test restart with permission."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        self.create_completed_regression_t_entries(3, [2])
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/restart_test/3')
            test = Test.query.filter(Test.id == 3).first()
            self.assertEqual(test.finished, False)

    def test_restart_fails_on_no_permission(self):
        """Test failed test restart because of no permission."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/restart_test/1')
            self.assert403(response)

    def test_stop_with_permission(self):
        """Test successful test stop because of permission."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.tester)
        self.create_forktest("own-fork-commit", TestPlatform.linux, regression_tests=[2])
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/stop_test/3')
            test = Test.query.filter(Test.id == 3).first()
            self.assertEqual(test.finished, True)

    def test_stop_fails_on_no_permission(self):
        """Test failed test stop because of no permission."""
        self.create_user_with_role(
            self.user.name, self.user.email, self.user.password, Role.user)
        with self.app.test_client() as c:
            response = c.post(
                '/account/login', data=self.create_login_form_data(self.user.email, self.user.password))
            response = c.get('/test/stop_test/1')
            self.assert403(response)

    def test_get_json_data_throw_not_found_error(self):
        """Test if get_json_data throws Error 404."""
        response = self.app.test_client().get('/test/get_json_data/99999')
        self.assertEqual(response.json['status'], 'failure')
        self.assertEqual(response.json['error'], 'Test not found')

    def test_get_nonexistent_test(self):
        """Test if it'll return a 404 on a non existent test."""
        response = self.app.test_client().get('/test/99999')
        self.assertEqual(response.status_code, 404)
        self.assert_template_used('test/test_not_found.html')

    def test_ccextractor_version_not_found(self):
        """Test View for CCExtractor Test if test won't be found."""
        response = self.app.test_client().get('/test/ccextractor/0.8494')
        self.assertEqual(response.status_code, 404)
        self.assert_template_used('test/test_not_found.html')

    @mock.patch('mod_test.controllers.g')
    @mock.patch('mod_test.controllers.GeneralData')
    @mock.patch('mod_test.controllers.Category')
    @mock.patch('mod_test.controllers.TestProgress')
    def test_data_for_test(self, mock_test_progress, mock_category, mock_gen_data, mock_g):
        """Test get_data_for_test method."""
        from mod_test.controllers import get_data_for_test

        mock_test = mock.MagicMock()

        result = get_data_for_test(mock_test)

        self.assertIsInstance(result, dict)
        self.assertEqual(6, mock_g.db.query.call_count)
        mock_category.query.filter.assert_called_once()
        mock_gen_data.query.filter.assert_called()

    @mock.patch('mod_test.controllers.Test')
    def test_get_json_data_no_test(self, mock_test):
        """Try to get json data when Test not present."""
        from mod_test.controllers import get_json_data

        mock_test.query.filter.return_value.first.return_value = None
        expected = b'{"error":"Test not found","status":"failure"}\n'

        result = get_json_data(1)

        self.assertEqual(result.data, expected)
        mock_test.query.filter.assert_called_once_with(mock_test.id == 1)

    @mock.patch('mod_test.controllers.jsonify')
    @mock.patch('mod_test.controllers.Test')
    def test_get_json_data(self, mock_test, mock_jsonify):
        """Try to get json data."""
        from mod_test.controllers import get_json_data

        result = get_json_data(1)

        mock_test.query.filter.assert_called_once_with(mock_test.id == 1)
        mock_jsonify.assert_called_once()

    @mock.patch('mod_test.controllers.TestResultFile')
    def test_generate_diff_abort_403(self, mock_test_result_file):
        """Try to generate diff without xhr request."""
        from mod_test.controllers import generate_diff

        with self.assertRaises(Forbidden):
            generate_diff(1, 1, 1)

    @mock.patch('mod_test.controllers.TestResultFile')
    @mock.patch('mod_test.controllers.request')
    def test_generate_diff_abort_404(self, mock_request, mock_test_result_file):
        """Try to generate diff when test file not present."""
        from mod_test.controllers import generate_diff

        mock_request.accept_mimetypes.best = 'application/json'
        mock_test_result_file.query.filter.return_value.first.return_value = None

        with self.assertRaises(NotFound):
            generate_diff(1, 1, 1)

    @mock.patch('mod_test.controllers.TestResultFile')
    @mock.patch('mod_test.controllers.request')
    def test_generate_diff(self, mock_request, mock_test_result_file):
        """Test to generate diff."""
        from mod_test.controllers import generate_diff

        mock_request.accept_mimetypes.best = 'application/json'

        response = generate_diff(1, 1, 1)

        self.assertTrue(response, mock_test_result_file.filter().first().generate_html_diff())
        mock_test_result_file.filter.assert_called_once()

    @mock.patch('mod_test.controllers.TestResultFile')
    @mock.patch('mod_test.controllers.request')
    @mock.patch('mod_test.controllers.Response')
    def test_generate_diff_download(self, mock_response, mock_request, mock_test_result_file):
        """Test to download generated diff."""
        from mod_test.controllers import generate_diff

        mock_request.accept_mimetypes.best = 'application/json'

        response = generate_diff(1, 1, 1, to_view=0)

        self.assertTrue(response, mock_response())

    @mock.patch('mod_test.controllers.Test')
    def test_download_build_log_file_test_not_found(self, mock_test):
        """Try to download build log for invalid test."""
        from mod_test.controllers import (TestNotFoundException,
                                          download_build_log_file)

        mock_test.query.filter.return_value.first.return_value = None

        with self.assertRaises(TestNotFoundException):
            download_build_log_file(1)

        mock_test.query.filter.assert_called_once()

    @mock.patch('mod_test.controllers.os')
    @mock.patch('mod_test.controllers.Test')
    def test_download_build_log_file_log_not_file(self, mock_test, mock_os):
        """Try to download build log for invalid file path."""
        from mod_test.controllers import (TestNotFoundException,
                                          download_build_log_file)

        mock_os.path.isfile.side_effect = TestNotFoundException('msg')

        with self.assertRaises(TestNotFoundException):
            download_build_log_file('1')

        mock_test.query.filter.assert_called_once()
        mock_os.path.isfile.assert_called_once()

    @mock.patch('mod_test.controllers.os')
    @mock.patch('mod_test.controllers.Test')
    @mock.patch('mod_test.controllers.serve_file_download')
    def test_download_build_log_file(self, mock_serve, mock_test, mock_os):
        """Try to download build log."""
        from mod_test.controllers import (TestNotFoundException,
                                          download_build_log_file)

        response = download_build_log_file('1')

        self.assertEqual(response, mock_serve())
        mock_test.query.filter.assert_called_once()
        mock_os.path.isfile.assert_called_once()
