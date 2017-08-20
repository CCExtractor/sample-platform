import hashlib
import json
import os
import shutil
import sys

import datetime

from flask import Blueprint, request, abort, g, url_for, jsonify
from git import Repo, InvalidGitRepositoryError, GitCommandError
from github import GitHub, ApiError
from multiprocessing import Process
from lxml import etree
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy.sql import label
from sqlalchemy.sql.functions import count
from werkzeug.utils import secure_filename
from pymysql.err import IntegrityError

from decorators import template_renderer, get_menu_entries
from mod_ci.models import Kvm, MaintenanceMode
from mod_deploy.controllers import request_from_github, is_valid_signature
from mod_home.models import GeneralData
from mod_regression.models import Category, RegressionTestOutput, \
    RegressionTest
from mod_auth.models import Role, User
from mod_sample.models import Issue
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


@mod_ci.before_app_request
def before_app_request():
    config_entries = get_menu_entries(
        g.user, 'Platform mgmt', 'cog', [], '', [
            {'title': 'Maintenance', 'icon': 'wrench', 'route':
                'ci.show_maintenance', 'access': [Role.admin]}
        ]
    )
    if 'config' in g.menu_entries and 'entries' in config_entries:
        g.menu_entries['config']['entries'] = \
            config_entries['entries'] + g.menu_entries['config']['entries']
    else:
        g.menu_entries['config'] = config_entries


def start_ci_vm(db, repository, delay=None):
    p_lin = Process(target=kvm_processor_linux, args=(db, repository, delay))
    p_lin.start()
    p_win = Process(
        target=kvm_processor_windows,
        args=(db, repository, delay)
    )
    p_win.start()


def kvm_processor_linux(db, repository, delay):
    from run import config
    kvm_name = config.get('KVM_LINUX_NAME', '')
    return kvm_processor(
        db, kvm_name, TestPlatform.linux, repository, delay)


def kvm_processor_windows(db, repository, delay):
    from run import config
    kvm_name = config.get('KVM_WINDOWS_NAME', '')
    return kvm_processor(
        db, kvm_name, TestPlatform.windows, repository, delay)


