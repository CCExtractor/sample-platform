from __future__ import print_function

import os
import sys
import traceback

from flask import Flask, g
from werkzeug.contrib.fixers import ProxyFix
from werkzeug.routing import BaseConverter

from config_parser import parse_config
from database import create_session
from decorators import template_renderer
from log_configuration import LogConfiguration
from mailer import Mailer
from mod_auth.controllers import mod_auth
from mod_ci.controllers import mod_ci
from mod_deploy.controllers import mod_deploy
from mod_home.controllers import mod_home
from mod_regression.controllers import mod_regression
from mod_sample.controllers import mod_sample
from mod_test.controllers import mod_test
from mod_upload.controllers import mod_upload
from mod_customized.controllers import mod_customized

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
# Load config
config = parse_config('config')
app.config.from_mapping(config)
try:
    app.config['DEBUG'] = os.environ['DEBUG']
except KeyError:
    app.config['DEBUG'] = False

# Init logger
log_configuration = LogConfiguration(app.root_path, 'platform', app.config['DEBUG'])
log = log_configuration.create_logger("Platform")


def install_secret_keys(application, secret_session='secret_key', secret_csrf='secret_csrf'):
    """
    Configure the SECRET_KEY from a file in the instance directory.

    If the file does not exist, print instructions to create it from a shell with a random key, then exit.
    """
    do_exit = False
    session_file_path = os.path.join(application.root_path, secret_session)
    csrf_file_path = os.path.join(application.root_path, secret_csrf)
    try:
        with open(session_file_path, 'rb') as session_file:
            application.config['SECRET_KEY'] = session_file.read()
    except IOError:
        traceback.print_exc()
        print('Error: No secret key. Create it with:')
        if not os.path.isdir(os.path.dirname(session_file)):
            print('mkdir -p', os.path.dirname(session_file))
        print('head -c 24 /dev/urandom >', session_file)
        do_exit = True

    try:
        with open(csrf_file_path, 'rb') as csrf_file:
            application.config['CSRF_SESSION_KEY'] = csrf_file.read()
    except IOError:
        print('Error: No secret CSRF key. Create it with:')
        if not os.path.isdir(os.path.dirname(csrf_file)):
            print('mkdir -p', os.path.dirname(csrf_file))
        print('head -c 24 /dev/urandom >', csrf_file)
        do_exit = True

    if do_exit:
        sys.exit(1)


if 'TESTING' not in os.environ or os.environ['TESTING'] == 'False':
    install_secret_keys(app)


# Expose submenu method for jinja templates
def sub_menu_open(menu_entries, active_route):
    for menu_entry in menu_entries:
        if 'route' in menu_entry and menu_entry['route'] == active_route:
            return True
    return False


app.jinja_env.globals.update(sub_menu_open=sub_menu_open)
app.jinja_env.add_extension('jinja2.ext.loopcontrols')


# Add datetime format filter
def date_time_format(value, fmt='%Y-%m-%d %H:%M:%S'):
    return value.strftime(fmt)


def get_github_issue_link(issue_id):
    return 'https://www.github.com/{org}/{repo}/issues/{id}'.format(
        org=config.get('GITHUB_OWNER', ''),
        repo=config.get('GITHUB_REPOSITORY', ''),
        id=issue_id
    )


def filename(filepath):
    return os.path.basename(filepath)


app.jinja_env.filters['date'] = date_time_format
app.jinja_env.filters['issue_link'] = get_github_issue_link
app.jinja_env.filters['filename'] = filename


class RegexConverter(BaseConverter):

    def __init__(self, url_map, *items):
        super(RegexConverter, self).__init__(url_map)
        self.regex = items[0]


# Allow regexes in routes
app.url_map.converters['regex'] = RegexConverter


@app.errorhandler(404)
@template_renderer('404.html', 404)
def not_found(error):
    return


@app.errorhandler(500)
@template_renderer('500.html', 500)
def internal_error(error):
    log.debug('500 error: {err}'.format(err=error))
    log.debug('Stacktrace:')
    log.debug(traceback.format_exc())
    return


@app.errorhandler(403)
@template_renderer('403.html', 403)
def forbidden(error):
    user_name = 'Guest' if g.user is None else g.user.name
    user_role = 'Guest' if g.user is None else g.user.role.value
    log.debug('{u} (role: {r}) tried to access {page}'.format(u=user_name, r=user_role, page=error.description))

    return {
        'user_role': user_role,
        'endpoint': error.description
    }


@app.before_request
def before_request():
    g.menu_entries = {}
    g.db = create_session(app.config['DATABASE_URI'])
    g.mailer = Mailer(
        app.config.get('EMAIL_DOMAIN', ''), app.config.get('EMAIL_API_KEY', ''), 'CCExtractor.org CI Platform'
    )
    g.version = "0.1"
    g.log = log
    g.github = get_github_config(app.config)


def get_github_config(config):
    return {
        'deploy_key': config.get('GITHUB_DEPLOY_KEY', ''),
        'ci_key': config.get('GITHUB_CI_KEY', ''),
        'bot_token': config.get('GITHUB_TOKEN', ''),
        'bot_name': config.get('GITHUB_BOT', ''),
        'repository_owner': config.get('GITHUB_OWNER', ''),
        'repository': config.get('GITHUB_REPOSITORY', '')
    }


@app.teardown_appcontext
def teardown(exception):
    db = g.get('db', None)
    if db is not None:
        db.remove()


# Register blueprints
app.register_blueprint(mod_auth, url_prefix='/account')  # Needs to be first
app.register_blueprint(mod_upload, url_prefix='/upload')
app.register_blueprint(mod_regression, url_prefix='/regression')
app.register_blueprint(mod_sample, url_prefix='/sample')
app.register_blueprint(mod_home)
app.register_blueprint(mod_deploy)
app.register_blueprint(mod_test, url_prefix="/test")
app.register_blueprint(mod_ci)
app.register_blueprint(mod_customized, url_prefix='/custom')

if __name__ == '__main__':
    # Run in development mode; Werkzeug server
    # Load variables for running (if defined)
    ssl_context = host = None
    proto = 'https'
    key = app.config.get('SSL_KEY', 'cert/key.key')
    cert = app.config.get('SSL_CERT', 'cert/cert.cert')

    if len(key) == 0 or len(cert) == 0:
        ssl_context = 'adhoc'
    else:
        ssl_context = (cert, key)

    server_name = app.config.get('0.0.0.0')
    port = app.config.get('SERVER_PORT', 443)

    print('Server should be running soon on {0}://{1}:{2}'.format(proto, server_name, port))
    if server_name != '127.0.0.1':
        host = '0.0.0.0'
    app.run(host, port, app.config['DEBUG'], ssl_context=ssl_context)
