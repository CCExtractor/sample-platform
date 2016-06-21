import json

from flask import Blueprint, request, abort, g
from github import GitHub

from mod_deploy.controllers import request_from_github, is_valid_signature

mod_ci = Blueprint('ci', __name__)


@mod_ci.route('/start-ci', methods=['GET', 'POST'])
@request_from_github()
def start_ci():
    if request.method != 'POST':
        return 'OK'
    else:
        abort_code = 418

        event = request.headers.get('X-GitHub-Event')
        if event == "ping":
            return json.dumps({'msg': 'Hi!'})

        x_hub_signature = request.headers.get('X-Hub-Signature')
        if not is_valid_signature(x_hub_signature, request.data,
                                  g.github['ci_key']):
            g.log.warning('CI signature failed: %s' % x_hub_signature)
            abort(abort_code)

        payload = request.get_json()
        if payload is None:
            g.log.warning('CI payload is empty: %s' % payload)
            abort(abort_code)

        gh = GitHub(access_token=g.github['bot_token'])
        # If it's a push, run the tests
        if event == "push":
            pass
        # If it's a PR, run the tests
        elif event == "pull_request":
            # States possible:
            # opened
            # synchronize
            gh.repos(g.github['repository_owner'])(
                g.github['repository']).statuses(
                payload['pull_request']['merge_commit_sha']).post(
                state="failure",
                target_url="https://sampleplatform.ccextractor.org/",
                description="Test results", context="CI")
            pass
        else:
            # Unknown type
            g.log.warning('CI unrecognized event: %s' % event)

        return json.dumps({'msg': 'EOL'})
