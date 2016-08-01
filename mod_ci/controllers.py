import json
import os
import sys

import datetime

from flask import Blueprint, request, abort, g, url_for
from git import Repo, InvalidGitRepositoryError, GitCommandError
from github import GitHub, ApiError
from multiprocessing import Process
from lxml import etree

from mod_ci.models import Kvm
from mod_deploy.controllers import request_from_github, is_valid_signature
from mod_regression.models import Category
from mod_test.models import TestType, Test, TestStatus, TestProgress, Fork, \
    TestPlatform

if sys.platform.startswith("linux"):
    import libvirt

mod_ci = Blueprint('ci', __name__)


class Status:
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"


def kvm_processor_linux(db):
    from run import config
    kvm_name = config.get('KVM_LINUX_NAME', '')
    return kvm_processor(db, kvm_name)


def kvm_processor_windows(db):
    from run import config
    kvm_name = config.get('KVM_WINDOWS_NAME', '')
    return kvm_processor(db, kvm_name)


def kvm_processor(db, kvm_name):
    from run import config, log
    if kvm_name == "":
        log.critical('KVM name is empty!')
        return
    # Open connection to libvirt
    conn = libvirt.open("qemu:///system")
    if conn is None:
        log.critical("Couldn't open connection to libvirt!")
        return
    try:
        vm = conn.lookupByName(kvm_name)
    except libvirt.libvirtError:
        log.critical("Couldn't find the Linux CI machine named %s" % kvm_name)
        return
    vm_info = vm.info()
    if vm_info[0] != libvirt.VIR_DOMAIN_SHUTOFF:
        # Running, check expiry (2 hours runtime max)
        status = Kvm.query.filter(Kvm.name == kvm_name).first()
        max_runtime = config.get("KVM_MAX_RUNTIME", 120)
        if status is not None:
            if datetime.datetime.now() >= status.timestamp + \
                    datetime.timedelta(minutes=max_runtime):
                # Mark entry as aborted
                test_progress = TestProgress(
                    status.test.id, TestStatus.canceled, 'Runtime exceeded')
                db.add(test_progress)
                db.delete(status)
                db.commit()
                # Abort process
                if vm.destroy() == -1:
                    # Failed to shut down
                    log.critical("Failed to shut down %s" % kvm_name)
                    return
            else:
                log.info("Current job is still running and not expired")
                return
        else:
            log.warn("No currently running task, but VM is running! Hard "
                     "reset necessary")
            if vm.destroy() == -1:
                # Failed to shut down
                log.critical("Failed to shut down %s" % kvm_name)
                return
    # Reset to snapshot
    if vm.hasCurrentSnapshot() != 1:
        log.critical("VM %s has no current snapshot set!" % kvm_name)
        return
    snapshot = vm.snapshotCurrent()
    if vm.revertToSnapshot(snapshot) == -1:
        log.critical("Failed to revert to snapshot %s for VM %s" % (
            snapshot.getName(), kvm_name))
        return
    log.info('Reverted to snapshot %s for VM %s' % (
        snapshot.getName(), kvm_name))
    # Get oldest test
    test = Test.query.filter(Test.id not in TestProgress.query.filter(
        TestProgress.status in [TestStatus.canceled, TestStatus.completed]
    ).all()).order_by(Test.id.asc()).first()
    if test is None:
        log.info('No more tests to run, returning')
        return
    status = Kvm(kvm_name, test.id)
    # Prepare data
    # 0) Write url to file
    full_url = url_for('.progress_reporter', test_id=test.id,
                       token=test.token, _external=True)
    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'reportURL')
    with open(file_path, 'w') as f:
        f.write(full_url)
    # 1) Generate test files
    base_folder = os.path.join(
        config.get('SAMPLE_REPOSITORY', ''), 'ci-tests')
    categories = Category.query.order_by(Category.id.desc()).all()
    # Init collection file
    multi_test = etree.Element('multitest')
    for category in categories:
        if len(category.regression_tests) == 0:
            # Skip categories without tests
            continue
        # Create XML file for test
        file_name = '{name}.xml'.format(name=category.name)
        single_test = etree.Element('tests')
        for regression_test in category.regression_tests:
            entry = etree.SubElement(
                single_test, 'entry', id=regression_test.id)
            command = etree.SubElement(entry, 'command')
            command.text = regression_test.command
            input_node = etree.SubElement(
                entry, 'input', type=regression_test.input_type.value)
            # Need a path that is relative to the folder we provide
            # inside the CI environment.
            input_node.text = regression_test.sample.filename
            output_node = etree.SubElement(entry, 'output')
            output_node.text = regression_test.output_type.value
            compare = etree.SubElement(entry, 'compare')
            for output_file in regression_test.output_files:
                file_node = etree.SubElement(
                    compare, 'file',
                    ignore='true' if output_file.ignore else 'false',
                    id=output_file.id
                )
                correct = etree.SubElement(file_node, 'correct')
                # Need a path that is relative to the folder we provide
                # inside the CI environment.
                correct.text = output_file.filename_correct
                expected = etree.SubElement(file_node, 'expected')
                expected.text = output_file.filename_expected(
                    regression_test.sample.sha)
        # Save XML
        single_test.getroottree().write(
            os.path.join(base_folder, file_name),
            encoding='utf-8', xml_declaration=True, pretty_print=True
        )
        # Append to collection file
        test_file = etree.SubElement(multi_test, 'testfile')
        location = etree.SubElement(test_file, 'location')
        location.text = file_name
    # Save collection file
    multi_test.getroottree().write(
        os.path.join(base_folder, 'TestAll.xml'),
        encoding='utf-8', xml_declaration=True, pretty_print=True
    )

    # 2) Create git repo clone and merge PR into it (if necessary)
    try:
        repo = Repo(os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'unsafe-ccextractor'))
    except InvalidGitRepositoryError:
        log.critical('Could not open CCExtractor\'s repository copy!')
        return
    # Return to master
    repo.heads.master.checkout(True)
    # Update repository from upstream
    try:
        origin = repo.remote('origin')
    except ValueError:
        log.critical('Origin remote doesn\'t exist!')
        return
    fetch_info = origin.fetch()
    if len(fetch_info) == 0:
        log.warn('No info fetched from remote!')
    # Pull code (finally)
    pull_info = origin.pull()
    if len(pull_info) == 0:
        log.warn('Didn\'t pull any information from remote!')

    if pull_info[0].flags > 128:
        log.critical('Didn\'t pull any information from remote: %s!' %
                     pull_info[0].flags)
        return
    # Delete the test branch if it exists, and recreate
    try:
        repo.delete_head('CI_Branch')
    except GitCommandError:
        pass
    # If PR, merge, otherwise reset to commit
    if test.test_type == TestType.pull_request:
        # Fetch PR (stored under origin/pull/<id>/head
        pull_info = origin.fetch('pull/2/head:CI_Branch')
        if len(pull_info) == 0:
            log.warn('Didn\'t pull any information from remote PR!')

        if pull_info[0].flags > 128:
            log.critical('Didn\'t pull any information from remote PR: %s!' %
                         pull_info[0].flags)
            return
        try:
            test_branch = repo.heads['CI_Branch']
        except IndexError:
            log.critical('CI_Branch does not exist')
            return
        # Check out branch
        test_branch.checkout(True)
        # Rebase on master
        repo.git.rebase('master')
        # TODO: check what happens on merge conflicts
    else:
        test_branch = repo.create_head('CI_Branch', 'HEAD')
        # Check out branch for test purposes
        test_branch.checkout(True)
        try:
            repo.head.reset(test.commit, working_tree=True)
        except GitCommandError:
            log.warn('Git commit %s (test %s) does not exist!' % (
                test.commit, test.id))
            return
    # Power on machine
    try:
        vm.create()
        db.add(status)
        db.commit()
    except libvirt.libvirtError:
        log.critical("Failed to launch VM %s" % kvm_name)
        return


