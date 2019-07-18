"""Contain function for updating the outputs of regression test with latest CCExtractor version."""


import os
import subprocess
from time import gmtime, strftime
from typing import List

from database import create_session
from mod_regression.models import RegressionTest
from run import config

INPUT_VIDEO_FOLDER = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
OUTPUT_RESULTS_FOLDER = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestResults')
LOG_DIR = os.path.join(os.path.expanduser('~'), 'sampleplatform_sample_update_logs')


class Test:
    """Object to hold all test details and get methods."""

    def __init__(self, input_file: str, args: str, output: str) -> None:
        self.input = input_file
        self.args = args
        self.output = output

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
    def get_outputfilepath(reg_test: RegressionTest) -> str:
        """
        Get absolute output captions path from RegressionTest entry.

        :param reg_test: regression test
        :type reg_test: RegressionTest
        :return: absolute file path of the output file
        :rtype: str
        """
        output = reg_test.output_files[0]
        file_name = output.filename_correct
        file_path = os.path.join(OUTPUT_RESULTS_FOLDER, file_name)
        abs_file_path = os.path.abspath(file_path)

        return abs_file_path

    @staticmethod
    def run_ccex(path_to_ccex: str, log_file: str, input_file: str, args: str, output_file: str) -> bool:
        """
        Run ccextractor in a subprocess in a synchronous manner.

        :param path_to_ccex: path to the latest ccextractor executable
        :type path_to_ccex: str
        :param log_file: absolute path to the log file where ccextractor output is saved
        :type log_file: str
        :param input_file: absolute path to the input file
        :type input_file: str
        :param args: arguments for ccextractor
        :type args: str
        :param output_file: absolute path to the output file
        :type output_file: str
        :return: True if successful, False otherwise
        :rtype: bool
        """
        proc_args = [path_to_ccex]
        proc_args.extend(list(args.split(' ')))
        proc_args.append(input_file)
        proc_args.extend(['-o', output_file])

        try:
            proc = subprocess.run(proc_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            with open(log_file, 'w+') as logf:
                logf.write(proc.stdout.decode('utf-8'))
            if proc.returncode != 0:
                print(f'ERROR: ccextractor encountered error for {input_file}, please see {log_file}')
                print(f'ccextractor was run as {" ".join(proc_args)}')
                return False
            else:
                return True
        except subprocess.CalledProcessError as err:
            print(f'ERROR: subprocess failed for {input_file}')
            print(f'ERROR: The run for subprocess was "{" ".join(proc_args)}"')
            return False


def update_expected_results(path_to_ccex: str) -> bool:
    """
    Update expected result in the regression.

    :param path_to_ccex: path to the ccextractor executable
    :type path_to_ccex: str
    """
    DBSession = create_session(config['DATABASE_URI'])

    if not os.path.isfile(path_to_ccex):
        return False

    all_regression_tests = DBSession.query(RegressionTest).all()

    tests_to_update = []

    if len(all_regression_tests) == 0:
        print('INFO: No regression tests found!')
        return True

    for test in all_regression_tests:
        input_file = Test.get_inputfilepath(test)
        output_file = Test.get_outputfilepath(test)
        args = test.command

        tests_to_update.append(Test(
            input_file,
            args,
            output_file
        ))

    log_folder_name = strftime("%Y_%m_%dT%H_%M_%SZ", gmtime())
    log_folder_path = os.path.join(LOG_DIR, log_folder_name)
    os.makedirs(log_folder_path, exist_ok=True)
    print(f'INFO: ccextractor logs can be found at {log_folder_path} for each sample after update')

    for test in tests_to_update:
        log_file = os.path.join(log_folder_path, os.path.basename(test.input) + '.log')
        success = Test.run_ccex(path_to_ccex, log_file, test.input, test.args, test.output)
        if success:
            print(f'SUCCESS: output {output_file} updated for sample {input_file}')
    return True
