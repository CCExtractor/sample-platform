from flask import Blueprint

from mod_test.models import Fork, Test, TestProgress

mod_test = Blueprint('test', __name__)


@mod_test.route('/test/<test_id>', methods=['GET', 'POST'])
def test(test_id):
    pass
