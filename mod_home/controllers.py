"""
mod_home Controllers
===================
In this module, we are trying to maintain all functionalities
running on homepage.
"""
from flask import Blueprint, g, render_template

from decorators import template_renderer
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion, GeneralData
from urllib import unquote

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

@mod_home_route('/confirm')
def confirm():
    """
    Used For Asking a Confirmation
    :return:
    """
    desc = request.args['desc']
    action_url = unquote(request.args['action_url'])

    # template_renderer doesn't give me an option to pass extra arguments other than a template and a status code
    return render_template('home/confirm.html', desc=desc, action_url=action_url)
