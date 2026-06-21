"""``sp health`` and ``sp queue`` — system status commands."""

from typing import Optional

import click

from sp_cli.runner import clean_params, fetch_and_render


@click.command('health')
@click.pass_context
def health(ctx: click.Context) -> None:
    """Show CI system health and dependency status."""
    fetch_and_render(ctx, '/system/health')


@click.command('queue')
@click.option('--platform', default=None, help='linux|windows')
@click.option('--status', default=None, help='queued|running')
@click.pass_context
def queue(ctx: click.Context, platform: Optional[str], status: Optional[str]) -> None:
    """Show queue depth and currently running jobs."""
    fetch_and_render(ctx, '/system/queue', clean_params({'platform': platform, 'status': status}))
