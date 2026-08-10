"""
System, health, queue, artifact, and platform configuration routes.

GET    /system/health                        Health check (unauthenticated)
GET    /system/queue                         Queue status — active + queued runs
GET    /runs/{id}/artifacts                  Run artifacts from GCS + local
GET    /system/about                         Versions this platform runs against
GET    /system/maintenance                   Maintenance state per platform
PATCH  /system/maintenance/{platform}        Pause or resume a platform
GET    /system/blocked-users                 CI users blocked from triggering
POST   /system/blocked-users                 Block a GitHub account
DELETE /system/blocked-users/{user_id}       Unblock a GitHub account
GET    /system/forbidden-extensions          Extensions rejected on upload
POST   /system/forbidden-extensions          Forbid an extension
DELETE /system/forbidden-extensions/{ext}    Allow an extension again

Every configuration route is admin-only, matching the classic maintenance and
blocked-user pages: the blocklist names accounts, and the rest decides whether
CI accepts work at all. Reads additionally need system:read and writes
system:write, so a token can be narrowed further than the role allows.
"""

import os
from datetime import datetime, timezone

from flask import g, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.models.api_token import Scope
from mod_api.schemas.common import DATETIME_FORMAT
from mod_api.schemas.system import (BlockedUserCreateSchema,
                                    ForbiddenExtensionCreateSchema,
                                    MaintenanceUpdateSchema)
from mod_api.services.status import batch_get_run_data, is_dummy_row
from mod_api.services.storage import (get_log_file_path,
                                      get_test_results_base_path,
                                      resolve_artifact)
from mod_api.utils import paginated_response, safe_resolve, single_response
from mod_auth.models import Role
from mod_ci.models import BlockedUsers, MaintenanceMode
from mod_home.models import CCExtractorVersion, GeneralData
from mod_sample.models import ForbiddenExtension
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
        dependencies.append({'name': 'database',
                             'status': 'down',
                             'message': 'Database connection failed.'})
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
            dependencies.append({'name': 'gcs',
                                 'status': 'degraded',
                                 'message': 'GCS client not initialized.'})
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
        'checked_at': now.strftime(DATETIME_FORMAT),
        'dependencies': dependencies,
    })
    response.status_code = http_status
    return response


def _apply_queue_filters(
        base_query,
        running_subq,
        queue_depth,
        running_count,
        status_filter):
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
            'validation_error', 'Invalid status. Must be queued or running.', http_status=400)
    else:
        query = base_query
        total = queue_depth + running_count
    return query, total, None


