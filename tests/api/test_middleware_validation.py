import json

from flask import jsonify
from marshmallow import Schema, fields

from mod_api.middleware.validation import (validate_body,
                                           validate_cursor_pagination,
                                           validate_date_range,
                                           validate_offset_pagination,
                                           validate_path_id, validate_sort)
from tests.api.base import ApiTestCase


class DummySchema(Schema):
    name = fields.String(required=True)
    age = fields.Integer()


class TestMiddlewareValidation(ApiTestCase):
    def test_validate_body_success(self):
        @validate_body(DummySchema)
        def dummy_handler(validated_data=None):
            return jsonify(validated_data)

        with self.app.test_request_context(
            '/dummy',
            method='POST',
            content_type='application/json',
            data=json.dumps({"name": "John", "age": 30})
        ):
            res = dummy_handler()
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['name'], "John")

    def test_validate_body_wrong_content_type(self):
        @validate_body(DummySchema)
        def dummy_handler(validated_data=None):
            return jsonify(validated_data)

        with self.app.test_request_context(
            '/dummy',
            method='POST',
            content_type='text/plain',
            data=json.dumps({"name": "John", "age": 30})
        ):
            res = dummy_handler()
            self.assertEqual(res.status_code, 415)
            self.assertEqual(res.json['code'], 'validation_error')

    def test_validate_body_invalid_json(self):
        @validate_body(DummySchema)
        def dummy_handler(validated_data=None):
            return jsonify(validated_data)

        with self.app.test_request_context(
            '/dummy',
            method='POST',
            content_type='application/json',
            data="not json"
        ):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

    def test_validate_body_schema_failure(self):
        @validate_body(DummySchema)
        def dummy_handler(validated_data=None):
            return jsonify(validated_data)

        with self.app.test_request_context(
            '/dummy',
            method='POST',
            content_type='application/json',
            data=json.dumps({"age": 30})  # Missing required 'name'
        ):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')
            self.assertIn('name', res.json['details']['fields'])

    def test_validate_path_id_success(self):
        @validate_path_id('run_id')
        def dummy_handler(run_id=None):
            return jsonify({"run_id": run_id})

        with self.app.test_request_context('/dummy'):
            res = dummy_handler(run_id='5')
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['run_id'], 5)

    def test_validate_path_id_invalid(self):
        @validate_path_id('run_id')
        def dummy_handler(run_id=None):
            return jsonify({"status": "ok"})

        with self.app.test_request_context('/dummy'):
            res = dummy_handler(run_id='abc')
            self.assertEqual(res.status_code, 400)

            res = dummy_handler(run_id='0')
            self.assertEqual(res.status_code, 400)

            res = dummy_handler(run_id='-5')
            self.assertEqual(res.status_code, 400)

    def test_validate_date_range_success(self):
        @validate_date_range
        def dummy_handler(created_after=None, created_before=None):
            return jsonify({"after": created_after.isoformat() if created_after else None})

        with self.app.test_request_context(
            '/dummy?created_after=2023-01-01T00:00:00Z&created_before=2023-12-31T00:00:00Z'
        ):
            res = dummy_handler()
            self.assertEqual(res.status_code, 200)
            self.assertIn('2023-01-01', res.json['after'])

    def test_validate_date_range_invalid_format(self):
        @validate_date_range
        def dummy_handler(created_after=None, created_before=None):
            return jsonify({"status": "ok"})

        with self.app.test_request_context('/dummy?created_after=not_a_date'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)

        with self.app.test_request_context('/dummy?created_before=not_a_date'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)

    def test_validate_date_range_inverted(self):
        @validate_date_range
        def dummy_handler(created_after=None, created_before=None):
            return jsonify({"status": "ok"})

        with self.app.test_request_context(
            '/dummy?created_after=2023-12-31T00:00:00Z&created_before=2023-01-01T00:00:00Z'
        ):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)

    def test_validate_sort(self):
        @validate_sort()
        def dummy_handler(sort=None):
            return jsonify({"sort": sort})

        with self.app.test_request_context('/dummy?sort=created_at'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['sort'], 'created_at')

        with self.app.test_request_context('/dummy?sort=invalid_sort'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)

    def test_validate_offset_pagination_boundaries(self):
        @validate_offset_pagination()
        def dummy_handler(limit=None, offset=None):
            return jsonify({"limit": limit, "offset": offset})

        # Test valid values
        with self.app.test_request_context('/dummy?limit=10&offset=20'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['limit'], 10)
            self.assertEqual(res.json['offset'], 20)

        # Test limit < 1
        with self.app.test_request_context('/dummy?limit=0'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

        # Test limit > 100
        with self.app.test_request_context('/dummy?limit=101'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

        # Test offset < 0
        with self.app.test_request_context('/dummy?offset=-1'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

    def test_validate_pagination_mixing(self):
        @validate_offset_pagination()
        def offset_handler(limit=None, offset=None):
            return jsonify({"limit": limit, "offset": offset})

        @validate_cursor_pagination()
        def cursor_handler(limit=None, cursor=None):
            return jsonify({"limit": limit, "cursor": cursor})

        # Test mixing offset query with cursor parameter
        with self.app.test_request_context('/dummy?offset=10&cursor=5'):
            res1 = offset_handler()
            self.assertEqual(res1.status_code, 400)
            self.assertEqual(res1.json['code'], 'validation_error')
            self.assertEqual(
                res1.json['message'], 'Cannot mix cursor and offset pagination.')
            self.assertIn('Cannot specify cursor',
                          res1.json['details']['fields']['cursor'])

            res2 = cursor_handler()
            self.assertEqual(res2.status_code, 400)
            self.assertEqual(res2.json['code'], 'validation_error')
            self.assertEqual(
                res2.json['message'], 'Cannot mix cursor and offset pagination.')
            self.assertIn('Cannot specify offset',
                          res2.json['details']['fields']['offset'])

    def test_validate_cursor_pagination_boundaries(self):
        @validate_cursor_pagination()
        def dummy_handler(limit=None, cursor=None):
            return jsonify({"limit": limit, "cursor": cursor})

        # Test valid values
        with self.app.test_request_context('/dummy?limit=10&cursor=20'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 200)

        # Test limit < 1
        with self.app.test_request_context('/dummy?limit=0'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

        # Test limit > 100
        with self.app.test_request_context('/dummy?limit=101'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

        # Test cursor < 0
        with self.app.test_request_context('/dummy?cursor=-1'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

        # Test cursor non-integer
        with self.app.test_request_context('/dummy?cursor=abc'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)

    def test_validate_offset_pagination_non_integer(self):
        @validate_offset_pagination()
        def dummy_handler(limit=None, offset=None):
            return jsonify({"status": "ok"})

        with self.app.test_request_context('/dummy?offset=abc'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)

        with self.app.test_request_context('/dummy?limit=xyz'):
            res = dummy_handler()
            self.assertEqual(res.status_code, 400)
