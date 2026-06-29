"""Semantic comparison of subtitle outputs: classify *how* two results differ."""

from typing import Dict, List, Optional

from mod_test.smartdiff.normalize import classify_text_pair, plain
from mod_test.smartdiff.parsing import parse_subtitles
from mod_test.smartdiff.srt import Cue

#: Cap on the number of per-cue change entries returned in a result.
_MAX_CHANGES = 25


def _result(kind: str, summary: str, n_exp: int, n_act: int,
            offset_ms: Optional[int] = None) -> Dict[str, object]:
    """
    Build a classification result dict.

    :param kind: The stable difference kind.
    :type kind: str
    :param summary: A human/agent-readable one-line explanation.
    :type summary: str
    :param n_exp: Number of expected cues.
    :type n_exp: int
    :param n_act: Number of actual cues.
    :type n_act: int
    :param offset_ms: Consistent timing offset, when ``kind`` is ``timing_shift``.
    :type offset_ms: Optional[int]
    :return: The classification result.
    :rtype: Dict[str, object]
    """
    out: Dict[str, object] = {
        'kind': kind,
        'summary': summary,
        'expected_cues': n_exp,
        'actual_cues': n_act,
    }
    if offset_ms is not None:
        out['offset_ms'] = offset_ms
    return out


def _content(cues: List[Cue]) -> str:
    """
    Join all cues' normalised, whitespace-collapsed text — for split/merge detection.

    :param cues: The parsed cues.
    :type cues: List[Cue]
    :return: A single normalised token string spanning every cue.
    :rtype: str
    """
    return ' '.join(' '.join(plain(cue.text).split()) for cue in cues)


def _monotonic(values: List[int]) -> bool:
    """
    Report whether a sequence is non-decreasing or non-increasing.

    :param values: The sequence to test.
    :type values: List[int]
    :return: True if monotonic in either direction.
    :rtype: bool
    """
    pairs = list(zip(values, values[1:]))
    non_decreasing = all(a <= b for a, b in pairs)
    non_increasing = all(a >= b for a, b in pairs)
    return non_decreasing or non_increasing


def _snippet(text: str, limit: int = 80) -> str:
    """
    Collapse whitespace and truncate cue text for compact change details.

    :param text: Raw cue text.
    :type text: str
    :param limit: Maximum characters to keep.
    :type limit: int
    :return: A single-line, length-capped snippet.
    :rtype: str
    """
    flat = ' '.join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + '…'


