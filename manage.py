#!/usr/local/bin/python3
"""Root module to manage flask CLI commands."""
import click

from exceptions import CCExtractorEndedWithNonZero, MissingPathToCCExtractor
from mod_regression.update_regression import update_expected_results
from run import app


@app.cli.command('update')
@click.argument('path_to_ccex')
def update_results(path_to_ccex):
    """
    Update results for the present samples with new ccextractor version.

    Pass path to CCExtractor binary as the argument.
    Example: flask update /path/to/ccextractor
    """
    if not path_to_ccex:
        click.echo('path to ccextractor is missing')
        raise MissingPathToCCExtractor

    click.echo(f'path to ccextractor: {path_to_ccex}')

    if not update_expected_results(path_to_ccex):
        click.echo('update function errored')
        raise CCExtractorEndedWithNonZero

    click.echo('update function finished')
    return 0


if __name__ == '__main__':
    app.cli()
