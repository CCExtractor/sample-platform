"""
Test run routes.

GET    /runs                   List runs (filtered, paginated, sorted)
POST   /runs                   Trigger a new run
GET    /runs/{id}              Single run details
GET    /runs/{id}/summary      Pass/fail/skip counts
GET    /runs/{id}/progress     Progress event timeline
GET    /runs/{id}/config       Run configuration and test matrix
POST   /runs/{id}/cancel       Cancel a queued or running test
"""

from flask import g, request
from sqlalchemy.exc import IntegrityError

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (PATTERNS, validate_body,
                                           validate_date_range,
                                           validate_offset_pagination,
                                           validate_path_id, validate_sort)
from mod_api.schemas.runs import ProgressEventSchema, RunCreateRequestSchema
from mod_api.services.status import (derive_run_status, derive_sample_status,
                                     get_run_timestamps)
from mod_api.utils import (cursor_paginated_response, get_sort_column,
                           paginated_response, single_response)
from mod_customized.models import CustomizedTest
from mod_regression.models import RegressionTest
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)


def _serialize_run(test):
    """Turn a Test row into the Run response shape the spec expects."""
    return _batch_serialize([test])[0]


def _batch_serialize(tests, statuses=None, timestamps=None):
    from mod_api.services.status import batch_get_run_data
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

    repository = request.args.get('repository')
    if repository:
        from mod_api.middleware.validation import PATTERNS
        if not PATTERNS['repository'].match(repository):
            return None, make_error_response(
                'validation_error',
                'repository must match owner/repo format.',
                details={'fields': {
                    'repository': 'Must match ^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$'}},
                http_status=400,
            )
        fork_url = f'https://github.com/{repository}.git'
        query = query.join(Fork).filter(Fork.github == fork_url)

    if created_after or created_before:
        from sqlalchemy import func
        first_progress = (
            g.db.query(TestProgress.test_id, func.min(
                TestProgress.timestamp).label('min_ts'))
            .group_by(TestProgress.test_id)
            .subquery()
        )
        query = query.join(first_progress, Test.id == first_progress.c.test_id)
        if created_after:
            query = query.filter(first_progress.c.min_ts >= created_after)
        if created_before:
            query = query.filter(first_progress.c.min_ts <= created_before)

    return query, None


