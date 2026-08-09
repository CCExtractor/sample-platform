"""
Sample and regression test routes.

GET /runs/{id}/samples              Per-run regression test results
GET /runs/{id}/samples/{sid}        Single result in a run
GET /samples                        Media sample catalog
GET /samples/{id}                   Single media sample
GET /samples/{id}/details           Upload metadata, extra files, media info
GET /samples/{id}/history           Cross-run history for a sample
GET /regression-tests               Regression test definitions
"""

from collections import defaultdict

from flask import g, request
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from mod_api import mod_api
from mod_api.middleware.auth import require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_date_range,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.models.api_token import Scope
from mod_api.schemas.samples import SampleHistoryEntrySchema
from mod_api.services.status import (batch_get_run_data, derive_output_status,
                                     derive_sample_status, get_run_timestamps,
                                     is_dummy_row)
from mod_api.utils import paginated_response, single_response
from mod_regression.models import (Category, RegressionTest,
                                   RegressionTestOutput)
from mod_sample.media_info_parser import (InvalidMediaInfoError,
                                          MediaInfoFetcher)
from mod_sample.models import ExtraFile, Sample, Tag
from mod_test.models import (Test, TestPlatform, TestProgress, TestResult,
                             TestResultFile)
from mod_upload.models import Upload

# Valid per-sample status values accepted by the ?status filter. Limited to the
# statuses derive_sample_status can actually emit, so filtering can't silently
# return empty for a value that never occurs.
_VALID_SAMPLE_STATUSES = frozenset({
    'pass', 'fail', 'missing_output', 'not_started',
})

# How many result rows /samples/{id}/history will scan when ?status is set.
# Status comes from derive_sample_status, which needs the result files and
# expected outputs, so it can't be pushed into SQL the way branch/platform
# can. Without a bound the endpoint has to load a sample's entire history to
# filter it, which is what made it time out on production. Bounded scans are
# reported with pagination.truncated so a caller can tell a capped page from
# a complete one.
_HISTORY_STATUS_SCAN_LIMIT = 1000


def _preload_expected_outputs(results):
    """Map regression_test_id -> [RegressionTestOutput] for the given results.

    Lets per-sample status derivation use the same missing-output detection
    as /runs/{id}/summary, so the two endpoints can't disagree.
    """
    rt_ids = {r.regression_test_id for r in results}
    expected_by_rt = defaultdict(list)
    if rt_ids:
        for rto in RegressionTestOutput.query.filter(
                RegressionTestOutput.regression_id.in_(rt_ids)).all():
            expected_by_rt[rto.regression_id].append(rto)
    return expected_by_rt


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


def _serialize_run_sample(result, result_files, expected_outputs=None):
    """Build the per-regression-test result dict for a run."""
    status = derive_sample_status(result, result_files, expected_outputs)
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
    samples = Sample.query.options(joinedload(Sample.tags)).filter(
        Sample.id.in_(valid_sample_ids)).all() if valid_sample_ids else []
    sample_map = {sample.id: sample for sample in samples}

    for s in serialized:
        if s['sample_id']:
            sample = sample_map.get(s['sample_id'])
            if sample and any(tag_lower == t.name.lower()
                              for t in sample.tags):
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
            if s.get('categories') and cat_lower in [
                c.lower() for c in s['categories']
            ]
        ]
    return serialized


