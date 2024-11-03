"""Maintain logic to perform CRUD operations on regression tests."""

from flask import (Blueprint, abort, flash, g, jsonify, redirect, request,
                   url_for)
from sqlalchemy import and_

from decorators import template_renderer
from mod_auth.controllers import check_access_rights, login_required
from mod_auth.models import Role
from mod_regression.forms import (AddCategoryForm, AddCorrectOutputForm,
                                  AddTestForm, ConfirmationForm, EditTestForm,
                                  RemoveCorrectOutputForm)
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput,
                                   RegressionTestOutputFiles)
from mod_sample.models import Sample, Tag
from mod_test.models import TestResultFile
from utility import serve_file_download

mod_regression = Blueprint('regression', __name__)


@mod_regression.before_app_request
def before_app_request() -> None:
    """Curate menu entries before app request."""
    g.menu_entries['regression'] = {
        'title': 'Regression tests',
        'icon': 'industry',
        'route': 'regression.index'
    }


@mod_regression.route('/')
@template_renderer()
def index():
    """Display all regression tests."""
    return {
        'tests': RegressionTest.query.all(),
        'categories': Category.query.order_by(Category.name.asc()).all(),
        'tags': Tag.query.all()
    }


@mod_regression.route('/sample/<sample_id>')
@template_renderer()
def by_sample(sample_id):
    """
    Display regression tests based on the given sample.

    :param sample_id: id of the sample
    :type sample_id: int
    :return: regression tests of the sample
    :rtype: dict
    """
    # Show all regression tests for sample
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is None:
        g.log.error(f'requested sample with id: {sample_id} not found!')
        abort(404)
    return {
        'sample': sample,
        'tests': RegressionTest.query.filter(
            RegressionTest.sample_id == sample.id).all()
    }


@mod_regression.route('/test/<regression_id>/view')
@template_renderer()
def test_view(regression_id):
    """
    Show a single regression test.

    :param regression_id: id of the regression test
    :type regression_id: int
    :return: Regression test
    :rtype: dict
    """
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        g.log.error(f'requested regression test with id: {regression_id} not found!')
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
    Delete the regression test.

    Requires contributor or admin role.

    :param regression_id: The ID of the Regression Test
    :type regression_id: int
    :return: Redirect
    """
    # Show a Single Test
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        g.log.error(f'requested regression test with id: {regression_id} not found!')
        abort(404)

    form = ConfirmationForm()

    if form.validate_on_submit():
        g.db.delete(test)
        g.db.commit()
        g.log.warning(f'regression test with id: {regression_id} deleted!')
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
    Edit regression test.

    Requires contributor or admin role.

    param regression_id : The ID of the Regression Test
    type regression_id : int
    """
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        g.log.error(f'requested regression test with id: {regression_id} not found!')
        abort(404)

    form = EditTestForm(request.form)
    form.sample_id.choices = [(sam.id, sam.sha) for sam in Sample.query.all()]
    form.category_id.choices = [(cat.id, cat.name) for cat in Category.query.all()]

    if form.validate_on_submit():
        # Remove category for test and add again.
        old_category = Category.query.filter(Category.id == test.categories[0].id).first()
        old_category.regression_tests.remove(test)

        new_category = Category.query.filter(Category.id == form.category_id.data).first()
        new_category.regression_tests.append(test)

        test.sample_id = form.sample_id.data
        test.command = form.command.data
        test.category_id = form.category_id.data
        test.expected_rc = form.expected_rc.data
        test.input_type = InputType.from_string(form.input_type.data)
        test.output_type = OutputType.from_string(form.output_type.data)
        test.description = form.description.data

        g.db.commit()
        g.log.info(f'regression test with id: {regression_id} updated!')
        return redirect(url_for('.test_view', regression_id=regression_id))

    if not form.is_submitted():
        # Populate form with current set sample values
        form.sample_id.data = test.sample_id
        form.command.data = test.command
        form.category_id.data = test.categories[0].id
        form.expected_rc.data = test.expected_rc
        form.input_type.data = test.input_type.value
        form.output_type.data = test.output_type.value
        form.description.data = test.description

    return {'form': form, 'regression_id': regression_id}


@mod_regression.route('/test/<regression_id>/toggle')
@login_required
@check_access_rights([Role.contributor, Role.admin])
def toggle_active_status(regression_id):
    """
    Change active status of the regression test.

    :param regression_id: id of the regression test
    :type regression_id: int
    :return: response of status toggle
    :rtype: dict
    """
    regression_test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()
    if regression_test is None:
        g.log.error(f'requested regression test with id: {regression_id} not found!')
        abort(404)
    regression_test.active = not regression_test.active
    g.db.commit()
    return jsonify({
        "status": "success",
        "active": str(regression_test.active)
    })


@mod_regression.route('/test/<regression_test_output_id>/download', methods=['GET'])
@login_required
def test_result_file(regression_test_output_id):
    """View the output files of the regression test."""
    rto = RegressionTestOutput.query.filter(RegressionTestOutput.id == regression_test_output_id).first()
    if rto is None:
        g.log.error(f'requested regression test output with id: {regression_test_output_id} not found!')
        abort(404)
    return serve_file_download(rto.filename_correct, 'TestResults')


