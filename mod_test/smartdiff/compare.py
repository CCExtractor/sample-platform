"""Semantic comparison of subtitle outputs: classify *how* two results differ."""

from typing import Dict, List, Optional

from mod_test.smartdiff.srt import parse_srt


def _norm(text: str) -> str:
    """
    Normalise cue text for comparison (collapse whitespace, case-fold).

    :param text: Raw cue text.
    :type text: str
    :return: Normalised text.
    :rtype: str
    """
    return ' '.join(text.split()).casefold()


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


def smart_diff(expected: str, actual: str) -> Dict[str, object]:
    """
    Compare expected vs actual SubRip output and classify the difference.

    Aligns cues by position and reports the *kind* of difference rather than a
    raw line diff: ``identical``, ``timing_shift`` (with a consistent offset),
    ``text_change``, ``missing_cues``, ``extra_cues``, or ``mixed``. The goal is
    an actionable answer ("subtitles are +120 ms late") instead of a wall of
    changed lines.

    :param expected: The expected/baseline .srt content.
    :type expected: str
    :param actual: The actual/produced .srt content.
    :type actual: str
    :return: A classification dict with keys ``kind``, ``summary``,
        ``expected_cues``, ``actual_cues`` and (for ``timing_shift``) ``offset_ms``.
    :rtype: Dict[str, object]
    """
    exp = parse_srt(expected)
    act = parse_srt(actual)
    n_exp, n_act = len(exp), len(act)
    count_mismatch = n_exp != n_act

    text_changes = 0
    timing_deltas: List[int] = []
    for e, a in zip(exp, act):
        if _norm(e.text) != _norm(a.text):
            text_changes += 1
        else:
            timing_deltas.append(a.start_ms - e.start_ms)

    if not count_mismatch and text_changes == 0 and all(d == 0 for d in timing_deltas):
        return _result('identical', 'Outputs are identical.', n_exp, n_act)

    uniform_shift = bool(timing_deltas) and len(set(timing_deltas)) == 1
    if not count_mismatch and text_changes == 0 and uniform_shift and timing_deltas[0] != 0:
        offset = timing_deltas[0]
        direction = 'late' if offset > 0 else 'early'
        return _result(
            'timing_shift',
            f'All {n_exp} cues match but are {abs(offset)} ms {direction}.',
            n_exp, n_act, offset_ms=offset)

    if count_mismatch and text_changes == 0:
        if n_act < n_exp:
            return _result(
                'missing_cues',
                f'{n_exp - n_act} of {n_exp} cues are missing from the output.',
                n_exp, n_act)
        return _result(
            'extra_cues',
            f'Output has {n_act - n_exp} extra cues ({n_act} vs {n_exp} expected).',
            n_exp, n_act)

    if not count_mismatch and text_changes > 0 and all(d == 0 for d in timing_deltas):
        return _result(
            'text_change',
            f'{text_changes} of {n_exp} cues differ in text only (timing matches).',
            n_exp, n_act)

    return _result(
        'mixed',
        f'Mixed differences: {text_changes} text change(s) across '
        f'{min(n_exp, n_act)} compared cues; expected {n_exp}, got {n_act}.',
        n_exp, n_act)
