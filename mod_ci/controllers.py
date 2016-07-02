import json
import libvirt

import datetime
from flask import Blueprint, request, abort, g, url_for
from github import GitHub
from multiprocessing import Process

from mod_ci.models import Kvm
from mod_deploy.controllers import request_from_github, is_valid_signature
from mod_test.models import TestType, Test, TestStatus, TestProgress, Fork, \
    TestPlatform

mod_ci = Blueprint('ci', __name__)


class Status:
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"


def kvm_processor_linux(db):
    from run import config, log
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
    # Prepare data
    # 1) Generate test files
    # TODO: finish
    # 2) Create git repo clone and merge PR into it (if necessary)
    # TODO: finish
    # Power on machine
    try:
        vm.create()
    except libvirt.libvirtError:
        log.critical("Failed to launch VM %s" % kvm_name)
        return


def queue_test(db, gh_commit, commit, test_type, branch="master"):
    fork = Fork.query.filter(Fork.github.like(
        "%/CCExtractor/ccextractor.git")).first()
    if test_type == TestType.commit:
        branch = "pull_request"
    # Create Linux test entry
    linux = Test(TestPlatform.linux, test_type, fork.id, branch, commit)
    db.add(linux)
    # Create Windows test entry
    windows = Test(TestPlatform.windows, test_type, fork.id, branch, commit)
    db.add(windows)
    # Update statuses on GitHub
    gh_commit.post(
        state=Status.PENDING, description="Tests queued",
        context="CI - %s" % linux.platform.value,
        target_url=url_for('test.test', test_id=linux.id))
    gh_commit.post(
        state=Status.PENDING, description="Tests queued",
        context="CI - %s" % windows.platform.value,
        target_url=url_for('test.test', test_id=windows.id))
    # Kick off KVM process
    p_lin = Process(target=kvm_processor_linux, args=(db))
    p_lin.start()
    p_win = Process(target=kvm_processor_windows, args=(db))
    p_win.start()


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
            pass

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
                pass
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
                pass
            elif payload['action'] == 'reopened':
                # Run tests again
                queue_test(g.db, gh_commit, commit, TestType.pull_request)
                pass
            pass
        else:
            # Unknown type
            g.log.warning('CI unrecognized event: %s' % event)

        return json.dumps({'msg': 'EOL'})


@mod_ci.route('/progress-reporter/<test_id>/<token>', methods=['POST'])
def progress_reporter(test_id, token):
    # Verify token
    test = Test.query.filter(Test.id == test_id).first()
    if test is not None and test.token == token:
        # TODO: finish
        return "OK"
    return "FAIL"
