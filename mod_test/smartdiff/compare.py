"""Semantic comparison of subtitle outputs: classify *how* two results differ."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from mod_test.smartdiff.normalize import classify_text_pair, plain
from mod_test.smartdiff.parsing import parse_subtitles
from mod_test.smartdiff.srt import Cue

#: Cap on the number of per-cue change entries returned in a result.
_MAX_CHANGES = 25

#: Text categories that count as cosmetic (the cue's words are unchanged).
_COSMETIC = ('formatting', 'whitespace', 'encoding')

#: A classification: (kind, summary, offset_ms).
_Verdict = Tuple[str, str, Optional[int]]


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


@dataclass
class _Tally:
    """Per-category counts and timing deltas collected over position-aligned cues."""

    text: int = 0
    formatting: int = 0
    whitespace: int = 0
    encoding: int = 0
    raw_matches: bool = True
    timing_deltas: List[int] = field(default_factory=list)
    changes: List[Dict[str, object]] = field(default_factory=list)

    @property
    def cosmetic(self) -> int:
        """Total cues that differ only cosmetically (formatting/whitespace/encoding)."""
        return self.formatting + self.whitespace + self.encoding


def _change_entry(position: int, category: str, delta: int,
                  expected_cue: Cue, actual_cue: Cue) -> Optional[Dict[str, object]]:
    """
    Describe one cue's change, or return None when the cue is unchanged.

    :param position: 1-based cue position.
    :type position: int
    :param category: The text classification from ``classify_text_pair``.
    :type category: str
    :param delta: Start-time offset (actual minus expected) in ms.
    :type delta: int
    :param expected_cue: The expected cue.
    :type expected_cue: Cue
    :param actual_cue: The actual cue.
    :type actual_cue: Cue
    :return: The change entry, or None.
    :rtype: Optional[Dict[str, object]]
    """
    if category == 'match' and delta == 0:
        return None
    entry: Dict[str, object] = {
        'cue': position,
        'kind': category if category != 'match' else 'timing',
    }
    if category == 'text':
        entry['expected'] = _snippet(expected_cue.text)
        entry['actual'] = _snippet(actual_cue.text)
    if delta != 0:
        entry['offset_ms'] = delta
    return entry


def _tally(exp: List[Cue], act: List[Cue]) -> _Tally:
    """
    Classify every position-aligned cue pair and collect the counts.

    :param exp: Expected cues.
    :type exp: List[Cue]
    :param act: Actual cues.
    :type act: List[Cue]
    :return: The collected tally.
    :rtype: _Tally
    """
    tally = _Tally()
    for position, (expected_cue, actual_cue) in enumerate(zip(exp, act), start=1):
        category = classify_text_pair(expected_cue.text, actual_cue.text)
        delta = actual_cue.start_ms - expected_cue.start_ms
        if category != 'match':
            tally.raw_matches = False
        if category == 'text':
            tally.text += 1
        else:
            if category in _COSMETIC:
                setattr(tally, category, getattr(tally, category) + 1)
            tally.timing_deltas.append(delta)
        entry = _change_entry(position, category, delta, expected_cue, actual_cue)
        if entry is not None:
            tally.changes.append(entry)
    return tally


def _classify_aligned(tally: _Tally, n_exp: int) -> Optional[_Verdict]:
    """
    Classify equal-count outputs whose cues differ only in timing, if any.

    :param tally: The collected tally.
    :type tally: _Tally
    :param n_exp: Number of expected cues.
    :type n_exp: int
    :return: (kind, summary, offset_ms), or None if not a pure timing case.
    :rtype: Optional[_Verdict]
    """
    deltas = tally.timing_deltas
    if tally.raw_matches and all(delta == 0 for delta in deltas):
        return 'identical', 'Outputs are identical.', None
    if tally.text or tally.cosmetic:
        return None
    if len(set(deltas)) == 1 and deltas[0] != 0:
        offset = deltas[0]
        direction = 'late' if offset > 0 else 'early'
        return ('timing_shift',
                f'All {n_exp} cues match but are {abs(offset)} ms {direction}.', offset)
    if len(set(deltas)) > 1 and _monotonic(deltas):
        return ('timing_drift',
                f'Timing drifts from {deltas[0]:+d} ms to {deltas[-1]:+d} ms '
                f'across {n_exp} cues.', None)
    return None


def _classify_count_mismatch(exp: List[Cue], act: List[Cue],
                             tally: _Tally) -> Optional[_Verdict]:
    """
    Classify outputs with different cue counts as split/merged/missing/extra.

    :param exp: Expected cues.
    :type exp: List[Cue]
    :param act: Actual cues.
    :type act: List[Cue]
    :param tally: The collected tally.
    :type tally: _Tally
    :return: (kind, summary, None), or None if no single kind fits.
    :rtype: Optional[_Verdict]
    """
    n_exp, n_act = len(exp), len(act)
    exp_content = _content(exp)
    if exp_content and exp_content == _content(act):
        if n_act > n_exp:
            return ('split_cues',
                    f'Same text, but cues were split: expected {n_exp}, got {n_act}.', None)
        return ('merged_cues',
                f'Same text, but cues were merged: expected {n_exp}, got {n_act}.', None)
    if tally.text:
        return None
    if n_act < n_exp:
        return ('missing_cues',
                f'{n_exp - n_act} of {n_exp} cues are missing from the output.', None)
    return ('extra_cues',
            f'Output has {n_act - n_exp} extra cues ({n_act} vs {n_exp} expected).', None)


def _classify_content(tally: _Tally, n_exp: int) -> Optional[_Verdict]:
    """
    Classify equal-count, untimed-shift outputs by the one kind of text change.

    :param tally: The collected tally.
    :type tally: _Tally
    :param n_exp: Number of expected cues.
    :type n_exp: int
    :return: (kind, summary, None), or None if the changes are mixed.
    :rtype: Optional[_Verdict]
    """
    if any(delta != 0 for delta in tally.timing_deltas):
        return None
    if tally.text:
        return 'text_change', f'{tally.text} of {n_exp} cues differ in text.', None
    only = {
        'encoding': (tally.encoding, 'encoding_change',
                     'differ only in character encoding (non-ASCII/accented characters)'),
        'formatting': (tally.formatting, 'formatting_change',
                       'differ only in formatting (tags/entities), not text'),
        'whitespace': (tally.whitespace, 'whitespace_change',
                       'differ only in trailing whitespace/padding'),
    }
    for count, kind, phrase in only.values():
        if count and count == tally.cosmetic:
            return kind, f'{count} of {n_exp} cues {phrase}.', None
    return None


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
    ``missing_cues``, ``extra_cues``, ``unsupported`` (no cues parsed), or
    ``mixed``.

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
    if n_exp == 0 and n_act == 0:
        if expected == actual:
            return _result('identical', 'Outputs are identical.', 0, 0)
        return _result(
            'unsupported',
            'No subtitle cues to compare (unsupported format); see the raw diff.',
            0, 0)

    tally = _tally(exp, act)
    if n_exp != n_act:
        verdict = _classify_count_mismatch(exp, act, tally)
    else:
        verdict = _classify_aligned(tally, n_exp) or _classify_content(tally, n_exp)
    if verdict is None:
        verdict = ('mixed',
                   f'Mixed differences across {min(n_exp, n_act)} compared cues; '
                   f'expected {n_exp}, got {n_act}.', None)

    kind, summary, offset_ms = verdict
    out = _result(kind, summary, n_exp, n_act, offset_ms)
    if tally.changes:
        out['changes'] = tally.changes[:_MAX_CHANGES]
        if len(tally.changes) > _MAX_CHANGES:
            out['changes_truncated'] = True
    return out
