from flask import g
from sqlalchemy import event

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput)
from mod_sample.models import Sample
from mod_test.models import TestResult, TestResultFile
from tests.api.base import ApiTestCase


class TestRoutesSamples(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.setup_run_data('samp')
        self.sample = Sample('test_sha', 'txt', 'test_sample')
        g.db.add(self.sample)
        g.db.commit()
        self.sample_id = self.sample.id

        self.category = Category('Test Category', 'Description')
        g.db.add(self.category)
        g.db.commit()

        self.reg_test = RegressionTest(
            self.sample_id,
            'command',
            InputType.file,
            OutputType.file,
            self.category.id,
            0)
        g.db.add(self.reg_test)
        g.db.commit()
        self.reg_test_id = self.reg_test.id

        self.reg_out = RegressionTestOutput(
            self.reg_test_id, 'expected_hash', '.txt', 'exp')
        g.db.add(self.reg_out)
        g.db.commit()
        self.reg_out_id = self.reg_out.id

        self.test_result = TestResult(self.test_id, self.reg_test_id, 0, 0, 0)
        g.db.add(self.test_result)
        g.db.commit()

        self.result_file = TestResultFile(
            self.test_id,
            self.reg_test_id,
            self.reg_out_id,
            'expected_hash',
            None)
        g.db.add(self.result_file)
        g.db.commit()

        _rate_limit_store.clear()

    def test_list_run_samples(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't1', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]
                         ['regression_test_id'], self.reg_test_id)

    def test_list_run_samples_missing_output_consistent(self):
        # A regression test with a non-ignored expected output but no
        # result file must report 'missing_output' (same derivation as
        # /runs/{id}/summary), not 'pass'. Guards the expected-outputs
        # threading in list_run_samples.
        reg_test2 = RegressionTest(
            self.sample_id, 'command2', InputType.file, OutputType.file,
            self.category.id, 0)
        g.db.add(reg_test2)
        g.db.commit()
        reg_test2_id = reg_test2.id
        g.db.add(RegressionTestOutput(reg_test2_id, 'hash2', '.txt', 'exp2'))
        # A result whose expected output has no matching TestResultFile.
        g.db.add(TestResult(self.test_id, reg_test2_id, 0, 0, 0))
        g.db.commit()

        token = self.get_token('samp_user@local.com',
                               'userpass123', 'tmo', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        entry = next(s for s in res.json['data']
                     if s['regression_test_id'] == reg_test2_id)
        self.assertEqual(entry['status'], 'missing_output')

    def _count_queries(self, url, token):
        """Return the number of SQL statements one GET request executes."""
        statements = []

        def counter(conn, cursor, statement, parameters, context,
                    executemany):
            statements.append(statement)

        engine = g.db.get_bind()
        event.listen(engine, 'before_cursor_execute', counter)
        try:
            res = self.client.get(
                url, headers={'Authorization': f'Bearer {token}'})
        finally:
            event.remove(engine, 'before_cursor_execute', counter)
        self.assertEqual(res.status_code, 200)
        return len(statements)

    def test_list_run_samples_query_count_is_flat(self):
        # Guards against reintroducing per-regression-test lazy loads:
        # the number of queries must not depend on how many regression
        # tests the run has.
        token = self.get_token('samp_user@local.com',
                               'userpass123', 'tqc', scopes=['runs:read'])
        # Plain ids only: the request below detaches ORM objects held by
        # this test's session.
        category_id = self.category.id
        url = f'/api/v1/runs/{self.test_id}/samples'
        baseline = self._count_queries(url, token)

        for i in range(8):
            rt = RegressionTest(self.sample_id, f'command_qc{i}',
                                InputType.file, OutputType.file,
                                category_id, 0)
            g.db.add(rt)
            g.db.commit()
            rto = RegressionTestOutput(rt.id, f'hash_qc{i}', '.txt', 'exp')
            g.db.add(rto)
            g.db.commit()
            g.db.add(TestResult(self.test_id, rt.id, 0, 0, 0))
            g.db.add(TestResultFile(self.test_id, rt.id, rto.id,
                                    f'hash_qc{i}', None))
            g.db.commit()

        self.assertEqual(self._count_queries(url, token), baseline)

    def test_get_run_sample(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't2', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples/{self.reg_test_id}',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['regression_test_id'], self.reg_test_id)

    def test_list_samples(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't3', scopes=['runs:read'])
        res = self.client.get(
            '/api/v1/samples', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 3)
        self.assertTrue(
            any(s['sample_id'] == self.sample_id for s in res.json['data']))

    def test_get_sample(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't4', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['sample_id'], self.sample_id)

    def test_get_sample_history(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't5', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertTrue(
            any(h['run_id'] == self.test_id for h in res.json['data']))

    def test_list_regression_tests(self):
        token = self.get_token('samp_user@local.com',
                               'userpass123', 't6', scopes=['runs:read'])
        res = self.client.get('/api/v1/regression-tests',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 3)
        self.assertTrue(any(rt['regression_test_id'] == self.reg_test_id
                            for rt in res.json['data']))

    def test_list_regression_tests_active_filter(self):
        # Create an inactive regression test
        rt_inactive = RegressionTest(
            self.sample_id,
            'cmd_inactive',
            InputType.file,
            OutputType.file,
            self.category.id,
            0)
        rt_inactive.active = False
        g.db.add(rt_inactive)
        g.db.commit()
        rt_inactive_id = rt_inactive.id

        token = self.get_token(
            'samp_user@local.com',
            'userpass123',
            't_active_filter',
            scopes=['runs:read'])

        # Default active=true
        res = self.client.get('/api/v1/regression-tests',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(rt['regression_test_id'] == self.reg_test_id
                            for rt in res.json['data']))
        self.assertFalse(any(rt['regression_test_id'] == rt_inactive_id
                             for rt in res.json['data']))

        res_false = self.client.get(
            '/api/v1/regression-tests?active=false',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res_false.status_code, 200)
        self.assertFalse(any(rt['regression_test_id'] == self.reg_test_id
                             for rt in res_false.json['data']))
        self.assertTrue(any(rt['regression_test_id'] == rt_inactive_id
                            for rt in res_false.json['data']))

    def test_list_samples_invalid_status(self):
        token = self.get_token(
            'samp_user@local.com',
            'userpass123',
            scopes=['runs:read'])
        res = self.client.get(
            '/api/v1/samples?status=invalid',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)

    def test_get_sample_not_found(self):
        token = self.get_token(
            'samp_user@local.com',
            'userpass123',
            scopes=['runs:read'])
        res = self.client.get('/api/v1/samples/99999',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 404)

    def test_list_run_samples_invalid_status(self):
        token = self.get_token(
            'samp_user@local.com',
            'userpass123',
            scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples?status=typo',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 400)

    def test_get_run_sample_not_found(self):
        token = self.get_token(
            'samp_user@local.com',
            'userpass123',
            scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/samples/999',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 404)

    def test_get_sample_history_invalid_status(self):
        token = self.get_token(
            'samp_user@local.com',
            'userpass123',
            scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history?status=typo',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)

    def test_get_sample_details(self):
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'det1', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/details',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['sample_id'], self.sample_id)
        self.assertEqual(res.json['original_name'], 'test_sample')
        self.assertEqual(res.json['extra_files'], [])
        # No upload row exists for this sample, and the media XML is absent
        # in tests; both degrade to null rather than failing the response.
        self.assertIsNone(res.json['upload'])
        self.assertIsNone(res.json['media_info'])

    def test_get_sample_details_includes_upload_metadata(self):
        from mod_upload.models import Platform, Upload
        g.db.add(Upload(self.admin.id, self.sample_id, None,
                        Platform.linux, '--autoprogram', 'a note'))
        g.db.commit()

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'det2', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/details',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['upload']['platform'], 'linux')
        self.assertEqual(res.json['upload']['parameters'], '--autoprogram')
        self.assertEqual(res.json['upload']['notes'], 'a note')
        # No CCExtractorVersion row is linked, so version reports null.
        self.assertIsNone(res.json['upload']['version'])

    def test_get_sample_details_not_found(self):
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'det3', scopes=['runs:read'])
        res = self.client.get(
            '/api/v1/samples/999999/details',
            headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 404)
