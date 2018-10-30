"""
mod_ci Controllers
===================
In this module, we are trying to maintain all functionality related
running virtual machines, starting and tracking tests.
"""

import hashlib
import json
import os
import shutil
import sys
import requests

import datetime

from flask import Blueprint, request, abort, g, url_for, jsonify, flash, redirect
from git import Repo, InvalidGitRepositoryError, GitCommandError
from github import GitHub, ApiError
from multiprocessing import Process
from lxml import etree
from sqlalchemy import and_, or_
from sqlalchemy import func
from sqlalchemy.sql import label
from sqlalchemy.sql.functions import count
from werkzeug.utils import secure_filename
from pymysql.err import IntegrityError

from decorators import template_renderer, get_menu_entries
from mod_auth.controllers import login_required, check_access_rights
from mod_ci.models import Kvm, MaintenanceMode, BlockedUsers
from mod_ci.forms import AddUsersToBlacklist, RemoveUsersFromBlacklist
from mod_deploy.controllers import request_from_github, is_valid_signature
from mod_home.models import GeneralData
from mod_regression.models import Category, RegressionTestOutput, RegressionTest, regressionTestLinkTable
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion
from mod_sample.models import Issue
from mod_test.models import TestType, Test, TestStatus, TestProgress, Fork, TestPlatform, TestResultFile, TestResult
from mod_customized.models import CustomizedTest
from mailer import Mailer

if sys.platform.startswith("linux"):
    import libvirt

mod_ci = Blueprint('ci', __name__)


class Status:
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"


@mod_ci.before_app_request
def before_app_request():
    """
    Function that organizes menu content such as Platform management
    """
    config_entries = get_menu_entries(
        g.user, 'Platform mgmt', 'cog', [], '', [
            {'title': 'Maintenance', 'icon': 'wrench', 'route': 'ci.show_maintenance', 'access': [Role.admin]},
            {'title': 'Blocked Users', 'icon': 'ban', 'route': 'ci.blocked_users', 'access': [Role.admin]}
        ]
    )
    if 'config' in g.menu_entries and 'entries' in config_entries:
        g.menu_entries['config']['entries'] = config_entries['entries'] + g.menu_entries['config']['entries']
    else:
        g.menu_entries['config'] = config_entries


def start_platform(db, repository, delay=None):
    """
    Function to check whether there is already running test for which it check the kvm progress and if no running test
    then it start a new test.
    """
    from run import config, log

    linux_kvm_name = config.get('KVM_LINUX_NAME', '')
    win_kvm_name = config.get('KVM_WINDOWS_NAME', '')
    kvm_test = Kvm.query.first()

    if kvm_test is None:
        start_new_test(db, repository, delay)
    elif kvm_test.name == linux_kvm_name:
        kvm_processor_linux(db, repository, delay)
    elif kvm_test.name == win_kvm_name:
        kvm_processor_windows(db, repository, delay)
    else:
        log.error(
            "There's a test in the KVM machine, but none of the platforms matched! We got {name}, compared against "
            "{lin}, {win}".format(name=kvm_test.name, lin=linux_kvm_name, win=win_kvm_name)
        )


def start_new_test(db, repository, delay):
    """
    Function to start a new test based on kvm table.
    """
    from run import log

    finished_tests = db.query(TestProgress.test_id).filter(
        TestProgress.status.in_([TestStatus.canceled, TestStatus.completed])
    ).subquery()
    test = Test.query.filter(and_(Test.id.notin_(finished_tests))).order_by(Test.id.asc()).first()

    if test is None:
        return
    elif test.platform == TestPlatform.windows:
        kvm_processor_windows(db, repository, delay)
    elif test.platform == TestPlatform.linux:
        kvm_processor_linux(db, repository, delay)
    else:
        log.error("Unsupported CI platform: {platform}".format(platform=test.platform))

    return


def kvm_processor_linux(db, repository, delay):
    from run import config
    kvm_name = config.get('KVM_LINUX_NAME', '')
    return kvm_processor(db, kvm_name, TestPlatform.linux, repository, delay)


def kvm_processor_windows(db, repository, delay):
    from run import config
    kvm_name = config.get('KVM_WINDOWS_NAME', '')
    return kvm_processor(db, kvm_name, TestPlatform.windows, repository, delay)


