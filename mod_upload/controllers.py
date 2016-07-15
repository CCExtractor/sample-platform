from flask import Blueprint

from models import Upload

mod_upload = Blueprint('upload', __name__)


@mod_upload.route('/')
def index():
    pass


@mod_upload.route('/ftp')
def ftp_index():
    pass


@mod_upload.route('/ftp/filezilla')
def ftp_filezilla():
    pass


@mod_upload.route('/new', methods=['GET', 'POST'])
def upload():
    pass


@mod_upload.route('/process')
def process_index():
    pass


@mod_upload.route('/<upload_id>', methods=['GET', 'POST'])
def process_id(upload_id):
    pass


@mod_upload.route('/link/<upload_id>', methods=['GET', 'POST'])
def link_id(upload_id):
    pass


@mod_upload.route('/delete/<upload_id>')
def delete_id(upload_id):
    pass
