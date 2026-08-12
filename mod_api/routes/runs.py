"""
Test run routes.

GET    /runs                   List runs (filtered, paginated, sorted)
POST   /runs                   Trigger a new run
GET    /runs/{id}              Single run details
GET    /runs/{id}/summary      Pass/fail/skip counts
GET    /runs/{id}/progress     Progress event timeline
GET    /runs/{id}/config       Run configuration and test matrix
POST   /runs/{id}/cancel       Cancel a queued or running test
POST   /runs/{id}/restart      Clear a run's results so CI picks it up again
"""

from collections import defaultdict

from flask import g, request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body, validate_date_range,
                                           validate_offset_pagination,
                                           validate_path_id, validate_sort)
from mod_api.models.api_token import Scope
from mod_api.schemas.runs import (ProgressEventSchema, RunCreateRequestSchema,
                                  RunSchema, RunSummarySchema)
from mod_api.services.error_service import derive_errors_for_run
from mod_api.services.status import (batch_get_run_data, derive_run_status,
                                     derive_sample_status)
from mod_api.utils import get_sort_column, paginated_response, single_response
from mod_auth.models import Role
from mod_customized.models import CustomizedTest
from mod_home.models import CCExtractorVersion
from mod_regression.models import RegressionTest, RegressionTestOutput
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)


def _serialize_run(test):
    """Turn a Test row into the Run response shape the spec expects."""
    return _batch_serialize([test])[0]


def _batch_serialize(tests, statuses=None, timestamps=None):
    if statuses is None or timestamps is None:
        statuses, timestamps = batch_get_run_data(tests)
    return [
        {
            'run_id': t.id,
            'status': statuses.get(t.id, 'queued'),
            'platform': t.platform.value,
            'test_type': 'pr' if t.test_type == TestType.pull_request else 'commit',
            'repository': t.fork.github_name if t.fork else 'unknown',
            'branch': t.branch,
            'commit_sha': t.commit,
            'pr_number': t.pr_nr if t.pr_nr and t.pr_nr > 0 else None,
            'created_at': timestamps.get(t.id, {}).get('created_at'),
            'queued_at': timestamps.get(t.id, {}).get('queued_at'),
            'started_at': timestamps.get(t.id, {}).get('started_at'),
            'completed_at': timestamps.get(t.id, {}).get('completed_at'),
            'github_link': t.github_link if t.fork else None,
        }
        for t in tests
    ]


def _apply_repository_filter(query, repository):
    repo_field = RunCreateRequestSchema().fields.get('repository')
    if repo_field:
        try:
            repo_field.deserialize(repository)
        except Exception as e:
            return None, make_error_response(
                'validation_error',
                'Invalid repository format.',
                details={'fields': {'repository': str(e)}},
                http_status=400,
            )
    fork_url = f'https://github.com/{repository}.git'
    return query.join(Fork).filter(Fork.github == fork_url), None


def _apply_date_filters(query, created_after, created_before):
    first_progress = (
        g.db.query(
            TestProgress.test_id, func.min(
                TestProgress.timestamp).label('min_ts')) .group_by(
            TestProgress.test_id) .subquery())
    # LEFT JOIN so queued runs (no TestProgress rows yet, hence no known
    # creation time) aren't silently dropped — otherwise combining a date
    # filter with ?status=queued always returns an empty page. Runs without
    # timestamps are treated as matching any requested window.
    query = query.outerjoin(
        first_progress, Test.id == first_progress.c.test_id)
    if created_after:
        query = query.filter(or_(first_progress.c.min_ts >= created_after,
                                 first_progress.c.min_ts.is_(None)))
    if created_before:
        query = query.filter(or_(first_progress.c.min_ts <= created_before,
                                 first_progress.c.min_ts.is_(None)))
    return query


