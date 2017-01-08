import os

from flask import Blueprint, g, jsonify
from flask import abort
from flask import make_response
from flask import request
from sqlalchemy import and_

from decorators import template_renderer
from mod_home.models import CCExtractorVersion
from mod_regression.models import Category, regressionTestCategoryLinkTable, \
    RegressionTestOutput, RegressionTest
from mod_test.models import Fork, Test, TestProgress, TestResult, \
    TestResultFile, TestType

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
    return {
        'tests': Test.query.order_by(Test.id.desc()).limit(50).all(),
        'TestType': TestType
    }


def get_data_for_test(test, title=None):
    if title is None:
        title = 'test {id}'.format(id=test.id)

    populated_categories = g.db.query(
        regressionTestCategoryLinkTable.c.category_id).subquery()
    categories = Category.query.filter(Category.id.in_(
        populated_categories)).order_by(Category.name.asc()).all()
    results = [{
                   'category': category,
                   'tests': [{
                                 'test': rt,
                                 'result': next((r for r in test.results if
                                                 r.regression_test_id ==
                                                 rt.id), None),
                                 'files': TestResultFile.query.filter(and_(
                                     TestResultFile.test_id == test.id,
                                     TestResultFile.regression_test_id ==
                                     rt.id)).all()
                             } for rt in category.regression_tests]
               } for category in categories]
    for category in results:
        error = False
        for category_test in category['tests']:
            result = category_test['result']
            if result is not None and result.exit_code != result.expected_rc:
                error = True
                break
            if len(category_test['files']) > 0:
                for result_file in category_test['files']:
                    if result_file.got is not None:
                        error = True
                        break
            else:
                # We need to check if the regression test had any file that
                #  shouldn't have been ignored.
                outputs = RegressionTestOutput.query.filter(and_(
                    RegressionTestOutput.regression_id ==
                    category_test['test'].id,
                    RegressionTestOutput.ignore is False
                )).all()
                got = None
                if len(outputs) > 0:
                    error = True
                    got = 'error'
                # Add dummy entry for pass/fail display
                category_test['files'] = [TestResultFile(-1, -1, -1, '', got)]
            if error:
                break
        category['error'] = error
    results.sort()
    return {
        'test': test,
        'TestType': TestType,
        'results': results,
        'title': title
    }


@mod_test.route('/<test_id>')
@template_renderer()
def by_id(test_id):
    test = Test.query.filter(Test.id == test_id).first()
    if test is None:
        raise TestNotFoundException(
            'Test with id {id} does not exist'.format(id=test_id))
    return get_data_for_test(test)


@mod_test.route('/ccextractor/<ccx_version>')
@template_renderer('test/by_id.html')
def ccextractor_version(ccx_version):
    # Look up the hash, find a test for it and redirect
    version = CCExtractorVersion.query.filter(
        CCExtractorVersion.version == ccx_version).first()
    if version is not None:
        test = Test.query.filter(Test.commit == version.commit).first()
        if test is None:
            raise TestNotFoundException(
                'There are no tests available for CCExtractor version '
                '{version}'.format(version=version.version))
        return get_data_for_test(
            test, 'CCExtractor {version}'.format(version=version.version))
    raise TestNotFoundException(
        'There is no CCExtractor version known as {version}'.format(
            version=ccx_version))


@mod_test.route('/commit/<commit_hash>')
@template_renderer('test/by_id.html')
def by_commit(commit_hash):
    # Look up the hash, find a test for it and redirect
    test = Test.query.filter(Test.commit == commit_hash).first()
    if test is None:
        raise TestNotFoundException(
            'There is no test available for commit {commit}'.format(
                commit=commit_hash))
    return get_data_for_test(
        test, 'commit {commit}'.format(commit=commit_hash))


@mod_test.route('/diff/<test_id>/<regression_test_id>/<output_id>')
def generate_diff(test_id, regression_test_id, output_id):
    from run import config
    if request.is_xhr:
        # Fetch test
        result = TestResultFile.query.filter(and_(
            TestResultFile.test_id == test_id,
            TestResultFile.regression_test_id == regression_test_id,
            TestResultFile.regression_test_output_id == output_id)).first()
        if result is not None:
            path = os.path.join(
                config.get('SAMPLE_REPOSITORY', ''), 'TestResults')
            return result.generate_html_diff(path)
        abort(404)
    abort(403, 'generate_diff')


def serve_file_download(file_name, content_type='application/octet-stream'):
    from run import config

    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''),
                             'LogFiles', file_name)
    response = make_response()
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = content_type
    response.headers['Content-Disposition'] = \
        'attachment; filename=%s' % file_name
    response.headers['Content-Length'] = \
        os.path.getsize(file_path)
    response.headers['X-Accel-Redirect'] = \
        '/' + os.path.join('logfile-download', file_name)
    return response


@mod_test.route('/log-files/<test_id>')
def download_build_log_file(test_id):
    from run import config
    test = Test.query.filter(Test.id == test_id).first()
    if test is not None:
        # Fetch logfile
        log_file_path = os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'LogFiles',
            test_id + '.txt')
        if os.path.isfile(log_file_path):
            return serve_file_download(test_id + '.txt',
                                       'text/plain')
        raise TestNotFoundException('Build log for Test %s not found' %
                                    test_id)
    raise TestNotFoundException('Test with id %s not found' % test_id)
