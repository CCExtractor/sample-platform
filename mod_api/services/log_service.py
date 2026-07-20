"""
Build log reader with cursor-based pagination.

Log files live at SAMPLE_REPOSITORY/LogFiles/{run_id}.txt. The cursor
is just a line number offset into the file.
"""

from typing import Any, Dict, List, Optional, Tuple

from mod_api.services.storage import get_log_file_path


def _parse_cursor(cursor: Optional[int]) -> int:
    if not cursor:
        return 0
    try:
        return int(cursor)
    except (ValueError, TypeError):
        return 0


def _format_log_line(raw: str, run_id: int) -> Dict[str, Any]:
    return {
        'timestamp': None,
        'level': _extract_level(raw),
        'source': _extract_source(raw),
        'message': raw,
        'run_id': run_id,
        'sample_id': None,
    }


def _should_include_line(raw: str, level: Optional[str], source: Optional[str], contains: Optional[str]) -> bool:
    if level and not _matches_level(raw, level):
        return False
    if source and _extract_source(raw) != source:
        return False
    if contains and contains.lower() not in raw.lower():
        return False
    return True


def read_log_lines(
    run_id: int,
    cursor: Optional[str] = None,
    limit: int = 100,
    level: Optional[str] = None,
    source: Optional[str] = None,
    contains: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Read and optionally filter lines from a run's build log.

    Returns (lines, next_cursor). Raises FileNotFoundError when the
    log file isn't on disk.
    """
    log_path = get_log_file_path(run_id)
    if log_path is None:
        raise FileNotFoundError(f'Log file not found for run {run_id}')

    limit = max(1, min(limit, 500))

    start_line = _parse_cursor(cursor)

    import itertools

    def _read_lines(encoding, errors='strict'):
        with open(log_path, encoding=encoding, errors=errors) as f:
            iterator = itertools.islice(f, start_line, None)

            result_lines = []
            line_num = start_line

            for raw_line in iterator:
                raw = raw_line.rstrip('\n\r')
                line_num += 1

                if not _should_include_line(raw, level, source, contains):
                    continue

                result_lines.append(_format_log_line(raw, run_id))

                if len(result_lines) >= limit:
                    break

            try:
                next(iterator)
                has_more = True
            except StopIteration:
                has_more = False

            next_cursor = str(line_num) if has_more else None
            return result_lines, next_cursor

    try:
        return _read_lines('utf-8')
    except UnicodeDecodeError:
        # cp1252 leaves five byte values undefined, so the fallback itself
        # can raise; replace those rather than turning a log read into a 500.
        return _read_lines('cp1252', errors='replace')


def _matches_level(line: str, target_level: str) -> bool:
    """Check if a log line matches the requested severity (case-insensitive)."""
    return _extract_level(line) == (target_level or '').lower()


def _extract_level(line: str) -> str:
    """Best-effort log level extraction from raw text."""
    line_upper = line.upper()
    for lvl in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
        if lvl in line_upper:
            return lvl.lower()
    return 'info'


def _extract_source(line: str) -> str:
    """Best-effort source component extraction from raw text."""
    line_lower = line.lower()
    for src in ['orchestrator', 'worker', 'build', 'test_runner', 'web']:
        if src in line_lower:
            return src
    return 'web'
