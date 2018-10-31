"""
mod_regression Controllers
===================
In this module, we are trying to create, update, edit, delete and
other various operations on regression tests.
"""

from flask import Blueprint, g, abort, jsonify, abort, redirect, url_for, request, flash

from decorators import template_renderer
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role
from mod_regression.models import Category, RegressionTest, RegressionTestOutput
from mod_regression.forms import AddCategoryForm
from mod_sample.models import Sample
from mod_customized.models import CustomizedTest
from mod_test.models import Test, TestResult, TestResultFile

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
@check_access_rights([Role.contributor, Role.admin])
def test_delete(regression_id):
    """
    Delete the regression test

    :param regression_id: The ID of the Regression Test
    :type int
    :return: Redirect
    """
    # Show a Single Test
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        abort(404)

    g.db.delete(test)
    g.db.commit()

    return redirect(url_for('.index'))


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


@mod_regression.route('/category_add', methods=['GET', 'POST'])
@template_renderer()
@check_access_rights([Role.admin])
def category_add():
    """
    Function to add a regression test category
    """
    form = AddCategoryForm(request.form)
    if form.validate():
        new_category = Category(
            name=form.category_name.data, description=form.category_description.data)
        g.db.add(new_category)
        g.db.commit()
        flash('New Category Added')
        return redirect(url_for('.index'))
    return {'form': form}
