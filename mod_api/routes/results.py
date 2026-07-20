"""
Expected/actual output, diffs, and baseline approval routes.

GET  /runs/{id}/samples/{sid}/regression-tests/{rid}/outputs/{oid}/expected
GET  /runs/{id}/samples/{sid}/regression-tests/{rid}/outputs/{oid}/actual
GET  /runs/{id}/samples/{sid}/regression-tests/{rid}/outputs/{oid}/diff
POST /runs/{id}/samples/{sid}/baseline-approval  Approve a new baseline
"""

import base64
import os

from flask import current_app, g, redirect, request, url_for

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import validate_body, validate_path_id
from mod_api.models.api_token import Scope
from mod_api.schemas.results import (BaselineApprovalRequestSchema,
                                     BaselineApprovalSchema,
                                     OutputFileContentSchema)
from mod_api.services.diff_service import compute_diff, file_sha256, read_lines
from mod_api.services.status import is_dummy_row
from mod_api.services.storage import (get_test_results_base_path,
                                      resolve_artifact)
from mod_api.utils import safe_resolve, single_response
from mod_auth.models import Role
from mod_regression.models import RegressionTestOutputFiles
from mod_test.models import Test, TestResultFile

INVALID_PATH_MSG = 'Invalid file path.'
READ_ERROR_MSG = 'Failed to read file.'


def _find_result_file(run_id, regression_test_id, output_id=None):
    """
    Look up the right TestResultFile row.

    Uses run_id + regression_test_id from the path. If output_id is
    given as a query param, narrow to that specific output file.
    """
    query = TestResultFile.query.filter_by(
        test_id=run_id,
        regression_test_id=regression_test_id,
    )

    if output_id is not None:
        query = query.filter_by(regression_test_output_id=output_id)

    return query.first()


