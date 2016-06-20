import hashlib
import hmac
import json

import ipaddress
import requests
import sys

import subprocess
from flask import Blueprint, g, request, flash, session, redirect, url_for, \
    abort, jsonify
from git import Repo, InvalidGitRepositoryError

from decorators import template_renderer

mod_deploy = Blueprint('deploy', __name__)

# Check if python version is less than 2.7.7
if sys.version_info < (2, 7, 7):
    # http://blog.turret.io/hmac-in-go-python-ruby-php-and-nodejs/
    def compare_digest(a, b):
        """
        ** From Django source **
        Run a constant time comparison against two strings
        Returns true if a and b are equal.
        a and b must both be the same length, or False is
        returned immediately
        """
        if len(a) != len(b):
            return False

        result = 0
        for ch_a, ch_b in zip(a, b):
            result |= ord(ch_a) ^ ord(ch_b)
        return result == 0
else:
    compare_digest = hmac.compare_digest


@mod_deploy.route('/deploy', methods=['GET', 'POST'])
@template_renderer()
def deploy():
    from run import app
    if request.method != 'POST':
        return 'OK'
    else:
        abort_code = 418
        # Do initial validations on required headers
        if 'X-Github-Event' not in request.headers or \
            'X-Github-Delivery' not in request.headers or \
            'X-Hub-Signature' not in request.headers or not \
            request.is_json or 'User-Agent' not in request.headers\
            or not request.headers.get('User-Agent').startswith(
                    'GitHub-Hookshot/'):
            abort(abort_code)

        request_ip = ipaddress.ip_address(u'{0}'.format(request.remote_addr))
        hook_blocks = requests.get('https://api.github.com/meta').json()[
            'hooks']

        # Check if the POST request is from GitHub
        for block in hook_blocks:
            if ipaddress.ip_address(request_ip) in ipaddress.ip_network(block):
                break
        else:
            abort(abort_code)

        if request.headers.get('X-GitHub-Event') == "ping":
            return json.dumps({'msg': 'Hi!'})
        if request.headers.get('X-GitHub-Event') != "push":
            return json.dumps({'msg': "Wrong event type"})

        hash_algorithm, github_signature = request.headers.get(
            'X-Hub-Signature').split('=', 1)
        mac = hmac.new(app.config['GITHUB_DEPLOY_KEY'], msg=request.data,
                       digestmod=hashlib.__dict__.get(hash_algorithm))
        if not compare_digest(mac.hexdigest(), github_signature.encode()):
            abort(abort_code)

        payload = request.get_json()
        if payload is None:
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
        subprocess.Popen(["sudo", "service", "platform", "reload"])
        return json.dumps({'msg': 'Platform upgraded to commit %s' %
                                  commit_hash})
