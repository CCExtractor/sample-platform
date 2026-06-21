"""Tests for the sp CLI command surface, mocking the API client."""

import json
import unittest
from unittest import mock

from click.testing import CliRunner

from sp_cli.client import ApiError
from sp_cli.main import cli

RUNS_PAGE = {
    'data': [{'run_id': 9299, 'status': 'fail', 'platform': 'windows', 'commit_sha': 'e6cd34e'}],
    'pagination': {'limit': 50, 'offset': 0, 'total': 1, 'next_offset': None},
}

# A run's results: a segfault, an exit mismatch, a missing output, and a pass.
RUN_SAMPLES = [
    {'regression_test_id': 18, 'sample_name': 'dvb', 'categories': ['DVB'],
     'status': 'fail', 'exit_code': -1073741819, 'expected_rc': 0, 'outputs': []},
    {'regression_test_id': 137, 'sample_name': 'cea708', 'categories': ['CEA-708'],
     'status': 'fail', 'exit_code': 10, 'expected_rc': 0, 'outputs': []},
    {'regression_test_id': 7, 'sample_name': 'broken', 'categories': ['Broken'],
     'status': 'missing_output', 'exit_code': 0, 'expected_rc': 0, 'outputs': []},
    {'regression_test_id': 1, 'sample_name': 'ok', 'categories': ['General'],
     'status': 'pass', 'exit_code': 0, 'expected_rc': 0, 'outputs': []},
]


