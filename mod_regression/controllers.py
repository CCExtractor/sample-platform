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
from mod_regression.models import Category, RegressionTest, InputType, OutputType
from mod_regression.forms import AddCategoryForm, AddTestForm, ConfirmationForm
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


@mod_regression.route('/test/<regression_id>/delete', methods=['GET', 'POST'])
@template_renderer()
@login_required
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

    form = ConfirmationForm()

    if form.validate_on_submit():
        g.db.delete(test)
        g.db.commit()
        flash('Regression Test Deleted')
        return redirect(url_for('.index'))

    return {
        'form': form,
        'regression_id': regression_id
    }


@mod_regression.route('/test/<regression_id>/edit', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def test_edit(regression_id):
    """
    Function  to edit regression test
    param regression_id : The ID of the Regression Test
    type regression_id : int
    """

    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if(test is None):
        abort(404)

    form = AddTestForm(request.form)
    form.sample_id.choices = [(sam.id, sam.sha) for sam in Sample.query.all()]
    form.category_id.choices = [(cat.id, cat.name) for cat in Category.query.all()]
    if form.validate_on_submit():
        # removing test from its previous category
        category = Category.query.filter(Category.id == test.categories[0].id).first()
        category.regression_tests.remove(test)

        # editing data
        test.sample_id = form.sample_id.data
        test.command = form.command.data
        test.category_id = form.category_id.data
        test.expected_rc = form.expected_rc.data
        test.input_type = InputType.from_string(form.input_type.data)
        test.output_type = OutputType.from_string(form.output_type.data)

        # adding test to its new category
        category = Category.query.filter(Category.id == form.category_id.data).first()
        category.regression_tests.append(test)

        g.db.commit()
        flash('Regression Test Updated')
        return redirect(url_for('.test_view',regression_id=regression_id))
    return {'form': form, 'regression_id': regression_id}


@mod_regression.route('/test/<regression_id>/toggle')
@login_required
@check_access_rights([Role.contributor, Role.admin])
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


@mod_regression.route('/test/new', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def test_add():
    """
    Function to add a regression test
    """
    form = AddTestForm(request.form)
    form.sample_id.choices = [(sam.id, sam.sha) for sam in Sample.query.all()]
    form.category_id.choices = [(cat.id, cat.name) for cat in Category.query.all()]
    if form.validate_on_submit():
        new_test = RegressionTest(
            sample_id=form.sample_id.data, command=form.command.data,
            category_id=form.category_id.data, expected_rc=form.expected_rc.data,
            input_type=InputType.from_string(form.input_type.data), output_type=OutputType.from_string(form.output_type.data))
        g.db.add(new_test)
        category = Category.query.filter(Category.id == form.category_id.data).first()
        category.regression_tests.append(new_test)
        g.db.commit()
        return redirect(url_for('.index'))
    return {'form': form}


@mod_regression.route('/category/<category_id>/delete', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def category_delete(category_id):
    """
    Delete the category
    :param category_id: The ID of the Category
    :type int
    :return: Redirect
    """

    category = Category.query.filter(Category.id == category_id).first()

    if category is None:
        abort(404)

    form = ConfirmationForm()

    if form.validate_on_submit():
        g.db.delete(category)
        g.db.commit()
        return redirect(url_for('.index'))
    return {
        'form': form,
        'category': category
    }


@mod_regression.route('/category/<category_id>/edit', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def category_edit(category_id):
    """
    Function  to edit regression test category
    param category_id : The ID of the Regression Test Category
    type category_id : int
    """

    test = Category.query.filter(Category.id == category_id).first()

    if(test is None):
        abort(404)

    form = AddCategoryForm(request.form)
    if form.validate():
        test.name = form.category_name.data
        test.description = form.category_description.data
        g.db.commit()
        flash('Category Updated')
        return redirect(url_for('.index'))
    return {'form': form, 'category_id': category_id}


@mod_regression.route('/category_add', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
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
