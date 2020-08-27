import os
from unittest import mock

from tests.base import BaseTestCase


class TestUpdateRegression(BaseTestCase):

    def test_update_expected_results_not_path(self):
        """
        Test updating when ccextractor path is not correct.
        """
        from mod_regression.update_regression import update_expected_results

        expected = False

        response = update_expected_results('/not/a/valid/path')

        self.assertEqual(response, expected)

    @mock.patch('mod_regression.update_regression.os')
    @mock.patch('mod_regression.update_regression.create_session')
    def test_update_expected_results_zero_regressions(self, mock_session, mock_os):
        """
        Test updating when there are no regression tests.
        """
        from mod_regression.update_regression import update_expected_results

        mock_os.path.isfile.return_value = True
        mock_session.return_value.query.return_value.all.return_value = []
        expected = True

        response = update_expected_results('valid/path')

        self.assertEqual(response, expected)

    @mock.patch('mod_regression.update_regression.os')
    @mock.patch('mod_regression.update_regression.Test')
    def test_update_expected_results_(self, mock_test, mock_os):
        """
        Test updating regression tests.
        """
        from mod_regression.update_regression import update_expected_results

        mock_os.path.isfile.return_value = True
        expected = True
        num_tests = 2   # store number of mock regression tests we have

        response = update_expected_results('valid/path')

        self.assertEqual(response, expected)
        self.assertEqual(mock_test.get_inputfilepath.call_count, num_tests)
        self.assertEqual(mock_test.get_outputfilepath.call_count, num_tests)
        self.assertEqual(mock_test.call_count, num_tests)
        mock_os.makedirs.assert_called_once()
        self.assertEqual(mock_test.run_ccex.call_count, num_tests)

    def test_Test_initiation(self):
        """
        Test initiation of Test class with mock arguments.
        """
        from mod_regression.update_regression import Test

        filename = 'some.txt'
        args = '--autotext'
        output = 'someout.txt'

        test = Test(
            filename,
            args,
            output
        )

        self.assertEqual(test.input, filename)
        self.assertEqual(test.args, args)
        self.assertEqual(test.output, output)

    def test_Test_get_inputfilepath(self):
        """
        Test method get_inputfilepath of Test class.
        """
        from mod_regression.update_regression import Test
        from run import config

        reg_test = mock.MagicMock()
        reg_test.sample.filename = 'some.txt'
        expected = os.path.abspath(os.path.join(os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles'),
                                   reg_test.sample.filename))

        filepath = Test.get_inputfilepath(reg_test)

        self.assertEqual(filepath, expected)

    def test_Test_get_outputfilepath(self):
        """
        Test method get_inputfilepath of Test class.
        """
        from mod_regression.update_regression import Test
        from run import config

        class MockOutput:
            def __init__(self, filename):
                self.filename_correct = filename

        reg_test = mock.MagicMock()
        reg_test.output_files = [MockOutput('output.txt')]
        expected = os.path.abspath(os.path.join(os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestResults'),
                                   reg_test.output_files[0].filename_correct))

        filepath = Test.get_outputfilepath(reg_test)

        self.assertEqual(filepath, expected)

    @mock.patch('mod_regression.update_regression.subprocess')
    @mock.patch('mod_regression.update_regression.open')
    def test_Test_run_ccex(self, mock_open, mock_subprocess):
        """
        Test run_ccex with proper arguments and no failure.
        """
        from mod_regression.update_regression import Test

        mock_subprocess.run.return_value.returncode = 0
        path_to_ccex = '/some/path'
        log_file = 'some/log'
        input_file = 'some/input'
        args = '--autotext'
        output_file = 'some/output'

        result = Test.run_ccex(
            path_to_ccex,
            log_file,
            input_file,
            args,
            output_file
        )

        self.assertEqual(result, True)

    @mock.patch('mod_regression.update_regression.subprocess')
    @mock.patch('mod_regression.update_regression.open')
    def test_Test_run_ccex_with_error(self, mock_open, mock_subprocess):
        """
        Test run_ccex with proper arguments and failure of ccextractor.
        """
        from mod_regression.update_regression import Test

        mock_subprocess.run.return_value.returncode = 1
        path_to_ccex = '/some/path'
        log_file = 'some/log'
        input_file = 'some/input'
        args = '--autotext'
        output_file = 'some/output'

        result = Test.run_ccex(
            path_to_ccex,
            log_file,
            input_file,
            args,
            output_file
        )

        self.assertEqual(result, False)

    @mock.patch('mod_regression.update_regression.subprocess')
    @mock.patch('mod_regression.update_regression.open')
    def test_Test_run_ccex_with_process_failure(self, mock_open, mock_subprocess):
        """
        Test run_ccex with proper arguments but failure of subprocess.
        """
        from subprocess import CalledProcessError

        from mod_regression.update_regression import Test

        mock_subprocess.run.side_effect = CalledProcessError(1, 'cmd')
        mock_subprocess.CalledProcessError = CalledProcessError
        path_to_ccex = '/some/path'
        log_file = 'some/log'
        input_file = 'some/input'
        args = '--autotext'
        output_file = 'some/output'

        result = Test.run_ccex(
            path_to_ccex,
            log_file,
            input_file,
            args,
            output_file
        )

        self.assertEqual(result, False)
