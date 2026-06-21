"""``sp auth`` — obtain and revoke API tokens."""

import click

from sp_cli.client import ApiError
from sp_cli.output import render, render_error


@click.group()
def auth() -> None:
    """Obtain and revoke API tokens."""


@auth.command('login')
@click.option('--email', prompt=True, help='Account email.')
@click.option('--password', prompt=True, hide_input=True, help='Account password (never stored).')
@click.option('--name', 'token_name', default='sp-cli', show_default=True, help='Token label.')
@click.option('--days', 'expires_in_days', type=int, default=30, show_default=True,
              help='Token lifetime in days (max 90).')
@click.pass_context
def auth_login(ctx: click.Context, email: str, password: str,
               token_name: str, expires_in_days: int) -> None:
    """Create an API token; store the printed value in SP_API_TOKEN."""
    client = ctx.obj['client']
    output = ctx.obj['output']
    body = {'email': email, 'password': password,
            'token_name': token_name, 'expires_in_days': expires_in_days}
    try:
        result = client.request('POST', '/auth/tokens', json_body=body)
    except ApiError as error:
        render_error(error, output)
        raise SystemExit(error.exit_code)
    render(result, output)


@auth.command('logout')
@click.pass_context
def auth_logout(ctx: click.Context) -> None:
    """Revoke the current API token."""
    client = ctx.obj['client']
    output = ctx.obj['output']
    try:
        client.request('DELETE', '/auth/tokens/current')
    except ApiError as error:
        render_error(error, output)
        raise SystemExit(error.exit_code)
    click.echo('Token revoked.')
