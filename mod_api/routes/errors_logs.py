"""
Error and build log routes.

GET /runs/{id}/errors                  Test-level errors for a run
GET /runs/{id}/infrastructure-errors   Infra errors (VM, build, worker)
GET /runs/{id}/error-summary           Grouped error counts
GET /runs/{id}/logs                    Build log (cursor-paginated)
GET /runs/{id}/samples/{sid}/logs      Per-sample logs (not yet available)
"""

from flask import g, request

from mod_api import mod_api
from mod_api.middleware.auth import require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_cursor_pagination,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.models.api_token import Scope
from mod_api.services.error_service import (derive_error_summary,
                                            derive_errors_for_run,
                                            derive_infrastructure_errors)
from mod_api.services.log_service import read_log_lines
from mod_api.utils import cursor_paginated_response, paginated_response
from mod_auth.models import Role
from mod_test.models import Test


@mod_api.route('/runs/<run_id>/errors', methods=['GET'])
@require_scope(Scope.RESULTS_READ)
@validate_path_id('run_id')
@validate_offset_pagination()
def list_run_errors(run_id, limit=50, offset=0):
    """List test errors for a run, derived from result and output data."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    errors = derive_errors_for_run(run_id)

    error_type = request.args.get('type')
    if error_type:
        errors = [e for e in errors if e['type'] == error_type]

    severity = request.args.get('severity')
    if severity:
        errors = [e for e in errors if e['severity'] == severity]

    sample_id = request.args.get('sample_id', type=int)
    if sample_id:
        errors = [e for e in errors if e.get('sample_id') == sample_id]

    total = len(errors)
    paged = errors[offset:offset + limit]

    return paginated_response(paged, total, limit, offset)


@mod_api.route('/runs/<run_id>/infrastructure-errors', methods=['GET'])
@require_scope(Scope.SYSTEM_READ)
@validate_path_id('run_id')
@validate_offset_pagination()
def list_infrastructure_errors(run_id, limit=50, offset=0):
    """
    Infra errors classified from TestProgress messages on a best-effort basis.

    Stack traces are opt-in because they may contain internal paths.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    include_stack = request.args.get(
        'include_stack', 'false').lower() == 'true'
    if include_stack:
        user = getattr(g, 'api_user', None)
        allowed = (Role.admin, Role.contributor)
        if user is None or user.role not in allowed:
            return make_error_response(
                'forbidden',
                'Stack traces require admin or contributor role.',
                details={'required_roles': [role.value for role in allowed]},
                http_status=403,
            )

    errors = derive_infrastructure_errors(run_id)

    if not include_stack:
        for e in errors:
            e.pop('stack', None)

    # Apply optional type and severity filters.
    error_type = request.args.get('type')
    if error_type:
        errors = [e for e in errors if e.get('type') == error_type]

    severity = request.args.get('severity')
    if severity:
        errors = [e for e in errors if e.get('severity') == severity]

    total = len(errors)
    paged = errors[offset:offset + limit]
    return paginated_response(paged, total, limit, offset)


@mod_api.route('/runs/<run_id>/error-summary', methods=['GET'])
@require_scope(Scope.RESULTS_READ)
@validate_path_id('run_id')
@validate_offset_pagination()
def get_error_summary(run_id, limit=50, offset=0):
    """Group error summary for triaging a run before drilling into details."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    group_by = request.args.get('group_by', 'type')
    if group_by not in ('type', 'severity', 'sample_id', 'regression_id'):
        return make_error_response(
            'validation_error',
            'group_by must be one of: type, severity, sample_id, regression_id.',
            http_status=400,
        )

    severity = request.args.get('severity')

    summary = derive_error_summary(run_id, group_by=group_by)

    if severity:
        summary = [s for s in summary if s.get('severity') == severity]

    total = len(summary)
    paged = summary[offset:offset + limit]
    return paginated_response(paged, total, limit, offset)


@mod_api.route('/runs/<run_id>/logs', methods=['GET'])
@require_scope(Scope.SYSTEM_READ)
@validate_path_id('run_id')
@validate_cursor_pagination(default_limit=100)
def get_run_logs(run_id, limit=100, cursor=None):
    """
    Read a run's build log with cursor-based pagination.

    Returns 404 (not a broken download link) when the file doesn't exist.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    level = request.args.get('level')
    source = request.args.get('source')
    contains = request.args.get('contains')
    if contains and len(contains) > 100:
        return make_error_response(
            'validation_error',
            'contains parameter must be 100 characters or less.',
            http_status=400,
        )

    try:
        lines, next_cursor = read_log_lines(
            run_id,
            cursor=cursor,
            limit=limit,
            level=level,
            source=source,
            contains=contains,
        )
    except FileNotFoundError:
        return make_error_response(
            'log_not_found',
            f'Log file for run {run_id} is not available locally. '
            'It may have been moved to cold storage. Please download it via the artifacts API.',
            details={'run_id': run_id,
                     'action_required': f'Use GET /runs/{run_id}/artifacts (type=build_log)'},
            http_status=404,
        )

    return cursor_paginated_response(lines, next_cursor, limit)


@mod_api.route('/runs/<run_id>/samples/<sample_id>/logs', methods=['GET'])
@require_scope(Scope.SYSTEM_READ)
@validate_path_id('run_id')
@validate_path_id('sample_id')
@validate_offset_pagination()
def get_sample_logs(run_id, sample_id, limit=50, offset=0):
    """Per-sample logs aren't available yet — the CI worker doesn't support them."""
    return make_error_response(
        'not_found',
        f'Per-sample logs are not available for sample {sample_id} in run {run_id}.',
        details={
            'reason': 'Per-sample log storage is not yet supported by the CI worker.'},
        http_status=404,
    )