@mod_api.route('/runs/<run_id>/samples', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('run_id')
@validate_offset_pagination()
def list_run_samples(run_id, limit=50, offset=0):
    """
    List per-sample results for a run, with optional filters.

    Supports ?status, ?name, ?tag, ?category query params.
    """
    # Validate the status filter up front, before any DB work.
    status_filter = request.args.get('status')
    if status_filter and status_filter not in _VALID_SAMPLE_STATUSES:
        return make_error_response(
            'validation_error',
            f"Invalid status: {status_filter}",
            http_status=400
        )

    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    results = TestResult.query.options(
        joinedload(TestResult.regression_test)
        .joinedload(RegressionTest.sample),
        joinedload(TestResult.regression_test)
        .selectinload(RegressionTest.categories),
    ).filter_by(test_id=run_id).all()

    # Preload TestResultFiles together with the expected-output rows that
    # derive_sample_status compares against.
    all_files = TestResultFile.query.options(
        joinedload(TestResultFile.regression_test_output)
        .joinedload(RegressionTestOutput.multiple_files)
    ).filter_by(test_id=run_id).all() if results else []
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[f.regression_test_id].append(f)

    # Preload expected outputs so per-sample status matches /summary.
    expected_by_rt = _preload_expected_outputs(results)

    # Serialize list to filter by derived status and joined fields
    serialized = []
    for result in results:
        result_files = files_by_result.get(result.regression_test_id, [])
        serialized.append(_serialize_run_sample(
            result, result_files,
            expected_by_rt.get(result.regression_test_id)))

    # Apply query param filters.
    serialized = _apply_run_sample_filters(serialized, request.args)

    total = len(serialized)
    paged = serialized[offset:offset + limit]
    return paginated_response(paged, total, limit, offset)


@mod_api.route('/runs/<run_id>/samples/<regression_test_id>', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('run_id')
@validate_path_id('regression_test_id')
def get_run_sample(run_id, regression_test_id):
    """Get a single regression test result within a run."""
    test = Test.query.filter(Test.id == run_id).first()
    if test is None:
        return make_error_response(
            'not_found',
            f'Run {run_id} not found.',
            http_status=404)

    result = TestResult.query.options(
        joinedload(TestResult.regression_test)
        .joinedload(RegressionTest.sample),
        joinedload(TestResult.regression_test)
        .selectinload(RegressionTest.categories),
    ).filter_by(
        test_id=run_id,
        regression_test_id=regression_test_id,
    ).first()
    if result is None:
        return make_error_response(
            'not_found',
            f'Regression test {regression_test_id} not found in run {run_id}.',
            http_status=404,
        )

    result_files = TestResultFile.query.options(
        joinedload(TestResultFile.regression_test_output)
        .joinedload(RegressionTestOutput.multiple_files)
    ).filter_by(
        test_id=run_id,
        regression_test_id=regression_test_id,
    ).all()

    expected_by_rt = _preload_expected_outputs([result])
    return single_response(_serialize_run_sample(
        result, result_files, expected_by_rt.get(result.regression_test_id)))


@mod_api.route('/samples', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_offset_pagination()
def list_samples(limit=50, offset=0):
    """
    List media samples from the catalog.

    Supports ?name, ?extension, ?tag, ?sha256,
    ?status (active/inactive) filters.
    """
    query = Sample.query.options(joinedload(Sample.tags))

    name = request.args.get('name')
    if name:
        # Escape LIKE wildcards to prevent unintended pattern matching.
        # The explicit escape char makes the backslash escaping portable
        # rather than relying on the backend's default.
        safe_name = name.replace('\\', '\\\\').replace(
            '%', '\\%').replace('_', '\\_')
        query = query.filter(
            Sample.original_name.ilike(f'%{safe_name}%', escape='\\'))

    extension = request.args.get('extension')
    if extension:
        query = query.filter(Sample.extension == extension)

    sha256_filter = request.args.get('sha256')
    if sha256_filter:
        query = query.filter(Sample.sha == sha256_filter)

    tag_filter = request.args.get('tag')
    if tag_filter:

        query = query.filter(Sample.tags.any(
            func.lower(Tag.name) == tag_filter.lower()))

    status_filter = request.args.get('status')
    if status_filter:
        if status_filter.lower() not in ('active', 'inactive'):
            return make_error_response(
                'validation_error',
                'Invalid status: {status_filter}. '
                'Must be active or inactive.'.format(
                    status_filter=status_filter),
                http_status=400)
        want_active = status_filter.lower() == 'active'
        if want_active:
            query = query.filter(
                Sample.tests.any(RegressionTest.active == True)  # noqa: E712
            )  # tests refers to RegressionTest
        else:
            query = query.filter(
                ~Sample.tests.any(RegressionTest.active == True)  # noqa: E712
            )  # tests refers to RegressionTest

    # Paginate at DB level without Python-side filters
    total = query.count()
    samples = query.offset(offset).limit(limit).all()

    # Batch load active regression test counts
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


@mod_api.route('/samples/<sample_id>/details', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('sample_id')
def get_sample_details(sample_id):
    """
    Everything known about one sample, for a detail view.

    Extends the /samples/{id} summary with the upload record, any extra
    files, and the parsed MediaInfo tree. Media info is best-effort: missing
    or unparseable XML reports ``null`` rather than failing the response.
    Unlike the classic page this never regenerates the XML, because a GET
    should not write to the sample repository.
    """
    sample = Sample.query.options(joinedload(Sample.tags)).filter(
        Sample.id == sample_id).first()
    if sample is None:
        return make_error_response(
            'not_found', f'Sample {sample_id} not found.', http_status=404)

    upload = Upload.query.filter(Upload.sample_id == sample.id).first()
    upload_info = None
    if upload is not None:
        version = upload.version
        upload_info = {
            'platform': upload.platform.value if upload.platform else None,
            'parameters': upload.parameters or '',
            'notes': upload.notes or '',
            'version': version.version if version else None,
            'version_released': (
                version.released.isoformat()
                if version and version.released else None),
        }

    extra_files = [
        {
            'id': extra.id,
            'original_name': extra.original_name,
            'extension': extra.extension,
        }
        for extra in ExtraFile.query.filter(
            ExtraFile.sample_id == sample.id).all()
    ]

    try:
        media_info = MediaInfoFetcher(sample).get_media_info()
    except InvalidMediaInfoError:
        media_info = None

    return single_response({
        'sample_id': sample.id,
        'sha': sample.sha,
        'extension': sample.extension,
        'original_name': sample.original_name,
        'filename': sample.filename,
        'tags': [tag.name for tag in sample.tags],
        'upload': upload_info,
        'extra_files': extra_files,
        'media_info': media_info,
    })


@mod_api.route('/samples/<sample_id>', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('sample_id')
def get_sample(sample_id):
    """Get a single media sample by its ID."""
    sample = Sample.query.options(joinedload(Sample.tags)).filter(
        Sample.id == sample_id).first()
    if sample is None:
        return make_error_response(
            'not_found',
            f'Sample {sample_id} not found.',
            http_status=404)

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


def _process_history_entries(
        results,
        files_by_result,
        status_filter,
        timestamps_map=None,
        test_map=None,
        expected_by_rt=None):
    entries = []
    for result in results:
        test = test_map.get(result.test_id) if test_map else result.test
        if test is None:
            continue

        result_files = files_by_result.get(
            (result.test_id, result.regression_test_id), [])
        expected = expected_by_rt.get(
            result.regression_test_id) if expected_by_rt else None
        status = derive_sample_status(result, result_files, expected)

        if status_filter and status != status_filter:
            continue

        failure_sig = _get_history_failure_signature(
            result, result_files, status)
        if timestamps_map is not None and test.id in timestamps_map:
            timestamps = timestamps_map[test.id]
        else:
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


def _build_history_entries(results, status_filter):
    """Build history entries for exactly ``results``, batching the lookups.

    Every follow-up query here is keyed off the results handed in, so the
    work scales with that list. Callers must therefore pass the page they
    intend to return, not the sample's whole history.
    """
    if not results:
        return []

    test_ids = list({r.test_id for r in results})

    all_files = TestResultFile.query.options(
        joinedload(TestResultFile.regression_test_output)
        .joinedload(RegressionTestOutput.multiple_files)
    ).filter(TestResultFile.test_id.in_(test_ids)).all()
    files_by_result = defaultdict(list)
    for f in all_files:
        files_by_result[(f.test_id, f.regression_test_id)].append(f)

    # Preload expected outputs so status matches /summary and /samples.
    expected_by_rt = _preload_expected_outputs(results)

    # Batch load tests to avoid N+1 in _process_history_entries
    unique_tests = Test.query.filter(Test.id.in_(test_ids)).all()
    test_map = {t.id: t for t in unique_tests}

    # Batch compute timestamps for all referenced tests
    _, timestamps_map = batch_get_run_data(unique_tests)

    return _process_history_entries(
        results,
        files_by_result,
        status_filter,
        timestamps_map=timestamps_map,
        test_map=test_map,
        expected_by_rt=expected_by_rt)


def _resolve_history_rt_ids(rt_ids, sample_id):
    """Narrow a sample's regression tests to the optional ?regression_test_id.

    Without this, ``limit`` counts rows across every regression test on the
    sample, so a caller asking about one test gets roughly
    limit / len(rt_ids) runs of it and cannot tell the window was short.
    """
    raw = request.args.get('regression_test_id')
    if raw is None:
        return rt_ids, None

    try:
        rt_id = int(raw)
        if rt_id < 1 or rt_id > 2147483647:
            raise ValueError('Out of bounds')
    except (ValueError, TypeError):
        return None, make_error_response(
            'validation_error',
            'regression_test_id must be a positive integer '
            'between 1 and 2147483647.',
            details={
                'fields': {
                    'regression_test_id': 'Must be a positive integer '
                    'between 1 and 2147483647.'}},
            http_status=400,
        )

    if rt_id not in rt_ids:
        return None, make_error_response(
            'validation_error',
            f'Regression test {rt_id} does not belong to sample {sample_id}.',
            details={
                'fields': {
                    'regression_test_id': 'Must be a regression test of '
                    'this sample.'}},
            http_status=400,
        )

    return [rt_id], None


def _apply_history_filters(
        query,
        branch,
        platform,
        created_after,
        created_before):
    if branch:
        query = query.filter(Test.branch == branch)

    if platform:
        try:
            platform_enum = TestPlatform.from_string(platform)
            query = query.filter(Test.platform == platform_enum)
        except Exception:
            valid_platforms = ', '.join(TestPlatform.values())
            return None, make_error_response(
                'validation_error', 'Invalid platform: {platform}. '
                'Must be one of: {valid_platforms}.'.format(
                    platform=platform, valid_platforms=valid_platforms
                ),
                http_status=400,
            )

    if created_after or created_before:

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
@require_scope(Scope.RUNS_READ)
@validate_path_id('sample_id')
@validate_offset_pagination()
@validate_date_range
def get_sample_history(
        sample_id,
        limit=50,
        offset=0,
        created_after=None,
        created_before=None):
    """
    Show how a sample performed across different runs.

    Use failure_signature to tell apart genuine regressions from infra flakes.

    Pass ?regression_test_id to follow a single regression test, so that
    ``limit`` means that many runs of it rather than that many rows spread
    across every regression test on the sample.

    ?status is applied after status derivation, which needs result files, so
    it can't be pushed into SQL. That path scans the most recent
    _HISTORY_STATUS_SCAN_LIMIT results and sets pagination.truncated when a
    sample has more history than that.
    """
    sample = Sample.query.options(joinedload(Sample.tags)).filter(
        Sample.id == sample_id).first()
    if sample is None:
        return make_error_response(
            'not_found',
            f'Sample {sample_id} not found.',
            http_status=404)

    regression_tests = RegressionTest.query.filter_by(
        sample_id=sample_id).all()
    rt_ids = [rt.id for rt in regression_tests]

    if not rt_ids:
        return paginated_response([], 0, limit, offset)

    rt_ids, err = _resolve_history_rt_ids(rt_ids, sample_id)
    if err:
        return err

    # Validate the status filter up front, before any heavy query.
    status_filter = request.args.get('status')
    if status_filter and status_filter not in _VALID_SAMPLE_STATUSES:
        return make_error_response(
            'validation_error',
            f"Invalid status: {status_filter}",
            http_status=400
        )

    query = TestResult.query.filter(
        TestResult.regression_test_id.in_(rt_ids)
    ).join(Test, Test.id == TestResult.test_id)

    branch = request.args.get('branch')
    platform = request.args.get('platform')

    query, err = _apply_history_filters(
        query, branch, platform, created_after, created_before)
    if err:
        return err

    # regression_test_id breaks ties so a row can't shift between pages when
    # several regression tests share a run.
    query = query.order_by(Test.id.desc(), TestResult.regression_test_id.asc())

    if status_filter:
        # One row past the cap tells us whether the scan was complete.
        scanned = query.limit(_HISTORY_STATUS_SCAN_LIMIT + 1).all()
        truncated = len(scanned) > _HISTORY_STATUS_SCAN_LIMIT
        entries = _build_history_entries(
            scanned[:_HISTORY_STATUS_SCAN_LIMIT], status_filter)
        return paginated_response(
            entries[offset:offset + limit],
            len(entries),
            limit,
            offset,
            schema=SampleHistoryEntrySchema(),
            truncated=truncated,
            extra_meta={'scan_limit': _HISTORY_STATUS_SCAN_LIMIT}
            if truncated else None,
        )

    # No status filter: the page can be cut in SQL, so everything below it
    # loads one page worth of rows instead of the sample's whole history.
    total = query.count()
    results = query.offset(offset).limit(limit).all()
    entries = _build_history_entries(results, None)

    return paginated_response(
        entries, total, limit, offset, schema=SampleHistoryEntrySchema()
    )


def serialize_rt(rt):
    """Public shape of a regression test definition, without its outputs."""
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


@mod_api.route('/regression-tests', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_offset_pagination()
def list_regression_tests(limit=50, offset=0):
    """
    List regression test definitions.

    Supports ?active, ?category, ?tag, ?sample_id filters. Note: when
    ?active is omitted it defaults to true, so inactive regression tests
    are hidden unless ?active=false is passed explicitly.
    """
    query = RegressionTest.query.options(
        joinedload(RegressionTest.sample),
        selectinload(RegressionTest.categories),
    )

    active_filter = request.args.get('active')
    if active_filter is not None:
        value = active_filter.lower()
        if value in ('true', '1', 'yes'):
            is_active = True
        elif value in ('false', '0', 'no'):
            is_active = False
        else:
            # Reject garbage instead of silently treating it as false.
            return make_error_response(
                'validation_error',
                f'Invalid active filter: {active_filter}. '
                'Must be true or false.',
                details={'fields': {'active': 'Must be true or false.'}},
                http_status=400,
            )
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
                'sample_id must be a positive integer '
                'between 1 and 2147483647.',
                details={
                    'fields': {
                        'sample_id': 'Must be a positive integer '
                        'between 1 and 2147483647.'}},
                http_status=400,
            )

    tag_filter = request.args.get('tag')
    if tag_filter:
        query = query.filter(
            RegressionTest.sample.has(
                Sample.tags.any(func.lower(Tag.name) == tag_filter.lower())
            )
        )

    # Paginate at DB level
    total = query.count()
    tests = query.offset(offset).limit(limit).all()
    serialized = [serialize_rt(rt) for rt in tests]
    return paginated_response(serialized, total, limit, offset)
