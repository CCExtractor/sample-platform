"""maintains all functionality related running virtual machines, starting and tracking tests."""

import datetime
import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from collections import defaultdict
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

import googleapiclient.discovery
import requests
from flask import (Blueprint, abort, flash, g, jsonify, redirect, request,
                   url_for)
from github import (Auth, Commit, Github, GithubException, GithubObject,
                    Repository)
from google.oauth2 import service_account
from lxml import etree
from markdown2 import markdown
from pymysql.err import IntegrityError
from sqlalchemy import and_, func
from sqlalchemy.sql import label
from sqlalchemy.sql.functions import count
from werkzeug.utils import secure_filename

from database import DeclEnum, create_session
from decorators import get_menu_entries, template_renderer
from mod_auth.controllers import check_access_rights, login_required
from mod_auth.models import Role
from mod_ci.forms import AddUsersToBlacklist, DeleteUserForm
from mod_ci.models import (BlockedUsers, CategoryTestInfo, GcpInstance,
                           MaintenanceMode, PrCommentInfo, Status)
from mod_customized.models import CustomizedTest
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import (Category, RegressionTest,
                                   RegressionTestOutput)
from mod_sample.models import Issue
from mod_test.controllers import get_test_results
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)
from utility import is_valid_signature, request_from_github

# Timeout constants (in seconds)
GITHUB_API_TIMEOUT = 30  # Timeout for GitHub API calls
GCP_API_TIMEOUT = 60  # Timeout for GCP API calls
ARTIFACT_DOWNLOAD_TIMEOUT = 300  # 5 minutes for artifact downloads
GCP_OPERATION_MAX_WAIT = 1800  # 30 minutes max wait for GCP operations

# Retry constants
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
MAX_BACKOFF = 30  # seconds

T = TypeVar('T')


def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = MAX_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF,
    max_backoff: float = MAX_BACKOFF,
    retryable_exceptions: Any = (GithubException, requests.RequestException)
) -> T:
    """
    Execute a function with exponential backoff retry logic.

    :param func: The function to execute (should be a callable with no arguments, use lambda for args)
    :param max_retries: Maximum number of retry attempts
    :param initial_backoff: Initial backoff time in seconds
    :param max_backoff: Maximum backoff time in seconds
    :param retryable_exceptions: Tuple of exception types that should trigger a retry
    :return: The result of the function call
    :raises: The last exception if all retries fail
    """
    from run import log

    last_exception: Optional[Exception] = None
    backoff = initial_backoff

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                log.warning(f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            else:
                log.error(f"All {max_retries + 1} attempts failed. Last error: {e}")

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("retry_with_backoff: unexpected state - no exception captured")


def safe_db_commit(db, operation_description: str = "database operation") -> bool:
    """
    Safely commit a database transaction with rollback on failure.

    :param db: The database session
    :param operation_description: Description of the operation for logging
    :return: True if commit succeeded, False otherwise
    """
    from run import log

    try:
        db.commit()
        return True
    except Exception as e:
        log.error(f"Database commit failed during {operation_description}: {e}")
        try:
            db.rollback()
            log.info(f"Successfully rolled back transaction for {operation_description}")
        except Exception as rollback_error:
            log.error(f"Rollback also failed for {operation_description}: {rollback_error}")
        return False


# User-friendly messages for known GCP error codes
GCP_ERROR_MESSAGES = {
    'ZONE_RESOURCE_POOL_EXHAUSTED': (
        "GCP resources temporarily unavailable in the configured zone. "
        "The test will be retried automatically when resources become available."
    ),
    'QUOTA_EXCEEDED': (
        "GCP quota limit reached. Please wait for other tests to complete "
        "or contact the administrator."
    ),
    'RESOURCE_NOT_FOUND': "Required GCP resource not found. Please contact the administrator.",
    'RESOURCE_ALREADY_EXISTS': "A VM with this name already exists. Please contact the administrator.",
    'TIMEOUT': "GCP operation timed out. The test will be retried automatically.",
}


def parse_gcp_error(result: Dict, log=None) -> str:
    """
    Parse a GCP API error response and return a user-friendly message.

    GCP errors have the structure:
    {
        'error': {
            'errors': [{'code': 'ERROR_CODE', 'message': '...'}]
        }
    }

    For known error codes, returns a user-friendly message.
    For unknown errors, logs the details server-side and returns a generic message
    to avoid exposing potentially sensitive information.

    :param result: The GCP API response dictionary
    :param log: Optional logger instance. If not provided, uses module logger.
    :return: A user-friendly error message
    """
    import logging
    if log is None:
        log = logging.getLogger('Platform')

    if not isinstance(result, dict):
        log.error(f"GCP error (non-dict): {result}")
        return "VM creation failed. Please contact the administrator."

    error = result.get('error')
    if error is None:
        log.error(f"GCP error (no error key): {result}")
        return "VM creation failed. Please contact the administrator."

    if not isinstance(error, dict):
        log.error(f"GCP error (error not dict): {error}")
        return "VM creation failed. Please contact the administrator."

    errors = error.get('errors', [])
    if not errors:
        log.error(f"GCP error (empty errors list): {error}")
        return "VM creation failed. Please contact the administrator."

    # Get the first error (usually the most relevant)
    first_error = errors[0] if isinstance(errors, list) and len(errors) > 0 else {}
    error_code = first_error.get('code', 'UNKNOWN')
    error_message = first_error.get('message', 'No details provided')

    # Check if we have a user-friendly message for this error code
    if error_code in GCP_ERROR_MESSAGES:
        return GCP_ERROR_MESSAGES[error_code]

    # For unknown errors, log full details server-side but return generic message
    # to avoid exposing potentially sensitive information (project names, zones, etc.)
    log.error(f"GCP error ({error_code}): {error_message}")
    return f"VM creation failed ({error_code}). Please contact the administrator."


mod_ci = Blueprint('ci', __name__)


class Workflow_builds(DeclEnum):
    """Define GitHub Action workflow build names."""

    LINUX = "Build CCExtractor on Linux"
    WINDOWS = "Build CCExtractor on Windows"


class Artifact_names(DeclEnum):
    """Define CCExtractor GitHub Artifacts names."""

    linux = "CCExtractor Linux build"
    windows = "CCExtractor Windows Release build"


def is_valid_commit_hash(commit: Optional[str]) -> bool:
    """
    Validate that a string is a valid Git commit hash.

    A valid commit hash is:
    - Not None or empty
    - At least 7 characters (short hash) up to 40 characters (full SHA-1)
    - Contains only hexadecimal characters (0-9, a-f, A-F)
    - Not the Git null SHA (all zeros)

    :param commit: The commit hash to validate
    :type commit: Optional[str]
    :return: True if valid, False otherwise
    :rtype: bool
    """
    if not commit or not isinstance(commit, str):
        return False

    commit = commit.strip()

    # Check length (7-40 characters for valid git hashes)
    if len(commit) < 7 or len(commit) > 40:
        return False

    # Check for null SHA (all zeros)
    if commit == '0' * len(commit):
        return False

    # Check that it's a valid hexadecimal string
    try:
        int(commit, 16)
        return True
    except ValueError:
        return False


# Maximum number of artifacts to search through when looking for a specific commit
# GitHub keeps artifacts for 90 days by default, so this should be enough
MAX_ARTIFACTS_TO_SEARCH = 500


def find_artifact_for_commit(repository, commit_sha: str, platform: Any, log) -> Optional[Any]:
    """
    Find a build artifact for a specific commit and platform.

    This function properly handles GitHub API pagination to search through
    all available artifacts. This prevents race conditions where tests
    fail because artifacts are not found due to pagination issues.

    :param repository: GitHub repository object
    :type repository: Repository.Repository
    :param commit_sha: The commit SHA to find artifact for
    :type commit_sha: str
    :param platform: The platform (linux or windows) - TestPlatform enum value
    :type platform: TestPlatform
    :param log: Logger instance
    :return: The artifact object if found, None otherwise
    :rtype: Optional[Artifact]
    """
    if platform == TestPlatform.linux:
        artifact_name = Artifact_names.linux
    else:
        artifact_name = Artifact_names.windows

    try:
        artifacts = repository.get_artifacts()
        artifacts_checked = 0

        for artifact in artifacts:
            artifacts_checked += 1

            if artifact.name == artifact_name and artifact.workflow_run.head_sha == commit_sha:
                log.debug(f"Found artifact '{artifact_name}' for commit {commit_sha[:8]} "
                          f"(checked {artifacts_checked} artifacts)")
                return artifact

            # Limit search to prevent excessive API calls
            if artifacts_checked >= MAX_ARTIFACTS_TO_SEARCH:
                log.warning(f"Reached max artifact search limit ({MAX_ARTIFACTS_TO_SEARCH}) "
                            f"without finding artifact for commit {commit_sha[:8]}")
                break

        log.debug(f"No artifact '{artifact_name}' found for commit {commit_sha[:8]} "
                  f"(checked {artifacts_checked} artifacts)")
        return None

    except Exception as e:
        log.error(f"Error searching for artifact: {type(e).__name__}: {e}")
        return None


def verify_artifacts_exist(repository, commit_sha: str, log) -> Dict[str, bool]:
    """
    Verify that build artifacts exist for a commit before queuing tests.

    This function should be called before queue_test() to prevent the race
    condition where tests are queued before artifacts are available.

    :param repository: GitHub repository object
    :type repository: Repository.Repository
    :param commit_sha: The commit SHA to verify
    :type commit_sha: str
    :param log: Logger instance
    :return: Dict with 'linux' and 'windows' keys indicating artifact availability
    :rtype: Dict[str, bool]
    """
    result = {'linux': False, 'windows': False}

    linux_artifact = find_artifact_for_commit(repository, commit_sha, TestPlatform.linux, log)
    if linux_artifact is not None:
        result['linux'] = True
        log.info(f"Linux artifact verified for commit {commit_sha[:8]}")
    else:
        log.warning(f"Linux artifact NOT found for commit {commit_sha[:8]}")

    windows_artifact = find_artifact_for_commit(repository, commit_sha, TestPlatform.windows, log)
    if windows_artifact is not None:
        result['windows'] = True
        log.info(f"Windows artifact verified for commit {commit_sha[:8]}")
    else:
        log.warning(f"Windows artifact NOT found for commit {commit_sha[:8]}")

    return result


@mod_ci.before_app_request
def before_app_request() -> None:
    """Organize menu content such as Platform management before request."""
    config_entries = get_menu_entries(
        g.user, 'Platform mgmt', 'cog', [], '', [
            {'title': 'Maintenance', 'icon': 'wrench',
             'route': 'ci.show_maintenance', 'access': [Role.admin]},  # type: ignore
            {'title': 'Blocked Users', 'icon': 'ban',
             'route': 'ci.blocked_users', 'access': [Role.admin]}  # type: ignore
        ]
    )
    if 'config' in g.menu_entries and 'entries' in config_entries:
        g.menu_entries['config']['entries'] = config_entries['entries'] + g.menu_entries['config']['entries']
    else:
        g.menu_entries['config'] = config_entries


def start_platforms(repository, delay=None, platform=None) -> None:
    """
    Start new test on both platforms.

    :param repository: repository to run tests on
    :type repository: str
    :param delay: time delay after which to start gcp_instance function
    :type delay: int
    :param platform: operating system
    :type platform: str
    """
    from run import app, config, log

    vm_max_runtime = config.get("GCP_INSTANCE_MAX_RUNTIME", 120)
    zone = config.get('ZONE', '')
    project = config.get('PROJECT_NAME', '')
    # Check if zone and project both are provided
    if zone == "":
        log.critical('GCP zone name is empty!')
        return

    if project == "":
        log.critical('GCP project name is empty!')
        return

    with app.app_context():
        from flask import current_app
        app = current_app._get_current_object()  # type: ignore[attr-defined]

        # Create a database session
        db = create_session(config.get('DATABASE_URI', ''))

        compute = get_compute_service_object()
        delete_expired_instances(compute, vm_max_runtime, project, zone, db, repository)

        if platform is None or platform == TestPlatform.linux:
            log.info('Define process to run Linux GCP instances')
            gcp_instance(app, db, TestPlatform.linux, repository, delay)
            log.info('Linux GCP instances process kicked off')

        if platform is None or platform == TestPlatform.windows:
            log.info('Define process to run Windows GCP instances')
            gcp_instance(app, db, TestPlatform.windows, repository, delay)
            log.info('Windows GCP instances process kicked off')


def get_running_instances(compute, project, zone) -> list:
    """
    Get details of all the running GCP VM instances.

    :param compute: The cloud compute engine service object
    :type compute: googleapiclient.discovery.Resource
    :param project: The GCP project name
    :type project: str
    :param zone: Configured zone for the VM instances
    :type zone: str
    :return: List of VM instances
    :rtype: list
    """
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else []


def is_instance_testing(vm_name) -> bool:
    """
    Check if VM name is of the correct format and return if it is used for testing or not.

    :param vm_name: Name of the VM machine to be identified
    :type vm_name: str
    :return: Boolean whether instance is used for testing or not
    :rtype: bool
    """
    for platform in TestPlatform:
        if re.fullmatch(f"{platform.value}-[0-9]+", vm_name):
            return True
    return False


def delete_expired_instances(compute, max_runtime, project, zone, db, repository) -> None:
    """
    Get all running instances and delete instances whose maximum runtime limit is reached.

    :param compute: The cloud compute engine service object
    :type compute: googleapiclient.discovery.Resource
    :param max_runtime: The maximum runtime limit for VM instances
    :type max_runtime: int
    :param project: The GCP project name
    :type project: str
    :param zone: Zone for the new VM instance
    :type zone: str
    """
    for instance in get_running_instances(compute, project, zone):
        vm_name = instance['name']
        if is_instance_testing(vm_name):
            creationTimestamp = datetime.datetime.strptime(instance['creationTimestamp'], '%Y-%m-%dT%H:%M:%S.%f%z')
            currentTimestamp = datetime.datetime.now(datetime.timezone.utc)
            if currentTimestamp - creationTimestamp >= datetime.timedelta(minutes=max_runtime):
                # Update test status in database and on GitHub
                platform_name, test_id = vm_name.split('-')
                test = Test.query.filter(Test.id == test_id).first()
                message = "Could not complete test, time limit exceeded"
                progress = TestProgress(test_id, TestStatus.canceled, message)
                db.add(progress)
                if not safe_db_commit(db, f"canceling timed-out test {test_id}"):
                    continue  # Skip to next instance if commit failed

                gh_commit = repository.get_commit(test.commit)
                if gh_commit is not None:
                    update_status_on_github(gh_commit, Status.ERROR, message, f"CI - {platform_name}")

                # Delete VM instance
                operation = delete_instance(compute, project, zone, vm_name)
                wait_for_operation(compute, project, zone, operation['name'])


def gcp_instance(app, db, platform, repository, delay) -> None:
    """
    Find all the pending tests and start running them in new GCP instances.

    :param app: The Flask app
    :type app: Flask
    :param db: database connection
    :type db: sqlalchemy.orm.scoping.scoped_session
    :param platform: operating system
    :type platform: str
    :param repository: repository to run tests on
    :type repository: str
    :param delay: time delay after which to start gcp_instance function
    :type delay: int
    """
    from run import config, get_github_config, log

    github_config = get_github_config(config)

    log.info(f"[{platform}] Running gcp_instance")

    if delay is not None:
        import time
        log.debug(f'[{platform}] Sleeping for {delay} seconds')
        time.sleep(delay)

    maintenance_mode = MaintenanceMode.query.filter(MaintenanceMode.platform == platform).first()
    if maintenance_mode is not None and maintenance_mode.disabled:
        log.debug(f'[{platform}] In maintenance mode! Waiting...')
        return

    finished_tests = db.query(TestProgress.test_id).filter(
        TestProgress.status.in_([TestStatus.canceled, TestStatus.completed])
    )

    running_tests = db.query(GcpInstance.test_id)

    pending_tests = Test.query.filter(
        Test.id.notin_(finished_tests), Test.id.notin_(running_tests), Test.platform == platform
    ).order_by(Test.id.asc())

    compute = get_compute_service_object()

    for test in pending_tests:
        if test.test_type == TestType.pull_request:
            try:
                gh_commit = retry_with_backoff(lambda t=test: repository.get_commit(t.commit))
                if test.pr_nr == 0:
                    log.warn(f'[{platform}] Test {test.id} is invalid')
                    deschedule_test(gh_commit, message="Invalid PR number", test=test, db=db)
                    continue
                test_pr = retry_with_backoff(lambda t=test: repository.get_pull(t.pr_nr))
                # Note: We intentionally do NOT check if test.commit != test_pr.head.sha
                # If a new commit was pushed to the PR, a new test entry will be created for it.
                # We should still run the test for the commit that was originally queued.
                # This prevents the confusing "PR closed or updated" error when users push fixes.
                if test_pr.state != 'open':
                    log.info(f"[{platform}] PR {test.pr_nr} is closed, descheduling test {test.id}")
                    deschedule_test(gh_commit, message="PR is closed", test=test, db=db)
                    continue
            except GithubException as e:
                log.error(f"GitHub API error for test {test.id} after retries: {e}")
                continue  # Skip this test, try next one
            except Exception as e:
                log.error(f"Unexpected error checking PR status for test {test.id}: {e}")
                continue
        start_test(compute, app, db, repository, test, github_config['bot_token'])


def get_compute_service_object() -> googleapiclient.discovery.Resource:
    """Get a Cloud Compute Engine service object."""
    from run import config

    scopes = config.get('SCOPES', '')
    sa_file = os.path.join(config.get('INSTALL_FOLDER', ''), config.get('SERVICE_ACCOUNT_FILE', ''))

    credentials = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes)

    return googleapiclient.discovery.build('compute', 'v1', credentials=credentials)


