from unittest.mock import MagicMock

from marshmallow import Schema, fields

from mod_api.utils import (cursor_paginated_response, get_sort_column,
                           paginated_response, single_response)
from tests.base import BaseTestCase


class DummySchema(Schema):
    id = fields.Integer()
    name = fields.String()


class TestUtils(BaseTestCase):
    def test_paginated_response_with_schema(self):
        data = [{'id': 1, 'name': 'Item 1'}, {'id': 2, 'name': 'Item 2'}]
        with self.app.test_request_context():
            res = paginated_response(
                data, total=5, limit=2, offset=0, schema=DummySchema())
            self.assertEqual(res.status_code, 200)
            json_data = res.json
            self.assertEqual(len(json_data['data']), 2)
            self.assertEqual(json_data['pagination']['total'], 5)
            self.assertEqual(json_data['pagination']['next_offset'], 2)

    def test_paginated_response_no_schema(self):
        data = [{'id': 1, 'name': 'Item 1'}, {'id': 2, 'name': 'Item 2'}]
        with self.app.test_request_context():
            res = paginated_response(data, total=2, limit=2, offset=0)
            self.assertEqual(res.status_code, 200)
            json_data = res.json
            self.assertEqual(len(json_data['data']), 2)
            self.assertEqual(json_data['pagination']['total'], 2)
            self.assertIsNone(json_data['pagination']['next_offset'])

    def test_cursor_paginated_response(self):
        data = [{'id': 1, 'name': 'Item 1'}]
        with self.app.test_request_context():
            res = cursor_paginated_response(
                data, next_cursor=2, limit=1, schema=DummySchema())
            self.assertEqual(res.status_code, 200)
            json_data = res.json
            self.assertEqual(json_data['pagination']['next_cursor'], 2)

            res2 = cursor_paginated_response(data, next_cursor=None, limit=1)
            self.assertIsNone(res2.json['pagination']['next_cursor'])

    def test_single_response(self):
        data = {'id': 1, 'name': 'Item 1'}
        with self.app.test_request_context():
            res = single_response(data, schema=DummySchema(), http_status=201)
            self.assertEqual(res.status_code, 201)
            self.assertEqual(res.json['name'], 'Item 1')

            res2 = single_response(data)
            self.assertEqual(res2.status_code, 200)

    def test_get_sort_column(self):
        mock_col = MagicMock()
        mock_col.asc.return_value = 'asc_called'
        mock_col.desc.return_value = 'desc_called'

        column_map = {'created_at': mock_col}

        self.assertIsNone(get_sort_column('invalid', column_map))
        self.assertEqual(get_sort_column(
            'created_at', column_map), 'asc_called')
        self.assertEqual(get_sort_column(
            '-created_at', column_map), 'desc_called')
