"""
mod_test Controller
===================
In this module, we are trying to find all tests, their progress and details
of individual test.
"""

import os

from flask import Blueprint, g, abort, make_response, request, jsonify
from sqlalchemy import and_, func
from sqlalchemy.sql import label
from decorators import template_renderer
from mod_home.models import CCExtractorVersion
from mod_regression.models import Category, regressionTestLinkTable, \
    RegressionTestOutput
from mod_test.models import Fork, Test, TestProgress, TestResultFile, TestType, TestPlatform
from mod_home.models import GeneralData
from mod_ci.models import Kvm
from datetime import datetime
from github import GitHub
mod_test = Blueprint('test', __name__)


class TestNotFoundException(Exception):

    def __init__(self, message):
        Exception.__init__(self)
        self.message = message


@mod_test.before_app_request
def before_app_request():
    g.menu_entries['tests'] = {
        'title': 'Test results',
        'icon': 'flask',
        'route': 'test.index'
    }


@mod_test.errorhandler(TestNotFoundException)
@template_renderer('test/test_not_found.html', 404)
def not_found(error):
    return {
        'message': error.message
    }


@mod_test.route('/')
@template_renderer()
def index():
    fork = Fork.query.filter(Fork.github.like("%/CCExtractor/ccextractor.git")).first()
    return {
        'tests': Test.query.filter(Test.fork_id == fork.id).order_by(Test.id.desc()).limit(50).all(),
        'TestType': TestType
    }


def get_data_for_test(test, title=None):
    """
    Retrieves the data for a single test, with an optional title.

    :param test: The test to retrieve the data for.
    :type test: Test
    :param title: The title to use in the result. If empty, it's set to 'test {id}'
    :type title: str
    :return: A dictionary with the appropriate values.
    :rtype: dict
    """
    if title is None:
        title = 'test {id}'.format(id=test.id)

    populated_categories = g.db.query(regressionTestLinkTable.c.category_id).subquery()
    categories = Category.query.filter(Category.id.in_(populated_categories)).order_by(Category.name.asc()).all()
    hours = 0
    minutes = 0
    queued_tests = 0
    """
    evaluating estimated time if the test is still in queue
    estimated time = (number of tests already in queue + 1) * (average time of that platform)
                      - (time already spend by those tests)
    calculates time in minutes and hours
    """
    if len(test.progress) == 0:
        var_average = 'average_time_' + test.platform.value
        queued_kvm = g.db.query(Kvm.test_id).filter(Kvm.test_id < test.id).subquery()
        queued_kvm_entries = g.db.query(Test.id).filter(
            and_(Test.id.in_(queued_kvm), Test.platform == test.platform)
        ).subquery()
        kvm_test = g.db.query(TestProgress.test_id, label('time', func.group_concat(TestProgress.timestamp))).filter(
            TestProgress.test_id.in_(queued_kvm_entries)
        ).group_by(TestProgress.test_id).all()
        number_kvm_test = g.db.query(Test.id).filter(
            and_(Test.id.in_(queued_kvm), Test.platform == test.platform)
        ).count()
        average_duration = float(GeneralData.query.filter(GeneralData.key == var_average).first().value)
        queued_tests = number_kvm_test
        time_run = 0
        for pr_test in kvm_test:
            timestamps = pr_test.time.split(',')
            start = datetime.strptime(timestamps[0], '%Y-%m-%d %H:%M:%S')
            end = datetime.strptime(timestamps[-1], '%Y-%m-%d %H:%M:%S')
            time_run += (end - start).total_seconds()
        # subtracting current running tests
        total = (average_duration * (queued_tests + 1)) - time_run
        minutes = (total % 3600) // 60
        hours = total // 3600

    results = [{
        'category': category,
        'tests': [{
            'test': rt,
            'result': next((r for r in test.results if r.regression_test_id == rt.id), None),
            'files': TestResultFile.query.filter(
                and_(TestResultFile.test_id == test.id, TestResultFile.regression_test_id == rt.id)
            ).all()
        } for rt in category.regression_tests]
    } for category in categories]
    # Run through the categories to see if they should be marked as failed or passed. A category failed if one or more
    # tests in said category failed.
    for category in results:
        error = False
        for category_test in category['tests']:
            test_error = False
            # A test fails if:
            # - Exit code is not what we expected
            # - There are result files but one of them is not identical
            # - There are no result files but there should have been
            result = category_test['result']
            if result is not None and result.exit_code != result.expected_rc:
                test_error = True
            if len(category_test['files']) > 0:
                for result_file in category_test['files']:
                    if result_file.got is not None and result.exit_code == 0:
                        test_error = True
                        break
            else:
                # We need to check if the regression test had any file that shouldn't have been ignored.
                outputs = RegressionTestOutput.query.filter(and_(
                    RegressionTestOutput.regression_id == category_test['test'].id,
                    RegressionTestOutput.ignore is False
                )).all()
                got = None
                if len(outputs) > 0:
                    test_error = True
                    got = 'error'
                # Add dummy entry for pass/fail display
                category_test['files'] = [TestResultFile(-1, -1, -1, '', got)]
            # Store test status in error field
            category_test['error'] = test_error
            # Update category error
            error = error or test_error
        category['error'] = error
    results.sort(key=lambda entry: entry['category'].name)
    return {
        'test': test,
        'TestType': TestType,
        'results': results,
        'title': title,
        'next': queued_tests,
        'min': minutes,
        'hr': hours
    }


