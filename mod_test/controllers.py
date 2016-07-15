from flask import Blueprint

from mod_test.models import Fork, Test, TestProgress

mod_test = Blueprint('test', __name__)


@mod_test.route('/')
def index():
    pass


@mod_test.route('/<test_id>')
def test(test_id):
    pass


@mod_test.route('/ccextractor/<ccx_version>')
def ccextractor_version(ccx_version):
    pass


@mod_test.route('/commit/<commit_hash>')
def commit(commit_hash):
    pass


@mod_test.route('/sample/<sample_id>')
def sample(sample_id):
    pass
