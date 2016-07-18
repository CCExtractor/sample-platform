import base64

from flask import Blueprint, g, make_response, render_template

from decorators import template_renderer, get_menu_entries
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role
from models import Upload, QueuedSample, UploadLog, FTPCredentials

mod_upload = Blueprint('upload', __name__)


@mod_upload.before_app_request
def before_app_request():
    g.menu_entries['upload'] = {
        'title': 'Upload',
        'icon': 'upload',
        'route': 'upload.index'
    }
    config_entries = get_menu_entries(
        g.user, 'Platform mgmt', 'cog', [], '', [
            {'title': 'Upload manager', 'icon': 'upload', 'route':
                'upload.index_admin', 'access': [Role.admin]}
        ]
    )
    if 'config' in g.menu_entries and 'entries' in config_entries:
        g.menu_entries['config']['entries'] = \
            config_entries['entries'] + g.menu_entries['config']['entries']
    else:
        g.menu_entries['config'] = config_entries


@mod_upload.route('/')
@login_required
@template_renderer()
def index():
    return {
        'queue': QueuedSample.query.filter(
            QueuedSample.user_id == g.user.id).all(),
        'messages': UploadLog.query.filter(
            UploadLog.user_id == g.user.id).order_by(
            UploadLog.id.desc()).all()
    }


@mod_upload.route('/manage')
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def index_admin():
    return {
        'queue': QueuedSample.query.all(),
        'messages': UploadLog.query.order_by(UploadLog.id.desc()).all()
    }


@mod_upload.route('/ftp')
@login_required
@template_renderer()
def ftp_index():
    from run import config
    credentials = FTPCredentials.query.filter(FTPCredentials.user_id ==
                                              g.user.id).first()
    if credentials is None:
        credentials = FTPCredentials(g.user.id)
        g.db.add(credentials)
        g.db.commit()

    return {
        'host': config.get('SERVER_NAME', ''),
        'port': config.get('FTP_PORT', ''),
        'username': credentials.user_name,
        'password': credentials.password
    }


@mod_upload.route('/ftp/filezilla')
@login_required
def ftp_filezilla():
    from run import config
    credentials = FTPCredentials.query.filter(FTPCredentials.user_id ==
                                              g.user.id).first()
    if credentials is None:
        credentials = FTPCredentials(g.user.id)
        g.db.add(credentials)
        g.db.commit()

    response = make_response(
        render_template(
            'upload/filezilla_template.xml',
            host=config.get('SERVER_NAME', ''),
            port=config.get('FTP_PORT', ''),
            username=credentials.user_name,
            password=base64.b64encode(credentials.password)
        )
    )
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = 'text/xml'
    response.headers['Content-Disposition'] = \
        'attachment; filename=FileZilla.xml'

    return response


@mod_upload.route('/new', methods=['GET', 'POST'])
@login_required
def upload():
    pass


@mod_upload.route('/<upload_id>', methods=['GET', 'POST'])
@login_required
def process_id(upload_id):
    pass


@mod_upload.route('/link/<upload_id>', methods=['GET', 'POST'])
@login_required
def link_id(upload_id):
    pass


@mod_upload.route('/delete/<upload_id>')
@login_required
def delete_id(upload_id):
    pass
