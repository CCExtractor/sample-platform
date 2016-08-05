from flask import Blueprint, g

from decorators import template_renderer
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role
from mod_regression.models import Category, RegressionTest

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
        'categories': Category.query.order_by(Category.name.desc()).all()
    }


@mod_regression.route('/sample/<sample_id>')
def by_sample(sample_id):
    # Show all regression tests for sample
    pass


@mod_regression.route('/test/<regression_id>/view')
def test_view(regression_id):
    pass


@mod_regression.route('/test/<regression_id>/delete')
def test_delete(regression_id):
    pass


@mod_regression.route('/test/<regression_id>/edit')
def test_edit(regression_id):
    pass


@mod_regression.route('/test/<regression_id>/results')
def test_result(regression_id):
    pass


@mod_regression.route('/test/new')
def test_add():
    pass


@mod_regression.route('/category/<category_id>/delete')
def category_delete(category_id):
    pass


@mod_regression.route('/category/<category_id>/edit')
def category_edit(category_id):
    pass


@mod_regression.route('/category/add')
def category_add():
    pass