def _apply_run_filters(query, created_after, created_before):
    platform = request.args.get('platform')
    if platform:
        try:
            platform_enum = TestPlatform.from_string(platform)
            query = query.filter(Test.platform == platform_enum)
        except Exception:
            valid_platforms = ', '.join(TestPlatform.values())
            return None, make_error_response(
                'validation_error',
                f'Invalid platform: {platform}. Must be one of: {valid_platforms}.',
                http_status=400,
            )

    branch = request.args.get('branch')
    if branch:
        query = query.filter(Test.branch == branch)

    commit_sha = request.args.get('commit_sha')
    if commit_sha:
        query = query.filter(Test.commit == commit_sha)

    # A release is recorded as the commit it was cut from, so filtering by
    # version is the commit filter with one lookup in front of it.
    ccx_version = request.args.get('ccx_version')
    if ccx_version:
        version = CCExtractorVersion.query.filter(
            CCExtractorVersion.version == ccx_version).first()
        if version is None:
            return None, make_error_response(
                'validation_error',
                f'Unknown CCExtractor version: {ccx_version}.',
                http_status=400,
            )
        query = query.filter(Test.commit == version.commit)

    repository = request.args.get('repository')
    if repository:
        query, err = _apply_repository_filter(query, repository)
        if err:
            return None, err

    if created_after or created_before:
        query = _apply_date_filters(query, created_after, created_before)

    return query, None


def _validate_run_permissions(user, target_repo, main_repo_full):
    # GitHub owner/repo names are case-insensitive.
    if target_repo.lower() == main_repo_full.lower():
        allowed = (Role.admin, Role.tester, Role.contributor)
        if user.role not in allowed:
            return make_error_response(
                'forbidden',
                'Only admins, testers, and contributors can trigger runs for the main repository.',
                details={
                    'required_roles': [role.value for role in allowed],
                    'repository': target_repo,
                },
                http_status=403,
            )
    else:
        owner = target_repo.split('/')[0]
        github_login = getattr(user, 'github_login', None)

        if not github_login and getattr(user, 'github_token', None):
            from mod_auth.controllers import fetch_username_from_token
            github_login = fetch_username_from_token(user)
            if github_login:
                user.github_login = github_login
                g.db.add(user)

        github_login = github_login or ''

        if not github_login or owner.lower() != github_login.lower():
            return make_error_response(
                'forbidden',
                f'You can only trigger runs for your own repository (expected owner: {github_login}) '
                'or the main repository.',
                details={
                    'repository': target_repo,
                    'owner_required': github_login,
                },
                http_status=403,
            )
    return None


def _validate_regression_test_ids(regression_test_ids):
    if regression_test_ids is not None:
        if not regression_test_ids:
            return None, make_error_response(
                'validation_error',
                'regression_test_ids cannot be empty.',
                details={'fields': {
                    'regression_test_ids': 'Must contain at least one ID.'}},
                http_status=400,
            )
        active_tests = RegressionTest.query.filter(
            RegressionTest.id.in_(regression_test_ids),
            RegressionTest.active == True,  # noqa: E712
        ).all()
        active_ids = {t.id for t in active_tests}
        inactive_ids = [
            tid for tid in regression_test_ids if tid not in active_ids]
        if inactive_ids:
            return None, make_error_response(
                'unprocessable',
                'Some regression test IDs are inactive or do not exist.',
                details={'inactive_ids': inactive_ids},
                http_status=422,
            )
    else:
        active_tests = RegressionTest.query.filter_by(active=True).all()
        regression_test_ids = [t.id for t in active_tests]
    return regression_test_ids, None


