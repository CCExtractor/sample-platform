"""``sp run`` — list, inspect, and triage CI runs."""

from typing import Any, Dict, List, Optional, Tuple

import click

from sp_cli.client import ApiError
from sp_cli.output import render, render_error
from sp_cli.runner import clean_params, fetch_and_render
from sp_cli.triage import classify_sample, is_failure


@click.group()
def run() -> None:
    """List, inspect, and triage CI runs."""


@run.command('ls')
@click.option('--status', default=None, help='queued|running|pass|fail|canceled|error|incomplete')
@click.option('--platform', default=None, help='linux|windows')
@click.option('--branch', default=None, help='Filter by branch name.')
@click.option('--commit', 'commit_sha', default=None, help='Full 40-char commit SHA.')
@click.option('--limit', type=int, default=None, help='Page size (max 100).')
@click.option('--offset', type=int, default=None, help='Pagination offset.')
@click.pass_context
def run_ls(ctx: click.Context, status: Optional[str], platform: Optional[str], branch: Optional[str],
           commit_sha: Optional[str], limit: Optional[int], offset: Optional[int]) -> None:
    """List CI runs (newest first)."""
    params = clean_params({'status': status, 'platform': platform, 'branch': branch,
                           'commit_sha': commit_sha, 'limit': limit, 'offset': offset})
    fetch_and_render(ctx, '/runs', params)


@run.command('show')
@click.argument('run_id', type=int)
@click.pass_context
def run_show(ctx: click.Context, run_id: int) -> None:
    """Show a single run's details."""
    fetch_and_render(ctx, f'/runs/{run_id}')


@run.command('summary')
@click.argument('run_id', type=int)
@click.pass_context
def run_summary(ctx: click.Context, run_id: int) -> None:
    """Show a run's pass/fail summary."""
    fetch_and_render(ctx, f'/runs/{run_id}/summary')


@run.command('failures')
@click.argument('run_id', type=int)
@click.pass_context
def run_failures(ctx: click.Context, run_id: int) -> None:
    """Show a run's failing tests, each labeled with a classification code."""
    client = ctx.obj['client']
    output = ctx.obj['output']
    try:
        samples = client.get_paginated(f'/runs/{run_id}/samples')
    except ApiError as error:
        render_error(error, output)
        raise SystemExit(error.exit_code)

    rows = [classify_sample(s) for s in samples if is_failure(s)]
    render({'data': rows, 'summary': {'failures': len(rows), 'of_total': len(samples)}}, output)


@run.command('results')
@click.argument('run_id', type=int)
@click.option('--status', default=None, help='pass|fail|skipped|missing_output|running|not_started')
@click.option('--limit', type=int, default=None, help='Page size (max 100).')
@click.option('--offset', type=int, default=None, help='Pagination offset.')
@click.pass_context
def run_results(ctx: click.Context, run_id: int, status: Optional[str],
                limit: Optional[int], offset: Optional[int]) -> None:
    """List all regression-test results in a run."""
    params = clean_params({'status': status, 'limit': limit, 'offset': offset})
    fetch_and_render(ctx, f'/runs/{run_id}/samples', params)


@run.command('result')
@click.argument('run_id', type=int)
@click.argument('sample_id', type=int)
@click.pass_context
def run_result(ctx: click.Context, run_id: int, sample_id: int) -> None:
    """Show full details for a single regression-test result in a run."""
    fetch_and_render(ctx, f'/runs/{run_id}/samples/{sample_id}')


@run.command('diff')
@click.argument('run_id', type=int)
@click.argument('sample_id', type=int)
@click.option('--regression', 'regression_id', type=int, default=None,
              help='Regression test id (auto-resolved if omitted).')
@click.option('--output', 'output_id', type=int, default=None,
              help='Output file id (auto-resolved if omitted).')
@click.option('--context', 'context_lines', type=int, default=None, help='Diff context lines.')
@click.pass_context
def run_diff(ctx: click.Context, run_id: int, sample_id: int, regression_id: Optional[int],
             output_id: Optional[int], context_lines: Optional[int]) -> None:
    """Show the expected-vs-actual diff for a failing result.

    Resolves the (regression, output) ids automatically when omitted, so you
    don't need the hidden ids the web UI requires to build a diff URL.
    """
    client = ctx.obj['client']
    output = ctx.obj['output']
    try:
        targets = _resolve_diff_targets(client, run_id, sample_id, regression_id, output_id)
        if not targets:
            raise ApiError('not_found', 'No differing output to diff for this result', 404)
        diffs = []
        for media_sample_id, reg_id, out_id in targets:
            params = clean_params({'context_lines': context_lines})
            diffs.append(client.get(
                f'/runs/{run_id}/samples/{media_sample_id}'
                f'/regression-tests/{reg_id}/outputs/{out_id}/diff',
                params=params))
    except ApiError as error:
        render_error(error, output)
        raise SystemExit(error.exit_code)

    render(diffs[0] if len(diffs) == 1 else {'data': diffs}, output)


