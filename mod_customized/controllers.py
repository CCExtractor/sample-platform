"""
mod_customized Controllers
===================
In this module, users can test their fork branch with customized set of regression tests
"""
from flask import Blueprint, g, request, redirect, url_for
from github import GitHub, ApiError
from datetime import datetime
from dateutil.relativedelta import relativedelta

from decorators import template_renderer, get_menu_entries
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role, User
from mod_test.models import Fork, Test, TestType, TestPlatform
from mod_customized.forms import TestForkForm
from mod_customized.models import TestFork
from mod_test.controllers import get_data_for_test, TestNotFoundException
from mod_auth.controllers import fetch_username_from_token
from sqlalchemy import and_

mod_customized = Blueprint('custom', __name__)


@check_access_rights([Role.tester, Role.contributor, Role.admin])
@mod_customized.before_app_request
def before_app_request():
    if g.user is not None:
        g.menu_entries['custom'] = {
            'title': 'Customize Test',
            'icon': 'code-fork',
            'route': 'custom.index'
        }


@mod_customized.route('/', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.tester, Role.contributor, Role.admin])
@template_renderer()
def index():
    fork_test_form = TestForkForm(request.form)
    username = fetch_username_from_token()
    commit_options = False
    if username is not None:
        gh = GitHub(access_token=g.github['bot_token'])
        repository = gh.repos(username)(g.github['repository'])
        # Only commits since last month
        today_date = datetime.now()
        last_month = today_date - relativedelta(months=1)
        commit_since = last_month.isoformat() + 'Z'
        commits = repository.commits().get(since=commit_since)
        commit_arr = []
        for commit in commits:
            commit_url = commit['html_url']
            commit_sha = commit['sha']
            commit_option = (
                '<a href="{url}">{sha}</a>').format(url=commit_url, sha=commit_sha)
            commit_arr.append((commit_sha, commit_option))
        if len(commit_arr) > 0:
            fork_test_form.commit_select.choices = commit_arr
            commit_options = True
    if username is not None and fork_test_form.add.data and fork_test_form.validate_on_submit():
        import requests
        commit_hash = fork_test_form.commit_hash.data
        repo = g.github['repository']
        platforms = fork_test_form.platform.data
        api_url = ('https://api.github.com/repos/{user}/{repo}/commits/{hash}').format(
            user=username, repo=repo, hash=commit_hash
        )
        response = requests.get(api_url)
        if response.status_code == 404:
            fork_test_form.commit_hash.errors.append('Wrong Commit Hash')
        else:
            add_test_to_kvm(username, repo, commit_hash, platforms)
            return redirect(url_for('custom.index'))
    tests = Test.query.filter(and_(TestFork.user_id == g.user.id, TestFork.test_id == Test.id)).order_by(
        Test.id.desc()).limit(50).all()
    return {
        'addTestFork': fork_test_form,
        'commit_options': commit_options,
        'tests': tests,
        'TestType': TestType,
        'GitUser': username
    }


def add_test_to_kvm(username, repo, commit_hash, platforms):
    fork_url = ('https://github.com/{user}/{repo}.git').format(
        user=username, repo=g.github['repository']
    )
    fork = Fork.query.filter(Fork.github == fork_url).first()
    if fork is None:
        fork = Fork(fork_url)
        g.db.add(fork)
        g.db.commit()
    for platform in platforms:
        platform = TestPlatform.from_string(platform)
        test = Test(platform, TestType.commit, fork.id, 'master', commit_hash)
        g.db.add(test)
        g.db.commit()
        test_fork = TestFork(g.user.id, test.id)
        g.db.add(test_fork)
        g.db.commit()
