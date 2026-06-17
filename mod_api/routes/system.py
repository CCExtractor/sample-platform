"""
System, health, queue, and artifact routes.

GET /system/health           Health check (unauthenticated)
GET /system/queue            Queue status — active + queued runs
GET /runs/{id}/artifacts     Run artifacts from GCS + local storage
"""

import os
from datetime import datetime, timezone

from flask import g, jsonify, request
from sqlalchemy import text

from mod_api import mod_api
from mod_api.middleware.auth import require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_offset_pagination,
                                           validate_path_id)
from mod_api.services.status import derive_run_status, is_dummy_row
from mod_api.services.storage import (get_log_file_path,
                                      get_test_results_base_path,
                                      resolve_artifact)
from mod_api.utils import paginated_response
from mod_test.models import (Test, TestPlatform, TestProgress, TestResultFile,
                             TestStatus)

OCTET_STREAM = 'application/octet-stream'


@mod_api.route('/system/health', methods=['GET'])
def system_health():
    """
    Public health check — no auth required.

    Returns 200 when things are ok or degraded, 503 when the system is down.
    Monitoring services and load balancers can hit this freely.
    """
    now = datetime.now(timezone.utc)
    dependencies = []
    overall = 'ok'

    # Database connectivity.
    try:
        g.db.execute(text('SELECT 1'))
        dependencies.append(
            {'name': 'database', 'status': 'ok', 'message': None})
    except Exception:
        dependencies.append(
            {'name': 'database', 'status': 'down', 'message': 'Database connection failed.'})
        overall = 'down'

    # Local sample storage.
    try:
        from run import config
        sample_repo = config.get('SAMPLE_REPOSITORY', '')
        if os.path.isdir(sample_repo):
            dependencies.append(
                {'name': 'local_storage', 'status': 'ok', 'message': None})
        else:
            dependencies.append({
                'name': 'local_storage',
                'status': 'degraded',
                'message': 'Local storage check failed.',
            })
            if overall == 'ok':
                overall = 'degraded'
    except Exception:
        dependencies.append({'name': 'local_storage', 'status': 'down',
                            'message': 'Local storage check failed.'})
        overall = 'down'

    # Google Cloud Storage.
    try:
        from run import storage_client_bucket
        if storage_client_bucket:
            dependencies.append(
                {'name': 'gcs', 'status': 'ok', 'message': None})
        else:
            dependencies.append(
                {'name': 'gcs', 'status': 'degraded', 'message': 'GCS client not initialized.'})
            if overall == 'ok':
                overall = 'degraded'
    except Exception:
        dependencies.append({'name': 'gcs', 'status': 'degraded',
                            'message': 'GCS connectivity check failed.'})
        if overall == 'ok':
            overall = 'degraded'

    http_status = 503 if overall == 'down' else 200
    response = jsonify({
        'status': overall,
        'checked_at': now.isoformat(),
        'dependencies': dependencies,
    })
    response.status_code = http_status
    return response


def _apply_queue_filters(base_query, running_subq, queue_depth, running_count, status_filter):
    if status_filter == 'queued':
        query = base_query.filter(~Test.id.in_(
            g.db.query(running_subq.c.test_id)))
        total = queue_depth
    elif status_filter == 'running':
        query = base_query.filter(Test.id.in_(
            g.db.query(running_subq.c.test_id)))
        total = running_count
    elif status_filter:
        return None, None, make_error_response(
            'validation_error', 'Invalid status. Must be queued or running.', http_status=400
        )
    else:
        query = base_query
        total = queue_depth + running_count
    return query, total, None


@mod_api.route('/system/queue', methods=['GET'])
@require_scope('system:read')
@validate_offset_pagination()
def get_queue(limit=50, offset=0):
    """
    Return queued and running jobs.

    Excludes anything that's already completed or canceled. Supports
    ?platform and ?status filters.
    """
    terminal_subq = g.db.query(
        TestProgress.test_id
    ).filter(
        TestProgress.status.in_([TestStatus.completed, TestStatus.canceled])
    ).group_by(TestProgress.test_id).subquery()

    running_subq = g.db.query(
        TestProgress.test_id
    ).filter(
        TestProgress.status.in_([TestStatus.preparation, TestStatus.testing])
    ).group_by(TestProgress.test_id).subquery()

    base_query = Test.query.filter(
        ~Test.id.in_(g.db.query(terminal_subq.c.test_id))
    )

    platform_filter = request.args.get('platform')
    if platform_filter:
        try:
            plat = TestPlatform.from_string(platform_filter)
            base_query = base_query.filter(Test.platform == plat)
        except Exception:
            return make_error_response('validation_error', 'Invalid platform.', http_status=400)

    running_count = base_query.filter(Test.id.in_(
        g.db.query(running_subq.c.test_id))).count()
    queue_depth = base_query.filter(~Test.id.in_(
        g.db.query(running_subq.c.test_id))).count()

    status_filter = request.args.get('status')
    query, total, err = _apply_queue_filters(
        base_query, running_subq, queue_depth, running_count, status_filter)
    if err:
        return err

    query = query.order_by(Test.id.asc())
    paged_tests = query.offset(offset).limit(limit).all()

    from mod_api.services.status import batch_get_run_data
    statuses, timestamps = batch_get_run_data(paged_tests)

    paged_jobs = []
    queued_index = offset + 1 if status_filter == 'queued' else None

    for test in paged_tests:
        status = statuses.get(test.id, 'queued')
        ts = timestamps.get(test.id, {})

        pos = None
        if status == 'queued' and queued_index is not None:
            pos = queued_index
            queued_index += 1

        paged_jobs.append({
            'run_id': test.id,
            'status': status,
            'platform': test.platform.value,
            'queued_at': ts.get('queued_at').isoformat() if ts.get('queued_at') else None,
            'started_at': ts.get('started_at').isoformat() if ts.get('started_at') else None,
            'position': pos,
        })

    response = jsonify({
        'queue_depth': queue_depth,
        'running_count': running_count,
        'data': paged_jobs,
        'pagination': {
            'limit': limit,
            'offset': offset,
            'total': total,
            'next_offset': offset + limit if (offset + limit) < total else None,
        },
    })
    return response


