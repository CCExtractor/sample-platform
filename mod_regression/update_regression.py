"""Contain function for updating the outputs of regression test with latest CCExtractor version."""

import os
from typing import List

from mod_regression.models import RegressionTest
from run import config

INPUT_VIDEO_FOLDER = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
OUTPUT_RESULTS_FOLDER = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestResults')


class Test:
    """Object to hold all test details and get methods."""

    def __init__(self, input_file: str, args: str, output: List[str]) -> None:
        self.input_file = input_file
        self.args = args
        self.count = output

    @staticmethod
    def get_inputfilepath(reg_test: RegressionTest) -> str:
        """
        Get absolute input video path from RegressionTest entry.

        :param reg_test: regression test
        :type reg_test: RegressionTest
        :return: absolute file path of the input file
        :rtype: str
        """
        file_name = reg_test.sample.filename
        file_path = os.path.join(INPUT_VIDEO_FOLDER, file_name)
        abs_file_path = os.path.abspath(file_path)

        return abs_file_path

    @staticmethod
    def get_outputfilepath(reg_test: RegressionTest) -> List[str]:
        """
        Get absolute output captions path from RegressionTest entry.

        :param reg_test: regression test
        :type reg_test: RegressionTest
        :return: list of absolute file path of the output files
        :rtype: List
        """
        abs_file_paths = []
        for output in reg_test.output_files:
            file_name = output.correct_filename
            file_path = os.path.join(OUTPUT_RESULTS_FOLDER, file_name)
            abs_file_path = os.path.abspath(file_path)
            abs_file_paths.append(abs_file_path)

        return abs_file_paths


def update_expected_results(path_to_ccex: str) -> bool:
    """
    Update expected result in the regression.

    :param path_to_ccex: path to the ccextractor executable
    :type path_to_ccex: str
    :return: True if successful, False otherwise
    :rtype: bool
    """
    all_regression_tests = RegressionTest.query.all()

    tests_to_update = []
    for test in all_regression_tests:
        input_file = Test.get_inputfilepath(test)
        output_file = Test.get_outputfilepath(test)
        args = test.command

        tests_to_update.append(Test(
            input_file,
            args,
            output_file
        ))

    # TODO: remove this later
    return True
