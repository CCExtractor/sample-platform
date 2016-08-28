import hashlib
import json
import os
import sys

import datetime
import traceback

from flask import Blueprint, request, abort, g, url_for
from git import Repo, InvalidGitRepositoryError, GitCommandError
from github import GitHub, ApiError
from multiprocessing import Process
from lxml import etree
from sqlalchemy import and_
from sqlalchemy.sql.functions import count
from werkzeug.utils import secure_filename
from pymysql.err import IntegrityError

from mod_ci.models import Kvm
from mod_deploy.controllers import request_from_github, is_valid_signature
from mod_home.models import GeneralData
from mod_regression.models import Category, RegressionTestOutput
from mod_test.models import TestType, Test, TestStatus, TestProgress, Fork, \
    TestPlatform, TestResultFile, TestResult

if sys.platform.startswith("linux"):
    import libvirt

mod_ci = Blueprint('ci', __name__)


class Status:
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"


def start_ci_vm(db, delay=None):
    p_lin = Process(target=kvm_processor_linux, args=(db, delay))
    p_lin.start()
    # p_win = Process(target=kvm_processor_windows, args=(db, delay))
    # p_win.start()


def kvm_processor_linux(db, delay):
    from run import config
    kvm_name = config.get('KVM_LINUX_NAME', '')
    return kvm_processor(db, kvm_name, TestPlatform.linux, delay)


def kvm_processor_windows(db, delay):
    from run import config
    kvm_name = config.get('KVM_WINDOWS_NAME', '')
    return kvm_processor(db, kvm_name, TestPlatform.windows, delay)


def kvm_processor(db, kvm_name, platform, delay):
    from run import config, log, app
    if kvm_name == "":
        log.critical('KVM name is empty!')
        return
    if delay is not None:
        import time
        log.debug('Sleeping for {time} seconds'.format(time=delay))
        time.sleep(delay)
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
    # Check if there's no KVM status left
    status = Kvm.query.filter(Kvm.name == kvm_name).first()
    if status is not None:
        log.warn("KVM is powered off, but test is still in there: %s" % status.test.id)
        db.delete(status)
        db.commit()
    # Get oldest test for this platform
    finished_tests = db.query(TestProgress.test_id).filter(
        TestProgress.status.in_([TestStatus.canceled, TestStatus.completed])
    ).subquery()
    test = Test.query.filter(
        and_(Test.id.notin_(finished_tests), Test.platform == platform)
    ).order_by(Test.id.asc()).first()
    if test is None:
        log.info('No more tests to run, returning')
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
    log.debug('Starting test %s' % test.id)
    status = Kvm(kvm_name, test.id)
    # Prepare data
    # 0) Write url to file
    with app.app_context():
        full_url = url_for('ci.progress_reporter', test_id=test.id,
                           token=test.token, _external=True, _scheme="https")
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
                single_test, 'entry', id=str(regression_test.id))
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
                    id=str(output_file.id)
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
        repo.delete_head('CI_Branch', force=True)
    except GitCommandError:
        log.warn('Could not delete CI_Branch head')
        traceback.print_exc()
    # If PR, merge, otherwise reset to commit
    if test.test_type == TestType.pull_request:
        # Fetch PR (stored under origin/pull/<id>/head
        pull_info = origin.fetch('pull/{id}/head:CI_Branch'.format(
            id=test.pr_nr))
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
        try:
            repo.git.rebase('master')
        except GitCommandError:
            progress = TestProgress(
                test.id, TestStatus.preparation, 
                'Rebase on master'
            )
            db.add(progress)
            progress = TestProgress(
                test.id, TestStatus.canceled, 
                'Merge conflict, please resolve.'
            )
            db.add(progress)
            db.commit()
            # Report back
            gh = GitHub(access_token=g.github['bot_token'])
            gh_commit = gh.repos(g.github['repository_owner'])(
                g.github['repository']).statuses(test.pr_nr)

            with app.app_context():
                target_url = url_for(
                    'test.by_id', test_id=test.id, _external=True)
            context = "CI - %s" % test.platform.value
            gh_commit.post(
                state=Status.ERROR, description='Failed to rebase',
                context=context, target_url=target_url)
            # Return, so next one can be handled
            return
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
    except IntegrityError:
        log.warn("Duplicate entry for %s" % test.id)


