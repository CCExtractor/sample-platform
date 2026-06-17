"""
Status derivation from the raw data model.

Normalizes TestProgress/TestResult/TestResultFile states into clean
strings for the API layer. This is the single source of truth for
status logic — route handlers must not inline their own derivation.

Run statuses:   queued, running, pass, fail, canceled, error, incomplete
Sample statuses: pass, fail, skipped, missing_output, running, not_started

Things to watch out for:
    - test.failed only checks for TestStatus.canceled — never use it
      for determining whether regression tests actually passed
    - TestResultFile.got = null means MATCH, not missing output
    - Dummy row (-1,-1,-1,'','error') = test produced no output at all
    - TestStatus.canceled covers both user cancels and infra failures
"""

from typing import List, Optional

from mod_test.models import (Test, TestProgress, TestResult, TestResultFile,
                             TestStatus)


def derive_run_status(test: Test) -> str:
    """
    Map the raw model state to one of the 7 normalized run statuses.

    Looks at the most recent TestProgress row and, for completed runs,
    counts actual failures from TestResult rows.
    """
    statuses, _ = batch_get_run_data([test])
    return statuses.get(test.id, 'queued')


def _check_output_acceptable(rf: TestResultFile) -> bool:
    if rf.regression_test_output:
        for multi in rf.regression_test_output.multiple_files:
            if multi.file_hashes == rf.got:
                return True
    return False


def derive_sample_status(
    test_result: Optional[TestResult],
    result_files: List[TestResultFile],
) -> str:
    """
    Map a TestResult + its output files to a per-sample status string.

    Checks for the dummy sentinel row first (missing_output), then exit
    code, then output diffs against accepted baselines.
    """
    if test_result is None:
        return 'not_started'

    for rf in result_files:
        if is_dummy_row(rf):
            return 'missing_output'

    if test_result.exit_code != test_result.expected_rc:
        return 'fail'

    for rf in result_files:
        if rf.got is not None and not _check_output_acceptable(rf):
            return 'fail'

    # All got == null → every output matched expected.
    return 'pass'


def is_dummy_row(rf: TestResultFile) -> bool:
    """
    Detect the sentinel TestResultFile row where regression_test_output_id == -1 and got == 'error'.

    This row means the test produced no output when output was expected.
    The old test_id == -1 and regression_test_id == -1 checks were removed
    because they are no longer populated as -1 in newer data.
    It should never show up as a real file in API responses.

    DEPLOYMENT PREREQUISITE: Before deploying this change, verify that no
    old-format sentinel rows exist that would be missed by the new detection.
    Run against production:

        SELECT COUNT(*)
        FROM test_result_file
        WHERE (test_id = -1 OR regression_test_id = -1)
          AND NOT (regression_test_output_id = -1 AND got = 'error');

    If result > 0, those rows need a data migration to normalize them
    before this code is deployed. Include the query output in the PR
    description as evidence.
    """
    return bool(rf.regression_test_output_id == -1 and rf.got == 'error')


def derive_output_status(rf: TestResultFile) -> str:
    """Classify a single output file: pass, fail, or missing_output."""
    if is_dummy_row(rf):
        return 'missing_output'
    if rf.got is None:
        return 'pass'
    return 'fail'


def get_run_timestamps(test: Test) -> dict:
    """
    Build a timestamp dict from TestProgress rows.

    Test doesn't have a created_at column, so we use the earliest
    progress entry as a proxy.
    """
    _, timestamps = batch_get_run_data([test])
    ts = timestamps.get(test.id, {})
    return {
        'created_at': ts.get('created_at'),
        'queued_at': ts.get('queued_at'),
        'started_at': ts.get('started_at'),
        'completed_at': ts.get('completed_at'),
    }


def _compute_run_timestamps(t_prog):
    ts = {
        'created_at': None,
        'queued_at': None,
        'started_at': None,
        'completed_at': None,
    }
    if t_prog:
        ts['queued_at'] = t_prog[0].timestamp
        ts['created_at'] = t_prog[0].timestamp
        for p in t_prog:
            if p.status == TestStatus.testing and ts['started_at'] is None:
                ts['started_at'] = p.timestamp
            if p.status in (TestStatus.completed, TestStatus.canceled):
                ts['completed_at'] = p.timestamp
    return ts


def _compute_run_status(t_prog, results_by_test, files_by_test_and_rt, t_id):
    if not t_prog:
        return 'queued'

    latest = t_prog[-1]
    raw_status = latest.status

    if raw_status in (TestStatus.preparation, TestStatus.testing):
        return 'running'
    elif raw_status == TestStatus.canceled:
        return 'canceled'
    elif raw_status == TestStatus.completed:
        fail_count = 0
        for r in results_by_test.get(t_id, []):
            r_files = files_by_test_and_rt.get(
                (t_id, r.regression_test_id), [])
            sample_status = derive_sample_status(r, r_files)
            if sample_status not in ('pass', 'not_started'):
                fail_count += 1
        return 'fail' if fail_count > 0 else 'pass'
    else:
        return 'incomplete'


def batch_get_run_data(tests: list) -> tuple:
    """
    Batch compute derive_run_status and get_run_timestamps for a list of tests.

    Returns (statuses_dict, timestamps_dict)
    """
    if not tests:
        return {}, {}

    test_ids = [t.id for t in tests]

    # Preload TestProgress
    all_progress = TestProgress.query.filter(TestProgress.test_id.in_(
        test_ids)).order_by(TestProgress.id.asc()).all()
    progress_by_test = {tid: [] for tid in test_ids}
    for p in all_progress:
        progress_by_test[p.test_id].append(p)

    # Preload TestResult
    all_results = TestResult.query.filter(
        TestResult.test_id.in_(test_ids)).all()
    results_by_test = {tid: [] for tid in test_ids}
    for r in all_results:
        results_by_test[r.test_id].append(r)

    # Preload TestResultFile
    from sqlalchemy.orm import joinedload

    from mod_regression.models import RegressionTestOutput
    all_files = TestResultFile.query.options(
        joinedload(TestResultFile.regression_test_output)
        .joinedload(RegressionTestOutput.multiple_files)
    ).filter(TestResultFile.test_id.in_(test_ids)).all()
    files_by_test_and_rt = {}
    for f in all_files:
        key = (f.test_id, f.regression_test_id)
        if key not in files_by_test_and_rt:
            files_by_test_and_rt[key] = []
        files_by_test_and_rt[key].append(f)

    statuses = {}
    timestamps_dict = {}

    for t in tests:
        t_prog = progress_by_test[t.id]
        timestamps_dict[t.id] = _compute_run_timestamps(t_prog)
        statuses[t.id] = _compute_run_status(
            t_prog, results_by_test, files_by_test_and_rt, t.id)

    return statuses, timestamps_dict