@mod_regression.route('/test/<regression_test_output_id>/download/variant', methods=['GET'])
@login_required
def multiple_test_result_file(regression_test_output_id):
    """View the output files of the regression test (variants)."""
    rtof = RegressionTestOutputFiles.query.filter(RegressionTestOutputFiles.id == regression_test_output_id).first()
    if rtof is None:
        g.log.error(f'requested regression test output file with id: {regression_test_output_id} not found!')
        abort(404)
    return serve_file_download(rtof.file_hashes + rtof.output.correct_extension, 'TestResults')


@mod_regression.route('/test/new', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def test_add():
    """
    Add a regression test.

    :return: form to add regression test
    :rtype: dict
    """
    form = AddTestForm(request.form)
    form.sample_id.choices = [(sam.id, sam.sha) for sam in Sample.query.all()]
    form.category_id.choices = [(cat.id, cat.name) for cat in Category.query.all()]
    if form.validate_on_submit():
        new_test = RegressionTest(
            sample_id=form.sample_id.data,
            command=form.command.data,
            category_id=form.category_id.data,
            expected_rc=form.expected_rc.data,
            input_type=InputType.from_string(form.input_type.data),
            output_type=OutputType.from_string(form.output_type.data),
            description=form.description.data,
        )
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
    Delete the category.

    :param category_id: The ID of the Category
    :type category_id: int
    :return: form and category
    :rtype: dict
    """
    category = Category.query.filter(Category.id == category_id).first()

    if category is None:
        g.log.error(f'requested category with id: {category_id} not found!')
        abort(404)

    form = ConfirmationForm()

    if form.validate_on_submit():
        g.db.delete(category)
        g.db.commit()
        g.log.warning(f'category with id: {category_id} deleted!')
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
    Edit regression test category.

    :param category_id: The ID of the Regression Test Category
    :type category_id: int
    :return: form and category id
    :rtype: dict
    """
    category = Category.query.filter(Category.id == category_id).first()

    if category is None:
        g.log.error(f'requested category with id: {category_id} not found!')
        abort(404)

    form = AddCategoryForm(request.form)
    if form.validate():
        category.name = form.category_name.data
        category.description = form.category_description.data
        g.db.commit()
        g.log.info(f'category with id: {category_id} updated!')
        flash('Category Updated')
        return redirect(url_for('.index'))

    if not form.is_submitted():
        # Populate form with current set category values
        form.category_name.data = category.name
        form.category_description.data = category.description

    return {'form': form, 'category_id': category_id}


@mod_regression.route('/category_add', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def category_add():
    """
    Add a regression test category.

    :return: form to add category
    :rtype: dict
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


@mod_regression.route('/test/<regression_id>/output/new', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def output_add(regression_id):
    """
    Add New Output.

    Requires contributor or admin role.

    param regression_id : The ID of the Regression Test
    type regression_id : int
    """
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        g.log.error(f'requested regression test with id: {regression_id} not found!')
        abort(404)

    form = AddCorrectOutputForm(request.form)
    test_result = TestResultFile.query.filter(
        and_(TestResultFile.regression_test_id == regression_id, TestResultFile.got.isnot(None))
    ).order_by(TestResultFile.test_id.desc()).limit(50).all()
    check_doubles = {}
    for result in test_result:
        if result.got not in check_doubles:
            append = True
            for output_file in result.regression_test_output.multiple_files:
                if result.got.strip() == output_file.file_hashes.strip():
                    append = False
                    break
            if append:
                check_doubles[result.got] = int(result.test_id)
    form.output_file.choices = [(output.id, output.filename_correct + ' (original)') for output in test.output_files]
    form.test_id.choices = [f'Test id {test_id} with output {got}' for got, test_id in check_doubles.items()]
    if form.validate_on_submit():
        test_data = form.test_id.data.strip().split()
        new_output = RegressionTestOutputFiles(
            regression_test_output_id=form.output_file.data,
            file_hashes=test_data[5]
        )
        g.db.add(new_output)
        g.db.commit()
        g.log.warning(f'Output file for RegressionTestOutput id: {form.output_file.data} added!')
        return redirect(url_for('.test_view', regression_id=regression_id))
    return {'form': form, 'regression_id': regression_id}


@mod_regression.route('/test/<regression_id>/output/remove', methods=['GET', 'POST'])
@template_renderer()
@login_required
@check_access_rights([Role.contributor, Role.admin])
def output_remove(regression_id):
    """
    Remove an Output File.

    Requires contributor or admin role.

    param regression_id : The ID of the Regression Test
    type regression_id : int
    """
    test = RegressionTest.query.filter(RegressionTest.id == regression_id).first()

    if test is None:
        g.log.error(f'requested regression test with id: {regression_id} not found!')
        abort(404)

    form = RemoveCorrectOutputForm(request.form)
    form.output_file.choices = [(a.id, a.file_hashes + ' (variant)')
                                for r in test.output_files for a in r.multiple_files]
    if form.validate_on_submit():
        variant_file = RegressionTestOutputFiles.query.filter(
            RegressionTestOutputFiles.id == form.output_file.data
        ).first()
        g.db.delete(variant_file)
        g.db.commit()
        g.log.warning(f'Output file with id: {form.output_file.data} deleted!')
        return redirect(url_for('.test_view', regression_id=regression_id))
    return {'form': form, 'regression_id': regression_id}