def kvm_processor(db, kvm_name, platform, repository, delay):
    from run import config, log, app
    log.info("[{platform}] Running kvm_processor".format(platform=platform))
    if kvm_name == "":
        log.critical('[{platform}] KVM name is empty!')
        return
    if delay is not None:
        import time
        log.debug('[{platform}] Sleeping for {time} seconds'.format(
            platform=platform, time=delay))
        time.sleep(delay)
    # Open connection to libvirt
    conn = libvirt.open("qemu:///system")
    if conn is None:
        log.critical("[{platform}] Couldn't open connection to "
                     "libvirt!".format(platform=platform))
        return
    try:
        vm = conn.lookupByName(kvm_name)
    except libvirt.libvirtError:
        log.critical("[{platform}] No VM named {name} found!".format(
            platform=platform, name=kvm_name))
        return
    vm_info = vm.info()
    if vm_info[0] != libvirt.VIR_DOMAIN_SHUTOFF:
        # Running, check expiry (2 hours runtime max)
        status = Kvm.query.filter(Kvm.name == kvm_name).first()
        max_runtime = config.get("KVM_MAX_RUNTIME", 120)
        if status is not None:
            if datetime.datetime.now() - status.timestamp >= \
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
                    log.critical(
                        "[{platform}] Failed to shut down {name}".format(
                            platform=platform, name=kvm_name))
                    return
            else:
                log.info("[{platform}] Current job not expired "
                         "yet.".format(platform=platform))
                return
        else:
            log.warn("[{platform}] No task, but VM is running! Hard reset "
                     "necessary".format(platform=platform))
            if vm.destroy() == -1:
                # Failed to shut down
                log.critical(
                    "[{platform}] Failed to shut down {name}".format(
                        platform=platform, name=kvm_name))
                return
    # Check if there's no KVM status left
    status = Kvm.query.filter(Kvm.name == kvm_name).first()
    if status is not None:
        log.warn("[{platform}] KVM is powered off, but test {id} still "
                 "present".format(platform=platform, id=status.test.id))
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
        log.info('[{platform}] No more tests to run, returning'.format(
            platform=platform))
        return
    if test.test_type == TestType.pull_request and test.pr_nr == 0:
        log.warn('[{platform}] Test {id} is invalid, deleting'.format(
            platform=platform, id=test.id)
        )
        db.delete(test)
        db.commit()
        return
    # Reset to snapshot
    if vm.hasCurrentSnapshot() != 1:
        log.critical(
            "[{platform}] VM {name} has no current snapshot set!".format(
                platform=platform, name=kvm_name
            )
        )
        return
    snapshot = vm.snapshotCurrent()
    if vm.revertToSnapshot(snapshot) == -1:
        log.critical(
            "[{platform}] Failed to revert to {snapshot} for {name}".format(
                platform=platform,
                snapshot=snapshot.getName(),
                name=kvm_name
            )
        )
        return
    log.info("[{platform}] Reverted to {snapshot} for {name}".format(
        platform=platform, snapshot=snapshot.getName(), name=kvm_name))
    log.debug('Starting test %s' % test.id)
    status = Kvm(kvm_name, test.id)
    # Prepare data
    # 0) Write url to file
    with app.app_context():
        full_url = url_for('ci.progress_reporter', test_id=test.id,
                           token=test.token, _external=True, _scheme="https")
    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''),
                             'vm_data', kvm_name, 'reportURL')
    with open(file_path, 'w') as f:
        f.write(full_url)
    # 1) Generate test files
    base_folder = os.path.join(
        config.get('SAMPLE_REPOSITORY', ''), 'vm_data', kvm_name, 'ci-tests')
    categories = Category.query.order_by(Category.id.desc()).all()
    commit_hash = GeneralData.query.filter(
        GeneralData.key == 'last_commit').first().value
    last_commit = Test.query.filter(and_(Test.commit == commit_hash,
                                         Test.platform == platform)).first()
    if last_commit.id == test.id:
        commit_hash = GeneralData.query.filter(
            GeneralData.key == 'previous_to_last_commit').first().value
        last_commit = Test.query.filter(and_(Test.commit == commit_hash,
                                             Test.platform == platform
                                             )).first()

    log.debug("[{platform}] We will compare against the results of test "
              "{id}".format(platform=platform, id=last_commit.id))

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
            last_files = TestResultFile.query.filter(and_(
                TestResultFile.test_id == last_commit.id,
                TestResultFile.regression_test_id ==
                regression_test.id)).subquery()
            for output_file in regression_test.output_files:
                file_node = etree.SubElement(
                    compare, 'file',
                    ignore='true' if output_file.ignore else 'false',
                    id=str(output_file.id)
                )
                last_commit_files = db.query(last_files.c.got).filter(and_(
                    last_files.c.regression_test_output_id == output_file.id,
                    last_files.c.got.isnot(None))).first()
                correct = etree.SubElement(file_node, 'correct')
                # Need a path that is relative to the folder we provide
                # inside the CI environment.
                if last_commit_files is None:
                    correct.text = output_file.filename_correct
                else:
                    correct.text = output_file.create_correct_filename(
                        last_commit_files[0])
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
            config.get('SAMPLE_REPOSITORY', ''), 'vm_data', kvm_name,
                    'unsafe-ccextractor'))
    except InvalidGitRepositoryError:
        log.critical("[{platform}] Could not open CCExtractor's repository "
                     "copy!".format(platform=platform))
        return
    # Return to master
    repo.heads.master.checkout(True)
    # Update repository from upstream
    try:
        origin = repo.remote('origin')
    except ValueError:
        log.critical('[{platform}] Origin remote doesn\'t exist!')
        return
    fetch_info = origin.fetch()
    if len(fetch_info) == 0:
        log.warn('[{platform}] No info fetched from remote!')
    # Pull code (finally)
    pull_info = origin.pull()
    if len(pull_info) == 0:
        log.warn("[{platform}] Didn't pull any information from "
                 "remote!".format(platform=platform))

    if pull_info[0].flags > 128:
        log.critical(
            "[{platform}] Didn't pull any information from remote: "
            "{flags}!".format(platform=platform, flags=pull_info[0].flags)
        )
        return
    # Delete the test branch if it exists, and recreate
    try:
        repo.delete_head('CI_Branch', force=True)
    except GitCommandError:
        log.warn("[{platform}] Could not delete CI_Branch head".format(
            platform=platform))
    # Remove possible left rebase-apply directory
    try:
        shutil.rmtree(os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'unsafe-ccextractor',
            '.git', 'rebase-apply'))
    except OSError:
        log.warn("[{platform}] Could not delete rebase-apply".format(
            platform=platform))
    # If PR, merge, otherwise reset to commit
    if test.test_type == TestType.pull_request:
        # Fetch PR (stored under origin/pull/<id>/head
        pull_info = origin.fetch('pull/{id}/head:CI_Branch'.format(
            id=test.pr_nr))
        if len(pull_info) == 0:
            log.warn("[{platform}] Didn't pull any information from remote "
                     "PR!".format(platform=platform))

        if pull_info[0].flags > 128:
            log.critical(
                "[{platform}] Didn't pull any information from remote PR: "
                "{flags}!".format(platform=platform, flags=pull_info[0].flags)
            )
            return
        try:
            test_branch = repo.heads['CI_Branch']
        except IndexError:
            log.critical('CI_Branch does not exist')
            return
        # Check out branch
        test_branch.checkout(True)
        # Rebase on master
        # try:
        #     repo.git.rebase('master')
        # except GitCommandError:
        #     progress = TestProgress(
        #         test.id, TestStatus.preparation,
        #         'Rebase on master'
        #     )
        #     db.add(progress)
        #     progress = TestProgress(
        #         test.id, TestStatus.canceled,
        #         'Merge conflict, please resolve.'
        #     )
        #     db.add(progress)
        #     db.commit()
        #     # Report back
        #     gh_commit = repository.statuses(test.commit)
        #
        #     with app.app_context():
        #         target_url = url_for(
        #             'test.by_id', test_id=test.id, _external=True)
        #     context = "CI - %s" % test.platform.value
        #     gh_commit.post(
        #         state=Status.ERROR, description='Failed to rebase',
        #         context=context, target_url=target_url)
        #     # Return, so next one can be handled
        #     return
        # TODO: check what happens on merge conflicts
    else:
        test_branch = repo.create_head('CI_Branch', 'HEAD')
        # Check out branch for test purposes
        test_branch.checkout(True)
        try:
            repo.head.reset(test.commit, working_tree=True)
        except GitCommandError:
            log.warn("[{platform}] Commit {hash} for test {id} does not "
                     "exist!".format(platform=platform, hash=test.commit,
                                     id=test.id))
            return
    # Power on machine
    try:
        vm.create()
        db.add(status)
        db.commit()
    except libvirt.libvirtError:
        log.critical("[{platform}] Failed to launch VM {name}".format(
            platform=platform, name=kvm_name))
    except IntegrityError:
        log.warn("[{platform}] Duplicate entry for {id}".format(
            platform=platform, id=test.id))


