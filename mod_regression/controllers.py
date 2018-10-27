"""
mod_regression Controllers
===================
In this module, we are trying to create, update, edit, delete and
other various operations on regression tests.
"""
from flask import Blueprint, g, abort, jsonify, abort

from decorators import template_renderer
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role
from mod_regression.models import Category, RegressionTest
from mod_sample.models import Sample

mod_regression = Blueprint('regression', __name__)


@mod_regression.before_app_request
def before_app_request():
    g.menu_entries['regression'] = {
        'title': 'Regression tests',
        'icon': 'industry',
        'route': 'regression.index'
    }


@mod_regression.route('/')
@template_renderer()
def index():
    return {
        'tests': RegressionTest.query.all(),
        'categories': Category.query.order_by(Category.name.asc()).all()
    }


@mod_regression.route('/sample/<sample_id>')
@template_renderer()
def by_sample(sample_id):
    # Show all regression tests for sample
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is None:
        abort(404)
    return {
        'sample': sample,
        'tests': RegressionTest.query.filter(
            RegressionTest.sample_id == sample.id).all()
    }


@mod_regression.route('/test/<regression_id>/view')
@template_renderer()
def test_view(regression_id):
    # Show a single regression test
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        abort(404)

    return {
        'test': test
    }


@mod_regression.route('/test/<regression_id>/delete')
@template_renderer()
@check_access_rights([Role.contributor, Role.admin]) # confirmation to delete regression test
def test_delete(regression_id):
    """
    Function to delete regression tests
    :param regression_id: Id of the regression test to be deleted
    :type regression_id: int
    """

    regression_test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()  # find regression test corresponding to id given in argument

    if regression_test is None:
        abort(404) # aborting if a regression test with the given id doesn't exist

    customized_tests = CustomizedTest.query.filter(CustomizedTest.regression_id == regression_id).all() # finding all customized tests that have the given regression test
    regression_test_outputs = RegressionTestOutput.query.filter(RegressionTestOutput.regression_id == regression_id).all() # finding all regression test outputs that have the given regression test
    test_results = TestResult.query.filter(TestResult.regression_test_id == regression_id).all() # finding all test results that have the given regression test
    test_result_files = TestResultFile.query.filter(TestResultFile.regression_test_id == regression_id).all() # finding all test result files that have the given regression test

    # Deleting the tests/files which have the given regression test

    for customized_test in customized_tests:
        g.db.delete(customized_test)
    for regression_test_output in regression_test_outputs:
        g.db.delete(regression_test_output)
    for test_result in test_results:
        g.db.delete(test_result)
    for test_result_file in test_result_files:
        g.db.delete(test_result_file)

    g.db.delete(regression_test) # deleting the regression test
    g.db.commit() #  flush pending changes
    return redirect(url_for('.index')) # redirecting to the regression test page


@mod_regression.route('/test/<regression_id>/edit')
def test_edit(regression_id):
    # Edit the regression test
    pass


@mod_regression.route('/test/<regression_id>/toggle')
@check_access_rights([Role.admin])
def toggle_active_status(regression_id):
    # Change active status of the regression test
    regression_test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()
    if regression_test is None:
        abort(404)
    regression_test.active = not regression_test.active
    g.db.commit()
    return jsonify({
        "status": "success",
        "active": str(regression_test.active)
    })


@mod_regression.route('/test/<regression_id>/results')
def test_result(regression_id):
    # View the output files of the regression test
    pass


@mod_regression.route('/test/new')
def test_add():
    # Add a new regression test
    pass


@mod_regression.route('/category/<category_id>/delete')
def category_delete(category_id):
    # Delete a regression test category
    pass


@mod_regression.route('/category/<category_id>/edit')
def category_edit(category_id):
    # Edit a regression test category
    pass


@mod_regression.route('/category/add')
def category_add():
    # Add a regression test category
    pass
