"""Versioned REST API endpoints for test-result data."""

from typing import Any, Dict, List

from flask import Blueprint, jsonify
from sqlalchemy import and_

from exceptions import TestNotFoundException
from mod_regression.models import Category, RegressionTestOutput, regressionTestLinkTable
from mod_test.controllers import get_test_results
from mod_test.models import Test, TestResultFile

mod_api = Blueprint('api', __name__)


def _require_test(test_id: int) -> Test:
    test = Test.query.filter(Test.id == test_id).first()
    if test is None:
        raise TestNotFoundException(f"Test with id {test_id} does not exist")
    return test


@mod_api.errorhandler(TestNotFoundException)
def test_not_found(error: TestNotFoundException):
    return jsonify({'status': 'failure', 'error': error.message}), 404


@mod_api.route('/v1/tests/<int:test_id>/summary')
def test_summary(test_id: int):
    test = _require_test(test_id)
    customized_ids = test.get_customized_regressiontests()
    return jsonify({
        'status': 'success',
        'data': {
            'test_id': test.id,
            'platform': test.platform.value,
            'test_type': test.test_type.value,
            'commit': test.commit,
            'pr_nr': test.pr_nr,
            'finished': test.finished,
            'failed': test.failed,
            'sample_progress': {
                'current': len(test.results),
                'total': len(customized_ids),
                'percentage': int((len(test.results) / len(customized_ids)) * 100) if customized_ids else 0,
            },
        },
    })


@mod_api.route('/v1/tests/<int:test_id>/results')
def test_results(test_id: int):
    test = _require_test(test_id)
    categories: List[Dict[str, Any]] = []
    for entry in get_test_results(test):
        category = entry['category']
        tests: List[Dict[str, Any]] = []
        for category_test in entry['tests']:
            result = category_test['result']
            tests.append({
                'regression_test_id': category_test['test'].id,
                'command': category_test['test'].command,
                'expected_rc': category_test['test'].expected_rc if result is None else result.expected_rc,
                'exit_code': None if result is None else result.exit_code,
                'runtime': None if result is None else result.runtime,
                'error': category_test['error'],
            })
        categories.append({
            'id': category.id,
            'name': category.name,
            'error': entry['error'],
            'tests': tests,
        })

    return jsonify({'status': 'success', 'data': categories})


@mod_api.route('/v1/tests/<int:test_id>/files')
def test_result_files(test_id: int):
    test = _require_test(test_id)
    files = TestResultFile.query.filter(TestResultFile.test_id == test.id).all()
    data = [{
        'regression_test_id': item.regression_test_id,
        'regression_test_output_id': item.regression_test_output_id,
        'expected_hash': item.expected,
        'got_hash': item.got,
    } for item in files]
    return jsonify({'status': 'success', 'data': data})


@mod_api.route('/v1/tests/<int:test_id>/progress')
def test_progress(test_id: int):
    test = _require_test(test_id)
    progress = [{
        'status': entry.status.value,
        'message': entry.message,
        'timestamp': entry.timestamp.isoformat(),
    } for entry in test.progress]
    current_step = progress[-1]['status'] if progress else 'unknown'
    return jsonify({
        'status': 'success',
        'data': {
            'summary': {
                'complete': test.finished,
                'failed': test.failed,
                'current_step': current_step,
                'event_count': len(progress),
            },
            'events': progress,
        },
    })


@mod_api.route('/v1/categories')
def categories():
    populated_categories = regressionTestLinkTable.select().with_only_columns(
        regressionTestLinkTable.c.category_id
    ).subquery()
    category_rows = Category.query.filter(Category.id.in_(populated_categories)).order_by(Category.name.asc()).all()

    data = []
    for category in category_rows:
        active_outputs = RegressionTestOutput.query.filter(and_(
            RegressionTestOutput.regression_id.in_([rt.id for rt in category.regression_tests]),
            RegressionTestOutput.ignore.is_(False),
        )).count()
        data.append({
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'regression_test_count': len(category.regression_tests),
            'output_file_count': active_outputs,
        })

    return jsonify({'status': 'success', 'data': data})
