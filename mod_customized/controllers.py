"""logic to allow users to test their fork branch with customized set of regression tests."""

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from flask import Blueprint, flash, g, redirect, request, url_for
from github import ApiError, GitHub
from sqlalchemy import and_

import mod_auth.models
import mod_customized.forms
import mod_customized.models
import mod_regression.models
import mod_test.controllers
import mod_test.models
from decorators import get_menu_entries, template_renderer
from mod_auth.controllers import (check_access_rights,
                                  fetch_username_from_token, login_required)
from mod_auth.models import Role, User
from mod_customized.forms import TestForkForm
from mod_customized.models import CustomizedTest, TestFork
from mod_regression.models import (Category, RegressionTest,
                                   regressionTestLinkTable)
from mod_test.controllers import TestNotFoundException, get_data_for_test
from mod_test.models import Fork, Test, TestPlatform, TestType

mod_customized = Blueprint('custom', __name__)  # type: ignore


@mod_customized.before_app_request  # type: ignore
def before_app_request() -> None:
    """Run before app request to ready menu items."""
    if g.user is not None:
        g.menu_entries['custom'] = {
            'title': 'Customize Test',
            'icon': 'code-fork',
            'route': 'custom.index',
            'access': [Role.tester, Role.contributor, Role.admin]
        }


@mod_customized.route('/', methods=['GET', 'POST'])  # type: ignore
@login_required
@check_access_rights([Role.tester, Role.contributor, Role.admin])
@template_renderer()
def index():
    """
    Display a form to allow users to run tests.

    User can enter commit or select the commit from their repo that are not more than 30 days old.
    User can customized test based on selected regression tests and platforms.
    Also Display list of customized tests started by user.
    User will be redirected to the same page on submit.
    """
    fork_test_form = TestForkForm(request.form)
    username = fetch_username_from_token()
    commit_options = False
    if username is not None:
        gh = GitHub(access_token=g.github['bot_token'])
        repository = gh.repos(username)(g.github['repository'])
        # Only commits since last month
        last_month = datetime.now() - timedelta(days=30)
        commit_since = last_month.isoformat() + 'Z'
        commits = repository.commits().get(since=commit_since)
        commit_arr = []
        for commit in commits:
            commit_url = commit['html_url']
            commit_sha = commit['sha']
            commit_option = (
                '<a href="{url}">{sha}</a>').format(url=commit_url, sha=commit_sha)
            commit_arr.append((commit_sha, commit_option))
        # If there are commits present, display it on webpage
        if len(commit_arr) > 0:
            fork_test_form.commit_select.choices = commit_arr
            commit_options = True
        fork_test_form.regression_test.choices = [(regression_test.id, regression_test)
                                                  for regression_test in RegressionTest.query.all()]
        if fork_test_form.add.data and fork_test_form.validate_on_submit():
            import requests
            regression_tests = fork_test_form.regression_test.data
            commit_hash = fork_test_form.commit_hash.data
            repo = g.github['repository']
            platforms = fork_test_form.platform.data
            api_url = ('https://api.github.com/repos/{user}/{repo}/commits/{hash}').format(
                user=username, repo=repo, hash=commit_hash
            )
            # Show error if github fails to recognize commit
            response = requests.get(api_url)
            if response.status_code == 500:
                fork_test_form.commit_hash.errors.append('Error contacting Github')
            elif response.status_code != 200:
                fork_test_form.commit_hash.errors.append('Wrong Commit Hash')
            else:
                add_test_to_kvm(username, commit_hash, platforms, regression_tests)
                return redirect(url_for('custom.index'))

    populated_categories = g.db.query(regressionTestLinkTable.c.category_id).subquery()
    categories = Category.query.filter(Category.id.in_(populated_categories)).order_by(Category.name.asc()).all()

    tests = Test.query.filter(and_(TestFork.user_id == g.user.id, TestFork.test_id == Test.id)).order_by(
        Test.id.desc()).limit(50).all()
    return {
        'addTestFork': fork_test_form,
        'commit_options': commit_options,
        'tests': tests,
        'TestType': TestType,
        'GitUser': username,
        'categories': categories,
        'customize': True
    }


def add_test_to_kvm(username, commit_hash, platforms, regression_tests) -> None:
    """
    Create new tests and add it to CustomizedTests based on parameters.

    :param username: git username required to find fork
    :type username: str
    :param commit_hash: commit hash of the repo user selected to run test
    :type commit_hash: str
    :param platforms: platforms user selected to run test
    :type platforms: list
    :param regression_tests: regression tests user selected to run tests
    :type regression_tests: list
    """
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
        for regression_test in regression_tests:
            customized_test = CustomizedTest(test.id, regression_test)
            g.db.add(customized_test)
        test_fork = TestFork(g.user.id, test.id)
        g.db.add(test_fork)
        g.db.commit()
