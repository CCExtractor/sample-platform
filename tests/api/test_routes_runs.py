import json
from unittest.mock import patch

from flask import g

from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)
from tests.api.base import ApiTestCase


class TestRoutesRuns(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.setup_run_data('runs')
        self.progress = TestProgress(
            self.test_id, TestStatus.preparation, "Queued")
        g.db.add(self.progress)
        g.db.commit()
        patcher = patch.dict(
            'mod_api.middleware.rate_limit._rate_limit_store', {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        # create_run checks for a CI build artifact via GitHub; stub it as
        # present by default so tests don't make network calls. The
        # no-artifact path is covered explicitly in
        # test_create_run_no_artifact_rejected.
        artifact_patcher = patch(
            'mod_api.routes.runs._ci_artifact_exists', return_value=True)
        artifact_patcher.start()
        self.addCleanup(artifact_patcher.stop)

    def test_list_runs(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't1', scopes=['runs:read'])
        res = self.client.get(
            '/api/v1/runs', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        # BaseTestCase.setUp creates 2 Test objects; this setUp creates 1 more = 3 total
        self.assertEqual(len(res.json['data']), 3)
        self.assertTrue(
            any(r['run_id'] == self.test_id for r in res.json['data']))

    def test_list_runs_filters(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't2', scopes=['runs:read'])
        # Invalid platform
        res = self.client.get('/api/v1/runs?platform=invalid',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)

        # Valid platform
        res = self.client.get('/api/v1/runs?platform=linux',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 3)

        # Invalid repository
        res = self.client.get('/api/v1/runs?repository=invalid_repo',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)

    def test_list_runs_status_filter(self):
        # We already have a TestProgress 'preparation' from setUp.
        # Add a 'testing' one to make the run have 'running' / 'testing' status?
        # Wait, the frontend query asks for 'testing'. The API uses 'running' or 'testing' in some places.
        # Let's insert a TestStatus.testing progress to make the
        # derive_run_status be 'running'
        prog2 = TestProgress(self.test_id, TestStatus.testing, "Testing")
        g.db.add(prog2)
        g.db.commit()

        token = self.get_token('runs_user@local.com',
                               'userpass123', 't3', scopes=['runs:read'])
        res = self.client.get('/api/v1/runs?status=running',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)

    def test_list_runs_status_queued(self):
        # A run with no TestProgress rows is 'queued'. This guards the
        # status=queued filter, which must emit SQL `IS NULL`
        # (TestProgress.id.is_(None)) rather than a Python identity check.
        queued_test = Test(TestPlatform.linux, TestType.commit,
                           self.fork.id, 'master', 'queued_commit')
        g.db.add(queued_test)
        g.db.commit()
        queued_id = queued_test.id  # capture before the request detaches it

        token = self.get_token('runs_user@local.com',
                               'userpass123', 'tq', scopes=['runs:read'])
        res = self.client.get('/api/v1/runs?status=queued',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        run_ids = [r['run_id'] for r in res.json['data']]
        # The new run (no progress) is queued; the setUp run (has progress) is not.
        self.assertIn(queued_id, run_ids)
        self.assertNotIn(self.test_id, run_ids)

    @patch('mod_api.routes.runs._ci_artifact_exists', return_value=False)
    @patch('run.config')
    def test_create_run_no_artifact_rejected(self, mock_config, _mock_artifact):
        # When no CI build artifact exists for the commit+platform, the run
        # cannot execute, so create_run must reject it with 422 rather than
        # accepting a run that would fail silently in the worker.
        mock_config.get.side_effect = lambda k, d='': 'testowner' if k == 'GITHUB_OWNER' else 'testrepo'

        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 'tna', scopes=['runs:write'])
        payload = {
            'commit_sha': 'a' * 40,
            'platform': 'linux',
            'repository': 'testowner/testrepo',
            'regression_test_ids': [],
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json['code'], 'unprocessable')

    @patch('run.config')
    def test_create_run(self, mock_config):
        mock_config.get.side_effect = lambda k, d='': 'testowner' if k == 'GITHUB_OWNER' else 'testrepo'

        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't4', scopes=['runs:write'])
        payload = {
            'commit_sha': 'a' * 40,
            'platform': 'windows',
            'repository': 'testowner/testrepo',
            'regression_test_ids': []
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        # Empty regression_test_ids gives 400 validation error
        self.assertEqual(res.status_code, 400)

        # Test omitting regression_test_ids completely (it fetches active)
        payload.pop('regression_test_ids')
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 202)
        self.assertIn('run_id', res.json)

    def test_get_run(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't5', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['run_id'], self.test_id)

    def test_get_run_summary(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't6', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/summary', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['run_id'], self.test_id)
        self.assertIn('total_samples', res.json)

    def test_get_run_progress(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't7', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/progress', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        self.assertEqual(res.json['data'][0]['status'], 'preparation')

    def test_get_run_config(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't8', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/config', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['platform'], 'linux')

    def test_cancel_run(self):
        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't9', scopes=['runs:write'])
        res = self.client.post(
            f'/api/v1/runs/{self.test_id}/cancel', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.json['status'], 'accepted')

        # Verify db change
        progs = TestProgress.query.filter_by(test_id=self.test_id).all()
        self.assertEqual(progs[-1].status, TestStatus.canceled)

    def test_restart_run(self):
        token = self.get_token('runs_admin@local.com', 'adminpass123',
                               'restart1', scopes=['runs:write'])
        res = self.client.post(
            f'/api/v1/runs/{self.test_id}/restart',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.json['status'], 'accepted')
        # An empty progress trail is what makes CI pick the run up again.
        self.assertEqual(
            TestProgress.query.filter_by(test_id=self.test_id).count(), 0)
        self.assertEqual(
            TestResult.query.filter_by(test_id=self.test_id).count(), 0)

    def test_restart_run_not_found(self):
        token = self.get_token('runs_admin@local.com', 'adminpass123',
                               'restart2', scopes=['runs:write'])
        res = self.client.post(
            '/api/v1/runs/999999/restart',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 404)

    def test_restart_run_requires_write_role(self):
        token = self.get_token('runs_user@local.com', 'userpass123',
                               'restart3', scopes=['runs:write'])
        res = self.client.post(
            f'/api/v1/runs/{self.test_id}/restart',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 403)

    def test_cancel_run_idempotency(self):
        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't10', scopes=['runs:write'])
        # First cancel
        res = self.client.post(
            f'/api/v1/runs/{self.test_id}/cancel', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 202)

        # Second cancel should still be 202
        res2 = self.client.post(
            f'/api/v1/runs/{self.test_id}/cancel', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res2.status_code, 202)
        self.assertEqual(res2.json['status'], 'no_op')

    @patch('run.config')
    def test_create_run_inactive_regression_test(self, mock_config):
        mock_config.get.side_effect = lambda k, d='': 'testowner' if k == 'GITHUB_OWNER' else 'testrepo'

        # Make a regression test inactive
        from mod_regression.models import (Category, InputType, OutputType,
                                           RegressionTest)
        cat = Category('testcat', 'desc')
        g.db.add(cat)
        g.db.commit()
        reg_test = RegressionTest(
            1, 'command', InputType.file, OutputType.file, cat.id, 0)
        reg_test.active = False
        g.db.add(reg_test)
        g.db.flush()
        reg_test_id = reg_test.id
        g.db.commit()

        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't11', scopes=['runs:write'])
        payload = {
            'commit_sha': 'a' * 40,
            'platform': 'windows',
            'repository': 'testowner/testrepo',
            'regression_test_ids': [reg_test_id]
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 422)
        self.assertIn('inactive', res.json['message'])

    def test_create_run_fork_owner_can_trigger(self):
        # Verify that a user who owns a fork can trigger a run on it
        self.user.github_login = 'userfork'
        g.db.add(self.user)
        g.db.commit()

        # Trigger run on a fork repo using contributor user
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't12', scopes=['runs:write'])
        payload = {
            'commit_sha': 'b' * 40,
            'platform': 'windows',
            'repository': 'userfork/testrepo'
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 202)

    def test_run_summary_fail_count_ignores_test_failed_flag(self):
        # Ignore expected outputs so missing-output doesn't trigger first
        from mod_regression.models import RegressionTestOutput
        outputs = RegressionTestOutput.query.filter_by(regression_id=1).all()
        for o in outputs:
            o.ignore = True
            g.db.add(o)

        # set up test result with exit code mismatch (which counts as fail)
        tr = TestResult(self.test_id, 1, 100, 1, 0)
        g.db.add(tr)
        g.db.commit()

        token = self.get_token('runs_user@local.com',
                               'userpass123', 't13', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/summary', headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['fail_count'], 1)
        self.assertEqual(res.json['pass_count'], 0)

    def test_missing_output_not_double_counted_in_fail(self):
        # Insert a dummy RegressionTestOutput with id = -1 to satisfy foreign
        # key constraints
        from mod_regression.models import RegressionTestOutput
        dummy_out = RegressionTestOutput(1, '', '', '')
        dummy_out.id = -1
        g.db.add(dummy_out)
        g.db.commit()

        # exit code mismatch (would be fail)
        tr = TestResult(self.test_id, 1, 100, 1, 0)
        # but dummy row takes priority -> missing_output
        rf = TestResultFile(self.test_id, 1, -1, '', 'error')
        g.db.add_all([tr, rf])
        g.db.commit()

        token = self.get_token('runs_user@local.com',
                               'userpass123', 't14', scopes=['runs:read'])
        res = self.client.get(
            f'/api/v1/runs/{self.test_id}/summary', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['missing_output_count'], 1)
        self.assertEqual(res.json['fail_count'], 0)

    def test_cancel_run_reason_too_short(self):
        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't15', scopes=['runs:write'])
        res = self.client.post(f'/api/v1/runs/{self.test_id}/cancel',
                               data=json.dumps({'reason': 'no'}),
                               content_type='application/json',
                               headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_create_run_rejects_extra_fields(self):
        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't17', scopes=['runs:write'])
        payload = {
            'commit_sha': 'a' * 40,
            'platform': 'linux',
            'repository': 'testowner/testrepo',
            'unexpected_field': 'evil_val'
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_create_run_invalid_commit_sha_rejected(self):
        token = self.get_token('runs_admin@local.com',
                               'adminpass123', 't18', scopes=['runs:write'])
        payload = {
            'commit_sha': 'shortsha',
            'platform': 'linux',
            'repository': 'testowner/testrepo'
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_get_run_nonexistent_resource_404(self):
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't19', scopes=['runs:read'])
        res = self.client.get('/api/v1/runs/999999',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json['code'], 'not_found')

    def test_create_run_non_admin_forbidden(self):
        token = self.get_token(
            'runs_user@local.com',
            'userpass123',
            't_non_admin',
            scopes=['runs:write'])
        payload = {
            'commit_sha': 'a' * 40,
            'platform': 'windows',
            'repository': 'testowner/testrepo'
        }
        res = self.client.post(
            '/api/v1/runs',
            data=json.dumps(payload),
            content_type='application/json',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 403)

    def test_list_runs_pagination(self):
        # BaseTestCase.setUp creates 2 Test objects; this setUp creates 1 more = 3 total
        token = self.get_token('runs_user@local.com',
                               'userpass123', 't_pag', scopes=['runs:read'])
        # Fetch first page with limit=2
        res1 = self.client.get('/api/v1/runs?limit=2',
                               headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(len(res1.json['data']), 2)

        # Fetch second page with offset=2
        res2 = self.client.get(
            '/api/v1/runs?limit=2&offset=2',
            headers={
                'Authorization': f'Bearer {token}'})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.json['data']), 1)
