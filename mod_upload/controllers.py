"""
mod_upload Controllers
===================
In this module, we are trying to add functionality regarding upload
and finalizing of samples through html or ftp. Reporting issues along
with submitting sample
"""
import base64
import hashlib
import json
import os
import traceback
import magic
import mimetypes

import shutil
import requests

from flask import Blueprint, g, make_response, render_template, request,  redirect, url_for, flash
from werkzeug.utils import secure_filename

from decorators import template_renderer, get_menu_entries
from git import Repo, InvalidGitRepositoryError, GitCommandError
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role, User
from mod_home.models import CCExtractorVersion
from mod_sample.models import Sample, ForbiddenExtension, ForbiddenMimeType, Issue
from mod_upload.forms import UploadForm, DeleteQueuedSampleForm, \
    FinishQueuedSampleForm
from .models import Upload, QueuedSample, UploadLog, FTPCredentials, Platform

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
        g.user, 'Platform mgmt', 'cog', all_entries=[
            {'title': 'Upload manager', 'icon': 'upload', 'route':
                'upload.index_admin', 'access': [Role.admin]}
        ]
    )
    if 'config' in g.menu_entries and 'entries' in config_entries:
        g.menu_entries['config']['entries'] = config_entries['entries'] + g.menu_entries['config']['entries']
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
        'queue': QueuedSample.query.filter(QueuedSample.user_id == g.user.id).all(),
        'messages': UploadLog.query.filter(UploadLog.user_id == g.user.id).order_by(UploadLog.id.desc()).all()
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


def make_github_issue(title, body=None, labels=None):
    """
    Create an issue on github.com using the given parameters.

    :param title: The issue title
    :type title: str
    :param body: The content in the body
    :type body: str
    :param labels: The labels to add to the issue
    :type labels: list[str]
    :return: void
    :rtype: void
    """
    from run import config
    # Our url to create issues via POST
    url = 'https://api.github.com/repos/{org}/{repo}/issues'.format(
        org=config.get('GITHUB_OWNER', ''),
        repo=config.get('GITHUB_REPOSITORY', '')
    )
    session = requests.Session()
    session.auth = (g.user.email, g.user.github_token)
    # Create an authenticated session to create the issue
    # Create our issue
    issue = {'title': title,
             'body': body,
             'labels': labels}
    # Add the issue to our repository
    r = session.post(url, json.dumps(issue))

    if r.status_code == 201:
        return r.json()

    return 'ERROR'


@mod_upload.route('/ftp')
@login_required
@template_renderer()
def ftp_index():
    from run import config

    credentials = FTPCredentials.query.filter(FTPCredentials.user_id == g.user.id).first()

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

    credentials = FTPCredentials.query.filter(FTPCredentials.user_id == g.user.id).first()

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
            password=base64.b64encode(credentials.password.encode()).decode()
        )
    )
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = 'text/xml'
    response.headers['Content-Disposition'] = 'attachment; filename=FileZilla.xml'

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
            temp_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TempFiles', filename)
            # Save to temporary location
            uploaded_file.save(temp_path)
            # Get hash and check if it's already been submitted
            file_hash = create_hash_for_sample(temp_path)
            if sample_already_uploaded(file_hash):
                # Remove existing file and notice user
                os.remove(temp_path)
                form.errors['file'] = ['Sample with same hash already uploaded or queued']
            else:
                add_sample_to_queue(file_hash, temp_path, g.user.id, g.db)
                return redirect(url_for('.index'))
    return {
        'form': form,
        'accept': form.accept,
        'upload_size': (config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)),
    }


