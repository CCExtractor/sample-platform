"""
Error derivation from TestResult and TestResultFile rows.

Walks result data and produces structured ErrorItem dicts. There's no
dedicated error table — errors are inferred from:
    exit_code_mismatch  → exit code != expected
    diff_mismatch       → got != null and not in multiple correct files
    missing_output      → dummy (-1,-1,-1,'','error') row present
"""

import logging
from typing import Any, Dict, List

from mod_api.services.status import is_dummy_row
from mod_test.models import TestResult, TestResultFile

_SEVERITY_ORDER = ('info', 'warning', 'error', 'critical')


def _is_output_acceptable(rf: TestResultFile) -> bool:
    if not rf.regression_test_output:
        return False
    for multi in rf.regression_test_output.multiple_files:
        if multi.file_hashes == rf.got:
            return True
    return False


def _evaluate_test_result(result, result_files, test_id, occurred_at):
    errors = []
    if result.exit_code != result.expected_rc:
        errors.append({
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
        })

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
        elif rf.got is not None and not _is_output_acceptable(rf):
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


def derive_errors_for_run(test_id: int) -> List[Dict[str, Any]]:
    """Walk result rows and emit one ErrorItem per detected failure."""
    from mod_test.models import TestProgress
    progress = TestProgress.query.filter_by(test_id=test_id).order_by(
        TestProgress.timestamp.desc()).first()
    occurred_at = progress.timestamp.isoformat(
    ) if progress and progress.timestamp else None

    errors = []
    results = TestResult.query.filter_by(test_id=test_id).all()

    # Preload TestResultFiles
    from collections import defaultdict

    from sqlalchemy.orm import joinedload

    from mod_regression.models import RegressionTestOutput
    all_files = (
        TestResultFile.query.options(
            joinedload(TestResultFile.regression_test_output)
            .joinedload(RegressionTestOutput.multiple_files)
        )
        .filter_by(test_id=test_id).all() if results else []
    )
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[f.regression_test_id].append(f)

    for result in results:
        result_files = files_by_result.get(result.regression_test_id, [])
        errors.extend(_evaluate_test_result(
            result, result_files, test_id, occurred_at))

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
    if sid and sid not in bucket['sample_ids'] and len(bucket['sample_ids']) < 1000:
        bucket['sample_ids'].append(sid)


def derive_error_summary(test_id: int, group_by: str = 'type') -> List[Dict[str, Any]]:
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
    from mod_test.models import TestProgress, TestStatus

    errors = []
    progress_rows = TestProgress.query.filter_by(
        test_id=test_id,
        status=TestStatus.canceled,
    ).all()

    for p in progress_rows:
        msg_lower = (p.message or '').lower()
        error_type = _classify_infra_error(msg_lower)
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