def queue_test(db, gh_commit, commit, test_type, branch="master"):
    from run import log
    fork = Fork.query.filter(Fork.github.like(
        "%/CCExtractor/ccextractor.git")).first()
    if test_type == TestType.pull_request:
        branch = "pull_request"
    # Create Linux test entry
    linux = Test(TestPlatform.linux, test_type, fork.id, branch, commit)
    db.add(linux)
    # Create Windows test entry
    windows = Test(TestPlatform.windows, test_type, fork.id, branch, commit)
    db.add(windows)
    db.commit()
    # Update statuses on GitHub
    try:
        gh_commit.post(
            state=Status.PENDING, description="Tests queued",
            context="CI - %s" % linux.platform.value,
            target_url=url_for('test.test', test_id=linux.id, _external=True))
        gh_commit.post(
            state=Status.PENDING, description="Tests queued",
            context="CI - %s" % windows.platform.value,
            target_url=url_for(
                'test.test', test_id=windows.id, _external=True))
    except ApiError as a:
        log.critical('Could not post to GitHub! Response: %s' % a.response)
        return
    # Kick off KVM process
    p_lin = Process(target=kvm_processor_linux, args=(db,))
    p_lin.start()
    # p_win = Process(target=kvm_processor_windows, args=(db,))
    # p_win.start()


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

        if event == "push":  # If it's a push, run the tests
            commit = payload['after']
            gh_commit = gh.repos(g.github['repository_owner'])(
                g.github['repository']).statuses(commit)
            queue_test(g.db, gh_commit, commit, TestType.commit)

        elif event == "pull_request":  # If it's a PR, run the tests
            commit = payload['after']
            gh_commit = gh.repos(g.github['repository_owner'])(
                g.github['repository']).statuses(commit)
            if payload['action'] == 'opened':
                # Run initial tests
                queue_test(g.db, gh_commit, commit, TestType.pull_request)
            elif payload['action'] == 'synchronize':
                # Run/queue a new test set
                queue_test(g.db, gh_commit, commit, TestType.pull_request)
            elif payload['action'] == 'closed':
                # Cancel running queue
                tests = Test.query.filter(Test.commit == commit).all()
                for test in tests:
                    # Add canceled status only if the test hasn't started yet
                    if len(test.progress) > 0:
                        continue
                    progress = TestProgress(test.id, TestStatus.canceled,
                                            "PR closed",
                                            datetime.datetime.now())
                    g.db.add(progress)
                    gh.repos(g.github['repository_owner'])(
                        g.github['repository']).statuses(test.commit).post(
                        state=Status.FAILURE, description="Tests canceled",
                        context="CI - %s" % test.platform.value,
                        target_url=url_for('test.test', test_id=test.id))
            elif payload['action'] == 'reopened':
                # Run tests again
                queue_test(g.db, gh_commit, commit, TestType.pull_request)
        else:
            # Unknown type
            g.log.warning('CI unrecognized event: %s' % event)

        return json.dumps({'msg': 'EOL'})


