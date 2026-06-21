"""``sp investigate`` — one-shot triage of a run (status + counts + classified failures)."""

from typing import Any, Dict, List

import click

from sp_cli.client import ApiError
from sp_cli.output import render, render_error
from sp_cli.triage import classify_sample, group_by_code, is_failure

_RUN_FIELDS = ('run_id', 'pr_number', 'platform', 'commit_sha', 'branch', 'status', 'github_link')


@click.command('investigate')
@click.argument('run_id', type=int)
@click.pass_context
def investigate(ctx: click.Context, run_id: int) -> None:
    """Triage a run in one shot: run info, pass/fail counts, and classified failures.

    Combines the run detail, summary, and per-result classification into a single
    report — the whole "what failed and why" investigation in one command.
    """
    client = ctx.obj['client']
    output = ctx.obj['output']
    try:
        run = client.get(f'/runs/{run_id}')
        summary = client.get(f'/runs/{run_id}/summary')
        samples = client.get_paginated(f'/runs/{run_id}/samples')
    except ApiError as error:
        render_error(error, output)
        raise SystemExit(error.exit_code)

    failures = [classify_sample(s) for s in samples if is_failure(s)]
    report = {
        'run': {field: run.get(field) for field in _RUN_FIELDS},
        'summary': summary,
        'by_code': group_by_code(failures),
        'failures': failures,
    }

    if output == 'json':
        render(report, 'json')
    else:
        _print_digest(report)


def _print_digest(report: Dict[str, Any]) -> None:
    """
    Print a human-readable investigation digest.

    :param report: The assembled investigation report.
    :type report: Dict[str, Any]
    """
    run = report['run']
    summary = report['summary']
    header = (f"Run {run.get('run_id')} · PR {run.get('pr_number')} · {run.get('platform')} · "
              f"{run.get('commit_sha')} · {str(run.get('status')).upper()}")
    click.echo(header)
    click.echo(f"  {summary.get('fail_count')} failed / {summary.get('total_samples')} total"
               f"  ({summary.get('pass_count')} pass)")

    by_code = report['by_code']
    if by_code:
        click.echo()
        click.echo("  by code:")
        for code, count in by_code.items():
            click.echo(f"    {str(count).rjust(4)}  {code}")

    failures: List[Dict[str, Any]] = report['failures']
    if failures:
        click.echo()
        render({'data': failures}, 'table')
