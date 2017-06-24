import base64
import hashlib
import os
import traceback

from flask import Blueprint, g, make_response, render_template, request, \
    redirect, url_for
from werkzeug.utils import secure_filename

from decorators import template_renderer, get_menu_entries
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion
from mod_sample.models import Sample
from mod_upload.forms import UploadForm, DeleteQueuedSampleForm, \
    FinishQueuedSampleForm
from models import Upload, QueuedSample, UploadLog, FTPCredentials, Platform

mod_upload = Blueprint('upload', __name__)


class QueuedSampleNotFoundException(Exception):

    def __init__(self, message):
        Exception.__init__(self)
        self.message = message


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


@mod_upload.errorhandler(QueuedSampleNotFoundException)
@template_renderer('upload/queued_sample_not_found.html', 404)
def not_found(error):
    return {
        'message': error.message
    }


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
@template_renderer()
def upload():
    from run import config
    form = UploadForm()
    if form.validate_on_submit():
        # Process uploaded file
        uploaded_file = request.files[form.file.name]
        if uploaded_file:
            filename = secure_filename(uploaded_file.filename)
            temp_path = os.path.join(
                config.get('SAMPLE_REPOSITORY', ''), 'TempFiles', filename)
            # Save to temporary location
            uploaded_file.save(temp_path)
            # Get hash and check if it's already been submitted
            hash_sha256 = hashlib.sha256()
            with open(temp_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            file_hash = hash_sha256.hexdigest()

            queued_sample = QueuedSample.query.filter(
                QueuedSample.sha == file_hash).first()
            sample = Sample.query.filter(Sample.sha == file_hash).first()

            if sample is not None or queued_sample is not None:
                # Remove existing file and notice user
                os.remove(temp_path)
                form.errors['file'] = [
                    'Sample with same hash already uploaded or queued']
            else:
                filename, file_extension = os.path.splitext(filename)
                queued_sample = QueuedSample(file_hash, file_extension,
                                             filename, g.user.id)
                final_path = os.path.join(
                    config.get('SAMPLE_REPOSITORY', ''), 'QueuedFiles',
                    queued_sample.filename)
                # Move to queued folder
                os.rename(temp_path, final_path)
                # Add to queue
                g.db.add(queued_sample)
                g.db.commit()
                # Redirect
                return redirect(url_for('.index'))
    return {
        'form': form,
        'accept': form.accept,
        'upload_size': (config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)),
    }



def upload_ftp(db, path):
    from run import config, log
    temp_path = str(path)
    hash_sha256 = hashlib.sha256()
    log.debug('Checking hash value')
    with open(temp_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    file_hash = hash_sha256.hexdigest()
    log.debug('Checking queued_sample exist or not with same hash ')
    queued_sample = QueuedSample.query.filter(
        QueuedSample.sha == file_hash).first()
    sample = Sample.query.filter(Sample.sha == file_hash).first()
    log.debug('Checking existence in the database')
    if sample is not None or queued_sample is not None:
        # Remove existing file and notice user
        os.remove(temp_path)
        log.debug(
            temp_path + ' Sample with same hash already uploaded or queued')
    else:
        log.debug('Adding to the database ' + str(path))
        split_arr = temp_path.split('/')
        filename = split_arr[-1]
        user_id = split_arr[-2]
        filename, file_extension = os.path.splitext(filename)
        queued_sample = QueuedSample(file_hash, file_extension,
                                     filename, user_id)
        final_path = os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'QueuedFiles',
            queued_sample.filename)
        # Move to queued folder
        log.debug('Changing the path to ' + final_path)
        os.rename(temp_path, final_path)
        # Add to queue
        db.add(queued_sample)
        db.commit()


@mod_upload.route('/<upload_id>', methods=['GET', 'POST'])
@login_required
@template_renderer()
def process_id(upload_id):
    from run import config
    # Fetch upload id
    queued_sample = QueuedSample.query.filter(QueuedSample.id ==
                                              upload_id).first()
    if queued_sample is not None:
        if queued_sample.user_id == g.user.id:
            # Allowed to process
            versions = CCExtractorVersion.query.all()
            form = FinishQueuedSampleForm(request.form)
            form.version.choices = [(v.id, v.version) for v in versions]
            if form.validate_on_submit():
                # Store in DB
                db_committed = False
                temp_path = os.path.join(
                    config.get('SAMPLE_REPOSITORY', ''), 'QueuedFiles',
                    queued_sample.filename)
                final_path = os.path.join(
                    config.get('SAMPLE_REPOSITORY', ''), 'TestFiles',
                    queued_sample.filename)
                try:
                    extension = queued_sample.extension[1:] if len(
                        queued_sample.extension) > 0 else ""
                    sample = Sample(queued_sample.sha, extension,
                                    queued_sample.original_name)
                    g.db.add(sample)
                    g.db.flush([sample])
                    uploaded = Upload(
                        g.user.id, sample.id, form.version.data,
                        Platform.from_string(form.platform.data),
                        form.parameters.data, form.notes.data
                    )
                    g.db.add(uploaded)
                    g.db.delete(queued_sample)
                    g.db.commit()
                    db_committed = True
                except:
                    traceback.print_exc()
                    g.db.rollback()
                # Move file
                if db_committed:
                    os.rename(temp_path, final_path)
                    return redirect(
                        url_for('sample.sample_by_id', sample_id=sample.id))

            return {
                'form': form,
                'queued_sample': queued_sample
            }

    # Raise error
    raise QueuedSampleNotFoundException()


@mod_upload.route('/link/<upload_id>')
@login_required
@template_renderer()
def link_id(upload_id):
    # Fetch upload id
    queued_sample = QueuedSample.query.filter(QueuedSample.id ==
                                              upload_id).first()
    if queued_sample is not None:
        if queued_sample.user_id == g.user.id:
            # Allowed to link
            user_uploads = Upload.query.filter(
                Upload.user_id == g.user.id).all()
            return {
                'samples': [u.sample for u in user_uploads],
                'queued_sample': queued_sample
            }

    # Raise error
    raise QueuedSampleNotFoundException()


@mod_upload.route('/link/<upload_id>/<sample_id>')
@login_required
def link_id_confirm(upload_id, sample_id):
    # Fetch upload id
    queued_sample = QueuedSample.query.filter(QueuedSample.id ==
                                              upload_id).first()
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if queued_sample is not None and sample is not None:
        if queued_sample.user_id == g.user.id and sample.upload.user_id == \
                g.user.id:
            # Allowed to link
            return redirect(url_for('.index'))

    # Raise error
    raise QueuedSampleNotFoundException()


@mod_upload.route('/delete/<upload_id>', methods=['GET', 'POST'])
@login_required
@template_renderer()
def delete_id(upload_id):
    from run import config
    # Fetch upload id
    queued_sample = QueuedSample.query.filter(QueuedSample.id ==
                                              upload_id).first()
    if queued_sample is not None:
        if queued_sample.user_id == g.user.id or g.user.is_admin:
            # Allowed to remove
            form = DeleteQueuedSampleForm(request.form)
            if form.validate_on_submit():
                # Delete file, then delete from database
                file_path = os.path.join(
                    config.get('SAMPLE_REPOSITORY', ''), 'QueuedFiles',
                    queued_sample.filename)
                os.remove(file_path)
                g.db.delete(queued_sample)
                g.db.commit()

                return redirect(url_for('.index'))

            return {
                'form': form,
                'queued_sample': queued_sample
            }

    # Raise error
    raise QueuedSampleNotFoundException()
