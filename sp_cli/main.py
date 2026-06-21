"""Entry point and root command group for the ``sp`` CLI."""

from typing import Optional

import click

from sp_cli import __version__
from sp_cli.client import ApiClient
from sp_cli.commands.auth import auth
from sp_cli.commands.investigate import investigate
from sp_cli.commands.regression import regression
from sp_cli.commands.run import run
from sp_cli.commands.sample import sample
from sp_cli.commands.system import health, queue

DEFAULT_BASE_URL = 'http://localhost:5000/api/v1'


@click.group(invoke_without_command=True)
@click.option('--base-url', envvar='SP_BASE_URL', default=DEFAULT_BASE_URL, show_default=True,
              help='API base URL incl. the /api/v1 prefix. Env: SP_BASE_URL.')
@click.option('--token', envvar='SP_API_TOKEN', default=None,
              help='Bearer token sent with each request. Env: SP_API_TOKEN.')
@click.option('--output', '-o', type=click.Choice(['json', 'table']), default='json', show_default=True,
              help='Output format.')
@click.option('--timeout', type=int, default=30, show_default=True, help='Per-request timeout (seconds).')
@click.version_option(__version__, prog_name='sp')
@click.pass_context
def cli(ctx: click.Context, base_url: str, token: Optional[str], output: str, timeout: int) -> None:
    """AI-friendly CLI for the CCExtractor CI / Sample Platform.

    Emits JSON by default so it can be driven by agents and scripts. Point it at
    a running platform with --base-url or the SP_BASE_URL environment variable,
    and authenticate with a token via --token / SP_API_TOKEN (see `sp auth login`).
    """
    ctx.obj = {
        'client': ApiClient(base_url, token=token, timeout=timeout),
        'output': output,
    }
    if ctx.invoked_subcommand is None:
        from sp_cli.banner import show_welcome
        show_welcome()


cli.add_command(investigate)
cli.add_command(run)
cli.add_command(sample)
cli.add_command(regression)
cli.add_command(auth)
cli.add_command(health)
cli.add_command(queue)
