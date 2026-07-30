import json

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput,
                                   RegressionTestOutputFiles)
from mod_sample.models import Sample
from mod_test.models import TestResult
from tests.api.base import ApiTestCase


class TestRoutesRegressionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.setup_run_data('rtw')

        g.db.add(User('testcontrib_rtw', Role.contributor,
                      'rtw_contrib@local.com',
                      User.generate_hash('contribpass123')))
        g.db.commit()

        sample = Sample('rtw_sha', 'ts', 'rtw_sample')
        g.db.add(sample)
        g.db.commit()
        self.sample_id = sample.id

        self.category = Category('Broadcast', 'Broadcast streams')
        free_category = Category('Unused', 'Nothing points here')
        g.db.add_all([self.category, free_category])
        g.db.commit()
        self.category_id = self.category.id
        self.free_category_id = free_category.id

        existing = RegressionTest(
            self.sample_id, 'original command', InputType.file,
            OutputType.file, None, 0)
        g.db.add(existing)
        g.db.commit()
        existing.categories = [self.category]
        g.db.commit()
        self.existing_id = existing.id

        _rate_limit_store.clear()

    def _admin(self, name='rt_admin', scopes=('runs:read', 'runs:write')):
        token = self.get_token('rtw_admin@local.com', 'adminpass123', name,
                               scopes=list(scopes))
        return {'Authorization': f'Bearer {token}'}

    def _as(self, email, password, name, scopes):
        token = self.get_token(email, password, name, scopes=scopes)
        return {'Authorization': f'Bearer {token}'}

    def _write(self, method, path, headers, body):
        return getattr(self.client, method)(
            f'/api/v1{path}', data=json.dumps(body),
            content_type='application/json', headers=headers)

    # ---- regression tests: create --------------------------------------

    def test_create_regression_test(self):
        res = self._write('post', '/regression-tests', self._admin(), {
            'sample_id': self.sample_id,
            'command': '--autoprogram --out=srt',
            'categories': ['Broadcast'],
            'description': 'checks srt output',
        })

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['command'], '--autoprogram --out=srt')
        self.assertEqual(res.json['categories'], ['Broadcast'])
        # A new test must not join the CI suite until its output is verified.
        self.assertFalse(res.json['active'])

        created = RegressionTest.query.filter(
            RegressionTest.id == res.json['regression_test_id']).first()
        self.assertEqual(created.sample_id, self.sample_id)

    def test_create_regression_test_active_when_requested(self):
        res = self._write('post', '/regression-tests', self._admin(), {
            'sample_id': self.sample_id, 'command': 'cmd',
            'categories': ['Broadcast'], 'active': True})
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json['active'])

    def test_create_regression_test_as_contributor(self):
        headers = self._as('rtw_contrib@local.com', 'contribpass123',
                           'rt_contrib', ['runs:write'])
        res = self._write('post', '/regression-tests', headers, {
            'sample_id': self.sample_id, 'command': 'cmd',
            'categories': ['Broadcast']})
        self.assertEqual(res.status_code, 201)

    def test_create_regression_test_forbidden_for_plain_user(self):
        # Holding runs:write is not enough; the role is checked separately.
        headers = self._as('rtw_user@local.com', 'userpass123', 'rt_user',
                           ['runs:write'])
        res = self._write('post', '/regression-tests', headers, {
            'sample_id': self.sample_id, 'command': 'cmd',
            'categories': ['Broadcast']})
        self.assertEqual(res.status_code, 403)

    def test_create_regression_test_requires_write_scope(self):
        res = self._write(
            'post', '/regression-tests',
            self._admin('rt_noscope', scopes=['runs:read']),
            {'sample_id': self.sample_id, 'command': 'cmd',
             'categories': ['Broadcast']})
        self.assertEqual(res.status_code, 403)

    def test_create_regression_test_unknown_sample(self):
        res = self._write('post', '/regression-tests', self._admin(), {
            'sample_id': 999999, 'command': 'cmd',
            'categories': ['Broadcast']})
        self.assertEqual(res.status_code, 404)

    def test_create_regression_test_unknown_category(self):
        res = self._write('post', '/regression-tests', self._admin(), {
            'sample_id': self.sample_id, 'command': 'cmd',
            'categories': ['Broadcast', 'Nope']})

        # The whole request is rejected rather than silently dropping the
        # category the client believed it had set.
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['details']['fields']['categories'], ['Nope'])

    def test_create_regression_test_rejects_bad_output_type(self):
        res = self._write('post', '/regression-tests', self._admin(), {
            'sample_id': self.sample_id, 'command': 'cmd',
            'categories': ['Broadcast'], 'output_type': 'not-a-type'})
        self.assertEqual(res.status_code, 400)

    def test_create_regression_test_requires_categories(self):
        res = self._write('post', '/regression-tests', self._admin(), {
            'sample_id': self.sample_id, 'command': 'cmd'})
        self.assertEqual(res.status_code, 400)

    # ---- regression tests: update --------------------------------------

    def test_update_regression_test(self):
        res = self._write(
            'patch', f'/regression-tests/{self.existing_id}', self._admin(),
            {'command': 'updated command', 'description': 'new description'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['command'], 'updated command')
        self.assertEqual(res.json['description'], 'new description')
        self.assertEqual(RegressionTest.query.filter(
            RegressionTest.id == self.existing_id).first().command,
            'updated command')

    def test_update_regression_test_leaves_untouched_fields(self):
        res = self._write(
            'patch', f'/regression-tests/{self.existing_id}', self._admin(),
            {'description': 'only this'})

        self.assertEqual(res.status_code, 200)
        # command was not in the body, so it must survive unchanged.
        self.assertEqual(res.json['command'], 'original command')

    def test_update_regression_test_toggles_active(self):
        res = self._write(
            'patch', f'/regression-tests/{self.existing_id}', self._admin(),
            {'active': False})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json['active'])

    def test_update_regression_test_replaces_categories(self):
        res = self._write(
            'patch', f'/regression-tests/{self.existing_id}', self._admin(),
            {'categories': ['Unused']})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['categories'], ['Unused'])

    def test_update_regression_test_unknown_category(self):
        res = self._write(
            'patch', f'/regression-tests/{self.existing_id}', self._admin(),
            {'categories': ['Missing']})
        self.assertEqual(res.status_code, 400)

    def test_update_regression_test_empty_body(self):
        res = self._write(
            'patch', f'/regression-tests/{self.existing_id}', self._admin(),
            {})
        self.assertEqual(res.status_code, 400)

    def test_update_regression_test_not_found(self):
        res = self._write('patch', '/regression-tests/999999', self._admin(),
                          {'command': 'x'})
        self.assertEqual(res.status_code, 404)

    # ---- regression tests: detail and delete ---------------------------

    def test_get_regression_test_detail(self):
        output = RegressionTestOutput(
            self.existing_id, 'expected_hash', '.srt', 'expected_name')
        g.db.add(output)
        g.db.commit()
        g.db.add(RegressionTestOutputFiles('variant_hash', output.id))
        g.db.commit()

        res = self.client.get(
            f'/api/v1/regression-tests/{self.existing_id}',
            headers=self._as('rtw_user@local.com', 'userpass123', 'rt_detail',
                             ['runs:read']))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['regression_test_id'], self.existing_id)
        self.assertEqual(res.json['outputs'][0]['correct'], 'expected_hash')
        # Alternative accepted hashes travel with the baseline.
        self.assertEqual(res.json['outputs'][0]['variants'], ['variant_hash'])

    def test_get_regression_test_detail_not_found(self):
        res = self.client.get(
            '/api/v1/regression-tests/999999',
            headers=self._as('rtw_user@local.com', 'userpass123', 'rt_404',
                             ['runs:read']))
        self.assertEqual(res.status_code, 404)

    def test_delete_regression_test_without_history(self):
        res = self.client.delete(
            f'/api/v1/regression-tests/{self.existing_id}',
            headers=self._admin('rt_del'))

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(RegressionTest.query.filter(
            RegressionTest.id == self.existing_id).first())

    def test_delete_regression_test_removes_its_outputs(self):
        output = RegressionTestOutput(self.existing_id, 'h', '.srt', 'name')
        g.db.add(output)
        g.db.commit()
        output_id = output.id
        g.db.add(RegressionTestOutputFiles('variant', output_id))
        g.db.commit()

        res = self.client.delete(
            f'/api/v1/regression-tests/{self.existing_id}',
            headers=self._admin('rt_del2'))

        self.assertEqual(res.status_code, 200)
        # Baselines and variants are RESTRICT-linked, so they must be gone
        # too or the delete would have failed at the database.
        self.assertIsNone(RegressionTestOutput.query.filter(
            RegressionTestOutput.id == output_id).first())
        self.assertEqual(RegressionTestOutputFiles.query.filter_by(
            regression_test_output_id=output_id).count(), 0)

    def test_delete_regression_test_with_history_refused(self):
        g.db.add(TestResult(self.test_id, self.existing_id, 0, 0, 0))
        g.db.commit()

        res = self.client.delete(
            f'/api/v1/regression-tests/{self.existing_id}',
            headers=self._admin('rt_del3'))

        # Deleting would erase evidence of past regressions; retiring the
        # test is a PATCH with active=false instead.
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json['details']['result_count'], 1)
        self.assertIsNotNone(RegressionTest.query.filter(
            RegressionTest.id == self.existing_id).first())

    def test_delete_regression_test_not_found(self):
        res = self.client.delete('/api/v1/regression-tests/999999',
                                 headers=self._admin('rt_del4'))
        self.assertEqual(res.status_code, 404)

    # ---- categories ----------------------------------------------------

    def test_list_categories(self):
        res = self.client.get('/api/v1/categories', headers=self._admin())

        self.assertEqual(res.status_code, 200)
        names = [row['name'] for row in res.json['data']]
        # Alphabetical, so a client can render the rail without sorting.
        self.assertEqual(names, sorted(names))
        used = next(r for r in res.json['data'] if r['name'] == 'Broadcast')
        self.assertEqual(used['test_count'], 1)

    def test_create_category(self):
        res = self._write('post', '/categories', self._admin(),
                          {'name': 'Teletext', 'description': 'DVB teletext'})

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['name'], 'Teletext')
        self.assertEqual(res.json['test_count'], 0)
        self.assertIsNotNone(
            Category.query.filter(Category.name == 'Teletext').first())

    def test_create_category_duplicate_name(self):
        res = self._write('post', '/categories', self._admin(),
                          {'name': 'Broadcast'})
        self.assertEqual(res.status_code, 409)

    def test_create_category_allows_contributor(self):
        headers = self._as('rtw_contrib@local.com', 'contribpass123', 'cat_c',
                           ['runs:write'])
        res = self._write('post', '/categories', headers,
                          {'name': 'Contributed'})
        self.assertEqual(res.status_code, 201)

    def test_update_category_renames(self):
        res = self._write('patch', f'/categories/{self.free_category_id}',
                          self._admin(), {'name': 'Renamed'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['name'], 'Renamed')

    def test_update_category_to_existing_name(self):
        res = self._write('patch', f'/categories/{self.free_category_id}',
                          self._admin(), {'name': 'Broadcast'})
        self.assertEqual(res.status_code, 409)

    def test_update_category_keeping_own_name_is_allowed(self):
        # Re-sending the current name must not collide with itself.
        res = self._write('patch', f'/categories/{self.free_category_id}',
                          self._admin(),
                          {'name': 'Unused', 'description': 'new text'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['description'], 'new text')

    def test_update_category_empty_body(self):
        res = self._write('patch', f'/categories/{self.free_category_id}',
                          self._admin(), {})
        self.assertEqual(res.status_code, 400)

    def test_update_category_not_found(self):
        res = self._write('patch', '/categories/999999', self._admin(),
                          {'name': 'x'})
        self.assertEqual(res.status_code, 404)

    def test_delete_unused_category(self):
        res = self.client.delete(
            f'/api/v1/categories/{self.free_category_id}',
            headers=self._admin())

        self.assertEqual(res.status_code, 200)
        self.assertIsNone(Category.query.filter(
            Category.id == self.free_category_id).first())

    def test_delete_in_use_category_refused(self):
        res = self.client.delete(f'/api/v1/categories/{self.category_id}',
                                 headers=self._admin())

        # Dropping it would change which tests a suite selection picks up.
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json['details']['regression_test_count'], 1)
        self.assertIsNotNone(Category.query.filter(
            Category.id == self.category_id).first())

    def test_delete_category_not_found(self):
        res = self.client.delete('/api/v1/categories/999999',
                                 headers=self._admin())
        self.assertEqual(res.status_code, 404)