def queue_test(db, repository, gh_commit, commit, test_type, branch="master",
               pr_nr=0):
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
    windows = Test(TestPlatform.windows, test_type, fork.id, branch,
                   commit, pr_nr)
    db.add(windows)
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
    start_ci_vm(db, repository)


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
        repository = gh.repos(g.github['repository_owner'])(
            g.github['repository'])

        if event == "push":  # If it's a push, run the tests
            commit = payload['after']
            gh_commit = repository.statuses(commit)
            # Update the db to the new last commit
            ref = repository.git().refs('heads/master').get()
            last_commit = GeneralData.query.filter(GeneralData.key ==
                                                   'last_commit').first()
            previous_to_last_commit = GeneralData.query.filter(
                GeneralData.key == 'previous_to_last_commit').first()
            if previous_to_last_commit is None:
                prev_commit = GeneralData(
                    'previous_to_last_commit', last_commit.value)
                g.db.add(prev_commit)
            else:
                previous_to_last_commit.value = last_commit.value
            last_commit.value = ref['object']['sha']
            g.db.commit()
            queue_test(g.db, repository, gh_commit, commit, TestType.commit)

        elif event == "pull_request":  # If it's a PR, run the tests
            if payload['action'] == 'opened':
                try:
                    commit = payload['pull_request']['head']['sha']
                except KeyError:
                    g.log.critical(
                        "Didn't find a SHA value for a newly opened PR!")
                    g.log.debug(payload)
                    commit = ''
            elif payload['action'] == 'closed':
                g.log.debug('PR was closed, no after hash available')
                commit = ''
            else:
                try:
                    commit = payload['after']
                except KeyError:
                    g.log.critical("Didn't find the after SHA for the "
                                   "updated commit!")
                    g.log.debug(payload)
                    commit = ''
            pr_nr = payload['pull_request']['number']
            gh_commit = repository.statuses(commit)
            if payload['action'] == 'opened':
                # Run initial tests
                queue_test(g.db, repository, gh_commit, commit,
                           TestType.pull_request, pr_nr=pr_nr)
            elif payload['action'] == 'synchronize':
                # Run/queue a new test set
                queue_test(g.db, repository, gh_commit, commit,
                           TestType.pull_request, pr_nr=pr_nr)
            elif payload['action'] == 'closed':
                # Cancel running queue
                tests = Test.query.filter(Test.pr_nr == pr_nr).all()
                for test in tests:
                    # Add canceled status only if the test hasn't started yet
                    if len(test.progress) > 0:
                        continue
                    progress = TestProgress(test.id, TestStatus.canceled,
                                            "PR closed",
                                            datetime.datetime.now())
                    g.db.add(progress)
                    repository.statuses(test.commit).post(
                        state=Status.FAILURE, description="Tests canceled",
                        context="CI - %s" % test.platform.value,
                        target_url=url_for(
                            'test.by_id', test_id=test.id, _external=True))
            elif payload['action'] == 'reopened':
                # Run tests again
                queue_test(g.db, repository, gh_commit, commit,
                           TestType.pull_request)
        elif event == "issues":
            issue_data = payload['issue']
            issue = Issue.query.filter(
                Issue.issue_id == issue_data['number']).first()
            if issue is not None:
                issue.title = issue_data['title']
                issue.status = issue_data['state']
                g.db.commit()
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

                gh = GitHub(access_token=g.github['bot_token'])
                repository = gh.repos(g.github['repository_owner'])(
                    g.github['repository'])
                # If status is complete, remove the Kvm entry
                if status in [TestStatus.completed, TestStatus.canceled]:
                    log.debug("Test {id} has been {status}".format(
                        id=test_id, status=status))
                    var_average = 'average_time_' + test.platform.value
                    current_average = GeneralData.query.filter(
                        GeneralData.key == var_average).first()
                    average_time = 0
                    total_time = 0
                    if current_average is None:
                        platform_tests = g.db.query(Test.id).filter(
                            Test.platform == test.platform).subquery()
                        finished_tests = g.db.query(
                            TestProgress.test_id).filter(and_(
                                TestProgress.status.in_(
                                    [TestStatus.canceled,
                                     TestStatus.completed]),
                                TestProgress.test_id.in_(platform_tests))
                        ).subquery()
                        finished_tests_progress = g.db.query(
                            TestProgress).filter(
                            and_(TestProgress.test_id.in_(
                                finished_tests), TestProgress.status.in_(
                                [TestStatus.preparation, TestStatus.completed,
                                 TestStatus.canceled]))
                        ).subquery()
                        times = g.db.query(
                            finished_tests_progress.c.test_id,
                            label(
                                'time',
                                func.group_concat(
                                    finished_tests_progress.c.timestamp
                                )
                            )
                        ).group_by(finished_tests_progress.c.test_id).all()
                        for p in times:
                            parts = p.time.split(',')
                            start = datetime.datetime.strptime(
                                parts[0], '%Y-%m-%d %H:%M:%S')
                            end = datetime.datetime.strptime(
                                parts[-1], '%Y-%m-%d %H:%M:%S')
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
                        updated_average = \
                            float(current_average.value) * (number_test - 1)
                        pr = test.progress_data()
                        end_time = pr['end']
                        start_time = pr['start']
                        if end_time.tzinfo is not None:
                            end_time = end_time.replace(tzinfo=None)
                        if start_time.tzinfo is not None:
                            start_time = start_time.replace(tzinfo=None)
                        last_running_test = end_time - start_time
                        updated_average = (updated_average +
                                           last_running_test.total_seconds())
                        current_average.value = updated_average // number_test
                        g.db.commit()
                    kvm = Kvm.query.filter(Kvm.test_id == test_id).first()
                    if kvm is not None:
                        log.debug("Removing KVM entry")
                        g.db.delete(kvm)
                        g.db.commit()
                    # Start next test if necessary
                    start_ci_vm(g.db, repository, 60)
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
                            TestResultFile.regression_test_id.in_(
                                results_zero_rc
                            ),
                            TestResultFile.got.isnot(None)
                        )
                    ).scalar()
                    log.debug(
                        'Test {id} completed: {crashes} crashes, {results} '
                        'results'.format(id=test.id, crashes=crashes,
                                         results=results))
                    if crashes > 0 or results > 0:
                        state = Status.FAILURE
                        message = 'Not all tests completed successfully, ' \
                                  'please check'
                    else:
                        state = Status.SUCCESS
                        message = 'Tests completed'
                else:
                    message = progress.message

                gh_commit = repository.statuses(test.commit)
                try:
                    gh_commit.post(
                        state=state, description=message, context=context,
                        target_url=target_url
                    )
                except ApiError as a:
                    log.error('Got an exception while posting to GitHub! '
                              'Message: {message}'.format(message=a.message))

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

            elif request.form['type'] == 'logupload':
                log.debug(
                    "Received log file for test {id}".format(id=test_id))
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
                    final_path = os.path.join(
                        config.get('SAMPLE_REPOSITORY', ''), 'LogFiles',
                        '{id}{ext}'.format(id=test.id, ext='.txt')
                    )

                    os.rename(temp_path, final_path)
                    log.debug("Stored log file")

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
                regression_test = RegressionTest.query.filter(
                    RegressionTest.id == request.form['test_id']).first()
                result = TestResult(
                    test.id, regression_test.id, request.form['runTime'],
                    request.form['exitCode'], regression_test.expected_rc
                )
                g.db.add(result)
                try:
                    g.db.commit()
                except IntegrityError as e:
                    log.error('Could not save the results: {msg}'.format(
                        msg=e.message))
            return "OK"
    return "FAIL"