class CliCommandTests(unittest.TestCase):
    """Exercise the CLI commands with a mocked client."""

    def setUp(self):
        """Create a runner for each test."""
        self.runner = CliRunner()

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_ls_calls_runs_with_filters(self, mock_get):
        """`run ls` hits /runs and forwards set filters only."""
        mock_get.return_value = RUNS_PAGE
        result = self.runner.invoke(cli, ['run', 'ls', '--platform', 'windows'])

        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with('/runs', params={'platform': 'windows'})

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_show(self, mock_get):
        """`run show <id>` targets the run detail path."""
        mock_get.return_value = {'run_id': 9299, 'status': 'fail'}
        result = self.runner.invoke(cli, ['run', 'show', '9299'])

        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with('/runs/9299', params=None)

    @mock.patch('sp_cli.client.ApiClient.get_paginated')
    def test_run_failures_classifies(self, mock_paginated):
        """`run failures` keeps only failures and labels each with a code."""
        mock_paginated.return_value = RUN_SAMPLES
        result = self.runner.invoke(cli, ['run', 'failures', '9299'])

        self.assertEqual(result.exit_code, 0)
        mock_paginated.assert_called_once_with('/runs/9299/samples')
        data = json.loads(result.output)
        codes = {row['regression_test_id']: row['code'] for row in data['data']}
        self.assertEqual(codes, {18: 'SEGFAULT', 137: 'EXIT_CODE_MISMATCH', 7: 'MISSING_OUTPUT'})
        self.assertEqual(data['summary'], {'failures': 3, 'of_total': 4})

    @mock.patch('sp_cli.client.ApiClient.get_paginated')
    def test_run_failures_table_output(self, mock_paginated):
        """Table mode renders the classification columns."""
        mock_paginated.return_value = RUN_SAMPLES
        result = self.runner.invoke(cli, ['-o', 'table', 'run', 'failures', '9299'])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('SEGFAULT', result.output)
        self.assertIn('code', result.output)

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_sample_ls(self, mock_get):
        """`sample ls` hits /samples."""
        mock_get.return_value = {'data': [], 'pagination': {'total': 0, 'next_offset': None}}
        result = self.runner.invoke(cli, ['sample', 'ls', '--tag', 'teletext'])

        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with('/samples', params={'tag': 'teletext'})

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_health(self, mock_get):
        """`sp health` hits /system/health."""
        mock_get.return_value = {'status': 'ok', 'dependencies': []}
        result = self.runner.invoke(cli, ['health'])

        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with('/system/health', params=None)

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_not_found_maps_to_exit_code_and_stderr(self, mock_get):
        """A not-found error exits 4 with a JSON envelope on stderr."""
        mock_get.side_effect = ApiError('not_found', 'Run 9 not found', 404)
        result = self.runner.invoke(cli, ['run', 'show', '9'])

        self.assertEqual(result.exit_code, 4)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'not_found')

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_result(self, mock_get):
        """`run result <run> <sample>` targets the result-detail path."""
        mock_get.return_value = {'regression_test_id': 137, 'status': 'fail'}
        result = self.runner.invoke(cli, ['run', 'result', '9299', '5'])

        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with('/runs/9299/samples/5', params=None)

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_diff_auto_resolves_hidden_ids(self, mock_get):
        """`run diff` resolves the media sample id + regression/output ids from detail."""
        mock_get.side_effect = [
            {'regression_test_id': 137, 'sample_id': 42,
             'outputs': [{'output_id': 2, 'status': 'fail'}]},
            {'status': 'different', 'hunks': []},
        ]
        result = self.runner.invoke(cli, ['run', 'diff', '9299', '5'])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(mock_get.call_count, 2)
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], '/runs/9299/samples/42/regression-tests/137/outputs/2/diff')
        self.assertEqual(kwargs['params'], {})

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_diff_with_explicit_ids_uses_media_sample_from_detail(self, mock_get):
        """Explicit --regression/--output still fetch detail for the media sample id."""
        mock_get.side_effect = [
            {'regression_test_id': 137, 'sample_id': 42, 'outputs': []},
            {'status': 'different', 'hunks': []},
        ]
        result = self.runner.invoke(cli, ['run', 'diff', '9299', '5', '--regression', '137', '--output', '2'])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(mock_get.call_count, 2)
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], '/runs/9299/samples/42/regression-tests/137/outputs/2/diff')
        self.assertEqual(kwargs['params'], {})

    @mock.patch('sp_cli.client.ApiClient.request')
    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_approve_baseline_resolves_media_sample_and_posts(self, mock_get, mock_request):
        """`run approve-baseline` POSTs to the media-sample path resolved from detail."""
        mock_get.return_value = {'regression_test_id': 137, 'sample_id': 42, 'outputs': []}
        mock_request.return_value = {'status': 'approved', 'run_id': 9299, 'sample_id': 42,
                                     'regression_id': 137, 'output_id': 2}
        result = self.runner.invoke(cli, ['run', 'approve-baseline', '9299', '5',
                                          '--regression', '137', '--output', '2', '--remove-variants'])

        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with('/runs/9299/samples/5')
        mock_request.assert_called_once_with(
            'POST', '/runs/9299/samples/42/baseline-approval',
            json_body={'regression_id': 137, 'output_id': 2, 'remove_variants': True})

    @mock.patch('sp_cli.client.ApiClient.get')
    def test_run_approve_baseline_requires_regression_and_output(self, mock_get):
        """Approving a baseline refuses to run without the explicit target ids."""
        result = self.runner.invoke(cli, ['run', 'approve-baseline', '9299', '5'])

        self.assertNotEqual(result.exit_code, 0)
        mock_get.assert_not_called()

    @mock.patch('sp_cli.client.ApiClient.get_paginated')
    @mock.patch('sp_cli.client.ApiClient.get')
    def test_investigate_combines_run_summary_and_failures(self, mock_get, mock_paginated):
        """`investigate` merges run detail, summary, and classified failures."""
        mock_get.side_effect = [
            {'run_id': 9299, 'pr_number': 2264, 'platform': 'windows', 'status': 'fail'},
            {'run_id': 9299, 'total_samples': 4, 'pass_count': 1, 'fail_count': 3},
        ]
        mock_paginated.return_value = RUN_SAMPLES
        result = self.runner.invoke(cli, ['investigate', '9299'])

        self.assertEqual(result.exit_code, 0)
        report = json.loads(result.output)
        self.assertEqual(report['run']['pr_number'], 2264)
        self.assertEqual(report['summary']['fail_count'], 3)
        self.assertEqual(report['by_code'],
                         {'SEGFAULT': 1, 'EXIT_CODE_MISMATCH': 1, 'MISSING_OUTPUT': 1})
        self.assertEqual(len(report['failures']), 3)