def mark_test_failed(db, test, repository, message: str) -> bool:
    """
    Mark a test as failed and update GitHub status.

    This function ensures that GitHub is always notified of the failure,
    even if database operations fail. The GitHub status update is critical
    to prevent tests from appearing stuck in "pending" state forever.

    :param db: Database session
    :type db: sqlalchemy.orm.scoping.scoped_session
    :param test: The test to mark as failed
    :type test: mod_test.models.Test
    :param repository: GitHub repository object
    :type repository: Repository.Repository
    :param message: Error message to display
    :type message: str
    :return: True if operation succeeded, False otherwise
    """
    from run import log

    db_success = False
    github_success = False

    # Step 1: Try to update the database
    try:
        progress = TestProgress(test.id, TestStatus.canceled, message)
        db.add(progress)
        db.commit()
        db_success = True
        log.info(f"Test {test.id}: Database updated with failure status")
    except Exception as e:
        log.error(f"Test {test.id}: Failed to update database: {e}")
        # Continue to try GitHub update even if DB fails

    # Step 2: Try to update GitHub status (CRITICAL - must not be skipped)
    # Use retry logic since this is critical to prevent stuck "pending" status
    try:
        # Build target_url first (doesn't need retry)
        from flask import url_for
        try:
            target_url = url_for('test.by_id', test_id=test.id, _external=True)
        except RuntimeError:
            # Outside of request context
            target_url = f"https://sampleplatform.ccextractor.org/test/{test.id}"

        # Use retry_with_backoff for GitHub API calls
        def update_github_status():
            gh_commit = repository.get_commit(test.commit)
            update_status_on_github(gh_commit, Status.ERROR, message, f"CI - {test.platform.value}", target_url)

        retry_with_backoff(update_github_status, max_retries=3, initial_backoff=2.0)
        github_success = True
        log.info(f"Test {test.id}: GitHub status updated to ERROR: {message}")
    except GithubException as e:
        log.error(f"Test {test.id}: GitHub API error while updating status (after retries): {e.status} - {e.data}")
    except Exception as e:
        log.error(f"Test {test.id}: Failed to update GitHub status (after retries): {type(e).__name__}: {e}")

    # Log final status
    if db_success and github_success:
        log.info(f"Test {test.id}: Successfully marked as failed")
    elif github_success:
        log.warning(f"Test {test.id}: GitHub updated but database update failed - test may be retried")
    elif db_success:
        log.error(f"Test {test.id}: Database updated but GitHub status NOT updated - "
                  f"status will appear stuck as 'pending' on GitHub!")
    else:
        log.critical(f"Test {test.id}: BOTH database and GitHub updates failed - "
                     f"test is in inconsistent state!")

    return db_success and github_success