def smart_diff(expected: str, actual: str,
               fmt: Optional[str] = None) -> Dict[str, object]:
    """
    Compare expected vs actual subtitle output and classify the difference.

    Supports SubRip (.srt) and WebVTT (.vtt); the format is auto-detected from
    content unless ``fmt`` is given. Aligns cues by position and reports the
    *kind* of difference rather than a raw line diff: ``identical``,
    ``timing_shift`` (constant offset), ``timing_drift`` (growing offset),
    ``text_change``, ``formatting_change`` (tags/entities only),
    ``whitespace_change`` (CEA-608 padding only), ``encoding_change``
    (non-ASCII/accented characters only), ``split_cues``, ``merged_cues``,
    ``missing_cues``, ``extra_cues``, or ``mixed``.

    :param expected: The expected/baseline subtitle content.
    :type expected: str
    :param actual: The actual/produced subtitle content.
    :type actual: str
    :param fmt: Explicit format ('srt' or 'vtt'); auto-detected when None.
    :type fmt: Optional[str]
    :return: A classification dict with keys ``kind``, ``summary``,
        ``expected_cues``, ``actual_cues`` and (for ``timing_shift``) ``offset_ms``.
    :rtype: Dict[str, object]
    """
    exp = parse_subtitles(expected, fmt)
    act = parse_subtitles(actual, fmt)
    n_exp, n_act = len(exp), len(act)
    count_mismatch = n_exp != n_act

    text_changes = 0
    formatting_changes = 0
    whitespace_changes = 0
    encoding_changes = 0
    raw_matches = True
    timing_deltas: List[int] = []
    changes: List[Dict[str, object]] = []
    for position, (expected_cue, actual_cue) in enumerate(zip(exp, act), start=1):
        category = classify_text_pair(expected_cue.text, actual_cue.text)
        delta = actual_cue.start_ms - expected_cue.start_ms
        if category != 'match':
            raw_matches = False
        if category == 'text':
            text_changes += 1
        else:
            if category == 'formatting':
                formatting_changes += 1
            elif category == 'whitespace':
                whitespace_changes += 1
            elif category == 'encoding':
                encoding_changes += 1
            timing_deltas.append(delta)
        if category != 'match' or delta != 0:
            entry: Dict[str, object] = {
                'cue': position,
                'kind': category if category != 'match' else 'timing',
            }
            if category == 'text':
                entry['expected'] = _snippet(expected_cue.text)
                entry['actual'] = _snippet(actual_cue.text)
            if delta != 0:
                entry['offset_ms'] = delta
            changes.append(entry)

    no_timing_move = all(delta == 0 for delta in timing_deltas)
    uniform_shift = bool(timing_deltas) and len(set(timing_deltas)) == 1
    varying_timing = len(set(timing_deltas)) > 1
    drifting = varying_timing and _monotonic(timing_deltas)
    cosmetic_changes = formatting_changes + whitespace_changes + encoding_changes
    fully_aligned = text_changes == 0 and cosmetic_changes == 0

    def _finish(kind: str, summary: str, exp_count: int, act_count: int,
                offset_ms: Optional[int] = None) -> Dict[str, object]:
        """Attach the (capped) per-cue change list to a classification result."""
        out = _result(kind, summary, exp_count, act_count, offset_ms)
        if changes:
            out['changes'] = changes[:_MAX_CHANGES]
            if len(changes) > _MAX_CHANGES:
                out['changes_truncated'] = True
        return out

    if not count_mismatch and raw_matches and no_timing_move:
        return _finish('identical', 'Outputs are identical.', n_exp, n_act)

    if not count_mismatch and fully_aligned and uniform_shift and timing_deltas[0] != 0:
        offset = timing_deltas[0]
        direction = 'late' if offset > 0 else 'early'
        return _finish(
            'timing_shift',
            f'All {n_exp} cues match but are {abs(offset)} ms {direction}.',
            n_exp, n_act, offset_ms=offset)

    if not count_mismatch and fully_aligned and drifting:
        first, last = timing_deltas[0], timing_deltas[-1]
        return _finish(
            'timing_drift',
            f'Timing drifts from {first:+d} ms to {last:+d} ms across {n_exp} cues.',
            n_exp, n_act)

    if count_mismatch:
        if _content(exp) and _content(exp) == _content(act):
            if n_act > n_exp:
                return _finish(
                    'split_cues',
                    f'Same text, but cues were split: expected {n_exp}, got {n_act}.',
                    n_exp, n_act)
            return _finish(
                'merged_cues',
                f'Same text, but cues were merged: expected {n_exp}, got {n_act}.',
                n_exp, n_act)
        if text_changes == 0:
            if n_act < n_exp:
                return _finish(
                    'missing_cues',
                    f'{n_exp - n_act} of {n_exp} cues are missing from the output.',
                    n_exp, n_act)
            return _finish(
                'extra_cues',
                f'Output has {n_act - n_exp} extra cues ({n_act} vs {n_exp} expected).',
                n_exp, n_act)

    if not count_mismatch and no_timing_move:
        if text_changes > 0:
            return _finish(
                'text_change',
                f'{text_changes} of {n_exp} cues differ in text (timing aligned).',
                n_exp, n_act)
        if encoding_changes > 0 and formatting_changes == 0 and whitespace_changes == 0:
            return _finish(
                'encoding_change',
                f'{encoding_changes} of {n_exp} cues differ only in character '
                f'encoding (non-ASCII/accented characters).',
                n_exp, n_act)
        if formatting_changes > 0 and whitespace_changes == 0 and encoding_changes == 0:
            return _finish(
                'formatting_change',
                f'{formatting_changes} of {n_exp} cues differ only in formatting '
                f'(tags/entities), not text.',
                n_exp, n_act)
        if whitespace_changes > 0 and formatting_changes == 0 and encoding_changes == 0:
            return _finish(
                'whitespace_change',
                f'{whitespace_changes} of {n_exp} cues differ only in trailing '
                f'whitespace/padding.',
                n_exp, n_act)

    return _finish(
        'mixed',
        f'Mixed differences across {min(n_exp, n_act)} compared cues; '
        f'expected {n_exp}, got {n_act}.',
        n_exp, n_act)
