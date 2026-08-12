import json
from unittest import mock

from flask import g
from sqlalchemy import event

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput)
from mod_sample.models import ExtraFile, Sample, Tag
from mod_test.models import (Test, TestPlatform, TestResult, TestResultFile,
                             TestType)
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

        # Requests below detach ORM objects held by this session, so keep a
        # plain id for the tests that add runs after a request.
        self.fork_id = self.fork.id

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

    def _capture_statements(self, url, token):
        """Return (statement, parameters) for every SQL one GET executes."""
        statements = []

        def counter(conn, cursor, statement, parameters, context,
                    executemany):
            statements.append((statement, parameters))

        engine = g.db.get_bind()
        event.listen(engine, 'before_cursor_execute', counter)
        try:
            res = self.client.get(
                url, headers={'Authorization': f'Bearer {token}'})
        finally:
            event.remove(engine, 'before_cursor_execute', counter)
        self.assertEqual(res.status_code, 200)
        return statements

    def _count_queries(self, url, token):
        """Return the number of SQL statements one GET request executes."""
        return len(self._capture_statements(url, token))

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

    def _add_history_run(self, commit, results):
        """Add a run holding one result per (rt_id, output_id, exit_code)."""
        run = Test(TestPlatform.linux, TestType.commit, self.fork_id,
                   'master', commit)
        g.db.add(run)
        g.db.commit()
        run_id = run.id
        for rt_id, output_id, exit_code in results:
            g.db.add(TestResult(run_id, rt_id, 0, exit_code, 0))
            g.db.add(TestResultFile(run_id, rt_id, output_id,
                                    'expected_hash', None))
        g.db.commit()
        return run_id

    def _add_second_regression_test(self):
        """Add a second regression test on the same sample, with an output."""
        rt = RegressionTest(self.sample_id, 'command_hist2', InputType.file,
                            OutputType.file, self.category.id, 0)
        g.db.add(rt)
        g.db.commit()
        rt_id = rt.id
        rto = RegressionTestOutput(rt_id, 'expected_hash', '.txt', 'exp2')
        g.db.add(rto)
        g.db.commit()
        return rt_id, rto.id

    def test_get_sample_history_paginates_in_sql(self):
        # limit has to bound the work, not just the response. The endpoint
        # used to build an entry for every result in the sample's history
        # and slice the page out of that list afterwards, which is what made
        # it time out on production data.
        for i in range(4):
            self._add_history_run(f'hist_commit_{i}',
                                  [(self.reg_test_id, self.reg_out_id, 0)])

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'thp', scopes=['runs:read'])
        base = f'/api/v1/samples/{self.sample_id}/history?limit=2'
        first = self.client.get(
            base, headers={'Authorization': f'Bearer {token}'})
        second = self.client.get(
            f'{base}&offset=2', headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        # 4 added runs plus the one from setUp; total counts the whole
        # history even though only a page was loaded.
        self.assertEqual(first.json['pagination']['total'], 5)
        self.assertEqual(first.json['pagination']['next_offset'], 2)
        self.assertEqual(len(first.json['data']), 2)
        self.assertEqual(len(second.json['data']), 2)

        first_ids = [e['run_id'] for e in first.json['data']]
        second_ids = [e['run_id'] for e in second.json['data']]
        # Newest first, and the pages must not overlap.
        self.assertEqual(first_ids, sorted(first_ids, reverse=True))
        self.assertEqual(set(first_ids) & set(second_ids), set())

    def test_get_sample_history_loads_only_the_page(self):
        # The follow-up queries are keyed off the results of the page, so
        # they must not widen as the sample accumulates history.
        for i in range(8):
            self._add_history_run(f'bounded_commit_{i}',
                                  [(self.reg_test_id, self.reg_out_id, 0)])

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'tbp', scopes=['runs:read'])
        statements = self._capture_statements(
            f'/api/v1/samples/{self.sample_id}/history?limit=2', token)

        # The file lookup is the one that fans out through two nested
        # joinedloads, so it is the one worth pinning.
        file_selects = [params for stmt, params in statements
                        if 'FROM test_result_file' in stmt]
        self.assertTrue(file_selects)
        for params in file_selects:
            self.assertLessEqual(len(params), 2)

    def test_get_sample_history_regression_test_filter(self):
        rt2_id, rto2_id = self._add_second_regression_test()
        for i in range(3):
            self._add_history_run(
                f'multi_rt_commit_{i}',
                [(self.reg_test_id, self.reg_out_id, 0),
                 (rt2_id, rto2_id, 0)])

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'trt', scopes=['runs:read'])
        url = (f'/api/v1/samples/{self.sample_id}/history'
               f'?limit=3&regression_test_id={self.reg_test_id}')
        res = self.client.get(url, headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        data = res.json['data']
        self.assertEqual({e['regression_test_id'] for e in data},
                         {self.reg_test_id})
        # limit means runs of the requested test: 3 asked for, 3 distinct
        # runs back.
        self.assertEqual(len({e['run_id'] for e in data}), 3)
        # 3 added runs plus the one from setUp, counting only this test.
        self.assertEqual(res.json['pagination']['total'], 4)

        # Without the filter the same limit is spread over both regression
        # tests, so it covers fewer runs — the reason the filter exists.
        unfiltered = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history?limit=3',
            headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(unfiltered.status_code, 200)
        self.assertLess(
            len({e['run_id'] for e in unfiltered.json['data']}), 3)

    def test_get_sample_history_regression_test_filter_foreign_id(self):
        other_sample = Sample('other_sha', 'txt', 'other_sample')
        g.db.add(other_sample)
        g.db.commit()
        other_rt = RegressionTest(other_sample.id, 'other_command',
                                  InputType.file, OutputType.file,
                                  self.category.id, 0)
        g.db.add(other_rt)
        g.db.commit()
        other_rt_id = other_rt.id

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'trtf', scopes=['runs:read'])
        # A regression test of another sample would otherwise silently
        # return an empty page.
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history'
            f'?regression_test_id={other_rt_id}',
            headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)

    def test_get_sample_history_regression_test_filter_invalid(self):
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'trti', scopes=['runs:read'])
        for value in ('abc', '0', '-1'):
            res = self.client.get(
                f'/api/v1/samples/{self.sample_id}/history'
                f'?regression_test_id={value}',
                headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(res.status_code, 400, f'value={value}')

    def test_get_sample_history_status_filter(self):
        failing_run_id = self._add_history_run(
            'failing_commit', [(self.reg_test_id, self.reg_out_id, 1)])

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'tsf', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history?status=fail',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual([e['run_id'] for e in res.json['data']],
                         [failing_run_id])
        # The whole history fit inside the scan, so the page is complete.
        self.assertNotIn('truncated', res.json['pagination'])

    @mock.patch('mod_api.routes.samples._HISTORY_STATUS_SCAN_LIMIT', 2)
    def test_get_sample_history_status_filter_scan_is_bounded(self):
        # status is derived in Python, so it can't be pushed into SQL. The
        # scan is capped instead, and a capped page says so rather than
        # passing itself off as the sample's whole history.
        for i in range(3):
            self._add_history_run(f'scan_commit_{i}',
                                  [(self.reg_test_id, self.reg_out_id, 0)])

        token = self.get_token('samp_user@local.com', 'userpass123',
                               'tsb', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/history?status=pass',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json['pagination']['truncated'])
        self.assertEqual(res.json['meta']['scan_limit'], 2)
        self.assertEqual(len(res.json['data']), 2)

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

    @mock.patch('mod_api.routes.samples.resolve_artifact')
    def test_download_sample(self, resolve):
        resolve.return_value = ('https://signed.url', 'ok')
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'dl1', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/download',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['download_url'], 'https://signed.url')
        # Spelled out rather than read back off self.sample, which the
        # request teardown detaches from its session.
        resolve.assert_called_once_with('TestFiles/test_sha.txt')

    @mock.patch('mod_api.routes.samples.resolve_artifact')
    def test_download_sample_local_only_has_no_url(self, resolve):
        resolve.return_value = (None, 'degraded')
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'dl2', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/download',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json['download_url'])
        self.assertEqual(res.json['storage_status'], 'degraded')

    @mock.patch('mod_api.routes.samples.resolve_artifact')
    def test_download_sample_missing_from_storage(self, resolve):
        resolve.return_value = (None, 'missing')
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'dl3', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/download',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 404)

    def test_download_sample_not_found(self):
        token = self.get_token('samp_user@local.com', 'userpass123',
                               'dl4', scopes=['runs:read'])
        res = self.client.get(
            '/api/v1/samples/999999/download',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 404)

    # ---- tags, sample edits and deletes --------------------------------

    def _admin(self, name):
        token = self.get_token('samp_admin@local.com', 'adminpass123', name,
                               scopes=['runs:read', 'runs:write'])
        return {'Authorization': f'Bearer {token}'}

    def _post(self, path, headers, body):
        return self.client.post(
            f'/api/v1{path}', data=json.dumps(body),
            content_type='application/json', headers=headers)

    def test_create_and_list_tags(self):
        res = self._post('/tags', self._admin('tag1'),
                         {'name': 'dvb', 'description': 'DVB subtitles'})
        self.assertEqual(res.status_code, 201)

        listed = self.client.get('/api/v1/tags', headers=self._admin('tag2'))
        self.assertEqual(listed.status_code, 200)
        self.assertIn('dvb', [t['name'] for t in listed.json['data']])

    def test_create_tag_rejects_duplicate(self):
        self._post('/tags', self._admin('tag3'), {'name': 'dvb'})
        res = self._post('/tags', self._admin('tag4'), {'name': 'dvb'})
        self.assertEqual(res.status_code, 409)

    def test_create_tag_requires_admin(self):
        token = self.get_token('samp_user@local.com', 'userpass123', 'tag5',
                               scopes=['runs:write'])
        res = self._post('/tags', {'Authorization': f'Bearer {token}'},
                         {'name': 'nope'})
        self.assertEqual(res.status_code, 403)

    def test_update_sample_tags(self):
        g.db.add(Tag('dvb', 'DVB subtitles'))
        g.db.commit()

        res = self.client.patch(
            f'/api/v1/samples/{self.sample_id}',
            data=json.dumps({'tags': ['dvb']}),
            content_type='application/json',
            headers=self._admin('edit1'))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['tags'], ['dvb'])

    def test_update_sample_rejects_unknown_tag(self):
        res = self.client.patch(
            f'/api/v1/samples/{self.sample_id}',
            data=json.dumps({'tags': ['nosuchtag']}),
            content_type='application/json',
            headers=self._admin('edit2'))

        self.assertEqual(res.status_code, 400)

    def test_update_sample_without_upload_row_rejects_metadata(self):
        # notes and friends live on the upload row, and this sample has none.
        res = self.client.patch(
            f'/api/v1/samples/{self.sample_id}',
            data=json.dumps({'notes': 'a note'}),
            content_type='application/json',
            headers=self._admin('edit3'))

        self.assertEqual(res.status_code, 409)

    def test_delete_sample_in_use_is_refused(self):
        res = self.client.delete(
            f'/api/v1/samples/{self.sample_id}',
            headers=self._admin('del1'))

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json['details']['regression_test_count'], 1)

    def test_delete_unused_sample(self):
        spare = Sample('spare_sha', 'txt', 'spare')
        g.db.add(spare)
        g.db.commit()
        spare_id = spare.id

        res = self.client.delete(
            f'/api/v1/samples/{spare_id}', headers=self._admin('del2'))

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(Sample.query.filter(Sample.id == spare_id).first())

    @mock.patch('mod_api.routes.samples._remove_local')
    def test_delete_sample_unlinks_its_files_after_the_row(self, remove):
        spare = Sample('spare2_sha', 'txt', 'spare2')
        g.db.add(spare)
        g.db.flush([spare])
        g.db.add(ExtraFile(spare.id, 'srt', 'companion'))
        g.db.commit()
        spare_id = spare.id

        # Record whether the row had already gone at each unlink: nothing
        # may be removed from disk until the delete is committed.
        row_gone = []
        remove.side_effect = lambda path: row_gone.append(
            Sample.query.filter(Sample.id == spare_id).first() is None)

        res = self.client.delete(
            f'/api/v1/samples/{spare_id}', headers=self._admin('del4'))

        self.assertEqual(res.status_code, 200)
        paths = [call.args[0] for call in remove.call_args_list]
        # The media file, its media info, and the file uploaded alongside it.
        self.assertEqual(len(paths), 3)
        self.assertTrue(any('TestFiles/extra/' in p for p in paths))
        self.assertTrue(any(p.endswith('.xml') for p in paths))
        self.assertTrue(all(row_gone))

    def test_delete_sample_requires_admin(self):
        token = self.get_token('samp_user@local.com', 'userpass123', 'del3',
                               scopes=['runs:write'])
        res = self.client.delete(
            f'/api/v1/samples/{self.sample_id}',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 403)

    @mock.patch('mod_api.routes.samples.resolve_artifact')
    def test_download_media_info(self, resolve):
        resolve.return_value = ('https://signed.url', 'ok')
        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/media-info/download',
            headers=self._admin('mi1'))

        self.assertEqual(res.status_code, 200)
        resolve.assert_called_once_with('TestFiles/media/test_sha.xml')

    @mock.patch('mod_api.routes.samples.resolve_artifact')
    def test_download_extra_file(self, resolve):
        resolve.return_value = ('https://signed.url', 'ok')
        extra = ExtraFile(self.sample_id, 'srt', 'subs.srt')
        g.db.add(extra)
        g.db.commit()
        extra_id = extra.id

        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/extra-files/{extra_id}'
            f'/download',
            headers=self._admin('ex1'))

        self.assertEqual(res.status_code, 200)
        # ExtraFile.filename is <sample sha>_<id><extension>.
        resolve.assert_called_once_with(
            f'TestFiles/extra/test_sha_{extra_id}.srt')

    def test_download_extra_file_of_another_sample_is_not_found(self):
        other = Sample('other_sha', 'txt', 'other')
        g.db.add(other)
        g.db.commit()
        extra = ExtraFile(other.id, 'srt', 'subs.srt')
        g.db.add(extra)
        g.db.commit()

        res = self.client.get(
            f'/api/v1/samples/{self.sample_id}/extra-files/{extra.id}'
            f'/download',
            headers=self._admin('ex2'))

        self.assertEqual(res.status_code, 404)

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
