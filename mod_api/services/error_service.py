"""
Error derivation from TestResult and TestResultFile rows.

Walks result data and produces structured ErrorItem dicts. There's no
dedicated error table — errors are inferred from:
    exit_code_mismatch  → exit code != expected
    diff_mismatch       → got != null and not in multiple correct files
    missing_output      → dummy (-1,-1,-1,'','error') row present
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy.orm import joinedload

from mod_api.services.status import is_dummy_row
from mod_regression.models import RegressionTestOutput
from mod_test.models import (TestProgress, TestResult, TestResultFile,
                             TestStatus)

_SEVERITY_ORDER = ('info', 'warning', 'error', 'critical')


def _is_output_acceptable(rf: TestResultFile) -> bool:
    if not rf.regression_test_output:
        return False
    for multi in rf.regression_test_output.multiple_files:
        if multi.file_hashes == rf.got:
            return True
    return False


def _check_exit_code_errors(result, test_id, occurred_at):
    if result.exit_code != result.expected_rc:
        return [{
            'error_id': f'err_{test_id}_{result.regression_test_id}_rc',
            'run_id': test_id,
            'sample_id': _get_sample_id(result),
            'regression_id': result.regression_test_id,
            'type': 'exit_code_mismatch',
            'severity': 'error',
            'message': (
                f'Exit code {result.exit_code} != expected {result.expected_rc} '
                f'for regression test {result.regression_test_id}'
            ),
            'occurred_at': occurred_at,
        }]
    return []


def _check_missing_output_errors(result, result_files, test_id, occurred_at, expected_outputs):
    errors = []
    actual_output_ids = {rf.regression_test_output_id for rf in result_files}
    if expected_outputs is not None:
        for rto in expected_outputs:
            if not rto.ignore and rto.id not in actual_output_ids:
                errors.append({
                    'error_id': f'err_{test_id}_{result.regression_test_id}_missing_{rto.id}',
                    'run_id': test_id,
                    'sample_id': _get_sample_id(result),
                    'regression_id': result.regression_test_id,
                    'type': 'missing_output',
                    'severity': 'error',
                    'message': (
                        f'Regression test {result.regression_test_id} '
                        f'produced no output for expected file {rto.id}'
                    ),
                    'occurred_at': occurred_at,
                })
    else:
        for rf in result_files:
            if is_dummy_row(rf):
                errors.append({
                    'error_id': f'err_{test_id}_{result.regression_test_id}_missing',
                    'run_id': test_id,
                    'sample_id': _get_sample_id(result),
                    'regression_id': result.regression_test_id,
                    'type': 'missing_output',
                    'severity': 'error',
                    'message': (
                        f'Regression test {result.regression_test_id} '
                        f'produced no output when output was expected'
                    ),
                    'occurred_at': occurred_at,
                })
    return errors


def _check_diff_mismatch_errors(result, result_files, test_id, occurred_at):
    errors = []
    for rf in result_files:
        if is_dummy_row(rf):
            continue
        if rf.got is not None and not _is_output_acceptable(rf):
            errors.append({
                'error_id': f'err_{test_id}_{result.regression_test_id}_{rf.regression_test_output_id}',
                'run_id': test_id,
                'sample_id': _get_sample_id(result),
                'regression_id': result.regression_test_id,
                'type': 'diff_mismatch',
                'severity': 'warning',
                'message': (
                    f'Output differs from expected for regression test '
                    f'{result.regression_test_id}, output {rf.regression_test_output_id}'
                ),
                'occurred_at': occurred_at,
            })
    return errors


def _evaluate_test_result(
        result,
        result_files,
        test_id,
        occurred_at,
        expected_outputs=None):
    errors = []
    errors.extend(_check_exit_code_errors(result, test_id, occurred_at))
    errors.extend(_check_missing_output_errors(result, result_files, test_id, occurred_at, expected_outputs))
    errors.extend(_check_diff_mismatch_errors(result, result_files, test_id, occurred_at))
    return errors


def _group_result_files(test_id, results, preloaded_files=None):
    """Map regression_test_id -> [TestResultFile], loading if not preloaded."""
    if preloaded_files is not None:
        all_files = preloaded_files
    elif results:
        all_files = TestResultFile.query.options(
            joinedload(TestResultFile.regression_test_output)
            .joinedload(RegressionTestOutput.multiple_files)
        ).filter_by(test_id=test_id).all()
    else:
        all_files = []
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[f.regression_test_id].append(f)
    return files_by_result


def _load_expected_outputs(results):
    """Map regression_test_id -> [RegressionTestOutput] for the given results.

    Missing-output detection must use the same RegressionTestOutput
    comparison as /runs/{id}/summary — /errors and /summary have to agree.
    id > 0 excludes the -1 sentinel some fixtures create to satisfy the
    dummy TestResultFile row's foreign key; it is not a real expectation.
    """
    if not results:
        return {}
    rt_ids = {r.regression_test_id for r in results}
    expected_by_rt = defaultdict(list)
    for rto in RegressionTestOutput.query.filter(
            RegressionTestOutput.regression_id.in_(rt_ids),
            RegressionTestOutput.id > 0).all():
        expected_by_rt[rto.regression_id].append(rto)
    return expected_by_rt


def derive_errors_for_run(test_id: int,
                          expected_outputs_by_rt: Dict[int,
                                                       List[Any]] = None,
                          preloaded_results=None,
                          preloaded_files=None) -> List[Dict[str,
                                                             Any]]:
    """Walk result rows and emit one ErrorItem per detected failure."""
    progress = TestProgress.query.filter_by(test_id=test_id).order_by(
        TestProgress.timestamp.desc()).first()
    occurred_at = progress.timestamp.isoformat(
    ) if progress and progress.timestamp else None

    if preloaded_results is not None:
        results = preloaded_results
    else:
        results = TestResult.query.filter_by(test_id=test_id).all()

    files_by_result = _group_result_files(test_id, results, preloaded_files)

    if expected_outputs_by_rt is None:
        expected_outputs_by_rt = _load_expected_outputs(results)

    errors = []
    for result in results:
        result_files = files_by_result.get(result.regression_test_id, [])
        expected_outputs = expected_outputs_by_rt.get(
            result.regression_test_id) if expected_outputs_by_rt else None
        errors.extend(_evaluate_test_result(
            result, result_files, test_id, occurred_at, expected_outputs))

    return errors


def _aggregate_error_into_bucket(err, bucket):
    bucket['count'] += 1

    # Escalate severity to the worst we've seen.
    try:
        curr_idx = _SEVERITY_ORDER.index(bucket['severity'])
        new_idx = _SEVERITY_ORDER.index(err['severity'])
        if new_idx > curr_idx:
            bucket['severity'] = err['severity']
    except ValueError:
        # Fallback if unknown severity
        if err['severity'] == 'error':
            bucket['severity'] = 'error'

    err_time = err.get('occurred_at')
    if err_time:
        if bucket['first_seen_at'] is None or err_time < bucket['first_seen_at']:
            bucket['first_seen_at'] = err_time
        if bucket['last_seen_at'] is None or err_time > bucket['last_seen_at']:
            bucket['last_seen_at'] = err_time

    sid = err.get('sample_id')
    if sid and sid not in bucket['sample_ids'] and len(
            bucket['sample_ids']) < 1000:
        bucket['sample_ids'].append(sid)


def derive_error_summary(
        test_id: int, group_by: str = 'type') -> List[Dict[str, Any]]:
    """Group errors by the given key and return bucket counts."""
    errors = derive_errors_for_run(test_id)
    buckets: Dict[str, Dict[str, Any]] = {}

    for err in errors:
        key = str(err.get(group_by, 'unknown'))

        if key not in buckets:
            buckets[key] = {
                'key': key,
                'group_by': group_by,
                'count': 0,
                'severity': err['severity'],
                'sample_ids': [],
                'first_seen_at': None,
                'last_seen_at': None,
            }

        _aggregate_error_into_bucket(err, buckets[key])

    return list(buckets.values())


def derive_infrastructure_errors(test_id: int) -> List[Dict[str, Any]]:
    """
    Best-effort infra error extraction from TestProgress messages.

    There's no structured error protocol from the CI worker yet, so we
    do keyword matching against progress messages to guess the failure type.
    """
    errors = []
    progress_rows = TestProgress.query.filter_by(
        test_id=test_id,
        status=TestStatus.canceled,
    ).all()

    for p in progress_rows:
        message = p.message or ''
        # User-initiated cancellations (cancel_run writes "... via API") are not
        # infrastructure failures, so they must not be reported here.
        if 'via API' in message:
            continue
        error_type = _classify_infra_error(message.lower())
        errors.append({
            'error_id': f'infra_{test_id}_{p.id}',
            'run_id': test_id,
            'sample_id': None,
            'regression_id': None,
            'type': error_type,
            'severity': 'critical',
            'message': p.message or 'Unknown infrastructure error',
            'location': None,
            'occurred_at': p.timestamp.isoformat() if p.timestamp else None,
        })

    return errors


def _classify_infra_error(message_lower: str) -> str:
    """Guess the infra error type from progress message keywords."""
    if any(w in message_lower for w in ['provisioning', 'vm ', 'instance']):
        return 'vm_provisioning'
    if any(w in message_lower for w in ['checkout', 'git clone', 'fetch']):
        return 'checkout'
    if any(w in message_lower for w in ['merge', 'conflict']):
        return 'merge'
    if any(w in message_lower for w in ['build', 'compile', 'make']):
        return 'build'
    if any(w in message_lower for w in ['worker', 'timeout', 'connection']):
        return 'worker'
    if any(w in message_lower for w in ['storage', 'disk', 'gcs']):
        return 'storage'
    return 'worker'


def _get_sample_id(result: TestResult):
    """Pull sample_id through the RegressionTest relationship, if available."""
    try:
        if result.regression_test and result.regression_test.sample_id:
            return result.regression_test.sample_id
    except Exception:
        logging.getLogger(__name__).exception(
            f"Failed to fetch sample_id for TestResult {result.test_id}_{result.regression_test_id}"
        )
    return None
