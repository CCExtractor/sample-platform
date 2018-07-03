"""
mod_home Controllers
===================
In this module, we are trying to maintain all functionalities
running on homepage.
"""
from flask import Blueprint, g

from decorators import template_renderer
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion, GeneralData

mod_home = Blueprint('home', __name__)


@mod_home.before_app_request
def before_app_request():
    g.menu_entries['home'] = {
        'title': 'Home',
        'icon': 'home',
        'route': 'home.index'
    }


@mod_home.route('/', methods=['GET', 'POST'])
@template_renderer()
def index():
    last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first().value
    last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first()
    test_access = False
    if g.user is not None and g.user.role in [Role.tester, Role.contributor, Role.admin]:
        test_access = True
    return {
        'ccx_last_release': last_release,
        'ccx_latest_commit': last_commit,
        'test_access': test_access
    }


@mod_home.route('/about')
@template_renderer()
def about():
    return {}
