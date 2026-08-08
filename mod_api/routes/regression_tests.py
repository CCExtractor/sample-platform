"""
Regression test detail/write endpoints and the categories that group them.

GET    /regression-tests/{id}   Full detail, including baselines and variants
POST   /regression-tests        Create a test (inactive unless asked otherwise)
PATCH  /regression-tests/{id}   Partially update a test
DELETE /regression-tests/{id}   Delete a test that has never run
GET    /regression-tests/{id}/outputs/{oid}/download
                                Where a baseline lives in storage
GET    /regression-tests/{id}/outputs/{oid}/variants/{vid}/download
                                The same, for an accepted variant
POST   /regression-tests/{id}/outputs/{oid}/variants
                                Accept another output hash as correct
DELETE /regression-tests/{id}/outputs/{oid}/variants/{vid}
                                Stop accepting one
GET    /categories              List categories with their test counts
POST   /categories              Create a category
PATCH  /categories/{id}         Rename or re-describe a category
DELETE /categories/{id}         Delete a category no test references

Editing the suite previously meant hand-written SQL against the production
database. The regression test list view stays in routes/samples.py.
"""

from flask import g
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.models.api_token import Scope
from mod_api.routes.samples import serialize_rt
from mod_api.schemas.regression_tests import (CategoryCreateSchema,
                                              CategoryUpdateSchema,
                                              RegressionTestCreateSchema,
                                              RegressionTestUpdateSchema,
                                              VariantCreateSchema)
from mod_api.services.storage import resolve_artifact
from mod_api.utils import paginated_response, single_response
from mod_auth.models import Role
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput,
                                   RegressionTestOutputFiles,
                                   regressionTestLinkTable)
from mod_sample.models import Sample
from mod_test.models import TestResult


def _resolve_categories(names):
    """
    Look up categories by name.

    Returns the matching rows plus the names that matched nothing, so the
    caller can reject the whole request rather than silently dropping a
    category the client believed it had set.
    """
    rows = Category.query.filter(Category.name.in_(names)).all()
    found = {category.name for category in rows}
    return rows, [name for name in names if name not in found]


def _unknown_categories_response(unknown):
    """Build the 400 returned when a request names categories that don't exist."""
    return make_error_response(
        'validation_error',
        f"Unknown categories: {', '.join(unknown)}",
        details={'fields': {'categories': unknown}},
        http_status=400,
    )