def _validate_result_file_access(run_id, sample_id, regression_id, output_id):
    """Validate access to a result file and return it, or an error response."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return None, make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    result_file = _find_result_file(run_id, regression_id, output_id)

    if result_file is None:
        return None, make_error_response(
            'not_found',
            f'No result for regression test {regression_id}.',
            http_status=404,
        )

    actual_sample_id = (
        result_file.regression_test.sample_id
        if result_file.regression_test else None
    )
    if actual_sample_id != sample_id:
        return None, make_error_response(
            'not_found',
            f'Regression test {regression_id} does not belong to sample {sample_id}.',
            http_status=404,
        )

    return result_file, None


def _read_output_file(file_path, fmt, is_expected=True):
    """Read an output file into the response dict.

    The sha256 in the result is always computed over the complete file,
    even when content is truncated to the 1 MiB inline limit.
    """
    if not os.path.isfile(file_path):
        type_str = 'Expected' if is_expected else 'Actual'
        return None, make_error_response(
            'not_found',
            f'{type_str} output file not found on disk.',
            http_status=404,
        )

    sha256 = file_sha256(file_path)
    file_size = os.path.getsize(file_path)
    truncated = False
    download_url = None

    if file_size > 1048576:
        truncated = True
        filename = os.path.basename(file_path)
        download_url, _ = resolve_artifact(f'TestResults/{filename}')

    if fmt == 'text':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(1048576)
            encoding = 'utf-8'
        except Exception:
            return None, make_error_response('internal_error', READ_ERROR_MSG, http_status=500)
    else:
        try:
            with open(file_path, 'rb') as f:
                content = base64.b64encode(f.read(1048576)).decode('ascii')
            encoding = 'base64'
        except Exception:
            return None, make_error_response('internal_error', READ_ERROR_MSG, http_status=500)

    return {
        'content': content,
        'encoding': encoding,
        'sha256': sha256,
        'truncated': truncated,
        'download_url': download_url,
    }, None


@mod_api.route(
    '/runs/<run_id>/samples/<sample_id>/regression-tests/<int:regression_id>/outputs/<int:output_id>/expected',
    methods=['GET']
)
@require_scope(Scope.RESULTS_READ)
@validate_path_id('run_id')
@validate_path_id('sample_id')
@validate_path_id('regression_id')
@validate_path_id('output_id')
def get_expected_output(run_id, sample_id, regression_id, output_id):
    """Return the expected output file for a regression test result."""
    result_file, err = _validate_result_file_access(
        run_id, sample_id, regression_id, output_id)
    if err:
        return err

    if is_dummy_row(result_file):
        return make_error_response('not_found', 'Expected output not found.', http_status=404)

    base_path = get_test_results_base_path()
    expected_filename = result_file.expected
    ext = ''
    if result_file.regression_test_output:
        ext = result_file.regression_test_output.correct_extension
        if ext:
            ext = ext.replace('/', '').replace('\\', '').replace('..', '')
        expected_filename += ext

    file_path = safe_resolve(base_path, expected_filename)
    if file_path is None:
        return make_error_response('forbidden', INVALID_PATH_MSG, http_status=403)

    fmt = request.args.get('format', 'base64')

    data, err = _read_output_file(file_path, fmt, is_expected=True)
    if err:
        return err

    content = data['content']
    encoding = data['encoding']
    sha256 = data['sha256']
    truncated = data['truncated']
    download_url = data['download_url']

    _, storage_status = resolve_artifact(f'TestResults/{expected_filename}')

    return single_response({
        'run_id': run_id,
        'sample_id': sample_id,
        'regression_id': result_file.regression_test_id,
        'output_id': result_file.regression_test_output_id,
        'filename': expected_filename,
        'content_type': 'application/octet-stream',
        'encoding': encoding,
        'content': content,
        'truncated': truncated,
        'download_url': download_url,
        'sha256': sha256,
        'storage_status': storage_status,
    }, schema=OutputFileContentSchema())


@mod_api.route(
    '/runs/<run_id>/samples/<sample_id>/regression-tests/<int:regression_id>/outputs/<int:output_id>/actual',
    methods=['GET']
)
@require_scope(Scope.RESULTS_READ)
@validate_path_id('run_id')
@validate_path_id('sample_id')
@validate_path_id('regression_id')
@validate_path_id('output_id')
def get_actual_output(run_id, sample_id, regression_id, output_id):
    """
    Return the actual output file for a regression test result.

    got=null in the DB means the output matched expected — not that it's
    missing. We return 303 (redirect to expected) in that case. Missing
    output (the dummy sentinel row) returns 404.
    """
    result_file, err = _validate_result_file_access(
        run_id, sample_id, regression_id, output_id)
    if err:
        return err

    if is_dummy_row(result_file):
        return make_error_response(
            'missing_output',
            'Test produced no output when output was expected.',
            http_status=404,
        )

    if result_file.got is None:
        # Relative redirect: clients only resend Authorization headers on
        # same-origin redirects, and an absolute URL would break behind a
        # reverse proxy anyway.
        return redirect(url_for(
            'api.get_expected_output',
            run_id=run_id,
            sample_id=sample_id,
            regression_id=regression_id,
            output_id=output_id,
            format=request.args.get('format', 'base64'),
        ), code=303)

    base_path = get_test_results_base_path()
    actual_filename = result_file.got
    if result_file.regression_test_output:
        ext = result_file.regression_test_output.correct_extension
        if ext:
            ext = ext.replace('/', '').replace('\\', '').replace('..', '')
        actual_filename += ext

    file_path = safe_resolve(base_path, actual_filename)
    if file_path is None:
        return make_error_response('forbidden', INVALID_PATH_MSG, http_status=403)

    fmt = request.args.get('format', 'base64')

    data, err = _read_output_file(file_path, fmt, is_expected=False)
    if err:
        return err

    content = data['content']
    encoding = data['encoding']
    sha256 = data['sha256']
    truncated = data['truncated']
    download_url = data['download_url']

    _, storage_status = resolve_artifact(f'TestResults/{actual_filename}')

    return single_response({
        'run_id': run_id,
        'sample_id': sample_id,
        'regression_id': result_file.regression_test_id,
        'output_id': result_file.regression_test_output_id,
        'filename': actual_filename,
        'content_type': 'application/octet-stream',
        'encoding': encoding,
        'content': content,
        'truncated': truncated,
        'download_url': download_url,
        'sha256': sha256,
        'storage_status': storage_status,
    }, schema=OutputFileContentSchema())


def _handle_missing_diff(result_file, format_type, diff_ids):
    if is_dummy_row(result_file):
        if format_type == 'unified':
            return single_response({**diff_ids, 'format': 'unified', 'content': ''})
        return single_response({
            **diff_ids,
            'status': 'missing_actual',
            'format': 'structured',
            'summary': {'added_lines': 0, 'removed_lines': 0, 'changed_hunks': 0},
            'hunks': [],
        })

    if result_file.got is None:
        if format_type == 'unified':
            return single_response({**diff_ids, 'format': 'unified', 'content': ''})
        return single_response({
            **diff_ids,
            'status': 'identical',
            'format': 'structured',
            'summary': {'added_lines': 0, 'removed_lines': 0, 'changed_hunks': 0},
            'hunks': [],
        })
    return None


@mod_api.route(
    '/runs/<run_id>/samples/<sample_id>/regression-tests/<int:regression_id>/outputs/<int:output_id>/diff',
    methods=['GET']
)
@require_scope(Scope.RESULTS_READ)
@validate_path_id('run_id')
@validate_path_id('sample_id')
@validate_path_id('regression_id')
@validate_path_id('output_id')
def get_diff(run_id, sample_id, regression_id, output_id):
    """Structured diff between expected and actual output."""
    result_file, err = _validate_result_file_access(
        run_id, sample_id, regression_id, output_id)
    if err:
        return err

    diff_ids = {
        'run_id': run_id,
        'sample_id': sample_id,
        'regression_id': result_file.regression_test_id,
        'output_id': result_file.regression_test_output_id,
    }

    format_type = request.args.get('format', 'structured')

    missing_response = _handle_missing_diff(result_file, format_type, diff_ids)
    if missing_response:
        return missing_response

    base_path = get_test_results_base_path()
    ext = result_file.regression_test_output.correct_extension if result_file.regression_test_output else ''
    if ext:
        ext = ext.replace('/', '').replace('\\', '').replace('..', '')
    expected_path = safe_resolve(base_path, result_file.expected + ext)
    actual_path = safe_resolve(base_path, result_file.got + ext)

    if expected_path is None or actual_path is None:
        return make_error_response('forbidden', INVALID_PATH_MSG, http_status=403)

    if not os.path.isfile(expected_path):
        return make_error_response('not_found', 'Expected output file not found on disk.', http_status=404)
    if not os.path.isfile(actual_path):
        return make_error_response('not_found', 'Actual output file not found on disk.', http_status=404)

    max_diff_bytes = 10 * 1024 * 1024  # 10 MiB
    if os.path.getsize(expected_path) > max_diff_bytes or os.path.getsize(actual_path) > max_diff_bytes:
        return make_error_response('unprocessable', 'File too large for diff. Use download_url.', http_status=422)

    if format_type == 'unified':
        import difflib
        expected_lines = read_lines(expected_path)
        actual_lines = read_lines(actual_path)
        differ = list(difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile='expected',
            tofile='actual',
            lineterm=''
        ))
        if len(differ) > 10000:
            differ = differ[:10000]
            differ.append("\n... Diff truncated due to length ...")
        unified_content = '\n'.join(differ)
        return single_response({
            **diff_ids,
            'format': 'unified',
            'content': unified_content
        })

    context_lines = request.args.get('context_lines', 3, type=int)
    context_lines = max(1, min(context_lines, 50))

    diff_result = compute_diff(
        expected_path, actual_path, context_lines=context_lines)
    diff_result.update(diff_ids)
    diff_result['format'] = 'structured'
    return single_response(diff_result)


@mod_api.route('/runs/<run_id>/samples/<sample_id>/baseline-approval', methods=['POST'])
@require_roles([Role.admin])
@require_scope(Scope.BASELINES_WRITE)
@validate_path_id('run_id')
@validate_path_id('sample_id')
@validate_body(BaselineApprovalRequestSchema)
def create_baseline_approval(run_id, sample_id, validated_data=None):
    """
    Record intent to approve actual output as the new expected baseline.

    WARNING: When remove_variants is set to true, this action will remove all
    platform-specific variants, making this output the single source of truth
    across all platforms. Care should be taken as this applies globally.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    regression_id = validated_data['regression_id']
    output_id = validated_data['output_id']

    result_file = TestResultFile.query.filter_by(
        test_id=run_id,
        regression_test_id=regression_id,
        regression_test_output_id=output_id,
    ).first()

    if result_file is None:
        return make_error_response('not_found', 'Result file not found.', http_status=404)

    actual_sample_id = (
        result_file.regression_test.sample_id
        if result_file.regression_test else None
    )
    if actual_sample_id != sample_id:
        return make_error_response(
            'not_found',
            f'Regression test {regression_id} does not belong to sample {sample_id}.',
            http_status=404,
        )

    if is_dummy_row(result_file):
        return make_error_response('unprocessable', 'Cannot approve a dummy row.', http_status=422)

    if result_file.got is None:
        return make_error_response('unprocessable', 'Output already matches expected.', http_status=422)

    # The actual output file (named by its hash) is already in TestResults/.
    # We just need to update the RegressionTestOutput to point to this new hash.
    rto = result_file.regression_test_output
    if rto is None:
        return make_error_response('internal_error', 'No RegressionTestOutput linked.', http_status=500)

    new_baseline = result_file.got

    base_path = get_test_results_base_path()
    ext = rto.correct_extension or ''
    if ext:
        ext = ext.replace('/', '').replace('\\', '').replace('..', '')
    actual_filename = new_baseline + ext
    file_path = safe_resolve(base_path, actual_filename)
    if not file_path or not os.path.isfile(file_path):
        return make_error_response('unprocessable', 'Actual output file not found in storage.', http_status=422)

    old_baseline = rto.correct
    rto.correct = new_baseline

    remove_variants = validated_data.get('remove_variants', False)
    if remove_variants:
        RegressionTestOutputFiles.query.filter_by(
            regression_test_output_id=rto.id).delete()

    g.db.commit()

    # Audit log: this mutates the global expected baseline (and optionally
    # deletes all variants), so record who approved what.
    approver = getattr(g, 'api_user', None)
    current_app.logger.info(
        'Baseline approved by %s (user_id=%s): run=%s regression=%s '
        'output=%s old_hash=%s new_hash=%s remove_variants=%s',
        approver.name if approver else 'unknown',
        approver.id if approver else None,
        run_id, regression_id, output_id, old_baseline, new_baseline,
        remove_variants)

    import datetime
    return single_response({
        'status': 'approved',
        'run_id': run_id,
        'sample_id': sample_id,
        'regression_id': regression_id,
        'output_id': output_id,
        'requested_by': getattr(g, 'api_user').name if getattr(g, 'api_user', None) else 'unknown',
        'created_at': datetime.datetime.now(datetime.timezone.utc)
    }, schema=BaselineApprovalSchema())
