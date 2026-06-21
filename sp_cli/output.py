"""Render API responses to the terminal as JSON (default) or a simple table."""

import json
from typing import Any, Dict, List

import click

from sp_cli.client import ApiError

#: Value types rendered as plain table columns; nested structures are skipped.
_SCALAR = (str, int, float, bool, type(None))


def render(payload: Any, output: str) -> None:
    """
    Render a successful API payload in the requested format.

    Handles the API's three shapes: a list wrapper (``{data, pagination}``), a
    flat single object (run/summary/health), and bare values.

    :param payload: The decoded JSON body returned by the API.
    :type payload: Any
    :param output: Either ``json`` or ``table``.
    :type output: str
    """
    if output == 'json':
        click.echo(json.dumps(payload, indent=2))
        return

    if isinstance(payload, dict) and isinstance(payload.get('data'), list):
        _print_rows(payload['data'])
        footer = _footer(payload)
        if footer:
            click.echo(f"\n{footer}")
    elif isinstance(payload, dict):
        _print_kv(payload)
    else:
        click.echo(json.dumps(payload, indent=2))


def render_error(error: ApiError, output: str) -> None:
    """
    Render an API error as a JSON envelope on stderr, regardless of output mode.

    :param error: The error to render.
    :type error: ApiError
    :param output: The selected output mode (unused; kept for symmetry).
    :type output: str
    """
    envelope: Dict[str, Any] = {'error': {'code': error.code, 'message': error.message}}
    if error.status is not None:
        envelope['error']['status'] = error.status
    if error.details:
        envelope['error']['details'] = error.details
    click.echo(json.dumps(envelope, indent=2), err=True)


def _footer(payload: Dict[str, Any]) -> str:
    """
    Build a one-line footer from a ``summary`` or ``pagination`` block.

    :param payload: The full response payload.
    :type payload: Dict[str, Any]
    :return: A footer string (possibly empty).
    :rtype: str
    """
    summary = payload.get('summary')
    if isinstance(summary, dict):
        return ' · '.join(f"{k}: {v}" for k, v in summary.items())
    pagination = payload.get('pagination')
    if isinstance(pagination, dict):
        parts = []
        if pagination.get('total') is not None:
            parts.append(f"{pagination['total']} total")
        if pagination.get('next_offset') is not None:
            parts.append(f"more at offset {pagination['next_offset']}")
        return ' · '.join(parts)
    return ''


def _print_rows(rows: List[Any]) -> None:
    """
    Print a list of flat dicts as an aligned table of their scalar fields.

    :param rows: The list of row dicts to render.
    :type rows: List[Any]
    """
    if not rows:
        click.echo('(no results)')
        return
    if not all(isinstance(row, dict) for row in rows):
        click.echo(json.dumps(rows, indent=2))
        return

    columns: List[str] = []
    for row in rows:
        for key, value in row.items():
            if key not in columns and isinstance(value, _SCALAR):
                columns.append(key)

    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(_cell(row.get(col))))

    click.echo('  '.join(col.ljust(widths[col]) for col in columns))
    click.echo('  '.join('-' * widths[col] for col in columns))
    for row in rows:
        click.echo('  '.join(_cell(row.get(col)).ljust(widths[col]) for col in columns))


def _print_kv(record: Dict[str, Any]) -> None:
    """
    Print a single record as ``key: value`` lines, JSON-encoding nested values.

    :param record: The record to render.
    :type record: Dict[str, Any]
    """
    width = max((len(key) for key in record), default=0)
    for key, value in record.items():
        rendered = _cell(value) if isinstance(value, _SCALAR) else json.dumps(value)
        click.echo(f"{key.ljust(width)} : {rendered}")


def _cell(value: Any) -> str:
    """
    Format a scalar cell value for table display.

    :param value: The value to format.
    :type value: Any
    :return: A string representation (empty string for ``None``).
    :rtype: str
    """
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        return ', '.join(str(item) for item in value)
    return str(value)
