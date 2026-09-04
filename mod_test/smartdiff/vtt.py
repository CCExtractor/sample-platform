"""Parse WebVTT (.vtt) subtitle output into structured cues."""

import re
from typing import List, Optional

from mod_test.smartdiff.srt import Cue, join_cue_text

_TIMING_RE = re.compile(
    r'(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*'
    r'(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})'
)

_METADATA_PREFIXES = ('WEBVTT', 'NOTE', 'STYLE', 'REGION')


def _to_ms(hours: Optional[str], minutes: str, seconds: str, millis: str) -> int:
    """
    Convert WebVTT timestamp parts into total milliseconds.

    :param hours: Hours component, or None when absent (MM:SS.mmm form).
    :type hours: Optional[str]
    :param minutes: Minutes component.
    :type minutes: str
    :param seconds: Seconds component.
    :type seconds: str
    :param millis: Milliseconds component.
    :type millis: str
    :return: The timestamp in milliseconds.
    :rtype: int
    """
    hrs = int(hours) if hours else 0
    return ((hrs * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def parse_vtt(content: str) -> List[Cue]:
    """
    Parse WebVTT subtitle text into a list of cues.

    Skips the ``WEBVTT`` header and ``NOTE``/``STYLE``/``REGION`` blocks, tolerates
    an optional cue-identifier line, optional hours in timestamps, and trailing cue
    settings after the end timestamp.

    :param content: Raw .vtt file content.
    :type content: str
    :return: The parsed cues, in file order.
    :rtype: List[Cue]
    """
    content = content.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    cues: List[Cue] = []
    for block in re.split(r'\n[ \t]*\n', content.strip()):
        lines = block.split('\n')
        if lines[0].split(' ', 1)[0] in _METADATA_PREFIXES:
            continue
        timing_idx: Optional[int] = next(
            (i for i, ln in enumerate(lines) if _TIMING_RE.search(ln)), None)
        if timing_idx is None:
            continue
        match = _TIMING_RE.search(lines[timing_idx])
        if match is None:  # pragma: no cover - guaranteed by the search above
            continue
        start_ms = _to_ms(match.group(1), match.group(2), match.group(3), match.group(4))
        end_ms = _to_ms(match.group(5), match.group(6), match.group(7), match.group(8))
        text = join_cue_text(lines[timing_idx + 1:])
        cues.append(Cue(index=len(cues) + 1, start_ms=start_ms, end_ms=end_ms, text=text))
    return cues
