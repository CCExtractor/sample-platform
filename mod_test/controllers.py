from flask import Blueprint, g
from sqlalchemy import and_

from decorators import template_renderer
from mod_regression.models import Category, regressionTestCategoryLinkTable
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
@template_renderer('test/sample_not_found.html', 404)
def not_found(error):
    return {
        'message': error.message
    }


@mod_test.route('/')
@template_renderer()
def index():
    return {
        'tests': Test.query.order_by(Test.id.desc()).limit(10).all()
    }


@mod_test.route('/<test_id>')
@template_renderer()
def by_id(test_id):
    test = Test.query.filter(Test.id == test_id).first()
    if test is None:
        raise TestNotFoundException(
            'Test with id {id} does not exist'.format(id=test_id))
    populated_categories = g.db.query(
        regressionTestCategoryLinkTable.c.category_id).subquery()
    categories = Category.query.filter(Category.id.in_(
        populated_categories)).order_by(Category.name.asc()).all()
    results = [{
                   'category': category,
                   'tests': [{
                                 'test': rt,
                                 'result': next(r for r in test.results if
                                                r.regression_test_id ==
                                                rt.id),
                                 'files': TestResultFile.query.filter(and_(
                                     TestResultFile.test_id == test.id,
                                     TestResultFile.regression_test_id ==
                                     rt.id)).all()
                             } for rt in category.regression_tests]
               } for category in categories]
    for category in results:
        error = False
        for category_test in category['tests']:
            if category_test['result'].exit_code != 0:
                error = True
                break
            for result_file in category_test['files']:
                if result_file.got is not None:
                    error = True
                    break
            if error:
                break
        category['error'] = error
    results.sort()
    return {
        'test': test,
        'TestType': TestType,
        'results': results
    }


@mod_test.route('/ccextractor/<ccx_version>')
def ccextractor_version(ccx_version):
    pass


@mod_test.route('/commit/<commit_hash>')
def by_commit(commit_hash):
    pass


@mod_test.route('/sample/<sample_id>')
def by_sample(sample_id):
    pass
