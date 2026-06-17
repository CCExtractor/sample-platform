"""
Sample and regression test routes.

GET /runs/{id}/samples              Per-run regression test results
GET /runs/{id}/samples/{sid}        Single result in a run
GET /samples                        Media sample catalog
GET /samples/{id}                   Single media sample
GET /samples/{id}/history           Cross-run history for a sample
GET /regression-tests               Regression test definitions
"""

from flask import request

from mod_api import mod_api
from mod_api.middleware.auth import require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_date_range,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.services.status import (derive_output_status,
                                     derive_sample_status, get_run_timestamps,
                                     is_dummy_row)
from mod_api.utils import paginated_response, single_response
from mod_regression.models import Category, RegressionTest
from mod_sample.models import Sample
from mod_test.models import Test, TestResult, TestResultFile


def _serialize_outputs(result_files):
    outputs = []
    for rf in result_files:
        if is_dummy_row(rf):
            continue
        outputs.append({
            'output_id': rf.regression_test_output_id,
            'filename': (
                rf.regression_test_output.create_correct_filename(rf.expected)
                if rf.regression_test_output else rf.expected
            ),
            'status': derive_output_status(rf),
        })
    return outputs


def _serialize_run_sample(result, result_files):
    """Build the per-regression-test result dict for a run."""
    status = derive_sample_status(result, result_files)
    outputs = _serialize_outputs(result_files)

    sample_name = None
    sample_id = None
    command = None
    categories = []

    if result.regression_test:
        rt = result.regression_test
        command = rt.command
        if rt.sample:
            sample_id = rt.sample_id
            sample_name = rt.sample.original_name
        if rt.categories:
            categories = [c.name for c in rt.categories]

    return {
        'regression_test_id': result.regression_test_id,
        'sample_id': sample_id,
        'sample_name': sample_name,
        'status': status,
        'exit_code': result.exit_code,
        'expected_rc': result.expected_rc,
        'runtime_ms': result.runtime,
        'command': command,
        'categories': categories,
        'outputs': outputs,
    }


def _filter_run_samples_by_tag(serialized, tag_filter):
    tag_lower = tag_filter.lower()
    tagged_sample_ids = set()

    valid_sample_ids = [s['sample_id']
                        for s in serialized if s.get('sample_id')]
    samples = Sample.query.filter(Sample.id.in_(
        valid_sample_ids)).all() if valid_sample_ids else []
    sample_map = {sample.id: sample for sample in samples}

    for s in serialized:
        if s['sample_id']:
            sample = sample_map.get(s['sample_id'])
            if sample and any(tag_lower == t.name.lower() for t in sample.tags):
                tagged_sample_ids.add(s['sample_id'])
    return [s for s in serialized if s.get('sample_id') in tagged_sample_ids]


def _apply_run_sample_filters(serialized, args):
    status_filter = args.get('status')
    if status_filter:
        serialized = [s for s in serialized if s['status'] == status_filter]

    name_filter = args.get('name')
    if name_filter:
        name_lower = name_filter.lower()
        serialized = [s for s in serialized if s.get(
            'sample_name') and name_lower in s['sample_name'].lower()]

    tag_filter = args.get('tag')
    if tag_filter:
        serialized = _filter_run_samples_by_tag(serialized, tag_filter)

    category_filter = args.get('category')
    if category_filter:
        cat_lower = category_filter.lower()
        serialized = [
            s for s in serialized
            if s.get('categories') and cat_lower in [c.lower() for c in s['categories']]
        ]
    return serialized