def _get_gcs_artifacts(run_id, platform):
    binary_name = (
        'ccextractor' if platform == TestPlatform.linux
        else 'ccextractorwinfull.exe'
    )
    gcs_artifacts = [
        ('binary',
         f'test_artifacts/{run_id}/{binary_name}', binary_name, OCTET_STREAM),
        ('coredump', f'test_artifacts/{run_id}/coredump',
         f'coredump-{run_id}', OCTET_STREAM),
        (
            'combined_stdout',
            f'test_artifacts/{run_id}/combined_stdout.log',
            f'combined_stdout-{run_id}.log',
            'text/plain',
        ),
    ]
    artifacts = []
    for artifact_type, gcs_path, filename, content_type in gcs_artifacts:
        download_url, storage_status = resolve_artifact(gcs_path)
        artifacts.append({
            'artifact_id': f'{artifact_type}_{run_id}',
            'run_id': run_id,
            'sample_id': None,
            'type': artifact_type,
            'filename': filename,
            'content_type': content_type,
            'size_bytes': None,
            'storage_status': storage_status,
            'download_url': download_url,
        })
    return artifacts


def _get_output_artifacts(run_id):
    artifacts = []
    result_files = TestResultFile.query.filter_by(test_id=run_id).all()
    base_path = get_test_results_base_path()
    from mod_api.routes.results import _safe_resolve
    for rf in result_files:
        if is_dummy_row(rf):
            continue

        ext = rf.regression_test_output.correct_extension if rf.regression_test_output else ''

        expected_name = rf.expected + ext
        expected_url, expected_status = resolve_artifact(
            f'TestResults/{expected_name}')
        local_expected = _safe_resolve(base_path, expected_name)

        artifacts.append({
            'artifact_id': f'expected_{run_id}_{rf.regression_test_id}_{rf.regression_test_output_id}',
            'run_id': run_id,
            'sample_id': rf.regression_test_id,
            'type': 'expected_output',
            'filename': expected_name,
            'content_type': OCTET_STREAM,
            'size_bytes': (
                os.path.getsize(local_expected)
                if local_expected and os.path.isfile(local_expected) else None
            ),
            'storage_status': expected_status,
            'download_url': expected_url,
        })

        if rf.got is not None:
            actual_name = rf.got + ext
            actual_url, actual_status = resolve_artifact(
                f'TestResults/{actual_name}')
            local_actual = _safe_resolve(base_path, actual_name)

            artifacts.append({
                'artifact_id': f'actual_{run_id}_{rf.regression_test_id}_{rf.regression_test_output_id}',
                'run_id': run_id,
                'sample_id': rf.regression_test_id,
                'type': 'sample_output',
                'filename': actual_name,
                'content_type': OCTET_STREAM,
                'size_bytes': (
                    os.path.getsize(local_actual)
                    if local_actual and os.path.isfile(local_actual) else None
                ),
                'storage_status': actual_status,
                'download_url': actual_url,
            })
    return artifacts


@mod_api.route('/runs/<run_id>/artifacts', methods=['GET'])
@require_scope('results:read')
@validate_path_id('run_id')
@validate_offset_pagination()
def list_artifacts(run_id, limit=50, offset=0):
    """
    List all artifacts for a run.

    Checks both GCS and local storage. Falls back to local when GCS
    is unavailable. Supports ?type filter.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    artifacts = _get_gcs_artifacts(run_id, test.platform)

    # Build log — accessed via /runs/{id}/logs, no direct download link.
    log_path = get_log_file_path(run_id)
    artifacts.append({
        'artifact_id': f'buildlog_{run_id}',
        'run_id': run_id,
        'sample_id': None,
        'type': 'build_log',
        'filename': f'{run_id}.txt',
        'content_type': 'text/plain',
        'size_bytes': os.path.getsize(log_path) if log_path else None,
        'storage_status': 'ok' if log_path else 'missing',
        'download_url': None,
    })

    artifacts.extend(_get_output_artifacts(run_id))

    # Apply optional ?type filter.
    type_filter = request.args.get('type')
    if type_filter:
        artifacts = [a for a in artifacts if a['type'] == type_filter]

    total = len(artifacts)
    paged = artifacts[offset:offset + limit]
    return paginated_response(paged, total, limit, offset)