@mod_api.route('/regression-tests/<regression_test_id>', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('regression_test_id')
def get_regression_test(regression_test_id):
    """
    Return one regression test with its baselines.

    The list endpoint omits outputs because they multiply the payload for
    every row; a detail view needs them to show what "expected" means,
    including the alternative hashes accepted as variants.
    """
    test = RegressionTest.query.filter(
        RegressionTest.id == regression_test_id).first()
    if test is None:
        return make_error_response(
            'not_found', f'Regression test {regression_test_id} not found.',
            http_status=404)

    data = serialize_rt(test)
    data['outputs'] = [
        {
            'id': output.id,
            'correct': output.correct,
            'correct_extension': output.correct_extension,
            'expected_filename': output.expected_filename,
            'ignore': output.ignore,
            # Ids as well as hashes: the download route addresses a variant
            # by id, the same way the classic page does.
            'variants': [
                {'id': f.id, 'hash': f.file_hashes}
                for f in output.multiple_files
            ],
        }
        for output in test.output_files
    ]
    return single_response(data)


def _get_output(regression_test_id, output_id):
    """
    Look up one expected output, matched against its parent test.

    Filtering on both ids means an output id belonging to a different test
    reads as absent rather than resolving, so these URLs cannot be used to
    walk the table. Returns (output, error_response).
    """
    output = RegressionTestOutput.query.filter_by(
        id=output_id, regression_id=regression_test_id).first()
    if output is None:
        return None, make_error_response(
            'not_found',
            f'Output {output_id} not found on regression test '
            f'{regression_test_id}.',
            http_status=404)
    return output, None


def _located(filename):
    """
    Report where a TestResults file is, in the artifact response shape.

    Like the sample and run-artifact routes, this hands back a signed URL
    instead of the bytes, and says which backend holds the file when there
    is no URL to give.
    """
    url, status = resolve_artifact(f'TestResults/{filename}')
    if status == 'missing':
        return make_error_response(
            'not_found', f'{filename} is not present in storage.',
            http_status=404)
    return single_response({
        'filename': filename,
        'download_url': url,
        'storage_status': status,
    })


@mod_api.route(
    '/regression-tests/<regression_test_id>/outputs/<int:output_id>/download',
    methods=['GET']
)
@require_scope(Scope.RUNS_READ)
@validate_path_id('regression_test_id')
def download_output(regression_test_id, output_id):
    """Locate the baseline a regression test is expected to reproduce."""
    output, err = _get_output(regression_test_id, output_id)
    if err:
        return err
    return _located(output.filename_correct)


@mod_api.route(
    '/regression-tests/<regression_test_id>/outputs/<int:output_id>'
    '/variants/<int:variant_id>/download',
    methods=['GET']
)
@require_scope(Scope.RUNS_READ)
@validate_path_id('regression_test_id')
def download_variant(regression_test_id, output_id, variant_id):
    """Locate one of the alternative outputs accepted for a baseline."""
    output, err = _get_output(regression_test_id, output_id)
    if err:
        return err

    variant = RegressionTestOutputFiles.query.filter_by(
        id=variant_id, regression_test_output_id=output.id).first()
    if variant is None:
        return make_error_response(
            'not_found',
            f'Variant {variant_id} not found on output {output_id}.',
            http_status=404)

    return _located(f'{variant.file_hashes}{output.correct_extension}')


@mod_api.route(
    '/regression-tests/<regression_test_id>/outputs/<int:output_id>/variants',
    methods=['POST']
)
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('regression_test_id')
@validate_body(VariantCreateSchema)
def create_variant(regression_test_id, output_id, validated_data=None):
    """
    Accept another output hash as correct for a baseline.

    A test can legitimately produce different bytes on different platforms
    or CCExtractor builds. Recording the hash here makes those runs pass
    without overwriting the baseline everyone else is compared against,
    which is what promoting to baseline would do.
    """
    output, err = _get_output(regression_test_id, output_id)
    if err:
        return err

    file_hash = validated_data['hash']
    existing = RegressionTestOutputFiles.query.filter_by(
        regression_test_output_id=output.id, file_hashes=file_hash).first()
    if existing is not None:
        return make_error_response(
            'conflict',
            f'Output {output_id} already accepts {file_hash}.',
            http_status=409)

    variant = RegressionTestOutputFiles(file_hash, output.id)
    g.db.add(variant)
    g.db.commit()

    g.log.info(f'variant {file_hash} added to output {output_id} via API '
               f'by {g.api_user.id}')
    return single_response(
        {'id': variant.id, 'hash': variant.file_hashes}, http_status=201)


@mod_api.route(
    '/regression-tests/<regression_test_id>/outputs/<int:output_id>'
    '/variants/<int:variant_id>',
    methods=['DELETE']
)
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('regression_test_id')
def delete_variant(regression_test_id, output_id, variant_id):
    """Stop accepting one alternative output for a baseline."""
    output, err = _get_output(regression_test_id, output_id)
    if err:
        return err

    variant = RegressionTestOutputFiles.query.filter_by(
        id=variant_id, regression_test_output_id=output.id).first()
    if variant is None:
        return make_error_response(
            'not_found',
            f'Variant {variant_id} not found on output {output_id}.',
            http_status=404)

    g.db.delete(variant)
    g.db.commit()

    g.log.info(f'variant {variant_id} removed from output {output_id} via '
               f'API by {g.api_user.id}')
    return single_response({'id': variant_id, 'deleted': True})


@mod_api.route('/regression-tests', methods=['POST'])
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_body(RegressionTestCreateSchema)
def create_regression_test(validated_data=None):
    """
    Create a regression test.

    Created inactive unless the body says otherwise, so it cannot join a CI
    suite before someone has seen the output it actually produces.
    """
    data = validated_data

    sample = Sample.query.filter(Sample.id == data['sample_id']).first()
    if sample is None:
        return make_error_response(
            'not_found', f"Sample {data['sample_id']} not found.",
            http_status=404)

    categories, unknown = _resolve_categories(data['categories'])
    if unknown:
        return _unknown_categories_response(unknown)

    test = RegressionTest(
        sample_id=sample.id,
        command=data['command'],
        input_type=InputType.from_string(data['input_type']),
        output_type=OutputType.from_string(data['output_type']),
        # Categories live in a link table; the constructor argument is a
        # leftover from the single-category era and maps to no column.
        category_id=None,
        expected_rc=data['expected_rc'],
        active=data['active'],
        description=data['description'],
    )
    test.categories = categories
    g.db.add(test)
    g.db.commit()

    g.log.info(f'regression test {test.id} created via API by {g.api_user.id}')
    return single_response(serialize_rt(test), http_status=201)


@mod_api.route('/regression-tests/<regression_test_id>', methods=['PATCH'])
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('regression_test_id')
@validate_body(RegressionTestUpdateSchema)
def update_regression_test(regression_test_id, validated_data=None):
    """
    Update part of a regression test.

    Only the fields present in the body are touched, so two clients editing
    different fields cannot clobber each other's work.
    """
    test = RegressionTest.query.filter(
        RegressionTest.id == regression_test_id).first()
    if test is None:
        return make_error_response(
            'not_found', f'Regression test {regression_test_id} not found.',
            http_status=404)

    data = validated_data
    if not data:
        return make_error_response(
            'validation_error', 'No fields to update.', http_status=400)

    if 'categories' in data:
        categories, unknown = _resolve_categories(data['categories'])
        if unknown:
            return _unknown_categories_response(unknown)
        test.categories = categories

    for field in ('command', 'description', 'expected_rc', 'active'):
        if field in data:
            setattr(test, field, data[field])
    for field, enum in (('input_type', InputType), ('output_type', OutputType)):
        if field in data:
            setattr(test, field, enum.from_string(data[field]))

    g.db.commit()

    g.log.info(f'regression test {test.id} updated via API by '
               f'{g.api_user.id}: {sorted(data.keys())}')
    return single_response(serialize_rt(test))


@mod_api.route('/regression-tests/<regression_test_id>', methods=['DELETE'])
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('regression_test_id')
def delete_regression_test(regression_test_id):
    """
    Delete a regression test that has never run.

    Once results reference it the test carries history, and removing it
    would erase evidence of past regressions, so it is refused with 409 and
    the result count. Retiring such a test is a PATCH with active=false.

    Baselines, variants and category links are cleared first: those foreign
    keys are RESTRICT and would otherwise block the delete.
    """
    test = RegressionTest.query.filter(
        RegressionTest.id == regression_test_id).first()
    if test is None:
        return make_error_response(
            'not_found', f'Regression test {regression_test_id} not found.',
            http_status=404)

    result_count = TestResult.query.filter_by(
        regression_test_id=test.id).count()
    if result_count:
        return make_error_response(
            'conflict',
            f'Regression test {regression_test_id} has {result_count} '
            f'historical result(s). PATCH active=false to retire it instead.',
            details={'result_count': result_count},
            http_status=409,
        )

    deleted_id = test.id
    # Queried rather than read off test.output_files: deleting rows underneath
    # a live relationship collection mutates it mid-iteration. The outputs go
    # through the session so it knows they are gone before the test itself is
    # deleted, otherwise SQLAlchemy tries to orphan them and hits stale rows.
    outputs = RegressionTestOutput.query.filter_by(regression_id=test.id).all()
    for output in outputs:
        RegressionTestOutputFiles.query.filter_by(
            regression_test_output_id=output.id).delete(
                synchronize_session=False)
        g.db.delete(output)

    test.categories = []
    g.db.delete(test)
    g.db.commit()

    g.log.info(f'regression test {deleted_id} deleted via API by '
               f'{g.api_user.id}')
    return single_response({'id': deleted_id, 'deleted': True})


def _test_counts(category_ids):
    """Count the regression tests linked to each of these categories."""
    if not category_ids:
        return {}
    link = regressionTestLinkTable
    return dict(g.db.query(
        link.c.category_id, func.count(link.c.regression_id)
    ).filter(
        link.c.category_id.in_(category_ids)
    ).group_by(link.c.category_id).all())


def _serialize_category(category, test_count):
    """Public shape of a category, including how many tests reference it."""
    return {
        'id': category.id,
        'name': category.name,
        'description': category.description,
        'test_count': test_count,
    }


@mod_api.route('/categories', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_offset_pagination()
def list_categories(limit=50, offset=0):
    """List categories alphabetically."""
    query = Category.query.order_by(Category.name.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    # Counted in one grouped query rather than per row: reading
    # category.regression_tests would load every linked test just to size it.
    counts = _test_counts([row.id for row in rows])
    return paginated_response(
        [_serialize_category(row, counts.get(row.id, 0)) for row in rows],
        total, limit, offset)


@mod_api.route('/categories', methods=['POST'])
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_body(CategoryCreateSchema)
def create_category(validated_data=None):
    """Create a category. Names are unique, so a duplicate is a 409."""
    name = validated_data['name']
    if Category.query.filter(Category.name == name).first() is not None:
        return make_error_response(
            'conflict', f"Category '{name}' already exists.", http_status=409)

    category = Category(name, validated_data['description'])
    g.db.add(category)
    try:
        g.db.commit()
    except IntegrityError:
        # name is unique, so a request that raced the check above ends here.
        g.db.rollback()
        return make_error_response(
            'conflict', f"Category '{name}' already exists.", http_status=409)

    g.log.info(f'category {category.id} created via API by {g.api_user.id}')
    return single_response(_serialize_category(category, 0), http_status=201)


@mod_api.route('/categories/<category_id>', methods=['PATCH'])
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('category_id')
@validate_body(CategoryUpdateSchema)
def update_category(category_id, validated_data=None):
    """Rename or re-describe a category."""
    category = Category.query.filter(Category.id == category_id).first()
    if category is None:
        return make_error_response(
            'not_found', f'Category {category_id} not found.', http_status=404)

    data = validated_data
    if not data:
        return make_error_response(
            'validation_error', 'No fields to update.', http_status=400)

    # Comparing against the current name first keeps re-sending your own
    # name from colliding with yourself.
    if 'name' in data and data['name'] != category.name:
        if Category.query.filter(Category.name == data['name']).first():
            return make_error_response(
                'conflict', f"Category '{data['name']}' already exists.",
                http_status=409)
        category.name = data['name']

    if 'description' in data:
        category.description = data['description']

    try:
        g.db.commit()
    except IntegrityError:
        g.db.rollback()
        return make_error_response(
            'conflict', f"Category '{data.get('name')}' already exists.",
            http_status=409)

    g.log.info(f'category {category.id} updated via API by {g.api_user.id}')
    counts = _test_counts([category.id])
    return single_response(
        _serialize_category(category, counts.get(category.id, 0)))


@mod_api.route('/categories/<category_id>', methods=['DELETE'])
@require_roles([Role.contributor, Role.admin])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('category_id')
def delete_category(category_id):
    """
    Delete a category no regression test references.

    Dropping one still in use would change which tests a suite selection
    picks up, so it is refused with 409 and the count. Detaching the tests
    first is a PATCH on each test's categories.
    """
    category = Category.query.filter(Category.id == category_id).first()
    if category is None:
        return make_error_response(
            'not_found', f'Category {category_id} not found.', http_status=404)

    in_use = _test_counts([category.id]).get(category.id, 0)
    if in_use:
        return make_error_response(
            'conflict',
            f'Category {category_id} is used by {in_use} regression test(s). '
            f'Detach them before deleting it.',
            details={'regression_test_count': in_use},
            http_status=409,
        )

    deleted_id = category.id
    g.db.delete(category)
    g.db.commit()

    g.log.info(f'category {deleted_id} deleted via API by {g.api_user.id}')
    return single_response({'id': deleted_id, 'deleted': True})