@mod_api.route('/runs/<run_id>/samples', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('run_id')
@validate_offset_pagination()
def list_run_samples(run_id, limit=50, offset=0):
    """
    List per-sample results for a run, with optional filters.

    Supports ?status, ?name, ?tag, ?category query params.
    """
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    results = TestResult.query.filter_by(test_id=run_id).all()

    # Preload TestResultFiles
    from collections import defaultdict
    all_files = TestResultFile.query.filter_by(
        test_id=run_id).all() if results else []
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[f.regression_test_id].append(f)

    # Serialize list to filter by derived status and joined fields
    serialized = []
    for result in results:
        result_files = files_by_result.get(result.regression_test_id, [])
        serialized.append(_serialize_run_sample(result, result_files))

    # Apply query param filters.
    serialized = _apply_run_sample_filters(serialized, request.args)

    total = len(serialized)
    paged = serialized[offset:offset + limit]
    return paginated_response(paged, total, limit, offset)


@mod_api.route('/runs/<run_id>/samples/<regression_test_id>', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('run_id')
@validate_path_id('regression_test_id')
def get_run_sample(run_id, regression_test_id):
    """Get a single regression test result within a run."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response('not_found', f'Run {run_id} not found.', http_status=404)

    result = TestResult.query.filter_by(
        test_id=run_id,
        regression_test_id=regression_test_id,
    ).first()
    if result is None:
        return make_error_response(
            'not_found',
            f'Regression test {regression_test_id} not found in run {run_id}.',
            http_status=404,
        )

    result_files = TestResultFile.query.filter_by(
        test_id=run_id,
        regression_test_id=regression_test_id,
    ).all()

    return single_response(_serialize_run_sample(result, result_files))


@mod_api.route('/samples', methods=['GET'])
@require_scope('runs:read')
@validate_offset_pagination()
def list_samples(limit=50, offset=0):
    """
    List media samples from the catalog.

    Supports ?name, ?extension, ?tag, ?sha256, ?status (active/inactive) filters.
    """
    query = Sample.query

    name = request.args.get('name')
    if name:
        # Escape LIKE wildcards to prevent unintended pattern matching.
        safe_name = name.replace('%', '\\%').replace('_', '\\_')
        query = query.filter(Sample.original_name.ilike(f'%{safe_name}%'))

    extension = request.args.get('extension')
    if extension:
        query = query.filter(Sample.extension == extension)

    sha256_filter = request.args.get('sha256')
    if sha256_filter:
        query = query.filter(Sample.sha == sha256_filter)

    tag_filter = request.args.get('tag')
    if tag_filter:
        from sqlalchemy import func

        from mod_sample.models import Tag
        query = query.filter(Sample.tags.any(
            func.lower(Tag.name) == tag_filter.lower()))

    status_filter = request.args.get('status')
    if status_filter:
        want_active = status_filter.lower() == 'active'
        if want_active:
            query = query.filter(Sample.tests.any(RegressionTest.active == True))  # noqa: E712
        else:
            query = query.filter(~Sample.tests.any(RegressionTest.active == True))  # noqa: E712

    # Paginate at DB level without Python-side filters
    total = query.count()
    samples = query.offset(offset).limit(limit).all()

    # Batch load active regression test counts
    from flask import g
    from sqlalchemy import func
    sample_ids = [s.id for s in samples]
    counts_list = g.db.query(
        RegressionTest.sample_id,
        func.count(RegressionTest.id)
    ).filter(
        RegressionTest.sample_id.in_(sample_ids),
        RegressionTest.active == True  # noqa: E712
    ).group_by(RegressionTest.sample_id).all() if sample_ids else []
    counts = dict(counts_list)

    serialized = []
    for s in samples:
        active_count = counts.get(s.id, 0)
        serialized.append({
            'sample_id': s.id,
            'sha': s.sha,
            'extension': s.extension,
            'original_name': s.original_name,
            'filename': s.filename,
            'tags': [t.name for t in s.tags],
            'regression_test_count': active_count,
            'active': active_count > 0,
        })

    return paginated_response(serialized, total, limit, offset)


@mod_api.route('/samples/<sample_id>', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('sample_id')
def get_sample(sample_id):
    """Get a single media sample by its ID."""
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is None:
        return make_error_response('not_found', f'Sample {sample_id} not found.', http_status=404)

    active_count = RegressionTest.query.filter_by(
        sample_id=sample.id, active=True
    ).count()

    return single_response({
        'sample_id': sample.id,
        'sha': sample.sha,
        'extension': sample.extension,
        'original_name': sample.original_name,
        'filename': sample.filename,
        'tags': [t.name for t in sample.tags],
        'regression_test_count': active_count,
        'active': active_count > 0,
    })


def _get_history_failure_signature(result, result_files, status):
    if status == 'fail':
        for rf in result_files:
            if rf.got is not None and not is_dummy_row(rf):
                return f'diff_mismatch:output:{rf.regression_test_output_id}'
        if result.exit_code != result.expected_rc:
            return f'exit_code_mismatch:rc:{result.exit_code}'
    elif status == 'missing_output':
        return 'missing_output'
    return None


def _process_history_entries(results, files_by_result, status_filter):
    entries = []
    for result in results:
        test = result.test
        if test is None:
            test = Test.query.get(result.test_id)
            if test is None:
                continue

        result_files = files_by_result.get(
            (result.test_id, result.regression_test_id), [])
        status = derive_sample_status(result, result_files)

        if status_filter and status != status_filter:
            continue

        failure_sig = _get_history_failure_signature(
            result, result_files, status)
        timestamps = get_run_timestamps(test)

        entries.append({
            'run_id': test.id,
            'regression_test_id': result.regression_test_id,
            'status': status,
            'platform': test.platform.value,
            'branch': test.branch,
            'commit_sha': test.commit,
            'tested_at': timestamps.get('completed_at') or timestamps.get('started_at'),
            'failure_signature': failure_sig,
        })
    return entries


def _apply_history_filters(query, branch, platform, created_after, created_before):
    if branch:
        query = query.filter(Test.branch == branch)

    if platform:
        try:
            from mod_test.models import TestPlatform
            platform_enum = TestPlatform.from_string(platform)
            query = query.filter(Test.platform == platform_enum)
        except Exception:
            from mod_test.models import TestPlatform
            valid_platforms = ', '.join(TestPlatform.values())
            return None, make_error_response(
                'validation_error',
                f'Invalid platform: {platform}. Must be one of: {valid_platforms}.',
                http_status=400,
            )

    if created_after or created_before:
        from flask import g
        from sqlalchemy import func

        from mod_test.models import TestProgress
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


@mod_api.route('/samples/<sample_id>/history', methods=['GET'])
@require_scope('runs:read')
@validate_path_id('sample_id')
@validate_offset_pagination()
@validate_date_range
def get_sample_history(sample_id, limit=50, offset=0, created_after=None, created_before=None):
    """
    Show how a sample performed across different runs.

    Use failure_signature to tell apart genuine regressions from infra flakes.
    """
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is None:
        return make_error_response('not_found', f'Sample {sample_id} not found.', http_status=404)

    regression_tests = RegressionTest.query.filter_by(
        sample_id=sample_id).all()
    rt_ids = [rt.id for rt in regression_tests]

    if not rt_ids:
        return paginated_response([], 0, limit, offset)

    query = TestResult.query.filter(
        TestResult.regression_test_id.in_(rt_ids)
    ).join(Test, Test.id == TestResult.test_id)

    branch = request.args.get('branch')
    platform = request.args.get('platform')

    query, err = _apply_history_filters(
        query, branch, platform, created_after, created_before)
    if err:
        return err

    results = query.order_by(Test.id.desc()).all()

    status_filter = request.args.get('status')

    # Preload TestResultFiles
    from collections import defaultdict
    test_ids = list({r.test_id for r in results})
    all_files = TestResultFile.query.filter(
        TestResultFile.test_id.in_(test_ids)).all() if test_ids else []
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[(f.test_id, f.regression_test_id)].append(f)

    entries = _process_history_entries(results, files_by_result, status_filter)

    total = len(entries)
    paged = entries[offset:offset + limit]

    from mod_api.schemas.samples import SampleHistoryEntrySchema
    return paginated_response(paged, total, limit, offset, schema=SampleHistoryEntrySchema())


def _serialize_rt(rt):
    return {
        'regression_test_id': rt.id,
        'sample_id': rt.sample_id,
        'sample_name': rt.sample.original_name if rt.sample else None,
        'command': rt.command,
        'input_type': rt.input_type.value,
        'output_type': rt.output_type.value,
        'expected_rc': rt.expected_rc,
        'active': rt.active,
        'categories': [c.name for c in rt.categories],
        'description': rt.description,
    }


def _filter_regression_tests_by_tag(query, tag_filter):
    all_tests = query.all()
    serialized = []
    for rt in all_tests:
        if rt.sample:
            sample_tags = [t.name.lower() for t in rt.sample.tags]
            if tag_filter.lower() not in sample_tags:
                continue
        else:
            continue  # no sample = no tags to match
        serialized.append(_serialize_rt(rt))
    return serialized


@mod_api.route('/regression-tests', methods=['GET'])
@require_scope('runs:read')
@validate_offset_pagination()
def list_regression_tests(limit=50, offset=0):
    """
    List regression test definitions.

    Supports ?active, ?category, ?tag, ?sample_id filters.
    """
    query = RegressionTest.query

    active_filter = request.args.get('active')
    if active_filter is not None:
        is_active = active_filter.lower() in ('true', '1', 'yes')
    else:
        is_active = True
    query = query.filter(RegressionTest.active == is_active)

    category = request.args.get('category')
    if category:
        query = query.join(RegressionTest.categories).filter(
            Category.name == category)

    sample_id_filter = request.args.get('sample_id')
    if sample_id_filter:
        try:
            sid = int(sample_id_filter)
            if sid < 1 or sid > 2147483647:
                raise ValueError("Out of bounds")
            query = query.filter(RegressionTest.sample_id == sid)
        except (ValueError, TypeError):
            return make_error_response(
                'validation_error',
                'sample_id must be a positive integer between 1 and 2147483647.',
                details={'fields': {
                    'sample_id': 'Must be a positive integer between 1 and 2147483647.'}},
                http_status=400,
            )

    tag_filter = request.args.get('tag')

    # Filter tags in Python before paginating
    if tag_filter:
        serialized = _filter_regression_tests_by_tag(query, tag_filter)

        total = len(serialized)
        paged = serialized[offset:offset + limit]
        return paginated_response(paged, total, limit, offset)

    # Paginate at DB level without tag filters
    total = query.count()
    tests = query.offset(offset).limit(limit).all()
    serialized = [_serialize_rt(rt) for rt in tests]
    return paginated_response(serialized, total, limit, offset)