def _diagnose_missing_artifact(repository, commit_sha: str, platform, log) -> tuple:
    """
    Diagnose why an artifact was not found for a commit.

    Checks the workflow run status to provide a more helpful error message and
    indicate whether this is a retryable situation (build still in progress)
    or a permanent failure (build failed, artifact expired).

    :param repository: GitHub repository object
    :param commit_sha: The commit SHA to check
    :param platform: The platform (TestPlatform.linux or TestPlatform.windows)
    :param log: Logger instance
    :return: Tuple of (error_message: str, is_retryable: bool)
             is_retryable=True means the test should NOT be marked as failed
             and should be left for the next cron cycle to retry
    """
    if platform == TestPlatform.linux:
        expected_workflow = Workflow_builds.LINUX
    else:
        expected_workflow = Workflow_builds.WINDOWS

    try:
        # Build workflow name lookup
        workflow: Dict[int, Optional[str]] = defaultdict(lambda: None)
        for active_workflow in repository.get_workflows():
            workflow[active_workflow.id] = active_workflow.name

        # Check workflow runs for this commit
        workflow_found = False
        for workflow_run in repository.get_workflow_runs(head_sha=commit_sha):
            workflow_run_name = workflow[workflow_run.workflow_id]
            if workflow_run_name != expected_workflow:
                continue

            workflow_found = True
            if workflow_run.status != "completed":
                # Build is still running - this is RETRYABLE
                # Don't mark as failed, let the next cron cycle retry
                message = (f"Build still in progress: '{expected_workflow}' is {workflow_run.status}. "
                           f"Will retry when build completes.")
                return (message, True)  # Retryable
            elif workflow_run.conclusion != "success":
                # Build failed - this is a PERMANENT failure
                message = (f"Build failed: '{expected_workflow}' finished with conclusion "
                           f"'{workflow_run.conclusion}'. Check the GitHub Actions logs for details.")
                return (message, False)  # Not retryable
            else:
                # Build succeeded but artifact not found
                # Check if the build completed very recently - if so, this might be
                # GitHub API propagation delay (artifact exists but not visible yet)
                # In that case, treat as retryable
                ARTIFACT_PROPAGATION_GRACE_PERIOD = 300  # 5 minutes in seconds
                try:
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    # workflow_run.updated_at is when the run completed
                    if workflow_run.updated_at:
                        completed_at = workflow_run.updated_at
                        if completed_at.tzinfo is None:
                            completed_at = completed_at.replace(tzinfo=timezone.utc)
                        seconds_since_completion = (now - completed_at).total_seconds()
                        if seconds_since_completion < ARTIFACT_PROPAGATION_GRACE_PERIOD:
                            message = (f"Build completed recently ({int(seconds_since_completion)}s ago): "
                                       f"'{expected_workflow}' succeeded but artifact not yet visible. "
                                       f"Will retry (GitHub API propagation delay).")
                            log.info(f"Artifact not found but build completed {int(seconds_since_completion)}s ago - "
                                     f"treating as retryable (possible API propagation delay)")
                            return (message, True)  # Retryable - API propagation delay
                except Exception as e:
                    log.warning(f"Could not check workflow completion time: {e}")
                    # Fall through to permanent failure

                # Build completed more than 5 minutes ago - artifact should be visible
                # This is a PERMANENT failure (artifact expired or not uploaded)
                message = (f"Artifact not found: '{expected_workflow}' completed successfully, "
                           f"but no artifact was found. The artifact may have expired (GitHub deletes "
                           f"artifacts after a retention period) or was not uploaded properly.")
                return (message, False)  # Not retryable

        if not workflow_found:
            # No workflow run found - could be queued or not triggered
            # This is RETRYABLE (workflow might be queued or path filters excluded it)
            message = (f"No workflow run found: '{expected_workflow}' has not run for commit "
                       f"{commit_sha[:7]}. The workflow may be queued, or was not triggered "
                       f"due to path filters. Will retry.")
            return (message, True)  # Retryable

    except Exception as e:
        log.warning(f"Failed to diagnose missing artifact: {e}")
        # On diagnostic failure, assume retryable to be safe
        return (f"No build artifact found for this commit (diagnostic check failed: {e})", True)

    return ("No build artifact found for this commit", True)  # Default to retryable


def start_test(compute, app, db, repository: Repository.Repository, test, bot_token) -> None:
    """
    Start a VM instance and run the tests.

    Creates testing xml files to test the changes.
    Downloads the build artifacts generated during GitHub Action workflows.
    Create a GCP instance and start the test.

    :param compute: The cloud compute engine service object
    :type compute: googleapiclient.discovery.Resource
    :param app: The Flask app
    :type app: Flask
    :param db: database connection
    :type db: sqlalchemy.orm.scoping.scoped_session
    :param platform: operating system
    :type platform: str
    :param repository: repository to run tests on
    :type repository: str
    :param test: The test which is to be started
    :type test: mod_test.models.Test
    :param bot_token: The GitHub bot token
    :type bot_token: str
    :return: Nothing
    :rtype: None
    """
    from run import config, log

    # Check if test is already being processed (basic locking)
    existing_instance = GcpInstance.query.filter(GcpInstance.test_id == test.id).first()
    if existing_instance is not None:
        log.warning(f"Test {test.id} already has a GCP instance, skipping duplicate start")
        return

    # Check if test already has progress (already started or finished)
    existing_progress = TestProgress.query.filter(TestProgress.test_id == test.id).first()
    if existing_progress is not None:
        log.warning(f"Test {test.id} already has progress entries, skipping")
        return

    gcp_instance_name = f"{test.platform.value}-{test.id}"
    log.debug(f'[{gcp_instance_name}] Starting test {test.id}')

    test_folder = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'vm_data', gcp_instance_name)

    Path(test_folder).mkdir(parents=True, exist_ok=True)

    status = GcpInstance(gcp_instance_name, test.id)
    # Prepare data
    # 0) Write url to file
    with app.app_context():
        full_url = url_for('ci.progress_reporter', test_id=test.id, token=test.token, _external=True, _scheme="https")

    # 1) Generate test files
    base_folder = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'vm_data', gcp_instance_name, 'ci-tests')
    Path(base_folder).mkdir(parents=True, exist_ok=True)

    categories = Category.query.order_by(Category.id.desc()).all()
    commit_name = 'fetch_commit_' + test.platform.value
    commit_hash = GeneralData.query.filter(GeneralData.key == commit_name).first().value
    last_commit = Test.query.filter(and_(Test.commit == commit_hash, Test.platform == test.platform)).first()

    if last_commit is not None:
        log.debug(f"[{gcp_instance_name}] We will compare against the results of test {last_commit.id}")

    regression_ids = test.get_customized_regressiontests()

    # BREAKS REGULAR TESTS
    # if len(regression_ids) == 0:
    #     log.debug(f"[{gcp_instance_name}] No regression tests, skipping test {test.id}")
    #     return

    # Init collection file
    multi_test = etree.Element('multitest')
    for category in categories:
        # Skip categories without tests
        if len(category.regression_tests) == 0:
            continue
        # Create XML file for test
        file_name = f'{category.name}.xml'
        single_test = etree.Element('tests')
        should_write_xml = False
        for regression_test in category.regression_tests:
            if regression_test.id not in regression_ids:
                log.debug(f'Skipping RT #{regression_test.id} ({category.name}) as not in scope')
                continue
            should_write_xml = True
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
                    log.debug(f"Selecting original file for RT #{regression_test.id} ({category.name})")
                    correct.text = output_file.filename_correct
                else:
                    correct.text = output_file.create_correct_filename(last_commit_files[0])

                expected = etree.SubElement(file_node, 'expected')
                expected.text = output_file.filename_expected(regression_test.sample.sha)
        if not should_write_xml:
            continue
        save_xml_to_file(single_test, base_folder, file_name)
        # Append to collection file
        test_file = etree.SubElement(multi_test, 'testfile')
        location = etree.SubElement(test_file, 'location')
        location.text = file_name

    save_xml_to_file(multi_test, base_folder, 'TestAll.xml')

    # 2) Download the artifact for the current build from GitHub Actions
    # Use the improved artifact search function that handles pagination properly
    base_folder = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'vm_data', gcp_instance_name, 'unsafe-ccextractor')
    Path(base_folder).mkdir(parents=True, exist_ok=True)

    log.info(f"Test {test.id}: Searching for {test.platform.value} artifact for commit {test.commit[:8]}")
    artifact = find_artifact_for_commit(repository, test.commit, test.platform, log)

    if artifact is None:
        # Use diagnostic function to determine if this is retryable
        error_detail, is_retryable = _diagnose_missing_artifact(repository, test.commit, test.platform, log)

        if is_retryable:
            # Build is still in progress or workflow is queued - don't mark as failed
            # Just return and let the next cron cycle retry this test
            log.info(f"Test {test.id}: {error_detail}")
            return

        # Permanent failure - mark the test as failed
        log.critical(f"Test {test.id}: Could not find artifact for commit {test.commit[:8]}: {error_detail}")
        mark_test_failed(db, test, repository, error_detail)
        return

    log.info(f"Test {test.id}: Found artifact '{artifact.name}' (ID: {artifact.id})")
    artifact_url = artifact.archive_download_url

    try:
        auth_header = f"token {bot_token}"
        r = requests.get(
            artifact_url,
            headers={"Authorization": auth_header},
            timeout=ARTIFACT_DOWNLOAD_TIMEOUT
        )
    except requests.exceptions.Timeout:
        log.critical(f"Test {test.id}: Artifact download timed out after {ARTIFACT_DOWNLOAD_TIMEOUT}s")
        mark_test_failed(db, test, repository, "Artifact download timed out")
        return
    except Exception as e:
        log.critical(f"Test {test.id}: Could not fetch artifact: {e}")
        mark_test_failed(db, test, repository, f"Artifact download failed: {e}")
        return

    if r.status_code != 200:
        log.critical(f"Test {test.id}: Could not fetch artifact, response code: {r.status_code}")
        mark_test_failed(db, test, repository, f"Artifact download failed: HTTP {r.status_code}")
        return

    zip_path = os.path.join(base_folder, 'ccextractor.zip')
    with open(zip_path, 'wb') as f:
        f.write(r.content)
    with zipfile.ZipFile(zip_path, 'r') as artifact_zip:
        artifact_zip.extractall(base_folder)

    log.info(f"Test {test.id}: Artifact downloaded and extracted successfully")

    zone = config.get('ZONE', '')
    project_id = config.get('PROJECT_NAME', '')
    operation = create_instance(compute, project_id, zone, test, full_url)
    result = wait_for_operation(compute, project_id, zone, operation['name'])
    # Check if result indicates success (result is a dict with no 'error' key)
    if isinstance(result, dict) and 'error' not in result:
        db.add(status)
        if not safe_db_commit(db, f"recording GCP instance for test {test.id}"):
            log.error(f"Failed to record GCP instance for test {test.id}, but VM was created")
    else:
        error_msg = parse_gcp_error(result)
        log.error(f"Error creating test instance for test {test.id}, result: {result}")
        mark_test_failed(db, test, repository, error_msg)


