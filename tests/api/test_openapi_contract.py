"""
Check that the API accepts every query value the OpenAPI spec documents.

A filter value the spec lists but the API rejects with a 400 breaks any client
that follows the spec. This walks each GET operation in openapi-ci-api.yaml
and calls it with every documented enum and boolean value, and with the
pagination bounds, against the data BaseTestCase seeds.
"""

import os
import re
from unittest import mock

import yaml

from mod_api.models.api_token import VALID_SCOPES
from tests.api.base import ApiTestCase

SPEC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'openapi-ci-api.yaml')

# Path values resolving to rows BaseTestCase.setUp creates, so each request
# gets past its 404 checks and reaches the query parameter validation.
PATH_VALUES = {
    'run_id': 1,
    'sample_id': 1,
    'regression_test_id': 1,
    'regression_id': 1,
    'output_id': 1,
    'variant_id': 1,
    'queued_id': 1,
    'user_id': 1,
}

PAGINATION_PARAMS = ('limit', 'offset', 'cursor')


def _load_spec():
    with open(SPEC_PATH) as spec_file:
        return yaml.safe_load(spec_file)


def _resolve(spec, node):
    while '$ref' in node:
        target = spec
        for part in node['$ref'].lstrip('#/').split('/'):
            target = target[part]
        node = target
    return node


def _documented_values(param_name, schema):
    values = list(schema.get('enum', []))
    if schema.get('type') == 'boolean':
        values += ['true', 'false']
    if param_name in PAGINATION_PARAMS:
        values += [schema[bound] for bound in ('minimum', 'maximum') if bound in schema]
    return values


def _query_cases(spec):
    """Yield (path, param name, value) for every documented GET query value."""
    for path, item in spec['paths'].items():
        operation = item.get('get')
        if operation is None:
            continue
        params = item.get('parameters', []) + operation.get('parameters', [])
        for param in (_resolve(spec, p) for p in params):
            if param['in'] != 'query':
                continue
            schema = _resolve(spec, param.get('schema', {}))
            for value in _documented_values(param['name'], schema):
                yield path, param['name'], value


class TestOpenApiContract(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.setup_run_data('contract')
        self.token = self.get_token(
            'contract_admin@local.com', 'adminpass123', 'contract', scopes=sorted(VALID_SCOPES))
        # One request per documented value adds up to far more than the rate
        # limit allows. Lift the limit, and give the test its own request log
        # so the entries it records don't push later tests into 429s.
        for patcher in (
                mock.patch('mod_api.middleware.rate_limit._get_limits', return_value=(1_000_000, 1)),
                mock.patch.dict('mod_api.middleware.rate_limit._rate_limit_store', {}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_documented_query_values_are_accepted(self):
        spec = _load_spec()
        for path, name, value in _query_cases(spec):
            url = '/api/v1' + re.sub(r'\{(\w+)\}', lambda m: str(PATH_VALUES[m.group(1)]), path)
            with self.subTest(path=path, param=name, value=value):
                res = self.client.get(
                    url, query_string={name: value},
                    headers={'Authorization': f'Bearer {self.token}'})
                self.assertNotEqual(res.status_code, 400, res.get_json(silent=True))
                self.assertLess(res.status_code, 500)
