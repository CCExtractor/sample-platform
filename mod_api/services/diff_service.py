"""
Structured diff computation between expected and actual output files.

Produces JSON hunks with line-level detail instead of the legacy HTML
diff output. Uses difflib.unified_diff internally.
"""

import difflib
import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple


def compute_diff(
    expected_path: str,
    actual_path: str,
    context_lines: int = 3,
    max_hunks: int = 500,
) -> Dict[str, Any]:
    """
    Compute a structured diff between two files.

    Returns a dict matching the Diff schema: status, summary (added_lines,
    removed_lines, changed_hunks), and a list of hunks.
    """
    context_lines = max(1, min(context_lines, 50))

    if not os.path.isfile(expected_path):
        return {
            'status': 'missing_expected',
            'summary': {'added_lines': 0, 'removed_lines': 0, 'changed_hunks': 0},
            'hunks': [],
        }

    if not os.path.isfile(actual_path):
        return {
            'status': 'missing_actual',
            'summary': {'added_lines': 0, 'removed_lines': 0, 'changed_hunks': 0},
            'hunks': [],
        }

    expected_lines = read_lines(expected_path)
    actual_lines = read_lines(actual_path)

    if expected_lines == actual_lines:
        return {
            'status': 'identical',
            'summary': {'added_lines': 0, 'removed_lines': 0, 'changed_hunks': 0},
            'hunks': [],
        }

    hunks = _compute_hunks(expected_lines, actual_lines,
                           context_lines, max_hunks)
    added = sum(
        1 for h in hunks for line in h['lines'] if line['kind'] == 'added')
    removed = sum(
        1 for h in hunks for line in h['lines'] if line['kind'] == 'removed')

    return {
        'status': 'different',
        'summary': {
            'added_lines': added,
            'removed_lines': removed,
            'changed_hunks': len(hunks),
        },
        'hunks': hunks,
    }


# Matches the @@ -a,b +c,d @@ header line from unified_diff.
_HUNK_RE = re.compile(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@')


def _process_diff_line(line, current_hunk, expected_line_num, actual_line_num):
    if line.startswith('+'):
        current_hunk['lines'].append({
            'kind': 'added',
            'expected_line': None,
            'actual_line': actual_line_num,
            'text': line[1:],
        })
        actual_line_num += 1
    elif line.startswith('-'):
        current_hunk['lines'].append({
            'kind': 'removed',
            'expected_line': expected_line_num,
            'actual_line': None,
            'text': line[1:],
        })
        expected_line_num += 1
    else:
        content = line[1:] if line.startswith(' ') else line
        current_hunk['lines'].append({
            'kind': 'context',
            'expected_line': expected_line_num,
            'actual_line': actual_line_num,
            'text': content,
        })
        expected_line_num += 1
        actual_line_num += 1
    return expected_line_num, actual_line_num


def _process_hunk_header(
    line: str,
    current_hunk: Optional[Dict[str, Any]],
    hunks: List[Dict[str, Any]],
    max_hunks: int
) -> Tuple[Optional[Dict[str, Any]], int, int, bool]:
    if current_hunk and len(hunks) >= max_hunks:
        return None, 0, 0, True
    if current_hunk:
        hunks.append(current_hunk)

    m = _HUNK_RE.match(line)
    if m:
        expected_line_num = int(m.group(1))
        actual_line_num = int(m.group(2))
    else:
        expected_line_num = 0
        actual_line_num = 0

    new_hunk = {
        'expected_start': expected_line_num,
        'actual_start': actual_line_num,
        'lines': [],
    }
    return new_hunk, expected_line_num, actual_line_num, False


def _compute_hunks(
    expected_lines: List[str],
    actual_lines: List[str],
    context_lines: int,
    max_hunks: int,
) -> List[Dict[str, Any]]:
    """Parse unified_diff output into structured hunk dicts."""
    differ = difflib.unified_diff(
        expected_lines,
        actual_lines,
        lineterm='',
        n=context_lines,
    )

    hunks: List[Dict[str, Any]] = []
    current_hunk: Optional[Dict[str, Any]] = None
    expected_line_num = 0
    actual_line_num = 0

    for line in differ:
        if line.startswith(('---', '+++')):
            continue

        if line.startswith('@@'):
            current_hunk, expected_line_num, actual_line_num, stop = _process_hunk_header(
                line, current_hunk, hunks, max_hunks
            )
            if stop:
                break
            continue

        if current_hunk is None:
            continue

        expected_line_num, actual_line_num = _process_diff_line(
            line, current_hunk, expected_line_num, actual_line_num)

    if current_hunk:
        hunks.append(current_hunk)

    return hunks[:max_hunks]


def _enforce_safe_path(file_path: str) -> bool:
    from mod_api.services.storage import get_test_results_base_path
    base = os.path.realpath(get_test_results_base_path())
    target = os.path.realpath(file_path)
    return target.startswith(base + os.sep) or target == base


def read_lines(file_path: str) -> List[str]:
    """Read file lines with a cp1252 fallback, matching legacy behavior."""
    if not _enforce_safe_path(file_path):
        raise ValueError("Unsafe file path")
    try:
        with open(file_path, encoding='utf8') as f:
            return [line.rstrip('\n\r') for line in f.readlines()]
    except UnicodeDecodeError:
        with open(file_path, encoding='cp1252') as f:
            return [line.rstrip('\n\r') for line in f.readlines()]


def file_sha256(file_path: str) -> Optional[str]:
    """Compute SHA-256 of a file. Returns None if the file can't be read."""
    if not _enforce_safe_path(file_path):
        return None
    try:
        sha = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for block in iter(lambda: f.read(8192), b''):
                sha.update(block)
        return sha.hexdigest()
    except (OSError, IOError):
        return None