def create_instance(compute, project, zone, test, reportURL) -> Dict:
    """
    Start an instance and pass the VM metadata.

    :param compute: The cloud compute engine service object
    :type compute: googleapiclient.discovery.Resource
    :param project: The GCP project name
    :type project: str
    :param zone: Zone for the new VM instance
    :type zone: str
    :param test: The test for which VM is to be started
    :type test: mod_test.models.Test
    :param reportURL: Test-specific URL link for reporting progress to server
    :type reportURL: str
    :return: Create operation details after VM creation
    :rtype: Dict
    """
    from run import config

    if test.platform == TestPlatform.linux:
        image_response = compute.images().getFromFamily(project=config.get('LINUX_INSTANCE_PROJECT_NAME', ''),
                                                        family=config.get('LINUX_INSTANCE_FAMILY_NAME', '')).execute()
        startup_script = open(os.path.join(config.get('INSTALL_FOLDER', ''), 'install', 'ci-vm',
                                           'ci-linux', 'startup-script.sh'), 'r').read()
        metadata_items = [
            {'key': 'startup-script', 'value': startup_script},
            {'key': 'reportURL', 'value': reportURL},
            {'key': 'bucket', 'value': config.get('GCS_BUCKET_NAME', '')}
        ]
    elif test.platform == TestPlatform.windows:
        image_response = compute.images().getFromFamily(project=config.get('WINDOWS_INSTANCE_PROJECT_NAME', ''),
                                                        family=config.get('WINDOWS_INSTANCE_FAMILY_NAME', '')).execute()
        startup_script = open(os.path.join(config.get('INSTALL_FOLDER', ''), 'install', 'ci-vm',
                                           'ci-windows', 'startup-script.ps1'), 'r').read()
        service_account = open(os.path.join(config.get('INSTALL_FOLDER', ''),
                                            config.get('SERVICE_ACCOUNT_FILE', '')), 'r').read()
        rclone_conf = open(os.path.join(config.get('INSTALL_FOLDER', ''), 'install', 'ci-vm',
                                        'ci-windows', 'rclone.conf'), 'r').read()
        metadata_items = [
            {'key': 'windows-startup-script-ps1', 'value': startup_script},
            {'key': 'service_account', 'value': service_account},
            {'key': 'rclone_conf', 'value': rclone_conf},
            {'key': 'reportURL', 'value': reportURL},
            {'key': 'bucket', 'value': config.get('GCS_BUCKET_NAME', '')}
        ]
    source_disk_image = image_response['selfLink']

    vm_name = f"{test.platform.value}-{test.id}"

    vm_config = get_config_for_gcp_instance(vm_name, source_disk_image, metadata_items)

    return compute.instances().insert(
        project=project,
        zone=zone,
        body=vm_config).execute()


def delete_instance(compute, project, zone, vm_name) -> Dict:
    """
    Delete the GCP instance with given name.

    :param compute: The cloud compute engine service object
    :type compute: googleapiclient.discovery.Resource
    :param project: The GCP project name
    :type project: str
    :param zone: Zone for the new VM instance
    :type zone: str
    :param vm_name: Name of the instance to be deleted
    :type vm_name: str
    :return: Delete operation details after VM deletion
    :rtype: Dict
    """
    return compute.instances().delete(
        project=project,
        zone=zone,
        instance=vm_name).execute()


def get_config_for_gcp_instance(vm_name, source_disk_image, metadata_items) -> Dict:
    """
    Get VM config for new VM instance.

    :param vm_name: The name of the instance to be created
    :type vm_name: str
    :param source_disk_image: Source disk image for new instance
    :type source_disk_image: str
    :param metadata_items: VM Metadata for new instance
    :type metadata_items: list
    :return: Config for new instance
    :rtype: Dict
    """
    from run import config

    # Configure the machine
    machine_type = config.get('MACHINE_TYPE', '')

    return {
        'name': vm_name,
        'machineType': machine_type,

        # Specify the boot disk and the image to use as a source.
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': source_disk_image,
                }
            }
        ],

        # Specify a network interface with NAT to access the public
        # internet.
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [
                {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
            ]
        }],

        # Allow the instance to access cloud storage and logging.
        'serviceAccounts': [{
            'email': 'default',
            'scopes': [
                'https://www.googleapis.com/auth/devstorage.read_write',
                'https://www.googleapis.com/auth/logging.write'
            ]
        }],

        # Metadata is readable from the instance and allows you to
        # pass configuration from deployment scripts to instances.
        'metadata': {
            'items': metadata_items
        }
    }


def wait_for_operation(compute, project, zone, operation, max_wait: int = GCP_OPERATION_MAX_WAIT) -> Dict:
    """
    Wait for an operation to get completed with timeout.

    :param compute: The cloud compute engine service object
    :type compute: googleapiclient.discovery.Resource
    :param project: The GCP project name
    :type project: str
    :param zone: Zone for the new VM instance
    :type zone: str
    :param operation: Operation name for which server is waiting
    :type operation: str
    :param max_wait: Maximum time to wait in seconds (default: 30 minutes)
    :type max_wait: int
    :return: Response received after operation completion
    :rtype: Dict
    """
    from run import log
    log.info(f"Waiting for operation {operation} to finish (max {max_wait}s)")
    start_time = time.time()
    poll_interval = 1.0  # Start with 1 second polling

    while True:
        elapsed = time.time() - start_time
        if elapsed >= max_wait:
            log.error(f"Operation {operation} timed out after {elapsed:.0f} seconds")
            return {
                'status': 'TIMEOUT',
                'error': {
                    'errors': [{
                        'code': 'TIMEOUT',
                        'message': f'Operation timed out after {max_wait} seconds'
                    }]
                }
            }

        try:
            result = compute.zoneOperations().get(
                project=project,
                zone=zone,
                operation=operation).execute()

            if result['status'] == 'DONE':
                log.info(f"Operation {operation} completed in {elapsed:.0f} seconds")
                return result

        except Exception as e:
            log.error(f"Error checking operation status: {e}")
            return {'status': 'ERROR', 'error': {'errors': [{'code': 'API_ERROR', 'message': str(e)}]}}

        # Exponential backoff with cap at 10 seconds
        time.sleep(min(poll_interval, 10))
        poll_interval = min(poll_interval * 1.5, 10)


def save_xml_to_file(xml_node, folder_name, file_name) -> None:
    """
    Save the given XML node to a file in a certain folder.

    :param xml_node: The XML content element to write to the file.
    :type xml_node: Element
    :param folder_name: The folder name.
    :type folder_name: str
    :param file_name: The name of the file
    :type file_name: str
    :return: Nothing
    :rtype: None
    """
    xml_node.getroottree().write(
        os.path.join(folder_name, file_name), encoding='utf-8', xml_declaration=True, pretty_print=True
    )


