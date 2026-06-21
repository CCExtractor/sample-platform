"""``sp sample`` — list and inspect media samples."""

from typing import Optional

import click

from sp_cli.runner import clean_params, fetch_and_render


@click.group()
def sample() -> None:
    """List and inspect media samples."""


@sample.command('ls')
@click.option('--name', default=None, help='Filter by sample name.')
@click.option('--tag', default=None, help='Filter by tag.')
@click.option('--extension', default=None, help='Filter by file extension.')
@click.option('--limit', type=int, default=None, help='Page size (max 100).')
@click.option('--offset', type=int, default=None, help='Pagination offset.')
@click.pass_context
def sample_ls(ctx: click.Context, name: Optional[str], tag: Optional[str],
              extension: Optional[str], limit: Optional[int], offset: Optional[int]) -> None:
    """List known media samples."""
    params = clean_params({'name': name, 'tag': tag, 'extension': extension,
                           'limit': limit, 'offset': offset})
    fetch_and_render(ctx, '/samples', params)


@sample.command('show')
@click.argument('sample_id', type=int)
@click.pass_context
def sample_show(ctx: click.Context, sample_id: int) -> None:
    """Show metadata for a single sample."""
    fetch_and_render(ctx, f'/samples/{sample_id}')


@sample.command('history')
@click.argument('sample_id', type=int)
@click.option('--platform', default=None, help='linux|windows')
@click.option('--limit', type=int, default=None, help='Page size (max 100).')
@click.pass_context
def sample_history(ctx: click.Context, sample_id: int, platform: Optional[str],
                   limit: Optional[int]) -> None:
    """Show this sample's result history across runs."""
    params = clean_params({'platform': platform, 'limit': limit})
    fetch_and_render(ctx, f'/samples/{sample_id}/history', params)