def _validate_run_permissions(user, target_repo, main_repo_full):
    if target_repo == main_repo_full:
        if user.role.value not in ('admin', 'tester', 'contributor'):
            return make_error_response(
                'forbidden',
                'Only admins, testers, and contributors can trigger runs for the main repository.',
                details={
                    'required_roles': ['admin', 'tester', 'contributor'],
                    'repository': target_repo,
                },
                http_status=403,
            )
    else:
        owner = target_repo.split('/')[0]
        github_login = user.github_login

        if not github_login and user.github_token:
            from mod_auth.controllers import fetch_username_from_token
            github_login = fetch_username_from_token(user)
            if github_login:
                user.github_login = github_login
                from flask import g
                g.db.add(user)

        github_login = github_login or ''

        is_owner = bool(github_login) and owner.lower() == github_login.lower()
        is_staff = user.role.value in ('admin', 'tester', 'contributor')

        if not is_owner and not is_staff:
            return make_error_response(
                'forbidden',
                'You can only trigger runs for your own repository.',
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
@require_scope('runs:read')
@validate_offset_pagination()
@validate_sort()
@validate_date_range
def list_runs(limit=50, offset=0, sort='-created_at', created_after=None, created_before=None):
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
        # Hard limit to prevent loading all historical runs into memory
        all_matching = query.limit(1000).all()
        is_truncated = len(all_matching) == 1000
        # Batch derivation logic
        from mod_api.services.status import batch_get_run_data
        statuses, timestamps = batch_get_run_data(all_matching)

        filtered = []
        for t in all_matching:
            if statuses.get(t.id, 'queued') == status_filter:
                filtered.append(t)

        serialized = _batch_serialize(
            filtered, statuses=statuses, timestamps=timestamps)

        total = len(serialized)
        paged = serialized[offset:offset + limit]
        from mod_api.schemas.runs import RunSchema
        return paginated_response(paged, total, limit, offset, schema=RunSchema(), truncated=is_truncated)

    total = query.count()
    tests = query.offset(offset).limit(limit).all()
    serialized = _batch_serialize(tests)
    from mod_api.schemas.runs import RunSchema
    return paginated_response(serialized, total, limit, offset, schema=RunSchema())


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
                return None, make_error_response('internal_error', 'Failed to create or resolve fork.', http_status=500)
    return fork, None


@mod_api.route('/runs', methods=['POST'])
@require_scope('runs:write')
@validate_body(RunCreateRequestSchema)
def create_run(validated_data=None):
    """Trigger a new test run for a commit + platform combination.

    CI worker pickup: The worker's cron job (run_cron.py) polls the Test
    table for rows without a 'completed' or 'canceled' TestProgress entry.
    Creating a Test row here is sufficient to enqueue it — no explicit
    signal is needed. See mod_ci/controllers.py queue_test() which follows
    the same pattern: 'Created tests, waiting for cron...'.
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
    target_repo = repository or main_repo_full

    err = _validate_run_permissions(g.api_user, target_repo, main_repo_full)
    if err:
        return err

    if repository:
        fork_url = f'https://github.com/{repository}.git'
    else:
        fork_url = f"https://github.com/{main_owner}/{main_repo}.git"

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
        return make_error_response('internal_error', 'Failed to create run.', http_status=500)

    for rt_id in regression_test_ids:
        ct = CustomizedTest(test.id, rt_id)
        g.db.add(ct)
    try:
        g.db.commit()
    except Exception:
        g.db.rollback()
        return make_error_response('internal_error', 'Failed to finalize run.', http_status=500)

    from mod_api.schemas.runs import RunSchema
    return single_response(_serialize_run(test), schema=RunSchema(), http_status=202)


@mod_api.route('/runs/<run_id>', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('run_id')
def get_run(run_id):
    """Fetch a single run by ID."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    from mod_api.schemas.runs import RunSchema
    return single_response(_serialize_run(test), schema=RunSchema())


@mod_api.route('/runs/<run_id>/summary', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('run_id')
def get_run_summary(run_id):
    """
    Aggregate pass/fail/skip/missing/error counts from result rows.

    fail_count comes from TestResult rows, not from test.failed (which
    only reflects cancellation status and is unreliable for this purpose).
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    results = TestResult.query.filter_by(test_id=run_id).all()
    total_samples = len(test.get_customized_regressiontests())

    pass_count = 0
    fail_count = 0
    skipped_count = 0
    missing_count = 0
    total_runtime = 0

    # Preload TestResultFiles
    from collections import defaultdict
    all_files = TestResultFile.query.filter_by(
        test_id=run_id).all() if results else []
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[f.regression_test_id].append(f)

    for result in results:
        result_files = files_by_result.get(result.regression_test_id, [])

        status = derive_sample_status(result, result_files)

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

    # Retrieve error_count from the error service
    from mod_api.services.error_service import derive_errors_for_run
    error_count = len(derive_errors_for_run(run_id))

    return single_response({
        'run_id': run_id,
        'status': derive_run_status(test),
        'total_samples': total_samples,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'skipped_count': skipped_count,
        'missing_output_count': missing_count,
        'error_count': error_count,
        'duration_ms': total_runtime if total_runtime > 0 else None,
        'triggered_by': None,
    })


@mod_api.route('/runs/<run_id>/progress', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('run_id')
@validate_offset_pagination()
def get_run_progress(run_id, limit=50, offset=0):
    """
    Get the timeline of progress events for a run, paginated.

    Events come from TestProgress rows written by the CI worker.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

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
                details={'fields': {
                    'status': 'Must be one of: queued, preparation, testing, completed, canceled, error.'
                }},
                http_status=400,
            )

    query = query.order_by(TestProgress.id.asc())
    total = query.count()
    progress = query.offset(offset).limit(limit).all()

    events = [{
        'timestamp': p.timestamp,
        'status': p.status.name,
        'message': p.message,
        'step': None,
    } for p in progress]

    schema = ProgressEventSchema()
    return paginated_response(events, total, limit, offset, schema=schema)


@mod_api.route('/runs/<run_id>/config', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('run_id')
def get_run_config(run_id):
    """Get the configuration that was used to launch this run."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    regression_ids = test.get_customized_regressiontests()

    return single_response({
        'run_id': run_id,
        'platform': test.platform.value,
        'branch': test.branch,
        'commit_sha': test.commit,
        'regression_test_ids': regression_ids,
    })


@mod_api.route('/runs/<run_id>/cancel', methods=['POST'])
@require_roles(['admin', 'contributor', 'tester'])
@require_scope('runs:write')
@validate_path_id('run_id')
def cancel_run(run_id):
    """Cancel a running or queued test.

    Idempotent — canceling something already finished returns 202
    with status=no_op.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

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
