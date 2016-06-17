from flask import Blueprint, g
from github import GitHub

from decorators import template_renderer
from mod_home.models import CCExtractorVersion

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
    from run import app
    # TODO: do not look this up on every request
    g = GitHub(access_token=app.config.get('GITHUB_TOKEN', ''))
    ref = g.repos(app.config.get('GITHUB_OWNER', ''))(
        app.config.get('GITHUB_REPOSITORY', '')).git().refs(
        'heads/master').get()

    last_release = CCExtractorVersion.query.order_by(
            CCExtractorVersion.released.desc()).first()
    return {
        'ccx_last_release': last_release,
        'ccx_latest_commit': ref['object']['sha']
    }


@mod_home.route('/about')
@template_renderer()
def about():
    return {}