@mod_api.route('/runs', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_offset_pagination()
@validate_sort()
@validate_date_range
def list_runs(
        limit=50,
        offset=0,
        sort='-created_at',
        created_after=None,
        created_before=None):
    """List runs with filters for platform, branch, commit, repo, status, and date range."""
    query, err = _apply_run_filters(Test.query, created_after, created_before)
    if err:
        return err

    sort_map = {
        'run_id': Test.id,
        'created_at': Test.id,  # best proxy - Test has no created_at column
    }
    order = get_sort_column(sort, sort_map)
    if order is not None:
        query = query.order_by(order)
    else:
        query = query.order_by(Test.id.desc())

    status_filter = request.args.get('status')
    if status_filter:
        if status_filter not in ('queued', 'running', 'canceled'):
            return make_error_response(
                'validation_error',
                f'Filtering by status "{status_filter}" is not supported. Supported: queued, running, canceled.',
                http_status=400,
            )

        latest_progress_sq = (
            g.db.query(func.max(TestProgress.id).label('max_id'))
            .group_by(TestProgress.test_id)
            .subquery()
        )

        if status_filter == 'queued':
            query = query.outerjoin(TestProgress).filter(
                TestProgress.id.is_(None))
        elif status_filter == 'running':
            query = query.join(
                TestProgress,
                TestProgress.test_id == Test.id) .filter(
                TestProgress.id.in_(latest_progress_sq)) .filter(
                TestProgress.status.in_(
                    [
                        TestStatus.preparation,
                        TestStatus.testing]))
        elif status_filter == 'canceled':
            query = query.join(TestProgress, TestProgress.test_id == Test.id)\
                         .filter(TestProgress.id.in_(latest_progress_sq))\
                         .filter(TestProgress.status == TestStatus.canceled)

    total = query.count()
    tests = query.offset(offset).limit(limit).all()
    serialized = _batch_serialize(tests)
    return paginated_response(
        serialized,
        total,
        limit,
        offset,
        schema=RunSchema())


def _get_or_create_fork(fork_url):
    fork = Fork.query.filter(Fork.github == fork_url).first()
    if fork is None:
        fork = Fork(fork_url)
        g.db.add(fork)
        try:
            g.db.flush()
        except IntegrityError:
            g.db.rollback()
            fork = Fork.query.filter(Fork.github == fork_url).first()
            if fork is None:
                return None, make_error_response(
                    'internal_error', 'Failed to create or resolve fork.', http_status=500)
    return fork, None


def _ci_artifact_exists(commit_sha, platform):
    """Return True if a CI build artifact exists for this commit + platform.

    The worker runs prebuilt binaries downloaded from GitHub Actions rather
    than building from source, so a run can only execute if a build artifact
    keyed to ``commit_sha`` exists on the main repo (this is also true for
    fork PR commits, whose artifacts are produced by the main repo's PR
    workflow). Mirrors verify_artifacts_exist() in the webhook path.

    Fails open (returns True) if GitHub can't be reached, so run creation
    never depends on a successful artifact lookup — the cron still guards
    against genuinely missing artifacts.
    """
    from run import config, log
    try:
        from github import Auth, Github

        from mod_ci.controllers import find_artifact_for_commit
        gh = Github(auth=Auth.Token(config.get('GITHUB_TOKEN', '')))
        repo = gh.get_repo(
            f"{config.get('GITHUB_OWNER', '')}/{config.get('GITHUB_REPOSITORY', '')}")
        return find_artifact_for_commit(repo, commit_sha, platform, log) is not None
    except Exception:
        log.exception(
            'create_run: artifact pre-check failed; allowing run to proceed')
        return True


@mod_api.route('/runs', methods=['POST'])
@require_scope(Scope.RUNS_WRITE)
@validate_body(RunCreateRequestSchema)
def create_run(validated_data=None):
    """Trigger a new test run for a commit + platform combination.

    CI worker pickup: the cron (run_cron.py) picks up any Test row that has
    no 'completed'/'canceled' TestProgress, then runs the prebuilt GitHub
    Actions artifact for that commit. We therefore reject up front any
    commit+platform with no build artifact (see _ci_artifact_exists), so
    the run isn't accepted only to fail asynchronously in the worker.
    """
    commit_sha = validated_data['commit_sha']
    platform_str = validated_data['platform']
    branch = validated_data.get('branch', 'master')
    repository = validated_data.get('repository')
    pull_request = validated_data.get('pull_request') or 0
    regression_test_ids = validated_data.get('regression_test_ids')

    platform = TestPlatform.from_string(platform_str)

    # Main repo requires contributor+; forks allow any authenticated user.
    from run import config
    main_owner = config.get('GITHUB_OWNER', '')
    main_repo = config.get('GITHUB_REPOSITORY', '')
    main_repo_full = f'{main_owner}/{main_repo}'
    # repository is a required field (RunCreateRequestSchema), so it is always
    # present; a main-repo run passes the main repo's "owner/repo" explicitly.
    target_repo = repository

    err = _validate_run_permissions(g.api_user, target_repo, main_repo_full)
    if err:
        return err

    # Reject commits with no CI build artifact — the worker runs prebuilt
    # binaries, so such a run would be accepted but never execute.
    if not _ci_artifact_exists(commit_sha, platform):
        return make_error_response(
            'unprocessable',
            f'No CI build artifact found for commit {commit_sha[:8]} on '
            f'{platform.value}. Ensure the build workflow has completed for '
            'this commit before triggering a run.',
            details={'commit_sha': commit_sha, 'platform': platform.value},
            http_status=422,
        )

    fork_url = f'https://github.com/{repository}.git'

    fork, err = _get_or_create_fork(fork_url)
    if err:
        return err

    # Validate regression test IDs against active tests only.
    regression_test_ids, err = _validate_regression_test_ids(
        regression_test_ids)
    if err:
        return err

    test_type = TestType.pull_request if pull_request else TestType.commit

    test = Test(
        platform=platform,
        test_type=test_type,
        fork_id=fork.id,
        branch=branch,
        commit=commit_sha,
        pr_nr=pull_request,
    )
    g.db.add(test)
    try:
        g.db.flush()
    except Exception:
        g.db.rollback()
        return make_error_response(
            'internal_error',
            'Failed to create run.',
            http_status=500)

    for rt_id in regression_test_ids:
        ct = CustomizedTest(test.id, rt_id)
        g.db.add(ct)
    try:
        g.db.commit()
    except Exception:
        g.db.rollback()
        return make_error_response(
            'internal_error',
            'Failed to finalize run.',
            http_status=500)

    return single_response(
        _serialize_run(test),
        schema=RunSchema(),
        http_status=202)


@mod_api.route('/runs/<run_id>', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('run_id')
def get_run(run_id):
    """Fetch a single run by ID."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    return single_response(_serialize_run(test), schema=RunSchema())


def _run_regression_ids(test):
    """Regression test IDs that belong to this run.

    Uses the customized selection when present; otherwise falls back to
    every ACTIVE regression test, mirroring create_run's default. (The
    model's get_customized_regressiontests() falls back to all tests
    including inactive ones, which inflates total_samples/skipped_count
    with tests the run could never execute.)
    """
    if test.customized_tests:
        return [ct.regression_id for ct in test.customized_tests]
    return [rt.id for rt in
            RegressionTest.query.filter_by(active=True).all()]


def _aggregate_run_statistics(
        results,
        files_by_result,
        expected_outputs_by_rt):
    pass_count = fail_count = skipped_count = missing_count = total_runtime = 0
    for result in results:
        result_files = files_by_result.get(result.regression_test_id, [])
        expected = expected_outputs_by_rt.get(result.regression_test_id)
        status = derive_sample_status(result, result_files, expected)

        if status == 'pass':
            pass_count += 1
        elif status == 'fail':
            fail_count += 1
        elif status == 'missing_output':
            missing_count += 1
        else:
            skipped_count += 1

        if result.runtime:
            total_runtime += result.runtime

    return pass_count, fail_count, skipped_count, missing_count, total_runtime


@mod_api.route('/runs/<run_id>/summary', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('run_id')
def get_run_summary(run_id):
    """
    Aggregate pass/fail/skip/missing/error counts from result rows.

    fail_count comes from TestResult rows, not from test.failed (which
    only reflects cancellation status and is unreliable for this purpose).
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    results = TestResult.query.filter_by(test_id=run_id).all()
    total_samples = len(_run_regression_ids(test))

    # Preload TestResultFiles

    all_files = (
        TestResultFile.query.options(
            joinedload(TestResultFile.regression_test_output)
            .joinedload(RegressionTestOutput.multiple_files)
        )
        .filter_by(test_id=run_id).all() if results else []
    )
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[f.regression_test_id].append(f)

    # Preload expected outputs
    expected_outputs_by_rt = defaultdict(list)
    if results:
        all_expected = RegressionTestOutput.query.filter(
            RegressionTestOutput.regression_id.in_([r.regression_test_id for r in results])
        ).all()
        for rto in all_expected:
            expected_outputs_by_rt[rto.regression_id].append(rto)

    pass_count, fail_count, skipped_count, missing_count, total_runtime = _aggregate_run_statistics(
        results, files_by_result, expected_outputs_by_rt)

    # Reconcile skipped samples (those without any TestResult row)
    if len(results) < total_samples:
        skipped_count += (total_samples - len(results))

    # Retrieve error_count from the error service
    error_count = len(
        derive_errors_for_run(
            run_id,
            expected_outputs_by_rt,
            preloaded_results=results,
            preloaded_files=all_files))

    statuses, _ = batch_get_run_data([test])
    run_status = statuses.get(test.id, 'queued')

    return single_response({
        'run_id': run_id,
        'status': run_status,
        'total_samples': total_samples,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'skipped_count': skipped_count,
        'missing_output_count': missing_count,
        'error_count': error_count,
        'duration_ms': total_runtime if total_runtime > 0 else None,
    }, schema=RunSummarySchema())


@mod_api.route('/runs/<run_id>/progress', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('run_id')
@validate_offset_pagination()
def get_run_progress(run_id, limit=50, offset=0):
    """
    Get the timeline of progress events for a run, paginated.

    Events come from TestProgress rows written by the CI worker.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    query = TestProgress.query.filter_by(test_id=run_id)

    # Optional status filter.
    status_filter = request.args.get('status')
    if status_filter:
        try:
            status_enum = TestStatus.from_string(status_filter)
            query = query.filter(TestProgress.status == status_enum)
        except Exception:
            return make_error_response(
                'validation_error',
                f'Invalid status filter: {status_filter}.',
                details={
                    'fields': {
                        'status': 'Must be one of: queued, preparation, testing, completed, canceled, error.'}},
                http_status=400,
            )

    query = query.order_by(TestProgress.id.asc())
    total = query.count()
    progress = query.offset(offset).limit(limit).all()

    events = [{
        'timestamp': p.timestamp,
        'status': p.status.name,
        'message': p.message,
    } for p in progress]

    schema = ProgressEventSchema()
    return paginated_response(events, total, limit, offset, schema=schema)


@mod_api.route('/runs/<run_id>/config', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('run_id')
def get_run_config(run_id):
    """Get the configuration that was used to launch this run."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    regression_ids = _run_regression_ids(test)

    return single_response({
        'run_id': run_id,
        'platform': test.platform.value,
        'branch': test.branch,
        'commit_sha': test.commit,
        'regression_test_ids': regression_ids,
    })


@mod_api.route('/runs/<run_id>/cancel', methods=['POST'])
@require_roles([Role.admin, Role.contributor, Role.tester])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('run_id')
def cancel_run(run_id):
    """Cancel a running or queued test.

    Idempotent — canceling something already finished returns 202
    with status=no_op.

    Note: In this shared CI environment, any user with 'runs:write'
    (admin, contributor, tester) can cancel any run on the platform,
    regardless of ownership. This is intentional.
    """
    test = Test.query.with_for_update().filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    status = derive_run_status(test)
    if status in ('pass', 'fail', 'canceled', 'error'):
        return single_response({
            'run_id': run_id,
            'action': 'cancel',
            'status': 'no_op',
            'message': f'Run is already in terminal state: {status}',
        }, http_status=202)

    user = g.api_user
    reason = None
    if request.is_json and request.get_json(silent=True):
        reason = request.get_json(silent=True).get('reason')
        if reason:
            reason_str = str(reason).strip()
            if len(reason_str) < 5:
                return make_error_response(
                    'validation_error',
                    'Cancel reason must be at least 5 characters.',
                    details={'fields': {'reason': 'Minimum length is 5.'}},
                    http_status=400,
                )
            reason = reason_str[:255]

    cancel_msg = f'Canceled by {user.name} via API' if user else 'Canceled via API'
    if reason:
        cancel_msg = f'{cancel_msg}: {reason}'

    progress = TestProgress(run_id, TestStatus.canceled, cancel_msg)
    g.db.add(progress)
    g.db.commit()

    return single_response({
        'run_id': run_id,
        'action': 'cancel',
        'status': 'accepted',
        'message': 'Run has been canceled.',
    }, http_status=202)


@mod_api.route('/runs/<run_id>/restart', methods=['POST'])
@require_roles([Role.admin, Role.contributor, Role.tester])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('run_id')
def restart_run(run_id):
    """
    Queue a finished or stuck run to be executed again.

    Clearing the results and the progress trail is what makes the run
    eligible again, because CI picks up tests that have no progress
    recorded. The run keeps its id, so existing links stay valid, and the
    old results are replaced rather than kept alongside the new ones.

    Like cancel, this is open to anyone holding runs:write rather than to
    the run's owner, which suits a shared CI where a stuck VM blocks
    everybody.
    """
    # Locked the way cancel locks, so two restarts arriving together do not
    # both go clearing the same results.
    test = Test.query.with_for_update().filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    TestResultFile.query.filter(
        TestResultFile.test_id == test.id).delete(synchronize_session=False)
    TestResult.query.filter(
        TestResult.test_id == test.id).delete(synchronize_session=False)
    TestProgress.query.filter(
        TestProgress.test_id == test.id).delete(synchronize_session=False)
    g.db.commit()

    g.log.info(f'run {run_id} restarted via API by {g.api_user.id}')
    return single_response({
        'run_id': run_id,
        'action': 'restart',
        'status': 'accepted',
        'message': 'Run has been queued to run again.',
    }, http_status=202)