def kvm_processor(db, kvm_name, platform, repository, delay):
    """
    Checks whether there is no already running same kvm.
    Checks whether machine is in maintenance mode or not
    Launch kvm if not used by any other test
    Creates testing xml files to test the change in main repo.
    Creates clone with separate branch and merge pr into it.
    """
    from run import config, log, app, get_github_config

    github_config = get_github_config(config)

    log.info("[{platform}] Running kvm_processor".format(platform=platform))
    if kvm_name == "":
        log.critical('[{platform}] KVM name is empty!')
        return

    if delay is not None:
        import time
        log.debug('[{platform}] Sleeping for {time} seconds'.format(platform=platform, time=delay))
        time.sleep(delay)

    maintenance_mode = MaintenanceMode.query.filter(MaintenanceMode.platform == platform).first()
    if maintenance_mode is not None and maintenance_mode.disabled:
        log.debug('[{platform}] In maintenance mode! Waiting...'.format(platform=platform))
        return

    # Open connection to libvirt
    conn = libvirt.open("qemu:///system")
    if conn is None:
        log.critical("[{platform}] Couldn't open connection to libvirt!".format(platform=platform))
        return

    try:
        vm = conn.lookupByName(kvm_name)
    except libvirt.libvirtError:
        log.critical("[{platform}] No VM named {name} found!".format(platform=platform, name=kvm_name))
        return

    vm_info = vm.info()
    if vm_info[0] != libvirt.VIR_DOMAIN_SHUTOFF:
        # Running, check expiry (2 hours runtime max)
        status = Kvm.query.filter(Kvm.name == kvm_name).first()
        max_runtime = config.get("KVM_MAX_RUNTIME", 120)
        if status is not None:
            if datetime.datetime.now() - status.timestamp >= datetime.timedelta(minutes=max_runtime):
                # Mark entry as aborted
                test_progress = TestProgress(status.test.id, TestStatus.canceled, 'Runtime exceeded')
                db.add(test_progress)
                db.delete(status)
                db.commit()

                # Abort process
                if vm.destroy() == -1:
                    # Failed to shut down
                    log.critical("[{platform}] Failed to shut down {name}".format(platform=platform, name=kvm_name))
                    return
            else:
                log.info("[{platform}] Current job not expired yet.".format(platform=platform))
                return
        else:
            log.warn("[{platform}] No task, but VM is running! Hard reset necessary".format(platform=platform))
            if vm.destroy() == -1:
                # Failed to shut down
                log.critical("[{platform}] Failed to shut down {name}".format(platform=platform, name=kvm_name))
                return

    # Check if there's no KVM status left
    status = Kvm.query.filter(Kvm.name == kvm_name).first()
    if status is not None:
        log.warn("[{platform}] KVM is powered off, but test {id} still present".format(
            platform=platform, id=status.test.id))
        db.delete(status)
        db.commit()

    # Get oldest test for this platform
    finished_tests = db.query(TestProgress.test_id).filter(
        TestProgress.status.in_([TestStatus.canceled, TestStatus.completed])
    ).subquery()
    fork = Fork.query.filter(Fork.github.like(
        "%/{owner}/{repo}.git".format(owner=github_config['repository_owner'], repo=github_config['repository'])
    )).first()
    test = Test.query.filter(
            Test.id.notin_(finished_tests), Test.platform == platform, Test.fork_id == fork.id
    ).order_by(Test.id.asc()).first()

    if test is None:
        test = Test.query.filter(Test.id.notin_(finished_tests), Test.platform == platform).order_by(
            Test.id.asc()).first()

    if test is None:
        log.info('[{platform}] No more tests to run, returning'.format(platform=platform))
        return

    if test.test_type == TestType.pull_request and test.pr_nr == 0:
        log.warn('[{platform}] Test {id} is invalid, deleting'.format(platform=platform, id=test.id))
        db.delete(test)
        db.commit()
        return

    # Reset to snapshot
    if vm.hasCurrentSnapshot() != 1:
        log.critical("[{platform}] VM {name} has no current snapshot set!".format(platform=platform, name=kvm_name))
        return

    snapshot = vm.snapshotCurrent()
    if vm.revertToSnapshot(snapshot) == -1:
        log.critical("[{platform}] Failed to revert to {snapshot} for {name}".format(
            platform=platform, snapshot=snapshot.getName(), name=kvm_name)
        )
        return

    log.info("[{p}] Reverted to {snap} for {name}".format(p=platform, snap=snapshot.getName(), name=kvm_name))
    log.debug('Starting test {id}'.format(id=test.id))
    status = Kvm(kvm_name, test.id)
    # Prepare data
    # 0) Write url to file
    with app.app_context():
        full_url = url_for('ci.progress_reporter', test_id=test.id, token=test.token, _external=True, _scheme="https")

    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'vm_data', kvm_name, 'reportURL')

    with open(file_path, 'w') as f:
        f.write(full_url)

    # 1) Generate test files
    base_folder = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'vm_data', kvm_name, 'ci-tests')
    categories = Category.query.order_by(Category.id.desc()).all()
    commit_name = 'fetch_commit_' + platform.value
    commit_hash = GeneralData.query.filter(GeneralData.key == commit_name).first().value
    last_commit = Test.query.filter(and_(Test.commit == commit_hash, Test.platform == platform)).first()

    log.debug("[{p}] We will compare against the results of test {id}".format(p=platform, id=last_commit.id))

    regression_ids = test.get_customized_regressiontests()

    # Init collection file
    multi_test = etree.Element('multitest')
    for category in categories:
        # Skip categories without tests
        if len(category.regression_tests) == 0:
            continue
        # Create XML file for test
        file_name = '{name}.xml'.format(name=category.name)
        single_test = etree.Element('tests')
        check_write = False
        for regression_test in category.regression_tests:
            if regression_test.id not in regression_ids:
                continue
            check_write = True
            entry = etree.SubElement(single_test, 'entry', id=str(regression_test.id))
            command = etree.SubElement(entry, 'command')
            command.text = regression_test.command
            input_node = etree.SubElement(entry, 'input', type=regression_test.input_type.value)
            # Need a path that is relative to the folder we provide inside the CI environment.
            input_node.text = regression_test.sample.filename
            output_node = etree.SubElement(entry, 'output')
            output_node.text = regression_test.output_type.value
            compare = etree.SubElement(entry, 'compare')
            last_files = TestResultFile.query.filter(and_(
                TestResultFile.test_id == last_commit.id,
                TestResultFile.regression_test_id == regression_test.id
            )).subquery()

            for output_file in regression_test.output_files:
                ignore_file = str(output_file.ignore).lower()
                file_node = etree.SubElement(compare, 'file', ignore=ignore_file, id=str(output_file.id))
                last_commit_files = db.query(last_files.c.got).filter(and_(
                    last_files.c.regression_test_output_id == output_file.id,
                    last_files.c.got.isnot(None)
                )).first()
                correct = etree.SubElement(file_node, 'correct')
                # Need a path that is relative to the folder we provide inside the CI environment.
                if last_commit_files is None:
                    correct.text = output_file.filename_correct
                else:
                    correct.text = output_file.create_correct_filename(last_commit_files[0])

                expected = etree.SubElement(file_node, 'expected')
                expected.text = output_file.filename_expected(regression_test.sample.sha)
        # check whether category should be included or not
        if not check_write:
            continue
        # Save XML
        single_test.getroottree().write(
            os.path.join(base_folder, file_name), encoding='utf-8', xml_declaration=True, pretty_print=True
        )
        # Append to collection file
        test_file = etree.SubElement(multi_test, 'testfile')
        location = etree.SubElement(test_file, 'location')
        location.text = file_name

    # Save collection file
    multi_test.getroottree().write(
        os.path.join(base_folder, 'TestAll.xml'), encoding='utf-8', xml_declaration=True, pretty_print=True
    )

    # 2) Create git repo clone and merge PR into it (if necessary)
    try:
        repo = Repo(os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'vm_data', kvm_name, 'unsafe-ccextractor'))
    except InvalidGitRepositoryError:
        log.critical("[{platform}] Could not open CCExtractor's repository copy!".format(platform=platform))
        return

    # Return to master
    repo.heads.master.checkout(True)
    # Update repository from upstream
    try:
        fork_id = test.fork.id
        fork_url = test.fork.github
        if not check_main_repo(fork_url):
            existing_remote = [remote.name for remote in repo.remotes]
            remote = ('fork_{id}').format(id=fork_id)
            if remote in existing_remote:
                origin = repo.remote(remote)
            else:
                origin = repo.create_remote(remote, url=fork_url)
        else:
            origin = repo.remote('origin')
    except ValueError:
        log.critical("[{platform}] Origin remote doesn't exist!".format(platform=platform))
        return

    fetch_info = origin.fetch()
    if len(fetch_info) == 0:
        log.info('[{platform}] Fetch from remote returned no new data...'.format(platform=platform))
    # Checkout to Remote Master
    repo.git.checkout(origin.refs.master)
    # Pull code (finally)
    pull_info = origin.pull('master')
    if len(pull_info) == 0:
        log.info("[{platform}] Pull from remote returned no new data...".format(platform=platform))
    if pull_info[0].flags > 128:
        log.critical("[{platform}] Didn't pull any information from remote: {flags}!".format(
                platform=platform, flags=pull_info[0].flags))
        return

    # Delete the test branch if it exists, and recreate
    try:
        repo.delete_head('CI_Branch', force=True)
    except GitCommandError:
        log.warn("[{platform}] Could not delete CI_Branch head".format(platform=platform))

    # Remove possible left rebase-apply directory
    try:
        shutil.rmtree(os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'unsafe-ccextractor', '.git', 'rebase-apply'))
    except OSError:
        log.warn("[{platform}] Could not delete rebase-apply".format(platform=platform))
    # If PR, merge, otherwise reset to commit
    if test.test_type == TestType.pull_request:
        # Fetch PR (stored under origin/pull/<id>/head)
        pull_info = origin.fetch('pull/{id}/head:CI_Branch'.format(id=test.pr_nr))
        if len(pull_info) == 0:
            log.warn("[{platform}] Didn't pull any information from remote PR!".format(platform=platform))

        if pull_info[0].flags > 128:
            log.critical("[{platform}] Didn't pull any information from remote PR: {flags}!".format(
                platform=platform, flags=pull_info[0].flags))
            return

        try:
            test_branch = repo.heads['CI_Branch']
        except IndexError:
            log.critical('CI_Branch does not exist')
            return

        test_branch.checkout(True)

        try:
            pull = repository.pulls('{pr_nr}'.format(pr_nr=test.pr_nr)).get()
        except ApiError as a:
            log.error('Got an exception while fetching the PR payload! Message: {message}'.format(message=a.message))
            return
        if pull['mergeable'] is False:
            progress = TestProgress(test.id, TestStatus.canceled, "Commit could not be merged", datetime.datetime.now())
            db.add(progress)
            db.commit()
            try:
                with app.app_context():
                    repository.statuses(test.commit).post(
                        state=Status.FAILURE,
                        description="Tests canceled due to merge conflict",
                        context="CI - {name}".format(name=test.platform.value),
                        target_url=url_for('test.by_id', test_id=test.id, _external=True)
                    )
            except ApiError as a:
                log.error('Got an exception while posting to GitHub! Message: {message}'.format(message=a.message))
            return

        # Merge on master if no conflict
        repo.git.merge('master')

    else:
        test_branch = repo.create_head('CI_Branch', origin.refs.master)
        test_branch.checkout(True)
        try:
            repo.head.reset(test.commit, working_tree=True)
        except GitCommandError:
            log.warn("[{platform}] Commit {hash} for test {id} does not exist!".format(
                platform=platform, hash=test.commit, id=test.id))
            return

    # Power on machine
    try:
        vm.create()
        db.add(status)
        db.commit()
    except libvirt.libvirtError:
        log.critical("[{platform}] Failed to launch VM {name}".format(platform=platform, name=kvm_name))
    except IntegrityError:
        log.warn("[{platform}] Duplicate entry for {id}".format(platform=platform, id=test.id))

    # Close connection to libvirt
    conn.close()