@mod_upload.route('/<upload_id>', methods=['GET', 'POST'])
@login_required
@template_renderer()
def process_id(upload_id):
    """
    Process the sample that is uploaded to the platform

    :param upload_id: The identity of uploaded file that will be processed
    :type upload_id: str
    :return: Process progress in form and queue the sample
    :rtype: str
    """
    from run import config, log
    # Fetch upload id
    queued_sample = QueuedSample.query.filter(QueuedSample.id == upload_id).first()
    if queued_sample is not None:
        if queued_sample.user_id == g.user.id:
            # Allowed to process
            versions = CCExtractorVersion.query.all()
            form = FinishQueuedSampleForm(request.form)
            form.version.choices = [(v.id, v.version) for v in versions]
            if form.validate_on_submit():
                # Store in DB
                db_committed = False
                repo_folder = config.get('SAMPLE_REPOSITORY', '')
                temp_path = os.path.join(repo_folder, 'QueuedFiles', queued_sample.filename)
                final_path = os.path.join(repo_folder, 'TestFiles', queued_sample.filename)
                try:
                    extension = queued_sample.extension[1:] if len(queued_sample.extension) > 0 else ""
                    sample = Sample(queued_sample.sha, extension, queued_sample.original_name)
                    g.db.add(sample)
                    g.db.flush([sample])
                    uploaded = Upload(
                        g.user.id,
                        sample.id,
                        form.version.data,
                        Platform.from_string(form.platform.data),
                        form.parameters.data,
                        form.notes.data
                    )
                    g.db.add(uploaded)
                    g.db.delete(queued_sample)
                    g.db.commit()
                    db_committed = True
                except Exception:
                    traceback.print_exc()
                    g.db.rollback()
                # Move file
                if db_committed:
                    if form.report.data == 'y':
                        data = ""
                        try:
                            kvm_name = config.get('KVM_LINUX_NAME', '')
                            repo = Repo(os.path.join(repo_folder, 'vm_data', kvm_name, 'unsafe-ccextractor'))
                            data = repo.git.show('{branch}:{file}'.format(
                                branch=repo.heads.master,
                                file='.github/ISSUE_TEMPLATE.md')
                            )
                        except InvalidGitRepositoryError:
                            log.critical(" Could not open CCExtractor's repository ")

                        version = CCExtractorVersion.query.filter(CCExtractorVersion.id == form.version.data).first()
                        data = data.replace('**X.X**', version.version)
                        data = data.replace('[ ] I have read', '[X] I have read')
                        data = data.replace('[ ] I have checked', '[X] I have checked')
                        data = data.replace('[ ] I have used', '[X] I have used')
                        data = data.replace(
                            '[ ] I am an active contributor to CCExtractor.',
                            '[X] I used the platform to submit this issue!'
                        )
                        data = data.replace(
                            '`-autoprogram`',
                            '`{param}`'.format(param=form.parameters.data, version=form.version.data)
                        )
                        platform = form.platform.data.title()
                        data = data.replace('[ ] ' + platform, '[X] ' + platform)
                        # Remove everything starting from the video links
                        data = data[:data.find('**Video links**')]
                        # Append our own content here
                        sample_link = url_for('sample.sample_by_id', sample_id=sample.id, _external=True)
                        data += '**Sample**\n\n[Sample {id}]({link}) was uploaded on the sample platform.\n'.format(
                            id=sample.id, link=sample_link)
                        data += '**Extra information**\n\n*Notes:*\n{notes}\n*Description:*\n{desc}'.format(
                            notes=form.notes.data, desc=form.IssueBody.data)
                        issue_title = '[BUG] {data}'.format(data=form.IssueTitle.data)
                        issue_data = make_github_issue(issue_title, data, ['bug', 'sample' + str(sample.id)])

                        if issue_data != 'ERROR':
                            issue_id = issue_data['number']
                            issue_title = issue_data['title']
                            issue_user = issue_data['user']['login']
                            issue_date = issue_data['created_at']
                            issue_status = issue_data['state']
                            issue = Issue(sample.id, issue_id, issue_date, issue_title, issue_user, issue_status)
                            g.db.add(issue)
                            g.db.commit()
                        else:
                            flash('Could not submit an issue on GitHub (did you revoke permissions for the  platform?).'
                                  ' Please submit it manually.')

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
    queued_sample = QueuedSample.query.filter(QueuedSample.id == upload_id).first()
    if queued_sample is not None:
        if queued_sample.user_id == g.user.id:
            # Allowed to link
            user_uploads = Upload.query.filter(Upload.user_id == g.user.id).all()

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
    queued_sample = QueuedSample.query.filter(QueuedSample.id == upload_id).first()
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if queued_sample is not None and sample is not None:
        if queued_sample.user_id == g.user.id and sample.upload.user_id == g.user.id:
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
    queued_sample = QueuedSample.query.filter(QueuedSample.id == upload_id).first()
    if queued_sample is not None:
        if queued_sample.user_id == g.user.id or g.user.is_admin:
            # Allowed to remove
            form = DeleteQueuedSampleForm(request.form)
            if form.validate_on_submit():
                # Delete file, then delete from database
                file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'QueuedFiles', queued_sample.filename)
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