@mod_ci.route('/show_maintenance')
@login_required
@check_access_rights([Role.admin])
@template_renderer('maintenance.html', 404)
def show_maintenance():
    modes = MaintenanceMode.query.all()
    return {
        'modes': modes
    }


@mod_ci.route('/toggle_maintenance/<platform>/<status>')
@login_required
@check_access_rights([Role.admin])
def toggle_maintenance(platform, status):
    db_mode = MaintenanceMode.query.filter(MaintenanceMode.platform ==
                                           platform).first()
    if db_mode is None:
        status = 'failed'
        message = 'Platform Not found'
    elif status == 'True':
        db_mode.mode = 'True'
        g.db.commit()
        status = 'success'
        message = platform + ' platform is in maintenance mode'
    elif status == 'False':
        db_mode.mode = 'False'
        g.db.commit()
        status = 'success'
        message = platform + ' platform is in active mode'
    else:
        status = 'failed'
        message = 'No Change'
    return jsonify({
        'status': status,
        'message': message
    })


@mod_ci.route('/maintenance-mode/<platform>')
def in_maintenance_mode(platform):
    platforms = TestPlatform.list_all()
    if platform not in platforms:
        return 'ERROR'
    db_mode = MaintenanceMode.query.filter(MaintenanceMode.platform ==
                                           platform).first()
    if db_mode is None:
        db_mode = MaintenanceMode(
            platform, 'False')
        g.db.add(db_mode)
        g.db.commit()
    mode_value = db_mode.mode
    return mode_value
