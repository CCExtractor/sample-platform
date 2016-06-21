import hashlib
import hmac
import json
import subprocess
from functools import wraps

import requests
from flask import Blueprint, request, abort, g
from git import Repo, InvalidGitRepositoryError
from ipaddress import ip_address, ip_network

from compare_digest import compare_digest

mod_deploy = Blueprint('deploy', __name__)


def request_from_github(abort_code=418):
    def decorator(f):
        """
        Decorator that checks if a request is a GitHub hook request
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.method != 'POST':
                return 'OK'
            else:
                # Do initial validations on required headers
                if 'X-Github-Event' not in request.headers:
                    abort(abort_code)
                if 'X-Github-Delivery' not in request.headers:
                    abort(abort_code)
                if 'X-Hub-Signature' not in request.headers:
                    abort(abort_code)
                if not request.is_json:
                    abort(abort_code)
                if 'User-Agent' not in request.headers:
                    abort(abort_code)
                ua = request.headers.get('User-Agent')
                if not ua.startswith('GitHub-Hookshot/'):
                    abort(abort_code)

                request_ip = ip_address(u'{0}'.format(request.remote_addr))
                meta_json = requests.get('https://api.github.com/meta').json()
                hook_blocks = meta_json['hooks']

                # Check if the POST request is from GitHub
                for block in hook_blocks:
                    if ip_address(request_ip) in ip_network(block):
                        break
                else:
                    g.log.info("Unauthorized attempt to deploy by IP %s" %
                               request_ip)
                    abort(abort_code)
                return f(*args, **kwargs)
        return decorated_function
    return decorator


def is_valid_signature(x_hub_signature, data, private_key):
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    mac = hmac.new(private_key, msg=data, digestmod=algorithm)
    return compare_digest(mac.hexdigest(), github_signature.encode())


@mod_deploy.route('/deploy', methods=['GET', 'POST'])
@request_from_github()
def deploy():
    from run import app
    if request.method != 'POST':
        return 'OK'
    else:
        abort_code = 418

        event = request.headers.get('X-GitHub-Event')
        if event == "ping":
            return json.dumps({'msg': 'Hi!'})
        if event != "push":
            return json.dumps({'msg': "Wrong event type"})

        x_hub_signature = request.headers.get('X-Hub-Signature')
        if not is_valid_signature(x_hub_signature, request.data,
                                  g.deploy_key):
            g.log.warning('Deploy signature failed: %s' % x_hub_signature)
            abort(abort_code)

        payload = request.get_json()
        if payload is None:
            g.log.warning('Deploy payload is empty: %s' % payload)
            abort(abort_code)

        if payload['ref'] != 'refs/heads/master':
            return json.dumps({'msg': 'Not master; ignoring'})

        # Update code
        try:
            repo = Repo(app.config['INSTALL_FOLDER'])
        except InvalidGitRepositoryError:
            return json.dumps({'msg': 'Folder is not a valid git directory'})

        try:
            origin = repo.remote('origin')
        except ValueError:
            return json.dumps({'msg': 'Remote origin does not exist'})

        fetch_info = origin.fetch()
        if len(fetch_info) == 0:
            return json.dumps({'msg': 'Didn\'t fetch any information from '
                                      'remote!'})

        # Pull code (finally)
        pull_info = origin.pull()

        if len(pull_info) == 0:
            return json.dumps({'msg': 'Didn\'t pull any information from '
                                      'remote!'})

        if pull_info[0].flags > 128:
            return json.dumps({'msg': 'Didn\'t pull any information from '
                                      'remote!'})

        commit_hash = pull_info[0].commit.hexsha
        build_commit = 'build_commit = "%s"' % commit_hash
        with open('build_commit.py', 'w') as f:
            f.write(build_commit)

        # Reload platform service
        g.log.info('Platform upgraded to commit %s' % commit_hash)
        subprocess.Popen(["sudo", "service", "platform", "reload"])
        return json.dumps({'msg': 'Platform upgraded to commit %s' %
                                  commit_hash})