def queue_test(db, gh_commit, commit, test_type, branch="master", pr_nr=0):
    """
    Function to store test details into Test model for each platform, and post the status to GitHub.

    :param db: Database connection.
    :type db: sqlalchemy.orm.scoped_session
    :param gh_commit: The GitHub API call for the commit. Can be None
    :type gh_commit: Any
    :param commit: The commit hash.
    :type commit: str
    :param test_type: The type of test
    :type test_type: TestType
    :param branch: Branch name
    :type branch: str
    :param pr_nr: Pull Request number, if applicable.
    :type pr_nr: int
    :return: Nothing
    :rtype: None
    """
    from run import log

    fork = Fork.query.filter(Fork.github.like(("%/{owner}/{repo}.git").format(owner=g.github['repository_owner'],
                                                                              repo=g.github['repository']))).first()

    if test_type == TestType.pull_request:
        branch = "pull_request"

    linux_test = Test(TestPlatform.linux, test_type, fork.id, branch, commit, pr_nr)
    db.add(linux_test)
    windows_test = Test(TestPlatform.windows, test_type, fork.id, branch, commit, pr_nr)
    db.add(windows_test)
    db.commit()
    add_customized_regression_tests(linux_test.id)
    add_customized_regression_tests(windows_test.id)

    if gh_commit is not None:
        status_entries = {
            linux_test.platform.value: linux_test.id,
            windows_test.platform.value: windows_test.id
        }
        for platform_name, test_id in status_entries.items():
            try:
                gh_commit.post(
                    state=Status.PENDING,
                    description="Tests queued",
                    context="CI - {name}".format(name=platform_name),
                    target_url=url_for('test.by_id', test_id=test_id, _external=True)
                )
            except ApiError as a:
                log.critical('Could not post to GitHub! Response: {res}'.format(res=a.response))

    log.debug("Created tests, waiting for cron...")