@mod_test.route('/get_json_data/<test_id>')
def get_json_data(test_id):
    """
    Retrieves the status of a test id and returns it in JSON format.

    :param test_id: The id of the test to retrieve data for.
    :type test_id: int
    :return: A JSON structure that holds the data about this test.
    :rtype: Any
    """
    test = Test.query.filter(Test.id == test_id).first()
    if test is None:
        return jsonify({'status': 'failure', 'error': 'Test not found'})

    pr_data = test.progress_data()
    progress_array = []
    for entry in test.progress:
        progress_array.append({
            'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M:%S (%Z)'),
            'status': entry.status.description,
            'message': entry.message
        })

    return jsonify({
        'status': 'success',
        'details': pr_data["progress"],
        'complete': test.finished,
        'progress_array': progress_array
    })


@mod_test.route('/<test_id>')
@template_renderer()
def by_id(test_id):
    test = Test.query.filter(Test.id == test_id).first()
    if test is None:
        raise TestNotFoundException('Test with id {id} does not exist'.format(id=test_id))

    return get_data_for_test(test)


@mod_test.route('/ccextractor/<ccx_version>')
@template_renderer('test/by_id.html')
def ccextractor_version(ccx_version):
    # Look up the hash, find a test for it and redirect
    version = CCExtractorVersion.query.filter(CCExtractorVersion.version == ccx_version).first()

    if version is not None:
        test = Test.query.filter(Test.commit == version.commit).first()

        if test is None:
            raise TestNotFoundException(
                'There are no tests available for CCExtractor version {version}'.format(version=version.version)
            )

        return get_data_for_test(test, 'CCExtractor {version}'.format(version=version.version))

    raise TestNotFoundException('There is no CCExtractor version known as {version}'.format(version=ccx_version))


@mod_test.route('/commit/<commit_hash>')
@template_renderer('test/by_id.html')
def by_commit(commit_hash):
    # Look up the hash, find a test for it and redirect
    test = Test.query.filter(Test.commit == commit_hash).first()

    if test is None:
        raise TestNotFoundException('There is no test available for commit {commit}'.format(commit=commit_hash))

    return get_data_for_test(test, 'commit {commit}'.format(commit=commit_hash))


@mod_test.route('/master/<platform>')
@template_renderer('test/by_id.html')
def latest_commit_info(platform):
    try:
        platform = TestPlatform.from_string(platform)
    except ValueError:
        abort(404)
    # Look up the hash of the latest commit
    commit_hash = GeneralData.query.filter(GeneralData.key == 'last_commit').first().value
    test = Test.query.filter(Test.commit == commit_hash, Test.platform == platform).first()

    if test is None:
        raise TestNotFoundException('There is no test available for commit {commit}'.format(commit=commit_hash))

    return get_data_for_test(test, 'master {commit}'.format(commit=commit_hash))


@mod_test.route('/diff/<test_id>/<regression_test_id>/<output_id>')
def generate_diff(test_id, regression_test_id, output_id):
    from run import config
    if request.is_xhr:
        # Fetch test
        result = TestResultFile.query.filter(and_(
            TestResultFile.test_id == test_id,
            TestResultFile.regression_test_id == regression_test_id,
            TestResultFile.regression_test_output_id == output_id
        )).first()

        if result is not None:
            path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestResults')
            return result.generate_html_diff(path)

        abort(404)

    abort(403, 'generate_diff')


def serve_file_download(file_name, content_type='application/octet-stream'):
    from run import config

    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'LogFiles', file_name)
    response = make_response()
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = content_type
    response.headers['Content-Disposition'] = 'attachment; filename={name}'.format(name=file_name)
    response.headers['Content-Length'] = os.path.getsize(file_path)
    response.headers['X-Accel-Redirect'] = '/' + os.path.join('logfile-download', file_name)

    return response


@mod_test.route('/log-files/<test_id>')
def download_build_log_file(test_id):
    from run import config
    test = Test.query.filter(Test.id == test_id).first()

    if test is not None:
        # Fetch logfile
        log_file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'LogFiles', test_id + '.txt')

        if os.path.isfile(log_file_path):
            return serve_file_download(test_id + '.txt', 'text/plain')

        raise TestNotFoundException('Build log for Test {id} not found'.format(id=test_id))

    raise TestNotFoundException('Test with id {id} not found'.format(id=test_id))