@mod_api.route('/system/queue', methods=['GET'])
@require_scope(Scope.SYSTEM_READ)
@validate_offset_pagination()
def get_queue(limit=50, offset=0):
    """
    Get queue summary and list of runs.

    Note: The `position` field is only populated when `?status=queued` is
    explicitly provided. Otherwise, it will be null for all items.

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
            return make_error_response(
                'validation_error',
                'Invalid platform.',
                http_status=400)

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
            # Same 'Z' format the schemas use, so the API emits one
            # datetime style everywhere (timestamps are UTC).
            'queued_at': ts.get('queued_at').strftime(DATETIME_FORMAT) if ts.get('queued_at') else None,
            'started_at': ts.get('started_at').strftime(DATETIME_FORMAT) if ts.get('started_at') else None,
            'position': pos,
        })

    return paginated_response(
        paged_jobs, total, limit, offset,
        extra_meta={
            'queue_depth': queue_depth,
            'running_count': running_count,
        }
    )


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
    result_files = TestResultFile.query.options(
        joinedload(TestResultFile.regression_test_output),
        joinedload(TestResultFile.regression_test),
    ).filter_by(test_id=run_id).all()
    for rf in result_files:
        if is_dummy_row(rf):
            continue

        ext = rf.regression_test_output.correct_extension if rf.regression_test_output else ''
        sample_id = (rf.regression_test.sample_id
                     if rf.regression_test else None)

        expected_name = rf.expected + ext
        # NOTE: storage metadata (storage_status, download_url, size_bytes,
        # content_type) is resolved by list_artifacts for paged items only.

        yield {
            'artifact_id': f'expected_{run_id}_{rf.regression_test_id}_{rf.regression_test_output_id}',
            'run_id': run_id,
            'sample_id': sample_id,
            'type': 'expected_output',
            'filename': expected_name,
        }

        if rf.got is not None:
            actual_name = rf.got + ext
            yield {
                'artifact_id': f'actual_{run_id}_{rf.regression_test_id}_{rf.regression_test_output_id}',
                'run_id': run_id,
                'sample_id': sample_id,
                'type': 'actual_output',
                'filename': actual_name,
            }


@mod_api.route('/runs/<run_id>/artifacts', methods=['GET'])
@require_scope(Scope.RESULTS_READ)
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
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

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

    artifacts.extend(list(_get_output_artifacts(run_id)))

    # Apply optional ?type filter.
    type_filter = request.args.get('type')
    if type_filter:
        artifacts = [a for a in artifacts if a['type'] == type_filter]

    total = len(artifacts)
    paged = artifacts[offset:offset + limit]

    # Resolve heavy artifact metadata only for the returned page
    base_path = get_test_results_base_path()
    for a in paged:
        if 'storage_status' not in a:
            # It's an output artifact
            filename = a['filename']
            url, status = resolve_artifact(f'TestResults/{filename}')
            local = safe_resolve(base_path, filename)

            a['content_type'] = OCTET_STREAM
            a['size_bytes'] = (
                os.path.getsize(local)
                if local and os.path.isfile(local) else None
            )
            a['storage_status'] = status
            a['download_url'] = url

    return paginated_response(paged, total, limit, offset)


@mod_api.route('/system/about', methods=['GET'])
@require_scope(Scope.SYSTEM_READ)
def system_about():
    """
    Report the versions this platform is running against.

    The classic about page is static prose. The parts of it worth reading
    from a client are the CCExtractor release under test and the commit the
    platform itself was deployed from, so those are what this returns.
    """
    from run import app

    latest = CCExtractorVersion.query.order_by(
        CCExtractorVersion.released.desc()).first()
    last_commit = GeneralData.query.filter(
        GeneralData.key == 'last_commit').first()

    return single_response({
        'platform_commit': app.config.get('BUILD_COMMIT'),
        'ccextractor_version': latest.version if latest else None,
        'ccextractor_released': (
            latest.released.isoformat()
            if latest and latest.released else None),
        'last_tested_commit': last_commit.value if last_commit else None,
    })


def _maintenance_entry(platform, row):
    """Maintenance shape for one platform; no row means never paused."""
    return {
        'platform': platform.value,
        'disabled': bool(row.disabled) if row is not None else False,
    }


@mod_api.route('/system/maintenance', methods=['GET'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_READ)
def get_maintenance():
    """
    Report maintenance state, one entry per platform.

    Keyed on ``platforms`` rather than the ``data`` collection envelope: the
    list is derived from the platform enum, not a growable table, so there
    is nothing to paginate.
    """
    # No unique key on platform, so order it: a duplicated row must not make
    # the reported state depend on which one the database returns first.
    rows = {}
    for row in MaintenanceMode.query.order_by(MaintenanceMode.id.asc()).all():
        rows.setdefault(row.platform, row)
    return single_response({'platforms': [
        _maintenance_entry(platform, rows.get(platform))
        for platform in TestPlatform
    ]})


@mod_api.route('/system/maintenance/<platform>', methods=['PATCH'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_WRITE)
@validate_body(MaintenanceUpdateSchema)
def update_maintenance(platform, validated_data=None):
    """
    Pause or resume CI for one platform.

    While a platform is disabled new runs still queue; they are simply not
    handed to a VM until it is resumed.
    """
    if platform not in TestPlatform.values():
        return make_error_response(
            'validation_error',
            f'Invalid platform. Must be one of: '
            f'{", ".join(sorted(TestPlatform.values()))}.',
            http_status=400,
        )

    target = TestPlatform.from_string(platform)
    disabled = validated_data['disabled']
    row = MaintenanceMode.query.filter(
        MaintenanceMode.platform == target).order_by(
            MaintenanceMode.id.asc()).first()
    if row is None:
        row = MaintenanceMode(target, disabled)
        g.db.add(row)
    else:
        row.disabled = disabled
    g.db.commit()

    g.log.info(f'maintenance for {target.value} set to disabled={disabled} '
               f'via API by user {g.api_user.id}')
    return single_response(_maintenance_entry(target, row))


@mod_api.route('/system/blocked-users', methods=['GET'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_READ)
@validate_offset_pagination()
def list_blocked_users(limit=50, offset=0):
    """List the GitHub accounts blocked from triggering CI runs."""
    query = BlockedUsers.query.order_by(BlockedUsers.user_id.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return paginated_response(
        [{'user_id': row.user_id, 'comment': row.comment or ''}
         for row in rows],
        total, limit, offset)


@mod_api.route('/system/blocked-users', methods=['POST'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_WRITE)
@validate_body(BlockedUserCreateSchema)
def create_blocked_user(validated_data=None):
    """Block a GitHub account from triggering CI runs."""
    user_id = validated_data['user_id']
    if BlockedUsers.query.filter(
            BlockedUsers.user_id == user_id).first() is not None:
        return make_error_response(
            'conflict', f'GitHub user {user_id} is already blocked.',
            http_status=409)

    row = BlockedUsers(user_id, validated_data['comment'])
    g.db.add(row)
    try:
        g.db.commit()
    except IntegrityError:
        # user_id is the primary key, so a request that raced the check
        # above lands here instead of duplicating the row.
        g.db.rollback()
        return make_error_response(
            'conflict', f'GitHub user {user_id} is already blocked.',
            http_status=409)

    g.log.info(f'github user {user_id} blocked via API by user {g.api_user.id}')
    return single_response(
        {'user_id': row.user_id, 'comment': row.comment or ''},
        http_status=201)


@mod_api.route('/system/blocked-users/<int:user_id>', methods=['DELETE'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_WRITE)
def delete_blocked_user(user_id):
    """Unblock a GitHub account."""
    row = BlockedUsers.query.filter(BlockedUsers.user_id == user_id).first()
    if row is None:
        return make_error_response(
            'not_found', f'GitHub user {user_id} is not blocked.',
            http_status=404)

    g.db.delete(row)
    g.db.commit()

    g.log.info(f'github user {user_id} unblocked via API by {g.api_user.id}')
    return single_response({'user_id': user_id, 'deleted': True})


@mod_api.route('/system/forbidden-extensions', methods=['GET'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_READ)
@validate_offset_pagination()
def list_forbidden_extensions(limit=50, offset=0):
    """List the file extensions rejected on upload."""
    query = ForbiddenExtension.query.order_by(
        ForbiddenExtension.extension.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return paginated_response(
        [row.extension for row in rows], total, limit, offset)


@mod_api.route('/system/forbidden-extensions', methods=['POST'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_WRITE)
@validate_body(ForbiddenExtensionCreateSchema)
def create_forbidden_extension(validated_data=None):
    """Forbid an extension. Stored lower-cased and without a leading dot."""
    extension = validated_data['extension'].lower()
    if ForbiddenExtension.query.filter(
            ForbiddenExtension.extension == extension).first() is not None:
        return make_error_response(
            'conflict', f"Extension '{extension}' is already forbidden.",
            http_status=409)

    g.db.add(ForbiddenExtension(extension))
    try:
        g.db.commit()
    except IntegrityError:
        # extension is the primary key; same race as blocking a user.
        g.db.rollback()
        return make_error_response(
            'conflict', f"Extension '{extension}' is already forbidden.",
            http_status=409)

    g.log.info(f'extension {extension} forbidden via API by {g.api_user.id}')
    return single_response({'extension': extension}, http_status=201)


@mod_api.route('/system/forbidden-extensions/<extension>', methods=['DELETE'])
@require_roles([Role.admin])
@require_scope(Scope.SYSTEM_WRITE)
def delete_forbidden_extension(extension):
    """Allow an extension to be uploaded again."""
    normalized = extension.lstrip('.').lower()
    row = ForbiddenExtension.query.filter(
        ForbiddenExtension.extension == normalized).first()
    if row is None:
        return make_error_response(
            'not_found', f"Extension '{normalized}' is not forbidden.",
            http_status=404)

    g.db.delete(row)
    g.db.commit()

    g.log.info(f'extension {normalized} allowed via API by {g.api_user.id}')
    return single_response({'extension': normalized, 'deleted': True})