def inform_mailing_list(mailer, id, title, author, body):
    """
    Function that gets called when a issue is opened via the Webhook.
    :param mailer: The mailer instance
    :type mailer: Mailer
    :param id: ID of the Issue Opened
    :type id: int
    :param title: Title of the Created Issue
    :type title: str
    :param author: The Authors Username of the Issue
    :type author: str
    :param body: The Content of the Issue
    :type body: str
    """
    from run import get_github_issue_link
    subject = "GitHub Issue #{issue_number}".format(issue_number=id)
    url = get_github_issue_link(id)
    mailer.send_simple_message({
        "to": "ccextractor-dev@googlegroups.com",
        "subject": subject,
        "text": """{title} - {author}\n
        Link to Issue: {url}\n
        {author}(https://github.com/{author})\n\n
        {body}
        """.format(title=title, author=author, body=body, issue_number=id, url=url)
    })


@mod_ci.route('/start-ci', methods=['GET', 'POST'])
@request_from_github()
def start_ci():
    """
    Gets called when the webhook on GitHub is triggered. Reaction to the next events need to be processed
    (after verification):
        - Ping (for fun)
        - Push
        - Pull Request
        - Issues
    """
    if request.method != 'POST':
        return 'OK'
    else:
        abort_code = 418

        event = request.headers.get('X-GitHub-Event')
        if event == "ping":
            return json.dumps({'msg': 'Hi!'})

        x_hub_signature = request.headers.get('X-Hub-Signature')

        if not is_valid_signature(x_hub_signature, request.data, g.github['ci_key']):
            g.log.warning('CI signature failed: {sig}'.format(sig=x_hub_signature))
            abort(abort_code)

        payload = request.get_json()

        if payload is None:
            g.log.warning('CI payload is empty: {payload}'.format(payload=payload))
            abort(abort_code)

        gh = GitHub(access_token=g.github['bot_token'])
        repository = gh.repos(g.github['repository_owner'])(g.github['repository'])

        if event == "push":
            # If it's a push, and the 'after' hash is available, then it's a commit, so run the tests
            if 'after' in payload:
                commit = payload['after']
                gh_commit = repository.statuses(commit)
                # Update the db to the new last commit
                ref = repository.git().refs('heads/master').get()
                last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
                for platform in TestPlatform.values():
                    commit_name = 'fetch_commit_' + platform
                    fetch_commit = GeneralData.query.filter(GeneralData.key == commit_name).first()

                    if fetch_commit is None:
                        prev_commit = GeneralData(commit_name, last_commit.value)
                        g.db.add(prev_commit)

                last_commit.value = ref['object']['sha']
                g.db.commit()
                queue_test(g.db, gh_commit, commit, TestType.commit)
            else:
                g.log.warning('Unknown push type! Dumping payload for analysis')
                g.log.debug(payload)

        elif event == "pull_request":
            # If it's a valid PR, run the tests
            commit = ''
            gh_commit = None
            pr_nr = payload['pull_request']['number']
            if payload['action'] in ['opened', 'synchronize', 'reopened']:
                try:
                    commit = payload['pull_request']['head']['sha']
                    gh_commit = repository.statuses(commit)
                except KeyError:
                    g.log.critical("Didn't find a SHA value for a newly opened PR!")
                    g.log.debug(payload)

                # Check if user blacklisted
                user_id = payload['pull_request']['user']['id']
                if BlockedUsers.query.filter(BlockedUsers.user_id == user_id).first() is not None:
                    g.log.critical("User Blacklisted")
                    gh_commit.post(
                        state=Status.ERROR,
                        description="CI start aborted. You may be blocked from accessing this functionality",
                        target_url=url_for('home.index', _external=True)
                    )
                    return 'ERROR'

                queue_test(g.db, gh_commit, commit, TestType.pull_request, pr_nr=pr_nr)

            elif payload['action'] == 'closed':
                g.log.debug('PR was closed, no after hash available')
                # Cancel running queue
                tests = Test.query.filter(Test.pr_nr == pr_nr).all()
                for test in tests:
                    # Add canceled status only if the test hasn't started yet
                    if len(test.progress) > 0:
                        continue
                    progress = TestProgress(test.id, TestStatus.canceled, "PR closed", datetime.datetime.now())
                    g.db.add(progress)
                    repository.statuses(test.commit).post(
                        state=Status.FAILURE,
                        description="Tests canceled",
                        context="CI - {name}".format(name=test.platform.value),
                        target_url=url_for('test.by_id', test_id=test.id, _external=True)
                    )

        elif event == "issues":
            issue_data = payload['issue']
            issue_action = payload['action']
            issue = Issue.query.filter(Issue.issue_id == issue_data['number']).first()
            issue_title = issue_data['title']
            issue_id = issue_data['number']
            issue_author = issue_data['user']['login']
            issue_body = issue_data['body']

            # Send Email to the Mailing List using the Mailer Module and Mailgun's API
            if issue_action == "opened":
                inform_mailing_list(g.mailer, issue_id, issue_title, issue_author, issue_body)

            if issue is not None:
                issue.title = issue_title
                issue.status = issue_data['state']
                g.db.commit()

        elif event == "release":
            release_data = payload['release']
            release_type = payload['prerelease']
            # checking whether it is meant for production
            if release_type is False:
                g.log.debug("error, release event meant for pre-release")
                return
            else:
                release_version = payload['tag_name']
                # Github recommends adding v to the version
                if release_version[0] == 'v':
                    release_version = release_version[1:]
                release_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
                release = CCExtractorVersion(release_data, release_version, release_commit)
                g.db.add(release)
                g.db.commit()
                # adding test corresponding to last commit to the baseline regression results
                test = Test.query.filter(and_(Test.commit == release_commit,
                                         Test.platform == TestPlatform.linux)).first()
                test_result_file = g.db.query(TestResultFile).filter(
                                    TestResultFile.test_id == test.id).subquery()
                test_result = g.db.query(TestResult).filter(
                                    TestResult.test_id == test.id).subquery()
                g.db.query(RegressionTestOutput.correct).filter(
                                    and_(RegressionTestOutput.regression_id == test_result_file.c.regression_test_id,
                                         test_result_file.c.got is not None)).values(test_result_file.c.got)
                g.db.query(RegressionTest.expected_rc).filter(
                                RegressionTest.id == test_result.c.regression_test_id
                                ).values(test_result.c.expected_rc)
                g.db.commit()

        else:
            # Unknown type
            g.log.warning('CI unrecognized event: {event}'.format(event=event))

        return json.dumps({'msg': 'EOL'})


