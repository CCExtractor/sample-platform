import unittest
from unittest.mock import Mock, patch

from mod_ci.controllers import finish_type_request
from tests.base import BaseTestCase


class TestNegativeRuntimeFix(BaseTestCase):

    @patch('mod_ci.controllers.safe_db_commit')
    @patch('mod_ci.controllers.g')
    @patch('mod_ci.controllers.RegressionTest')
    @patch('mod_ci.controllers.TestResult')
    def test_negative_runtime_clamped_to_zero(self, mock_test_result,
                                              mock_regression_test, mock_g,
                                              mock_safe_db_commit):
        mock_log = Mock()
        mock_test = Mock()
        mock_test.id = 123

        mock_regression_test_instance = Mock()
        mock_regression_test_instance.id = 1
        mock_regression_test_instance.expected_rc = 0
        mock_regression_test.query.filter.return_value.first.return_value = \
            mock_regression_test_instance

        mock_request = Mock()
        mock_request.form = {
            'test_id': '1',
            'runTime': '-5000',
            'exitCode': '0'
        }

        mock_g.db = Mock()
        mock_safe_db_commit.return_value = True

        finish_type_request(mock_log, 123, mock_test, mock_request)

        mock_log.warning.assert_called_once_with(
            "Negative runtime -5000 for test 123; clamping to 0")
        mock_test_result.assert_called_once_with(123, 1, 0, '0', 0)
        mock_g.db.add.assert_called_once()
        mock_safe_db_commit.assert_called_once()

    @patch('mod_ci.controllers.safe_db_commit')
    @patch('mod_ci.controllers.g')
    @patch('mod_ci.controllers.RegressionTest')
    @patch('mod_ci.controllers.TestResult')
    def test_positive_runtime_unchanged(self, mock_test_result,
                                        mock_regression_test, mock_g,
                                        mock_safe_db_commit):
        mock_log = Mock()
        mock_test = Mock()
        mock_test.id = 123

        mock_regression_test_instance = Mock()
        mock_regression_test_instance.id = 1
        mock_regression_test_instance.expected_rc = 0
        mock_regression_test.query.filter.return_value.first.return_value = \
            mock_regression_test_instance

        mock_request = Mock()
        mock_request.form = {
            'test_id': '1',
            'runTime': '12345',
            'exitCode': '0'
        }

        mock_g.db = Mock()
        mock_safe_db_commit.return_value = True

        finish_type_request(mock_log, 123, mock_test, mock_request)

        mock_log.warning.assert_not_called()
        mock_test_result.assert_called_once_with(123, 1, 12345, '0', 0)
        mock_g.db.add.assert_called_once()
        mock_safe_db_commit.assert_called_once()

    @patch('mod_ci.controllers.safe_db_commit')
    @patch('mod_ci.controllers.g')
    @patch('mod_ci.controllers.RegressionTest')
    @patch('mod_ci.controllers.TestResult')
    def test_invalid_runtime_defaults_to_zero(self, mock_test_result,
                                              mock_regression_test, mock_g,
                                              mock_safe_db_commit):
        mock_log = Mock()
        mock_test = Mock()
        mock_test.id = 123

        mock_regression_test_instance = Mock()
        mock_regression_test_instance.id = 1
        mock_regression_test_instance.expected_rc = 0
        mock_regression_test.query.filter.return_value.first.return_value = \
            mock_regression_test_instance

        mock_request = Mock()
        mock_request.form = {
            'test_id': '1',
            'runTime': 'invalid_string',
            'exitCode': '0'
        }

        mock_g.db = Mock()
        mock_safe_db_commit.return_value = True

        finish_type_request(mock_log, 123, mock_test, mock_request)

        mock_log.warning.assert_called_once_with(
            "Invalid runtime 'invalid_string' for test 123; storing 0")
        mock_test_result.assert_called_once_with(123, 1, 0, '0', 0)
        mock_g.db.add.assert_called_once()
        mock_safe_db_commit.assert_called_once()

    @patch('mod_ci.controllers.safe_db_commit')
    @patch('mod_ci.controllers.g')
    @patch('mod_ci.controllers.RegressionTest')
    @patch('mod_ci.controllers.TestResult')
    def test_zero_runtime_unchanged(self, mock_test_result,
                                    mock_regression_test, mock_g,
                                    mock_safe_db_commit):
        mock_log = Mock()
        mock_test = Mock()
        mock_test.id = 123

        mock_regression_test_instance = Mock()
        mock_regression_test_instance.id = 1
        mock_regression_test_instance.expected_rc = 0
        mock_regression_test.query.filter.return_value.first.return_value = \
            mock_regression_test_instance

        mock_request = Mock()
        mock_request.form = {
            'test_id': '1',
            'runTime': '0',
            'exitCode': '0'
        }

        mock_g.db = Mock()
        mock_safe_db_commit.return_value = True

        finish_type_request(mock_log, 123, mock_test, mock_request)

        mock_log.warning.assert_not_called()
        mock_test_result.assert_called_once_with(123, 1, 0, '0', 0)
        mock_g.db.add.assert_called_once()
        mock_safe_db_commit.assert_called_once()

    @patch('mod_ci.controllers.safe_db_commit')
    @patch('mod_ci.controllers.g')
    @patch('mod_ci.controllers.RegressionTest')
    @patch('mod_ci.controllers.TestResult')
    def test_missing_runtime_defaults_to_zero(self, mock_test_result,
                                              mock_regression_test, mock_g,
                                              mock_safe_db_commit):
        mock_log = Mock()
        mock_test = Mock()
        mock_test.id = 123

        mock_regression_test_instance = Mock()
        mock_regression_test_instance.id = 1
        mock_regression_test_instance.expected_rc = 0
        mock_regression_test.query.filter.return_value.first.return_value = \
            mock_regression_test_instance

        mock_request = Mock()
        mock_request.form = {
            'test_id': '1',
            'exitCode': '0'
        }

        mock_g.db = Mock()
        mock_safe_db_commit.return_value = True

        finish_type_request(mock_log, 123, mock_test, mock_request)

        mock_log.warning.assert_not_called()
        mock_test_result.assert_called_once_with(123, 1, 0, '0', 0)
        mock_g.db.add.assert_called_once()
        mock_safe_db_commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
