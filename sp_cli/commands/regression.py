"""``sp regression`` — list regression-test definitions."""

from typing import Optional

import click

from sp_cli.runner import clean_params, fetch_and_render


@click.group()
def regression() -> None:
    """List regression-test definitions."""


@regression.command('ls')
@click.option('--category', default=None, help='Filter by category name.')
@click.option('--tag', default=None, help='Filter by tag.')
@click.option('--active/--all', 'active', default=None, help='Only active tests (default: all).')
@click.option('--sample-id', type=int, default=None, help='Filter by sample id.')
@click.option('--limit', type=int, default=None, help='Page size (max 100).')
@click.option('--offset', type=int, default=None, help='Pagination offset.')
@click.pass_context
def regression_ls(ctx: click.Context, category: Optional[str], tag: Optional[str],
                  active: Optional[bool], sample_id: Optional[int],
                  limit: Optional[int], offset: Optional[int]) -> None:
    """List regression-test definitions."""
    params = clean_params({'category': category, 'tag': tag, 'active': active,
                           'sample_id': sample_id, 'limit': limit, 'offset': offset})
    fetch_and_render(ctx, '/regression-tests', params)
