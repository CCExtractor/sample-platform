"""Branded welcome screen for the ``sp`` CLI.

Shown only when ``sp`` is invoked with no subcommand. Never emitted on command
output, so machine consumers (agents parsing JSON) are unaffected. Colors are
applied via :func:`click.style` and are auto-stripped when output is piped.
"""

import click

from sp_cli import __version__

#: Figlet-style "sp" wordmark.
LOGO = r"""  ___ _ __
 / __| '_ \
 \__ \ |_) |
 |___/ .__/
     |_|"""

_GROUPS = [
    ('TRIAGE', 'sp investigate <run>     ← one-shot: what failed and why'),
    ('RUNS', 'sp run ls · show · summary · failures · results · result · diff · artifacts · logs · errors'),
    ('SAMPLES', 'sp sample ls · show · history'),
    ('TESTS', 'sp regression ls'),
    ('SYSTEM', 'sp health · queue'),
    ('AUTH', 'sp auth login · logout'),
]

_EXAMPLES = [
    ('sp investigate 9299', 'triage a run end-to-end'),
    ('sp run failures 9299', 'failing tests, each labeled with why'),
    ('sp run diff 9299 137', 'expected-vs-actual diff (ids auto-resolved)'),
]


def show_welcome() -> None:
    """Print the branded welcome screen (banner, command map, examples)."""
    click.echo()
    click.echo(click.style(LOGO, fg='cyan'))
    click.echo(f"  {click.style('CCExtractor CI', bold=True)} · AI-friendly CLI · v{__version__}")
    click.echo("  drive CI investigations from the terminal — no UI, no HTML scraping")
    click.echo()

    for name, line in _GROUPS:
        click.echo(f"  {click.style(name.ljust(8), fg='green', bold=True)} {line}")
    click.echo()

    click.echo(f"  {click.style('Examples', bold=True)}")
    for command, note in _EXAMPLES:
        click.echo(f"    {command.ljust(28)} {click.style('# ' + note, fg='bright_black')}")
    click.echo()

    click.echo(f"  {click.style('Help', bold=True)} sp COMMAND --help"
               f"     {click.style('Config', bold=True)} SP_BASE_URL · SP_API_TOKEN")
    click.echo()