def create_hash_for_sample(file_path):
    """
    Creates the has for given file.

    :param file_path: The path to the file that needs to be hashed.
    :type file_path: str
    :return: A hash for the given file.
    :rtype: str
    """
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)

    return hash_sha256.hexdigest()


def sample_already_uploaded(file_hash):
    """
    Checks if a given file hash is already present in the database.

    :param file_hash: The file hash that needs to be checked.
    :type file_hash: str
    :return: True if the file is already in the database as a sample or queued file.
    :rtype: bool
    """
    queued_sample = QueuedSample.query.filter(QueuedSample.sha == file_hash).first()
    sample = Sample.query.filter(Sample.sha == file_hash).first()

    return sample is not None or queued_sample is not None


def add_sample_to_queue(file_hash, temp_path, user_id, db):
    """
    Adds a sample to the queue.
    :param file_hash: The hash of the file
    :type file_hash: str
    :param temp_path: The current location of the file
    :type temp_path: str
    :param user_id: The user ID
    :type user_id: int
    :param db: The database connection
    :type db: sqlalchemy.orm.scoped_session
    :return: Nothing
    :rtype: void
    """
    from run import config
    # Fetch file name from file path
    uploaded_file = os.path.basename(temp_path)
    filename, file_extension = os.path.splitext(uploaded_file)
    queued_sample = QueuedSample(file_hash, file_extension,
                                 filename, user_id)
    final_path = os.path.join(
        config.get('SAMPLE_REPOSITORY', ''), 'QueuedFiles',
        queued_sample.filename)
    # Move to queued folder
    os.rename(temp_path, final_path)
    # Add to queue
    db.add(queued_sample)
    db.commit()


def upload_ftp(db, path):
    from run import log, config
    temp_path = str(path)
    path_parts = temp_path.split(os.path.sep)
    # We assume /home/{uid}/ as specified in the model
    user_id = path_parts[2]
    user = User.query.filter(User.id == user_id).first()
    filename, file_extension = os.path.splitext(path)
    # FIRST, check extension. We can't limit extensions on FTP as we can on the web interface.
    log.debug('Checking if {path} has a forbidden extension'.format(path=temp_path))
    forbidden = ForbiddenExtension.query.filter(ForbiddenExtension.extension == file_extension[1:]).first()

    if forbidden is not None:
        log.error('User {name} tried to upload a file with a forbidden extension ({extension})!'.format(
            name=user.name, extension=file_extension[1:]
        ))
        os.remove(temp_path)
        return

    mimetype = magic.from_file(temp_path, mime=True)
    # Check for permitted mimetype
    forbidden_mime = ForbiddenMimeType.query.filter(ForbiddenMimeType.mimetype == mimetype).first()

    if forbidden_mime is not None:
        log.error('User {name} tried to upload a file with a forbidden mimetype ({mimetype})!'.format(
            name=user.name, mimetype=mimetype
        ))
        os.remove(temp_path)
        return

    # Check for permitted extension
    extension = mimetypes.guess_extension(mimetype)

    if extension is not None:
        forbidden_real = ForbiddenExtension.query.filter(ForbiddenExtension.extension == extension[1:]).first()
        if forbidden_real is not None:
            log.error('User {name} tried to upload a file with a forbidden extension ({extension})!'.format(
                name=user.name, extension=extension[1:]
            ))
            os.remove(temp_path)
            return

    log.debug('Moving file to temporary folder and changing permissions...')
    # Move the file to a temporary location
    filename = secure_filename(temp_path.replace('/home/' + user_id + '/', ''))
    intermediate_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TempFiles', filename)
    # Save to temporary location
    log.debug('Copy {old} to {new}'.format(old=temp_path, new=intermediate_path))
    shutil.copy(temp_path, intermediate_path)
    os.remove(temp_path)

    log.debug('Checking hash value for {path}'.format(path=intermediate_path))
    file_hash = create_hash_for_sample(intermediate_path)

    if sample_already_uploaded(file_hash):
        # Remove existing file
        log.debug('Sample already exists: {path}'.format(
            path=intermediate_path))
        os.remove(intermediate_path)
    else:
        add_sample_to_queue(file_hash, intermediate_path, user.id, db)