def update_build_badge(status, test):
    """
    Build status badge for current test to be displayed on sample-platform.ccextractor.org

    :param status: current testing status
    :type status: str
    :param test: current commit that is tested
    :type test: Test
    :return: Nothing.
    :rtype: None
    """
    if test.test_type == TestType.commit and check_main_repo(test.fork.github):
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        availableon = os.path.join(parent_dir, 'static', 'svg',
                                   '{status}-{platform}.svg'.format(status=status.upper(),
                                                                    platform=test.platform.value))
        svglocation = os.path.join(parent_dir, 'static', 'img', 'status',
                                   'build-{platform}.svg'.format(platform=test.platform.value))
        shutil.copyfile(availableon, svglocation)
    else:
        return


@mod_ci.route('/progress-reporter/<test_id>/<token>', methods=['POST'])
def progress_reporter(test_id, token):
    """
    Handle the progress of a certain test after validating the token. If necessary, update the status on GitHub.

    :param test_id: The id of the test to update.
    :type test_id: int
    :param token: The token to check the validity of the request.
    :type token: str
    :return: Nothing.
    :rtype: None
    """
    from run import config, log
    # Verify token
    test = Test.query.filter(Test.id == test_id).first()
    if test is not None and test.token == token:
        repo_folder = config.get('SAMPLE_REPOSITORY', '')
        if 'type' in request.form:
            if request.form['type'] == 'progress':
                # Progress, log
                status = TestStatus.from_string(request.form['status'])
                # Check whether test is not running previous status again
                istatus = TestStatus.progress_step(status)
                message = request.form['message']

                if len(test.progress) != 0:
                    laststatus = TestStatus.progress_step(test.progress[-1].status)

                    if laststatus in [TestStatus.completed, TestStatus.canceled]:
                        return "FAIL"

                    if laststatus > istatus:
                        status = TestStatus.canceled
                        message = "Duplicate Entries"

                progress = TestProgress(test.id, status, message)
                g.db.add(progress)
                g.db.commit()

                gh = GitHub(access_token=g.github['bot_token'])
                repository = gh.repos(g.github['repository_owner'])(g.github['repository'])
                # Store the test commit for testing in case of commit
                if status == TestStatus.completed and check_main_repo(test.fork.github):
                    commit_name = 'fetch_commit_' + test.platform.value
                    commit = GeneralData.query.filter(GeneralData.key == commit_name).first()
                    fetch_commit = Test.query.filter(
                        and_(Test.commit == commit.value, Test.platform == test.platform)
                    ).first()

                    if test.test_type == TestType.commit and test.id > fetch_commit.id:
                        commit.value = test.commit
                        g.db.commit()

                # If status is complete, remove the Kvm entry
                if status in [TestStatus.completed, TestStatus.canceled]:
                    log.debug("Test {id} has been {status}".format(id=test_id, status=status))
                    var_average = 'average_time_' + test.platform.value
                    current_average = GeneralData.query.filter(GeneralData.key == var_average).first()
                    average_time = 0
                    total_time = 0

                    if current_average is None:
                        platform_tests = g.db.query(Test.id).filter(Test.platform == test.platform).subquery()
                        finished_tests = g.db.query(TestProgress.test_id).filter(
                            and_(
                                TestProgress.status.in_([TestStatus.canceled, TestStatus.completed]),
                                TestProgress.test_id.in_(platform_tests)
                            )
                        ).subquery()
                        in_progress_statuses = [TestStatus.preparation, TestStatus.completed, TestStatus.canceled]
                        finished_tests_progress = g.db.query(TestProgress).filter(
                            and_(
                                TestProgress.test_id.in_(finished_tests),
                                TestProgress.status.in_(in_progress_statuses)
                            )
                        ).subquery()
                        times = g.db.query(
                            finished_tests_progress.c.test_id,
                            label('time', func.group_concat(finished_tests_progress.c.timestamp))
                        ).group_by(finished_tests_progress.c.test_id).all()

                        for p in times:
                            parts = p.time.split(',')
                            start = datetime.datetime.strptime(parts[0], '%Y-%m-%d %H:%M:%S')
                            end = datetime.datetime.strptime(parts[-1], '%Y-%m-%d %H:%M:%S')
                            total_time += (end - start).total_seconds()

                        if len(times) != 0:
                            average_time = total_time // len(times)

                        new_avg = GeneralData(var_average, average_time)
                        g.db.add(new_avg)
                        g.db.commit()

                    else:
                        all_results = TestResult.query.count()
                        regression_test_count = RegressionTest.query.count()
                        number_test = all_results / regression_test_count
                        updated_average = float(current_average.value) * (number_test - 1)
                        pr = test.progress_data()
                        end_time = pr['end']
                        start_time = pr['start']

                        if end_time.tzinfo is not None:
                            end_time = end_time.replace(tzinfo=None)

                        if start_time.tzinfo is not None:
                            start_time = start_time.replace(tzinfo=None)

                        last_running_test = end_time - start_time
                        updated_average = updated_average + last_running_test.total_seconds()
                        current_average.value = updated_average // number_test
                        g.db.commit()

                    kvm = Kvm.query.filter(Kvm.test_id == test_id).first()

                    if kvm is not None:
                        log.debug("Removing KVM entry")
                        g.db.delete(kvm)
                        g.db.commit()

                # Post status update
                state = Status.PENDING
                target_url = url_for('test.by_id', test_id=test.id, _external=True)
                context = "CI - {name}".format(name=test.platform.value)

                if status == TestStatus.canceled:
                    state = Status.ERROR
                    message = 'Tests aborted due to an error; please check'

                elif status == TestStatus.completed:
                    # Determine if success or failure
                    # It fails if any of these happen:
                    # - A crash (unexpected exit code)
                    # - A not None value on the "got" of a TestResultFile (
                    #       meaning the hashes do not match)
                    crashes = g.db.query(count(TestResult.exit_code)).filter(
                        and_(
                            TestResult.test_id == test.id,
                            TestResult.exit_code != TestResult.expected_rc
                        )).scalar()
                    results_zero_rc = g.db.query(RegressionTest.id).filter(
                        RegressionTest.expected_rc == 0
                    ).subquery()
                    results = g.db.query(count(TestResultFile.got)).filter(
                        and_(
                            TestResultFile.test_id == test.id,
                            TestResultFile.regression_test_id.in_(results_zero_rc),
                            TestResultFile.got.isnot(None)
                        )
                    ).scalar()
                    log.debug('Test {id} completed: {crashes} crashes, {results} results'.format(
                        id=test.id, crashes=crashes, results=results
                    ))
                    if crashes > 0 or results > 0:
                        state = Status.FAILURE
                        message = 'Not all tests completed successfully, please check'

                    else:
                        state = Status.SUCCESS
                        message = 'Tests completed'
                    if test.test_type == TestType.pull_request:
                        comment_pr(test.id, state, test.pr_nr, test.platform.name)
                    update_build_badge(state, test)

                else:
                    message = progress.message

                gh_commit = repository.statuses(test.commit)
                try:
                    gh_commit.post(state=state, description=message, context=context, target_url=target_url)
                except ApiError as a:
                    log.error('Got an exception while posting to GitHub! Message: {message}'.format(message=a.message))

                if status in [TestStatus.completed, TestStatus.canceled]:
                    # Start next test if necessary, on the same platform
                    process = Process(target=start_platform, args=(g.db, repository, 60))
                    process.start()

            elif request.form['type'] == 'equality':
                log.debug('Equality for {t}/{rt}/{rto}'.format(
                    t=test_id, rt=request.form['test_id'], rto=request.form['test_file_id'])
                )
                rto = RegressionTestOutput.query.filter(RegressionTestOutput.id == request.form['test_file_id']).first()

                if rto is None:
                    # Equality posted on a file that's ignored presumably
                    log.info('No rto for {test_id}: {test}'.format(test_id=test_id, test=request.form['test_id']))
                else:
                    result_file = TestResultFile(test.id, request.form['test_id'], rto.id, rto.correct)
                    g.db.add(result_file)
                    g.db.commit()

            elif request.form['type'] == 'logupload':
                log.debug("Received log file for test {id}".format(id=test_id))
                # File upload, process
                if 'file' in request.files:
                    uploaded_file = request.files['file']
                    filename = secure_filename(uploaded_file.filename)
                    if filename is '':
                        return 'EMPTY'

                    temp_path = os.path.join(repo_folder, 'TempFiles', filename)
                    # Save to temporary location
                    uploaded_file.save(temp_path)
                    final_path = os.path.join(repo_folder, 'LogFiles', '{id}{ext}'.format(id=test.id, ext='.txt'))

                    os.rename(temp_path, final_path)
                    log.debug("Stored log file")

            elif request.form['type'] == 'upload':
                log.debug('Upload for {t}/{rt}/{rto}'.format(
                    t=test_id, rt=request.form['test_id'], rto=request.form['test_file_id'])
                )
                # File upload, process
                if 'file' in request.files:
                    uploaded_file = request.files['file']
                    filename = secure_filename(uploaded_file.filename)
                    if filename is '':
                        return 'EMPTY'
                    temp_path = os.path.join(repo_folder, 'TempFiles', filename)
                    # Save to temporary location
                    uploaded_file.save(temp_path)
                    # Get hash and check if it's already been submitted
                    hash_sha256 = hashlib.sha256()
                    with open(temp_path, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_sha256.update(chunk)
                    file_hash = hash_sha256.hexdigest()
                    filename, file_extension = os.path.splitext(filename)
                    final_path = os.path.join(
                        repo_folder, 'TestResults', '{hash}{ext}'.format(hash=file_hash, ext=file_extension)
                    )
                    os.rename(temp_path, final_path)
                    rto = RegressionTestOutput.query.filter(
                        RegressionTestOutput.id == request.form['test_file_id']).first()
                    result_file = TestResultFile(test.id, request.form['test_id'], rto.id, rto.correct, file_hash)
                    g.db.add(result_file)
                    g.db.commit()

            elif request.form['type'] == 'finish':
                log.debug('Finish for {t}/{rt}'.format(t=test_id, rt=request.form['test_id']))
                regression_test = RegressionTest.query.filter(RegressionTest.id == request.form['test_id']).first()
                result = TestResult(
                    test.id, regression_test.id, request.form['runTime'],
                    request.form['exitCode'], regression_test.expected_rc
                )
                g.db.add(result)
                try:
                    g.db.commit()
                except IntegrityError as e:
                    log.error('Could not save the results: {msg}'.format(msg=e.message))

            return "OK"

    return "FAIL"


def comment_pr(test_id, state, pr_nr, platform):
    """
    Upload the test report to the github PR as comment

    :param test_id: The identity of Test whose report will be uploaded
    :type test_id: str
    :crash: whether test results in crash or not
    :type: boolean
    :pr_nr: PR number to which test commit is related and comment will be uploaded
    :type: str
    """
    from run import app, log
    regression_testid_passed = g.db.query(TestResult.regression_test_id).outerjoin(
                                TestResultFile, TestResult.test_id == TestResultFile.test_id).filter(
                                TestResult.test_id == test_id,
                                TestResult.expected_rc == TestResult.exit_code,
                                or_(
                                    TestResult.exit_code != 0,
                                    and_(TestResult.exit_code == 0,
                                         TestResult.regression_test_id == TestResultFile.regression_test_id,
                                         TestResultFile.got.is_(None)
                                         ),
                                    and_(
                                         RegressionTestOutput.regression_id == TestResult.regression_test_id,
                                         RegressionTestOutput.ignore.is_(True),
                                            ))).subquery()
    passed = g.db.query(label('category_id', Category.id), label(
        'success', count(regressionTestLinkTable.c.regression_id))).filter(
            regressionTestLinkTable.c.regression_id.in_(regression_testid_passed),
            Category.id == regressionTestLinkTable.c.category_id).group_by(
                 regressionTestLinkTable.c.category_id).subquery()
    tot = g.db.query(label('category', Category.name), label('total', count(regressionTestLinkTable.c.regression_id)),
                     label('success', passed.c.success)).outerjoin(
        passed, passed.c.category_id == Category.id).filter(
        Category.id == regressionTestLinkTable.c.category_id).group_by(
        regressionTestLinkTable.c.category_id).all()
    regression_testid_failed = RegressionTest.query.filter(RegressionTest.id.notin_(regression_testid_passed)).all()
    template = app.jinja_env.get_or_select_template('ci/pr_comment.txt')
    message = template.render(tests=tot, failed_tests=regression_testid_failed, test_id=test_id,
                              state=state, platform=platform)
    log.debug('Github PR Comment Message Created for Test_id: {test_id}'.format(test_id=test_id))
    try:
        gh = GitHub(access_token=g.github['bot_token'])
        repository = gh.repos(g.github['repository_owner'])(g.github['repository'])
        # Pull requests are just issues with code, so github consider pr comments in issues
        pull_request = repository.issues(pr_nr)
        comments = pull_request.comments().get()
        bot_name = g.github['bot_name']
        comment_id = None
        for comment in comments:
            if comment['user']['login'] == bot_name and platform in comment['body']:
                comment_id = comment['id']
                break
        log.debug('Github PR Comment ID Fetched for Test_id: {test_id}'.format(test_id=test_id))
        if comment_id is None:
            comment = pull_request.comments().post(body=message)
            comment_id = comment['id']
        else:
            repository.issues().comments(comment_id).post(body=message)
        log.debug('Github PR Comment ID {comment} Uploaded for Test_id: {test_id}'.format(
                comment=comment_id, test_id=test_id))
    except Exception as e:
        log.error('Github PR Comment Failed for Test_id: {test_id} with Exception {e}'.format(test_id=test_id, e=e))


@mod_ci.route('/show_maintenance')
@login_required
@check_access_rights([Role.admin])
@template_renderer('ci/maintenance.html')
def show_maintenance():
    return {
        'platforms': MaintenanceMode.query.all()
    }


@mod_ci.route('/blocked_users', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def blocked_users():
        """
        Method to render the blocked_users template.
        This returns a list of all currently blacklisted users.
        Also defines processing of forms to add/remove users from blacklist.
        When a user is added to blacklist, removes queued tests on any PR by the user.
        """
        blocked_users = BlockedUsers.query.order_by(BlockedUsers.user_id)

        # Initialize usernames dictionary
        usernames = {u.user_id: 'Error, cannot get username' for u in blocked_users}
        for key in usernames.keys():
            # Fetch usernames from GitHub API
            try:
                api_url = requests.get('https://api.github.com/user/{}'.format(key), timeout=10)
                userdata = api_url.json()
                # Set values to the actual usernames if no errors
                usernames[key] = userdata['login']
            except requests.exceptions.RequestException:
                break

        # Define addUserForm processing
        add_user_form = AddUsersToBlacklist()
        if add_user_form.add.data and add_user_form.validate_on_submit():
            if BlockedUsers.query.filter_by(user_id=add_user_form.user_id.data).first() is not None:
                flash('User already blocked.')
                return redirect(url_for('.blocked_users'))

            blocked_user = BlockedUsers(add_user_form.user_id.data, add_user_form.comment.data)
            g.db.add(blocked_user)
            g.db.commit()
            flash('User blocked successfully.')

            try:
                # Remove any queued pull request from blocked user
                gh = GitHub(access_token=g.github['bot_token'])
                repository = gh.repos(g.github['repository_owner'])(g.github['repository'])
                # Getting all pull requests by blocked user on the repo
                pulls = repository.pulls.get()
                for pull in pulls:
                    if pull['user']['id'] != add_user_form.user_id.data:
                        continue
                    tests = Test.query.filter(Test.pr_nr == pull['number']).all()
                    for test in tests:
                        # Add canceled status only if the test hasn't started yet
                        if len(test.progress) > 0:
                            continue
                        progress = TestProgress(test.id, TestStatus.canceled, "PR closed", datetime.datetime.now())
                        g.db.add(progress)
                        g.db.commit()
                        try:
                            repository.statuses(test.commit).post(
                                state=Status.FAILURE,
                                description="Tests canceled since user blacklisted",
                                context="CI - {name}".format(name=test.platform.value),
                                target_url=url_for('test.by_id', test_id=test.id, _external=True)
                            )
                        except ApiError as a:
                            g.log.error('Got an exception while posting to GitHub! Message: {message}'.format(
                                message=a.message))
            except ApiError as a:
                g.log.error('Pull Requests of Blocked User could not be fetched: {res}'.format(res=a.response))

            return redirect(url_for('.blocked_users'))

        # Define removeUserForm processing
        remove_user_form = RemoveUsersFromBlacklist()
        if remove_user_form.remove.data and remove_user_form.validate_on_submit():
            blocked_user = BlockedUsers.query.filter_by(user_id=remove_user_form.user_id.data).first()
            if blocked_user is None:
                flash('No such user in Blacklist')
                return redirect(url_for('.blocked_users'))

            g.db.delete(blocked_user)
            g.db.commit()
            flash('User removed successfully.')
            return redirect(url_for('.blocked_users'))

        return{
            'addUserForm': add_user_form,
            'removeUserForm': remove_user_form,
            'blocked_users': blocked_users,
            'usernames': usernames
        }


@mod_ci.route('/toggle_maintenance/<platform>/<status>')
@login_required
@check_access_rights([Role.admin])
def toggle_maintenance(platform, status):
    result = 'failed'
    message = 'Platform Not found'
    try:
        platform = TestPlatform.from_string(platform)
        db_mode = MaintenanceMode.query.filter(MaintenanceMode.platform == platform).first()
        if db_mode is not None:
            db_mode.disabled = status == 'True'
            g.db.commit()
            result = 'success'
            message = '{platform} in maintenance? {status}'.format(
                platform=platform.description,
                status=("Yes" if db_mode.disabled else 'No')
            )
    except ValueError:
        pass

    return jsonify({
        'status': result,
        'message': message
    })


@mod_ci.route('/maintenance-mode/<platform>')
def in_maintenance_mode(platform):
    try:
        platform = TestPlatform.from_string(platform)
    except ValueError:
        return 'ERROR'

    status = MaintenanceMode.query.filter(MaintenanceMode.platform == platform).first()

    if status is None:
        status = MaintenanceMode(platform, False)
        g.db.add(status)
        g.db.commit()

    return str(status.disabled)


def check_main_repo(repo_url):
    """
    Check whether the repo_url links to the main repository or not
    :param repo_url: url of fork/main repository of the user
    :type repo_url: str
    :return: checks whether url of main repo is same or not
    :rtype: bool
    """
    from run import config, get_github_config

    gh_config = get_github_config(config)
    return '{user}/{repo}'.format(user=gh_config['repository_owner'], repo=gh_config['repository']) in repo_url


def add_customized_regression_tests(test_id):
    active_regression_tests = RegressionTest.query.filter(RegressionTest.active == 1).all()
    for regression_test in active_regression_tests:
        customized_test = CustomizedTest(test_id, regression_test.id)
        g.db.add(customized_test)
        g.db.commit()
