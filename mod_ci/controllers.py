import json
import subprocess

from flask import Blueprint, request, abort, g
from git import Repo, InvalidGitRepositoryError

from mod_deploy.controllers import request_from_github, is_valid_signature

mod_ci = Blueprint('ci', __name__)


@mod_ci.route('/start-ci', methods=['GET', 'POST'])
@request_from_github()
def start_ci():
    from run import app
    if request.method != 'POST':
        return 'OK'
    else:
        abort_code = 418

        event = request.headers.get('X-GitHub-Event')
        if event == "ping":
            return json.dumps({'msg': 'Hi!'})

        x_hub_signature = request.headers.get('X-Hub-Signature')
        if not is_valid_signature(x_hub_signature, request.data,
                                  g.deploy_key):
            abort(abort_code)

        payload = request.get_json()
        if payload is None:
            abort(abort_code)

        return json.dumps({'msg': 'EOL'})