def add_test_entry(db, commit, test_type, branch="master", pr_nr=0) -> None:
    """
    Add test details entry into Test model for each platform.

    :param db: Database connection.
    :type db: sqlalchemy.orm.scoping.scoped_session
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

    # Validate commit hash before creating test entries
    # Based on issue identified by NexionisJake in PR #937
    if not is_valid_commit_hash(commit):
        log.error(f"Invalid commit hash '{commit}' - skipping test entry creation")
        return

    fork_url = f"%/{g.github['repository_owner']}/{g.github['repository']}.git"
    fork = Fork.query.filter(Fork.github.like(fork_url)).first()

    if test_type == TestType.pull_request:
        log.debug('pull request test type detected')
        branch = "pull_request"

    linux_test = Test(TestPlatform.linux, test_type, fork.id, branch, commit, pr_nr)
    db.add(linux_test)
    windows_test = Test(TestPlatform.windows, test_type, fork.id, branch, commit, pr_nr)
    db.add(windows_test)
    if not safe_db_commit(db, f"adding test entries for commit {commit[:7]}"):
        log.error(f"Failed to add test entries for commit {commit}")


def schedule_test(gh_commit: Commit.Commit) -> None:
    """
    Post status to GitHub as waiting for GitHub Actions completion.

    :param gh_commit: The GitHub API call for the commit. Can be None
    :type gh_commit: Any
    :return: Nothing
    :rtype: None
    """
    if gh_commit is not None:
        for platform in TestPlatform:
            status_description = "Waiting for actions to complete"
            update_status_on_github(gh_commit, Status.PENDING, status_description, f"CI - {platform.value}")


_GITHUB_NOT_SET: Any = getattr(GithubObject, 'NotSet')


def update_status_on_github(gh_commit: Commit.Commit, state, description, context,
                            target_url: Any = _GITHUB_NOT_SET):
    """
    Update status on GitHub.

    :param gh_commit: The GitHub API call for the commit. Can be None
    :type gh_commit: Any
    :param state: The test status.
    :type state: Status
    :param description: Description of test status.
    :type description: str
    :param context: Context for Github status.
    :type context: str
    :param target_url: Platform url for test status
    :type target_url: _NotSetType() | str
    """
    from run import log

    try:
        gh_commit.create_status(
            state=state,
            description=description,
            context=context,
            target_url=target_url
        )
    except GithubException as a:
        log.critical(f'Could not post to GitHub! Response: {a.data}')


def deschedule_test(gh_commit: Commit.Commit, commit=None, test_type=None, platform=None, branch="master",
                    message="Tests have been cancelled", state=Status.FAILURE, test=None, db=None) -> None:
    """
    Post status to GitHub (default: as failure due to GitHub Actions incompletion).

    :param gh_commit: The GitHub API call for the commit. Can be None
    :type gh_commit: Any
    :param commit: The commit hash.
    :type commit: str
    :param test_type: The type of test
    :type test_type: TestType
    :param platform: The platform name
    :type platform: TestPlatform
    :param branch: Branch name
    :type branch: str
    :param message: The message to be posted to GitHub
    :type message: str
    :param state: The status badge of the test
    :type state: Status
    :param test: The test which is to be canceled (optional)
    :type state: Test
    :param db: db session
    :type db: sqlalchemy.orm.scoping.scoped_session
    :return: Nothing
    :rtype: None
    """
    from run import log

    if test_type == TestType.pull_request:
        log.debug('pull request test type detected')
        branch = "pull_request"

    if test is None:
        fork_url = f"%/{g.github['repository_owner']}/{g.github['repository']}.git"
        fork = Fork.query.filter(Fork.github.like(fork_url)).first()
        test = Test.query.filter(and_(Test.platform == platform,
                                      Test.commit == commit,
                                      Test.fork_id == fork.id,
                                      Test.test_type == test_type,
                                      Test.branch == branch,
                                      )).first()

    if test is not None:
        progress = TestProgress(test.id, TestStatus.canceled, message, datetime.datetime.now())
        db = db or g.db
        db.add(progress)
        if not safe_db_commit(db, f"descheduling test {test.id}"):
            log.error(f"Failed to deschedule test {test.id}")
            return

        if gh_commit is not None:
            update_status_on_github(gh_commit, state, message, f"CI - {test.platform.value}")


def queue_test(gh_commit: Commit.Commit, commit, test_type, platform, branch="master", pr_nr=0) -> None:
    """
    Store test details into Test model for each platform, and post the status to GitHub.

    :param gh_commit: The GitHub API call for the commit. Can be None
    :type gh_commit: Any
    :param commit: The commit hash.
    :type commit: str
    :param test_type: The type of test
    :type test_type: TestType
    :param platform: The platform name
    :type platform: TestPlatform
    :param branch: Branch name
    :type branch: str
    :param pr_nr: Pull Request number, if applicable.
    :type pr_nr: int
    :return: Nothing
    :rtype: None
    """
    from run import log

    fork_url = f"%/{g.github['repository_owner']}/{g.github['repository']}.git"
    fork = Fork.query.filter(Fork.github.like(fork_url)).first()

    if test_type == TestType.pull_request:
        log.debug('pull request test type detected')
        branch = "pull_request"

    platform_test = Test.query.filter(and_(Test.platform == platform,
                                           Test.commit == commit,
                                           Test.fork_id == fork.id,
                                           Test.test_type == test_type,
                                           Test.branch == branch,
                                           Test.pr_nr == pr_nr
                                           )).first()
    add_customized_regression_tests(platform_test.id)

    if gh_commit is not None:
        target_url = url_for('test.by_id', test_id=platform_test.id, _external=True)
        status_context = f"CI - {platform_test.platform.value}"
        update_status_on_github(gh_commit, Status.PENDING, "Tests queued", status_context, target_url)

    log.debug("Created tests, waiting for cron...")


def inform_mailing_list(mailer, id, title, author, body) -> None:
    """
    Send mail to subscribed users when a issue is opened via the Webhook.

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

    subject = f"GitHub Issue #{id}"
    url = get_github_issue_link(id)
    if not mailer.send_simple_message({
        "to": "ccextractor-dev@googlegroups.com",
        "subject": subject,
        "html": get_html_issue_body(title=title, author=author, body=body, issue_number=id, url=url)
    }):
        g.log.error('failed to send issue to mailing list')


def get_html_issue_body(title, author, body, issue_number, url) -> Any:
    """
    Curate a HTML formatted body for the issue mail.

    :param title: title of the issue
    :type title: str
    :param author: author of the issue
    :type author: str
    :param body: content of the issue
    :type body: str
    :param issue_number: issue number
    :type issue_number: int
    :param url: link to the issue
    :type url: str
    :return: email body in html format
    :rtype: str
    """
    from run import app

    html_issue_body = markdown(body, extras=["target-blank-links", "task_list", "code-friendly"])
    template = app.jinja_env.get_or_select_template("email/new_issue.txt")
    html_email_body = template.render(title=title, author=author, body=html_issue_body, url=url)
    return html_email_body