@run.command('approve-baseline')
@click.argument('run_id', type=int)
@click.argument('sample_id', type=int)
@click.option('--regression', 'regression_id', type=int, required=True,
              help='Regression test id of the result to approve.')
@click.option('--output', 'output_id', type=int, required=True,
              help="Output file id whose actual output becomes the new baseline.")
@click.option('--remove-variants', is_flag=True, default=False,
              help='Remove all platform-specific variants (see WARNING below).')
@click.pass_context
def run_approve_baseline(ctx: click.Context, run_id: int, sample_id: int,
                         regression_id: int, output_id: int, remove_variants: bool) -> None:
    """Approve a result's actual output as the new expected baseline.

    Requires admin privileges (the ``baselines:write`` scope).

    WARNING: --remove-variants makes this output the single source of truth
    across ALL platforms by deleting every platform-specific variant. This
    applies globally and cannot be undone from the CLI -- use with care.

    --regression and --output are required (no auto-resolution): approving a
    baseline is destructive, so the exact target must be stated explicitly.
    """
    client = ctx.obj['client']
    output = ctx.obj['output']
    try:
        # The endpoint's <sample_id> path slot is the *media* sample id, which
        # differs from the regression-result id passed on the command line.
        # Resolve it from the result detail (same contract as `run diff`).
        detail = client.get(f'/runs/{run_id}/samples/{sample_id}')
        media_sample_id = detail.get('sample_id')
        if media_sample_id is None:
            raise ApiError('not_found', 'Could not resolve the media sample for this result', 404)
        body = {'regression_id': regression_id, 'output_id': output_id,
                'remove_variants': remove_variants}
        result = client.request(
            'POST', f'/runs/{run_id}/samples/{media_sample_id}/baseline-approval',
            json_body=body)
    except ApiError as error:
        render_error(error, output)
        raise SystemExit(error.exit_code)

    render(result, output)


@run.command('artifacts')
@click.argument('run_id', type=int)
@click.pass_context
def run_artifacts(ctx: click.Context, run_id: int) -> None:
    """List downloadable artifacts for a run (signed URLs)."""
    fetch_and_render(ctx, f'/runs/{run_id}/artifacts')


@run.command('logs')
@click.argument('run_id', type=int)
@click.pass_context
def run_logs(ctx: click.Context, run_id: int) -> None:
    """Show raw logs for a run (requires contributor or admin privileges)."""
    fetch_and_render(ctx, f'/runs/{run_id}/logs')


@run.command('errors')
@click.argument('run_id', type=int)
@click.option('--type', 'error_type', default=None,
              help='test_failure|exit_code_mismatch|missing_output|diff_mismatch')
@click.pass_context
def run_errors(ctx: click.Context, run_id: int, error_type: Optional[str]) -> None:
    """Show structured test errors for a run."""
    fetch_and_render(ctx, f'/runs/{run_id}/errors', clean_params({'type': error_type}))


def _resolve_diff_targets(client: Any, run_id: int, sample_id: int,
                          regression_id: Optional[int],
                          output_id: Optional[int]) -> List[Tuple[int, int, int]]:
    """
    Resolve the (media_sample_id, regression_id, output_id) triples to diff.

    The diff endpoint is keyed by the *media* sample id, the regression test
    id, and the output file id -- three different numbers. The CLI's
    ``sample_id`` argument is the result id within the run (the regression test
    id), so we always fetch the result detail to recover the media sample id
    (``detail['sample_id']``) and the differing output(s), and let the caller
    pass explicit ids only to narrow which output(s) to diff.

    :param client: The API client.
    :type client: Any
    :param run_id: The run id.
    :type run_id: int
    :param sample_id: The result id within the run (the regression test id).
    :type sample_id: int
    :param regression_id: Optional explicit regression id override.
    :type regression_id: Optional[int]
    :param output_id: Optional explicit output id to diff.
    :type output_id: Optional[int]
    :return: A list of ``(media_sample_id, regression_id, output_id)`` triples.
    :rtype: List[Tuple[int, int, int]]
    """
    detail = client.get(f'/runs/{run_id}/samples/{sample_id}')
    media_sample_id = detail.get('sample_id')
    reg_id = regression_id if regression_id is not None else detail.get('regression_test_id')
    if media_sample_id is None or reg_id is None:
        return []

    outputs = detail.get('outputs') or []
    # The API reports per-output status as pass|fail|missing_output; anything
    # not 'pass' is worth diffing. Fall back to all outputs if none qualify.
    differing = [o for o in outputs if o.get('status') not in (None, 'pass')] or outputs

    if output_id is not None:
        return [(media_sample_id, reg_id, output_id)]
    return [(media_sample_id, reg_id, o.get('output_id')) for o in differing
            if o.get('output_id') is not None]