def queue_test(db, gh_commit, commit, test_type, branch="master", pr_nr=0):
    from run import log
    fork = Fork.query.filter(Fork.github.like(
        "%/CCExtractor/ccextractor.git")).first()
    if test_type == TestType.pull_request:
        branch = "pull_request"
    # Create Linux test entry
    linux = Test(TestPlatform.linux, test_type, fork.id, branch, commit,
                 pr_nr)
    db.add(linux)
    # Create Windows test entry
    # windows = Test(TestPlatform.windows, test_type, fork.id, branch,
    # commit, pr_nr)
    # db.add(windows)
    db.commit()
    # Update statuses on GitHub
    try:
        gh_commit.post(
            state=Status.PENDING, description="Tests queued",
            context="CI - %s" % linux.platform.value,
            target_url=url_for(
                'test.by_id', test_id=linux.id, _external=True))
        # gh_commit.post(
        #     state=Status.PENDING, description="Tests queued",
        #     context="CI - %s" % windows.platform.value,
        #     target_url=url_for(
        #         'test.by_id', test_id=windows.id, _external=True))
    except ApiError as a:
        log.critical('Could not post to GitHub! Response: %s' % a.response)
        return
    # Kick off KVM process
    start_ci_vm(db)


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
            # Update the db to the new last commit
            ref = gh.repos(g.github['repository_owner'])(
                g.github['repository']).git().refs('heads/master').get()
            last_commit = GeneralData.query.filter(GeneralData.key ==
                                                   'last_commit').first()
            last_commit.value = ref['object']['sha']
            g.db.commit()

        elif event == "pull_request":  # If it's a PR, run the tests
            try:
                commit = payload['after']
            except KeyError:
                # If the PR is opened, there's no after available.
                commit = ''
            pr_nr = payload['pull_request']['number']
            gh_commit = gh.repos(g.github['repository_owner'])(
                g.github['repository']).statuses(pr_nr)
            if payload['action'] == 'opened':
                # Run initial tests
                queue_test(g.db, gh_commit, commit, TestType.pull_request,
                           pr_nr=pr_nr)
            elif payload['action'] == 'synchronize':
                # Run/queue a new test set
                queue_test(g.db, gh_commit, commit, TestType.pull_request,
                           pr_nr=pr_nr)
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
                        target_url=url_for(
                            'test.by_id', test_id=test.id, _external=True))
            elif payload['action'] == 'reopened':
                # Run tests again
                queue_test(g.db, gh_commit, commit, TestType.pull_request)
        else:
            # Unknown type
            g.log.warning('CI unrecognized event: %s' % event)

        return json.dumps({'msg': 'EOL'})


@mod_ci.route('/progress-reporter/<test_id>/<token>', methods=['POST'])
def progress_reporter(test_id, token):
    from run import config, log
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
                    if kvm is not None:
                        g.db.delete(kvm)
                        g.db.commit()
                    # Start next test if necessary
                    start_ci_vm(g.db, 60)
                # Post status update
                state = Status.PENDING
                message = 'Tests queued'
                target_url = url_for(
                    'test.by_id', test_id=test.id, _external=True)
                context = "CI - %s" % test.platform.value
                if status == TestStatus.canceled:
                    state = Status.ERROR
                    message = 'Tests aborted due to an error; please check'
                elif status == TestStatus.completed:
                    # Determine if success or failure
                    # It fails if any of these happen:
                    # - A crash (non-zero exit code)
                    # - A not None value on the "got" of a TestResultFile (
                    #       meaning the hashes do not match)
                    crashes = g.db.query(count(TestResult.exit_code)).filter(
                        and_(TestResult.test_id == test.id,
                             TestResult.exit_code != 0)).first()
                    results = g.db.query(count(TestResultFile.got)).filter(
                        and_(TestResultFile.test_id == test.id,
                             TestResultFile.got.isnot(None))).first()
                    if crashes > 0 or results > 0:
                        state = Status.FAILURE
                        message = 'Not all tests completed successfully, ' \
                                  'please check'
                    else:
                        state = Status.SUCCESS
                        message = 'Tests completed'
                else:
                    message = progress.message

                gh = GitHub(access_token=g.github['bot_token'])
                gh_commit = gh.repos(g.github['repository_owner'])(
                    g.github['repository']).statuses(test.commit)

                gh_commit.post(state=state, description=message,
                               context=context, target_url=target_url)
            elif request.form['type'] == 'equality':
                log.debug('Equality for {t}/{rt}/{rto}'.format(
                    t=test_id, rt=request.form['test_id'], rto=request.form[
                        'test_file_id']))
                rto = RegressionTestOutput.query.filter(
                    RegressionTestOutput.id == request.form[
                        'test_file_id']).first()
                if rto is None:
                    # Equality posted on a file that's ignored presumably
                    log.info('No rto for {test_id}: {test}'.format(
                        test_id=test_id, test=request.form['test_id']))
                else:
                    result_file = TestResultFile(test.id, request.form[
                        'test_id'], rto.id, rto.correct)
                    g.db.add(result_file)
                    g.db.commit()
            elif request.form['type'] == 'upload':
                log.debug('Upload for {t}/{rt}/{rto}'.format(
                    t=test_id, rt=request.form['test_id'], rto=request.form[
                        'test_file_id']))
                # File upload, process
                if 'file' in request.files:
                    uploaded_file = request.files['file']
                    filename = secure_filename(uploaded_file.filename)
                    if filename is '':
                        return 'EMPTY'
                    temp_path = os.path.join(
                        config.get('SAMPLE_REPOSITORY', ''), 'TempFiles',
                        filename)
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
                        config.get('SAMPLE_REPOSITORY', ''), 'TestResults',
                        '{hash}{ext}'.format(
                            hash=file_hash, ext=file_extension)
                    )
                    os.rename(temp_path, final_path)
                    rto = RegressionTestOutput.query.filter(
                        RegressionTestOutput.id == request.form[
                            'test_file_id']).first()
                    result_file = TestResultFile(test.id, request.form[
                        'test_id'], rto.id, rto.correct, file_hash)
                    g.db.add(result_file)
                    g.db.commit()
            elif request.form['type'] == 'finish':
                log.debug('Finish for {t}/{rt}'.format(
                    t=test_id, rt=request.form['test_id']))
                # Test was done
                result = TestResult(
                    test.id, request.form['test_id'], request.form['runTime'],
                    request.form['exitCode']
                )
                g.db.add(result)
                g.db.commit()
            return "OK"
    return "FAIL"