@mod_ci.route('/start-ci', methods=['GET', 'POST'])
@request_from_github()
def start_ci():
    """
    Perform various actions when the GitHub webhook is triggered.

    Reaction to the next events need to be processed

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
            g.log.debug('server ping successful')
            return json.dumps({'msg': 'Hi!'})

        x_hub_signature = request.headers.get('X-Hub-Signature')

        if not is_valid_signature(x_hub_signature, request.data, g.github['ci_key']):
            g.log.warning(f'CI signature failed: {x_hub_signature}')
            abort(abort_code)

        payload = request.get_json()

        if payload is None:
            g.log.warning(f'CI payload is empty')
            abort(abort_code)

        if not g.github['bot_token']:
            g.log.error('GitHub token not configured, cannot process webhook')
            return json.dumps({'msg': 'GitHub token not configured'}), 500

        gh = Github(auth=Auth.Token(g.github['bot_token']))
        repository = gh.get_repo(f"{g.github['repository_owner']}/{g.github['repository']}")

        if event == "push":
            g.log.debug('push event detected')
            if 'after' in payload and payload["ref"] == "refs/heads/master":
                commit_hash = payload['after']
                # Update the db to the new last commit
                try:
                    ref = retry_with_backoff(lambda: repository.get_git_ref("heads/master"))
                except GithubException as e:
                    g.log.error(f"Failed to get git ref after retries: {e}")
                    return 'ERROR'
                last_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first()
                for platform in TestPlatform.values():
                    commit_name = 'fetch_commit_' + platform
                    fetch_commit = GeneralData.query.filter(GeneralData.key == commit_name).first()

                    if fetch_commit is None:
                        prev_commit = GeneralData(commit_name, last_commit.value)
                        g.db.add(prev_commit)

                last_commit.value = ref.object.sha
                if not safe_db_commit(g.db, "updating last commit"):
                    return 'ERROR'
                add_test_entry(g.db, commit_hash, TestType.commit)
            else:
                g.log.warning('Unknown push type! Dumping payload for analysis')
                g.log.warning(payload)

        elif event == "pull_request":
            g.log.debug('Pull Request event detected')
            # If it's a valid PR, run the tests
            pr_nr = payload['pull_request']['number']

            action = payload['action']
            is_active = action in ['opened', 'synchronize', 'reopened']
            is_inactive = action in ['closed']

            if is_active:
                try:
                    commit_hash = payload['pull_request']['head']['sha']
                except KeyError:
                    g.log.error("Didn't find a SHA value for a newly opened PR!")
                    g.log.error(payload)
                    return 'ERROR'

                # Check if user blacklisted
                user_id = payload['pull_request']['user']['id']
                if BlockedUsers.query.filter(BlockedUsers.user_id == user_id).first() is not None:
                    g.log.warning("User Blacklisted")
                    return 'ERROR'
                try:
                    pr = retry_with_backoff(lambda: repository.get_pull(number=pr_nr))
                    if pr.mergeable is not False:
                        add_test_entry(g.db, commit_hash, TestType.pull_request, pr_nr=pr_nr)
                except GithubException as e:
                    g.log.error(f"Failed to get PR {pr_nr} after retries: {e}")

            elif is_inactive:
                pr_action = 'closed' if action == 'closed' else 'converted to draft'
                g.log.debug(f'PR was {pr_action}, no after hash available')

                # Cancel running queue
                tests = Test.query.filter(Test.pr_nr == pr_nr).all()
                for test in tests:
                    # Add cancelled status only if the test hasn't started yet
                    if len(test.progress) > 0:
                        continue
                    progress = TestProgress(test.id, TestStatus.canceled, f"PR {pr_action}", datetime.datetime.now())
                    g.db.add(progress)
                    if not safe_db_commit(g.db, f"canceling test {test.id} for closed PR"):
                        continue
                    gh_commit = repository.get_commit(test.commit)
                    # If test run status exists, mark them as cancelled
                    for status in gh_commit.get_statuses():
                        if status["context"] == f"CI - {test.platform.value}":
                            target_url = url_for('test.by_id', test_id=test.id, _external=True)
                            update_status_on_github(gh_commit, Status.FAILURE, "Tests canceled",
                                                    status["context"], target_url=target_url)

        elif event == "issues":
            g.log.debug('issues event detected')

            issue_data = payload['issue']
            issue_action = payload['action']
            issue = Issue.query.filter(Issue.issue_id == issue_data['number']).first()
            issue_title = issue_data['title']
            issue_id = issue_data['number']
            issue_author = issue_data['user']['login']
            issue_body = issue_data['body']

            if issue_action == "opened":
                inform_mailing_list(g.mailer, issue_id, issue_title, issue_author, issue_body)

            if issue is not None:
                issue.title = issue_title
                issue.status = issue_data['state']
                safe_db_commit(g.db, f"updating issue {issue_id}")

        elif event == "release":
            g.log.debug("Release webhook triggered")

            release_data = payload['release']
            action = payload['action']
            release_version = release_data['tag_name']
            if release_version[0] == 'v':
                release_version = release_version[1:]
            if action == "prereleased":
                g.log.debug("Ignoring event meant for pre-release")
            elif action in ["deleted", "unpublished"]:
                g.log.debug("Received delete/unpublished action")
                CCExtractorVersion.query.filter_by(version=release_version).delete()
                if not safe_db_commit(g.db, f"deleting release {release_version}"):
                    g.log.error(f"Failed to delete release {release_version}")
                else:
                    g.log.info(f"Successfully deleted release {release_version} on {action} action")
            elif action in ["edited", "published"]:
                g.log.debug(f"Latest release version is {release_version}")
                release_date = release_data['published_at']

                # Get commit hash from the release tag via GitHub API
                # This is more reliable than using last_commit which may be stale
                # Based on issue identified by NexionisJake in PR #937
                release_commit = None
                tag_name = release_data['tag_name']
                try:
                    tag_ref = repository.get_git_ref(f"tags/{tag_name}")
                    if tag_ref.object.type == "tag":
                        # Annotated tag - need to get the underlying commit
                        tag_obj = repository.get_git_tag(tag_ref.object.sha)
                        release_commit = tag_obj.object.sha
                    else:
                        # Lightweight tag - points directly to commit
                        release_commit = tag_ref.object.sha
                    g.log.debug(f"Got commit {release_commit} from tag {tag_name}")
                except GithubException as e:
                    g.log.warning(f"Failed to get commit from tag {tag_name}: {e}")

                # Fallback to last_commit if tag lookup failed
                if not is_valid_commit_hash(release_commit):
                    last_commit_data = GeneralData.query.filter(
                        GeneralData.key == 'last_commit').first()
                    if last_commit_data and is_valid_commit_hash(last_commit_data.value):
                        release_commit = last_commit_data.value
                        g.log.warning(f"Using fallback last_commit: {release_commit}")

                # Validate we have a valid commit hash
                if not is_valid_commit_hash(release_commit):
                    g.log.error(f"Cannot determine valid commit for release {release_version}")
                    return json.dumps({'msg': 'Invalid commit hash for release'})

                if action == "edited":
                    release = CCExtractorVersion.query.filter(
                        CCExtractorVersion.version == release_version).one()
                    release.released = datetime.datetime.strptime(
                        release_date, '%Y-%m-%dT%H:%M:%SZ').date()
                    release.commit = release_commit
                else:
                    release = CCExtractorVersion(release_version, release_date, release_commit)
                    g.db.add(release)
                if not safe_db_commit(g.db, f"updating release {release_version}"):
                    g.log.error(f"Failed to update release {release_version}")
                    return json.dumps({'msg': 'ERROR'})
                g.log.info(f"Release {release_version} updated with commit {release_commit}")

                # Update baseline regression results for this release
                # Only proceed if we have a test for this commit
                test = Test.query.filter(and_(Test.commit == release_commit,
                                         Test.platform == TestPlatform.linux)).first()
                if test is not None:
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
                    if safe_db_commit(g.db, "updating baseline regression results"):
                        g.log.info("Successfully updated baseline tests for release!")
                    else:
                        g.log.error("Failed to update baseline regression results")
                else:
                    g.log.warning(f"No test found for commit {release_commit} - "
                                  "baseline update skipped")
            else:
                g.log.warning(f"Unsupported release action: {action}")

        elif event == "workflow_run":
            workflow_name = payload['workflow_run']['name']
            if workflow_name in [Workflow_builds.LINUX, Workflow_builds.WINDOWS]:
                g.log.debug('workflow_run event detected')
                commit_hash = payload['workflow_run']['head_sha']
                github_status = repository.get_commit(commit_hash)

                if payload['action'] == "completed":
                    is_complete = True
                    has_failed = False
                    builds = {"linux": False, "windows": False}

                    # NOTE: Using this workaround because workflow name cannot be accessed using PyGitHub
                    # https://github.com/PyGithub/PyGithub/issues/2276
                    workflow = defaultdict(lambda: None)
                    for active_workflow in repository.get_workflows():
                        workflow[active_workflow.id] = active_workflow.name

                    for workflow_run in repository.get_workflow_runs(
                            event=payload['workflow_run']['event'],
                            actor=payload['sender']['login'],
                            branch=payload['workflow_run']['head_branch']
                    ):
                        workflow_run_name = workflow[workflow_run.workflow_id]
                        if workflow_run_name not in [Workflow_builds.LINUX, Workflow_builds.WINDOWS]:
                            continue
                        if workflow_run.head_sha == commit_hash:
                            if workflow_run.status == "completed":
                                if workflow_run.conclusion != "success":
                                    has_failed = True
                                    break
                                if workflow_run_name == Workflow_builds.LINUX:
                                    builds["linux"] = True
                                elif workflow_run_name == Workflow_builds.WINDOWS:
                                    builds["windows"] = True
                            else:
                                is_complete = False
                                break

                    if has_failed:
                        # no runs to be scheduled since build failed
                        if payload['workflow_run']['event'] == "pull_request":
                            test_type = TestType.pull_request
                        else:
                            test_type = TestType.commit
                        deschedule_test(github_status, commit_hash, test_type, TestPlatform.linux,
                                        message="Cancelling tests as Github Action(s) failed")
                        deschedule_test(github_status, commit_hash, test_type, TestPlatform.windows,
                                        message="Cancelling tests as Github Action(s) failed")
                    elif is_complete:
                        # CRITICAL: Verify artifacts exist before queuing tests
                        # This prevents the race condition where tests are queued before
                        # artifacts are available, causing "No build artifact found" errors
                        # See: https://github.com/CCExtractor/sample-platform/issues/XXX
                        artifacts_available = verify_artifacts_exist(repository, commit_hash, g.log)
                        g.log.info(f"Artifact verification for {commit_hash[:8]}: "
                                   f"Linux={artifacts_available['linux']}, Windows={artifacts_available['windows']}")

                        # Override builds dict if artifacts are not available
                        # This ensures we don't queue tests for which artifacts don't exist
                        # Determine test type for artifact verification failures
                        artifact_fail_test_type = (TestType.pull_request
                                                   if payload['workflow_run']['event'] == "pull_request"
                                                   else TestType.commit)

                        if builds['linux'] and not artifacts_available['linux']:
                            g.log.error(f"Linux workflow succeeded but artifact not found for {commit_hash[:8]}! "
                                        "This may indicate a GitHub API caching issue.")
                            deschedule_test(github_status, commit_hash, artifact_fail_test_type,
                                            TestPlatform.linux,
                                            message="Build succeeded but artifact not yet available - please retry",
                                            state=Status.ERROR)
                            builds['linux'] = False

                        if builds['windows'] and not artifacts_available['windows']:
                            g.log.error(f"Windows workflow succeeded but artifact not found for {commit_hash[:8]}! "
                                        "This may indicate a GitHub API caching issue.")
                            deschedule_test(github_status, commit_hash, artifact_fail_test_type,
                                            TestPlatform.windows,
                                            message="Build succeeded but artifact not yet available - please retry",
                                            state=Status.ERROR)
                            builds['windows'] = False

                        if payload['workflow_run']['event'] == "pull_request":
                            # In case of pull request run tests only if it is still in an open state
                            # and user is not blacklisted
                            for pull_request in repository.get_pulls(state='open'):
                                if pull_request.head.sha == commit_hash:
                                    user_id = pull_request.user.id
                                    if BlockedUsers.query.filter(BlockedUsers.user_id == user_id).first() is not None:
                                        g.log.warning("User Blacklisted")
                                        github_status.post(
                                            state=Status.ERROR,
                                            description="CI start aborted. \
                                            You may be blocked from accessing this functionality",
                                            target_url=url_for('home.index', _external=True)
                                        )
                                        return 'ERROR'
                                    if builds['linux']:
                                        queue_test(github_status, commit_hash, TestType.pull_request,
                                                   TestPlatform.linux, pr_nr=pull_request.number)
                                    else:
                                        deschedule_test(github_status, commit_hash, TestType.pull_request,
                                                        TestPlatform.linux, message="Not ran - no code changes",
                                                        state=Status.SUCCESS)
                                    if builds['windows']:
                                        queue_test(github_status, commit_hash, TestType.pull_request,
                                                   TestPlatform.windows, pr_nr=pull_request.number)
                                    else:
                                        deschedule_test(github_status, commit_hash, TestType.pull_request,
                                                        TestPlatform.windows, message="Not ran - no code changes",
                                                        state=Status.SUCCESS)
                                    return json.dumps({'msg': 'EOL'})
                            # Either PR head commit was updated or PR was closed, therefore cancelling tests
                            deschedule_test(github_status, commit_hash, TestType.pull_request, TestPlatform.linux,
                                            message="Tests canceled", state=Status.FAILURE)
                            deschedule_test(github_status, commit_hash, TestType.pull_request, TestPlatform.windows,
                                            message="Tests canceled", state=Status.FAILURE)
                        else:
                            if builds['linux']:
                                queue_test(github_status, commit_hash,
                                           TestType.commit, TestPlatform.linux)
                            else:
                                deschedule_test(github_status, commit_hash, TestType.commit, TestPlatform.linux,
                                                message="Not ran - no code changes", state=Status.SUCCESS)
                            if builds['windows']:
                                queue_test(github_status, commit_hash,
                                           TestType.commit, TestPlatform.windows)
                            else:
                                deschedule_test(github_status, commit_hash, TestType.commit, TestPlatform.windows,
                                                message="Not ran - no code changes", state=Status.SUCCESS)
                elif payload['action'] == 'requested':
                    schedule_test(github_status)
            else:
                g.log.warning('Unknown action type in workflow_run! Dumping payload for analysis')
                g.log.warning(payload)

        else:
            g.log.warning(f'CI unrecognized event: {event}')

        return json.dumps({'msg': 'EOL'})


def update_build_badge(status, test) -> None:
    """
    Build status badge for current test to be displayed on sample-platform.

    :param status: current testing status
    :type status: str
    :param test: current commit that is tested
    :type test: Test
    :return: null
    :rtype: null
    """
    if test.test_type == TestType.commit and is_main_repo(test.fork.github):
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        original_location = os.path.join(parent_dir, 'static', 'svg', f'{status.upper()}-{test.platform.value}.svg')
        build_status_location = os.path.join(parent_dir, 'static', 'img', 'status', f'build-{test.platform.value}.svg')
        shutil.copyfile(original_location, build_status_location)
        g.log.info('Build badge updated successfully!')

        test_results = get_test_results(test)
        test_ids_to_update = []
        for category_results in test_results:
            test_ids_to_update.extend([test['test'].id for test in category_results['tests'] if not test['error']])

        g.db.query(RegressionTest).filter(RegressionTest.id.in_(test_ids_to_update)).update(
            {f"last_passed_on_{test.platform.value}": test.id}, synchronize_session=False
        )
        if not safe_db_commit(g.db, "updating last passed regression tests"):
            g.log.error("Failed to update last passed regression tests")


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

    test = Test.query.filter(Test.id == test_id).first()
    if test is not None and test.token == token:
        repo_folder = config.get('SAMPLE_REPOSITORY', '')

        if 'type' in request.form:
            if request.form['type'] == 'progress':
                log.info(f'[PROGRESS_REPORTER][Test: {test_id}] Progress reported')
                if not progress_type_request(log, test, test_id, request):
                    return "FAIL"

            elif request.form['type'] == 'equality':
                log.info(f'[PROGRESS_REPORTER][Test: {test_id}] Equality reported')
                equality_type_request(log, test_id, test, request)

            elif request.form['type'] == 'logupload':
                log.info(f'[PROGRESS_REPORTER][Test: {test_id}] Log upload')
                if not upload_log_type_request(log, test_id, repo_folder, test, request):
                    return "EMPTY"

            elif request.form['type'] == 'upload':
                log.info(f'[PROGRESS_REPORTER][Test: {test_id}] File upload')
                if not upload_type_request(log, test_id, repo_folder, test, request):
                    return "EMPTY"

            elif request.form['type'] == 'finish':
                log.info(f'[PROGRESS_REPORTER][Test: {test_id}] Test finished')
                finish_type_request(log, test_id, test, request)
            else:
                return "FAIL"

            return "OK"

    return "FAIL"


def progress_type_request(log, test, test_id, request) -> bool:
    """
    Handle progress updates for progress reporter.

    :param log: logger
    :type log: Logger
    :param test: concerned test
    :type test: Test
    :param test_id: The id of the test to update.
    :type test_id: int
    :param request: Request parameters
    :type request: Request
    """
    status = TestStatus.from_string(request.form['status'])
    current_status = TestStatus.progress_step(status)
    message = request.form['message']

    if len(test.progress) != 0:
        last_status = TestStatus.progress_step(test.progress[-1].status)

        if last_status in [TestStatus.completed, TestStatus.canceled]:
            return False

        if last_status > current_status:
            status = TestStatus.canceled  # type: ignore
            message = "Duplicate Entries"

        if last_status < current_status:
            # get GCP VM instance start time for finding GCP VM instance preparation time
            gcp_instance_entry = GcpInstance.query.filter(GcpInstance.test_id == test_id).first()

            if status == TestStatus.testing:
                log.info(f'[Test: {test_id}] Preparation finished')
                prep_finish_time = datetime.datetime.now()
                # save preparation finish time
                gcp_instance_entry.timestamp_prep_finished = prep_finish_time
                safe_db_commit(g.db, f"saving prep finish time for test {test_id}")
                # set time taken in seconds to do preparation
                time_diff = (prep_finish_time - gcp_instance_entry.timestamp).total_seconds()
                set_avg_time(test.platform, "prep", time_diff)

    progress = TestProgress(test.id, status, message)
    g.db.add(progress)
    if not safe_db_commit(g.db, f"adding progress for test {test_id}"):
        return False

    if not g.github['bot_token']:
        log.error('GitHub token not configured, cannot update status on GitHub')
        return True

    gh = Github(auth=Auth.Token(g.github['bot_token']))
    repository = gh.get_repo(f"{g.github['repository_owner']}/{g.github['repository']}")
    # Store the test commit for testing in case of commit
    if status == TestStatus.completed and is_main_repo(test.fork.github):
        commit_name = 'fetch_commit_' + test.platform.value
        commit = GeneralData.query.filter(GeneralData.key == commit_name).first()
        fetch_commit = Test.query.filter(
            and_(Test.commit == commit.value, Test.platform == test.platform)
        ).first()

        if test.test_type == TestType.commit and test.id > fetch_commit.id:
            commit.value = test.commit
            safe_db_commit(g.db, f"updating fetch commit for {test.platform.value}")

    # Post status update
    state = Status.PENDING
    target_url = url_for('test.by_id', test_id=test.id, _external=True)
    context = f"CI - {test.platform.value}"

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
        log.debug(f'[Test: {test.id}] Test completed: {crashes} crashes, {results} results')
        if crashes > 0 or results > 0:
            state = Status.FAILURE
            message = 'Not all tests completed successfully, please check'

        else:
            state = Status.SUCCESS
            message = 'Tests completed'
        if test.test_type == TestType.pull_request:
            state = comment_pr(test)
            # Update message to match the state returned by comment_pr()
            # comment_pr() uses different logic: it returns SUCCESS if there are
            # no NEW failures compared to master (pre-existing failures are OK)
            if state == Status.SUCCESS:
                message = 'All tests passed'
            else:
                message = 'Not all tests completed successfully, please check'
        update_build_badge(state, test)

    else:
        message = progress.message

    # Use retry logic for final GitHub status update to prevent stuck "pending" states
    # This is critical - if this fails, the PR will show "Tests queued" forever
    try:
        def update_final_status():
            gh_commit = repository.get_commit(test.commit)
            update_status_on_github(gh_commit, state, message, context, target_url=target_url)

        retry_with_backoff(update_final_status, max_retries=3, initial_backoff=2.0)
    except Exception as e:
        log.error(f"Test {test_id}: Failed to update final GitHub status after retries: {e}")

    if status in [TestStatus.completed, TestStatus.canceled]:
        # Delete the current instance
        from run import config
        compute = get_compute_service_object()
        zone = config.get('ZONE', '')
        project = config.get('PROJECT_NAME', '')
        vm_name = f"{test.platform.value}-{test.id}"
        operation = delete_instance(compute, project, zone, vm_name)
        wait_for_operation(compute, project, zone, operation['name'])

    # If status is complete, remove the GCP Instance entry
    if status in [TestStatus.completed, TestStatus.canceled]:
        gcp_instance = GcpInstance.query.filter(GcpInstance.test_id == test_id).first()

        if gcp_instance is not None:
            log.debug(f"Removing GCP Instance entry: {gcp_instance}")
            g.db.delete(gcp_instance)
            safe_db_commit(g.db, f"removing GCP instance for test {test_id}")

        log.debug(f"[Test: {test_id}] Test {status}")
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
                try:
                    # Try parsing with microsecond precision first
                    start = datetime.datetime.strptime(parts[0], '%Y-%m-%d %H:%M:%S.%f')
                    end = datetime.datetime.strptime(parts[-1], '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    # Fall back to format without microseconds
                    start = datetime.datetime.strptime(parts[0], '%Y-%m-%d %H:%M:%S')
                    end = datetime.datetime.strptime(parts[-1], '%Y-%m-%d %H:%M:%S')
                total_time += int((end - start).total_seconds())

            if len(times) != 0:
                average_time = total_time // len(times)

            new_avg = GeneralData(var_average, average_time)
            log.info(f'new average time {str(average_time)} set successfully')
            g.db.add(new_avg)
            safe_db_commit(g.db, "setting new average time")

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
            current_average.value = 0 if number_test == 0 else updated_average // number_test
            safe_db_commit(g.db, "updating average time")
            log.info(f'average time updated to {str(current_average.value)}')

    return True


def equality_type_request(log, test_id, test, request):
    """
    Handle equality request type for progress reporter.

    :param log: logger
    :type log: Logger
    :param test_id: The id of the test to update.
    :type test_id: int
    :param test: concerned test
    :type test: Test
    :param request: Request parameters
    :type request: Request
    """
    log.debug(f'Equality for {test_id}/{request.form["test_id"]}/{request.form["test_file_id"]}')
    rto = RegressionTestOutput.query.filter(RegressionTestOutput.id == request.form['test_file_id']).first()

    if rto is None:
        # Equality posted on a file that's ignored presumably
        log.info(f'No rto for {test_id}: {request.form["test_id"]}')
    else:
        result_file = TestResultFile(test.id, request.form['test_id'], rto.id, rto.correct)
        g.db.add(result_file)
        safe_db_commit(g.db, f"saving result file for test {test_id}")


def upload_log_type_request(log, test_id, repo_folder, test, request) -> bool:
    """
    Handle logupload request type for progress reporter.

    :param log: logger
    :type log: Logger
    :param test_id: The id of the test to update.
    :type test_id: int
    :param repo_folder: repository folder
    :type repo_folder: str
    :param test: concerned test
    :type test: Test
    :param request: Request parameters
    :type request: Request
    """
    log.debug(f"Received log file for test {test_id}")
    # File upload, process
    if 'file' in request.files:
        uploaded_file = request.files['file']
        filename = secure_filename(uploaded_file.filename)
        if filename == '':
            return False

        temp_path = os.path.join(repo_folder, 'TempFiles', filename)
        # Save to temporary location
        uploaded_file.save(temp_path)
        final_path = os.path.join(repo_folder, 'LogFiles', f"{test.id}.txt")

        os.rename(temp_path, final_path)
        log.debug("Stored log file")
        return True

    return False


def upload_type_request(log, test_id, repo_folder, test, request) -> bool:
    """
    Handle upload request type for progress reporter.

    :param log: logger
    :type log: Logger
    :param test_id: The id of the test to update.
    :type test_id: int
    :param repo_folder: repository folder
    :type repo_folder: str
    :param test: concerned test
    :type test: Test
    :param request: Request parameters
    :type request: Request
    """
    log.debug(f'Upload for {test_id}/{request.form["test_id"]}/{request.form["test_file_id"]}'
              )
    # File upload, process
    if 'file' in request.files:
        uploaded_file = request.files['file']
        filename = secure_filename(uploaded_file.filename)
        if filename == '':
            log.warning('empty filename provided for uploading')
            return False
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
            repo_folder, 'TestResults', f'{file_hash}{file_extension}'
        )
        os.rename(temp_path, final_path)
        rto = RegressionTestOutput.query.filter(
            RegressionTestOutput.id == request.form['test_file_id']).first()
        result_file = TestResultFile(test.id, request.form['test_id'], rto.id, rto.correct, file_hash)
        g.db.add(result_file)
        if not safe_db_commit(g.db, f"saving test result file for test {test_id}"):
            return False
        return True

    return False


def finish_type_request(log, test_id, test, request):
    """
    Handle finish request type for progress reporter.

    :param log: logger
    :type log: Logger
    :param test_id: The id of the test to update.
    :type test_id: int
    :param test: concerned test
    :type test: Test
    :param request: Request parameters
    :type request: Request
    """
    log.debug(f"Finish for {test_id}/{request.form['test_id']}")
    regression_test = RegressionTest.query.filter(RegressionTest.id == request.form['test_id']).first()
    result = TestResult(
        test.id, regression_test.id, request.form['runTime'],
        request.form['exitCode'], regression_test.expected_rc
    )
    g.db.add(result)
    if not safe_db_commit(g.db, f"saving test result for test {test_id}"):
        log.error(f"Could not save the results for test {test_id}")


def set_avg_time(platform, process_type: str, time_taken: int) -> None:
    """
    Set average platform preparation time.

    :param platform: platform to which the average time belongs
    :type platform: TestPlatform
    :param process_type: process to save the average time for
    :type process_type: str
    :param time_taken: time taken to complete the process
    :type time_taken: int
    """
    val_key = "avg_" + str(process_type) + "_time_" + platform.value
    count_key = "avg_" + str(process_type) + "_count_" + platform.value

    current_avg_count = GeneralData.query.filter(GeneralData.key == count_key).first()

    # adding average data the first time
    if current_avg_count is None:
        avg_count_GD = GeneralData(count_key, str(1))
        avg_time_GD = GeneralData(val_key, str(time_taken))
        g.db.add(avg_count_GD)
        g.db.add(avg_time_GD)

    else:
        current_average = GeneralData.query.filter(GeneralData.key == val_key).first()
        avg_count = int(current_avg_count.value)
        avg_value = int(float(current_average.value))
        new_average = ((avg_value * avg_count) + time_taken) / (avg_count + 1)
        current_avg_count.value = str(avg_count + 1)
        current_average.value = str(new_average)

    safe_db_commit(g.db, f"updating average {process_type} time for {platform.value}")


def get_info_for_pr_comment(test: Test) -> PrCommentInfo:
    """
    Return info about the given test for use in a PR comment.

    :param test: The test whose report will be returned
    :type test: Test
    """
    last_test_master = g.db.query(Test).filter(Test.branch == "master", Test.test_type == TestType.commit,
                                               Test.platform == test.platform).join(
        TestProgress, Test.id == TestProgress.test_id).filter(
            TestProgress.status == TestStatus.completed).order_by(TestProgress.id.desc()).first()

    extra_failed_tests = []
    common_failed_tests = []
    fixed_tests = []
    category_stats = []

    test_results = get_test_results(test)
    platform_column = f"last_passed_on_{test.platform.value}"
    for category_results in test_results:
        category_name = category_results['category'].name

        category_test_pass_count = 0
        for test in category_results['tests']:
            if not test['error']:
                category_test_pass_count += 1
                if last_test_master and getattr(test['test'], platform_column) != last_test_master.id:
                    fixed_tests.append(test['test'])
            else:
                if last_test_master and getattr(test['test'], platform_column) != last_test_master.id:
                    common_failed_tests.append(test['test'])
                else:
                    extra_failed_tests.append(test['test'])

        category_stats.append(CategoryTestInfo(category_name, len(category_results['tests']), category_test_pass_count))

    return PrCommentInfo(category_stats, extra_failed_tests, fixed_tests, common_failed_tests, last_test_master)


def comment_pr(test: Test) -> str:
    """
    Upload the test report to the GitHub PR as comment.

    :param test: The test whose report will be uploaded
    :type test: Test
    """
    from run import app, log

    test_id = test.id
    platform = test.platform.name
    comment_info = get_info_for_pr_comment(test)
    template = app.jinja_env.get_or_select_template('ci/pr_comment.txt')
    message = template.render(comment_info=comment_info, test_id=test_id, platform=platform)
    log.debug(f"GitHub PR Comment Message Created for Test_id: {test_id}")
    if not g.github['bot_token']:
        log.error(f"GitHub token not configured, cannot post PR comment for Test_id: {test_id}")
        return Status.FAILURE
    try:
        gh = Github(auth=Auth.Token(g.github['bot_token']))
        repository = gh.get_repo(f"{g.github['repository_owner']}/{g.github['repository']}")
        # Pull requests are just issues with code, so GitHub considers PR comments in issues
        pull_request = repository.get_pull(number=test.pr_nr)
        comments = pull_request.get_issue_comments()
        bot_name = gh.get_user().login
        for comment in comments:
            if comment.user.login == bot_name and platform in comment.body:
                comment.delete()
                log.debug(f"GitHub PR old comment deleted for test_id: {test_id}")
        comment = pull_request.create_issue_comment(body=message)
        log.debug(f"GitHub PR Comment ID {comment.id} Uploaded for Test_id: {test_id}")
    except Exception as e:
        log.error(f"GitHub PR Comment Failed for Test_id: {test_id} with Exception {e}")
    return Status.SUCCESS if len(comment_info.extra_failed_tests) == 0 else Status.FAILURE


@mod_ci.route('/show_maintenance')
@login_required
@check_access_rights([Role.admin])
@template_renderer('ci/maintenance.html')
def show_maintenance():
    """
    Get list of Virtual Machines under maintenance.

    :return: platforms in maintenance
    :rtype: dict
    """
    return {
        'platforms': MaintenanceMode.query.all()
    }


@mod_ci.route('/blocked_users', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def blocked_users():
    """
    Render the blocked_users template.

    This returns a list of all currently blacklisted users.
    Also defines processing of forms to add/remove users from blacklist.
    When a user is added to blacklist, removes queued tests on any PR by the user.
    """
    blocked_users = BlockedUsers.query.order_by(BlockedUsers.user_id)

    # Initialize usernames dictionary
    usernames = {u.user_id: "Error, cannot get username" for u in blocked_users}
    for key in usernames.keys():
        # Fetch usernames from GitHub API
        try:
            api_url = requests.get(f"https://api.github.com/user/{key}", timeout=10)
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
        if not safe_db_commit(g.db, "adding blocked user"):
            flash('Failed to block user.')
            return redirect(url_for('.blocked_users'))
        flash('User blocked successfully.')

        if not g.github['bot_token']:
            g.log.error('GitHub token not configured, cannot check blocked user PRs')
            return redirect(url_for('.blocked_users'))

        try:
            # Remove any queued pull request from blocked user
            gh = Github(auth=Auth.Token(g.github['bot_token']))
            repository = gh.get_repo(f"{g.github['repository_owner']}/{g.github['repository']}")
            # Getting all pull requests by blocked user on the repo
            pulls = repository.get_pulls(state='open')
            for pull in pulls:
                if pull.user.id != add_user_form.user_id.data:
                    continue
                tests = Test.query.filter(Test.pr_nr == pull.number).all()
                for test in tests:
                    # Add canceled status only if the test hasn't started yet
                    if len(test.progress) > 0:
                        continue
                    progress = TestProgress(test.id, TestStatus.canceled, "PR closed", datetime.datetime.now())
                    g.db.add(progress)
                    if not safe_db_commit(g.db, f"canceling test {test.id} for blocked user"):
                        continue
                    gh_commit = repository.get_commit(test.commit)
                    message = "Tests canceled since user blacklisted"
                    target_url = url_for('test.by_id', test_id=test.id, _external=True)
                    update_status_on_github(gh_commit, Status.FAILURE, message,
                                            f"CI - {test.platform.value}", target_url=target_url)
        except GithubException as a:
            g.log.error(f"Pull Requests of Blocked User could not be fetched: {a.data}")

        return redirect(url_for('.blocked_users'))

    return {
        'addUserForm': add_user_form,
        'blocked_users': blocked_users,
        'usernames': usernames
    }


@mod_ci.route('/blocked_users/<int:blocked_user_id>', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def blocked_users_remove(blocked_user_id):
    """
    Render the blocked_users_remove template.

    Removes user from the list of blacklisted users.
    """
    blocked_user = BlockedUsers.query.filter_by(user_id=blocked_user_id).first()
    if blocked_user is None:
        flash("No such user in Blacklist")
        return redirect(url_for('.blocked_users'))

    form = DeleteUserForm(request.form)
    if form.validate_on_submit():
        g.db.delete(blocked_user)
        if not safe_db_commit(g.db, "removing blocked user"):
            flash("Failed to remove user.")
            return redirect(url_for('.blocked_users'))
        flash("User removed successfully.")
        return redirect(url_for('.blocked_users'))

    return {
        'blocked_user_id': blocked_user_id,
        'form': form
    }


@mod_ci.route('/toggle_maintenance/<platform>/<status>')
@login_required
@check_access_rights([Role.admin])
def toggle_maintenance(platform, status):
    """
    Toggle maintenance mode for a platform.

    :param platform: name of the platform
    :type platform: str
    :param status: current maintenance status
    :type status: str
    :return: success response if successful, failure response otherwise
    :rtype: JSON
    """
    result = 'failed'
    message = 'Platform Not found'
    disabled = status == 'True'
    try:
        platform = TestPlatform.from_string(platform)
        db_mode = MaintenanceMode.query.filter(MaintenanceMode.platform == platform).first()
        if db_mode is not None:
            db_mode.disabled = disabled
            if safe_db_commit(g.db, f"updating maintenance mode for {platform}"):
                result = 'success'
                message = f'{platform.description} in maintenance? {"Yes" if disabled else "No"}'
            else:
                message = 'Failed to update maintenance mode'
    except ValueError:
        pass

    return jsonify({
        'status': result,
        'message': message
    })


@mod_ci.route('/maintenance-mode/<platform>')
def in_maintenance_mode(platform):
    """
    Check if platform in maintenance mode.

    :param platform: name of the platform
    :type platform: str
    :return: status of the platform
    :rtype: str
    """
    try:
        platform = TestPlatform.from_string(platform)
    except ValueError:
        return 'ERROR'

    status = MaintenanceMode.query.filter(MaintenanceMode.platform == platform).first()

    if status is None:
        status = MaintenanceMode(platform, False)
        g.db.add(status)
        safe_db_commit(g.db, f"creating maintenance mode entry for {platform}")

    return str(status.disabled)


def is_main_repo(repo_url) -> bool:
    """
    Check whether a repo_url links to the main repository or not.

    :param repo_url: url of fork/main repository of the user
    :type repo_url: str
    :return: checks whether url of main repo is same or not
    :rtype: bool
    """
    from run import config, get_github_config

    gh_config = get_github_config(config)
    return f'{gh_config["repository_owner"]}/{gh_config["repository"]}' in repo_url


def add_customized_regression_tests(test_id) -> None:
    """
    Run custom regression tests.

    :param test_id: id of the test
    :type test_id: int
    """
    active_regression_tests = RegressionTest.query.filter(RegressionTest.active == 1).all()
    for regression_test in active_regression_tests:
        g.log.debug(f'Adding RT #{regression_test.id} to test {test_id}')
        customized_test = CustomizedTest(test_id, regression_test.id)
        g.db.add(customized_test)
    safe_db_commit(g.db, f"adding customized regression tests for test {test_id}")
