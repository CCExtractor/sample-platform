#!/usr/local/bin/python3
"""Root module to manage flask CLI commands."""
import click

from exceptions import CCExtractorEndedWithNonZero, MissingPathToCCExtractor
from mod_regression.update_regression import update_expected_results
from run import app

import json
from pathlib import Path
from mod_regression.sample_inventory import inventory_samples


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

def inventory_command():
    import argparse
    parser = argparse.ArgumentParser(description="Generate sample inventory")
    parser.add_argument(
        "--samples",
        default="TestData",
        help="Path to samples directory"
    )
    parser.add_argument(
        "--output",
        default="metadata/sample_inventory.json",
        help="Output JSON file"
    )

    args = parser.parse_args()

    samples_dir = Path(args.samples)
    out = Path(args.output)

    inventory = inventory_samples(samples_dir)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inventory, indent=2))

    print(f"Inventory written: {out} ({len(inventory)} samples)")

if __name__ == '__main__':
    app.cli()
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "inventory":
        sys.argv.pop(1)
        inventory_command()