@mod_ci.route('/progress-reporter/<test_id>/<token>', methods=['POST'])
def progress_reporter(test_id, token):
    from run import log
    # Verify token
    test = Test.query.filter(Test.id == test_id).first()
    if test is not None and test.token == token:
        if 'type' in request.form:
            if request.form['type'] == 'progress':
                # Progress, log
                status = TestStatus.from_string(request.form['status'])
                progress = TestProgress(
                    test.id, status, request.form['message'])
                g.db.add(progress)
                g.db.commit()
                # If status is complete, remove the Kvm entry
                if status == TestStatus.completed:
                    kvm = Kvm.query.filter(Kvm.test_id == test_id).first()
                    g.db.delete(kvm)
                    g.db.commit()
            elif request.form['type'] == 'equality':
                # TODO: finish
                log.debug(
                    'Result for file {f_id} from test {id} is equal to '
                    'the expected file!'.format(
                        f_id=request.form['test_file_id'],
                        id=request.form['test_id']
                    )
                )

            elif request.form['type'] == 'upload':
                # File upload, process
                # TODO: finish
                log.debug(
                    'Result for file {f_id} from test {id} is not equal to '
                    'the expected file!'.format(
                        f_id=request.form['test_file_id'],
                        id=request.form['test_id']
                    )
                )
                pass
            elif request.form['type'] == 'finish':
                # Test was done
                # TODO: finish
                log.debug(
                    'Test {id} finished in {time} with code: {exit}'.format(
                        id=request.form['test_id'],
                        time=request.form['runTime'],
                        exit=request.form['exitCode']
                    )
                )
                pass
            return "OK"
    return "FAIL"
