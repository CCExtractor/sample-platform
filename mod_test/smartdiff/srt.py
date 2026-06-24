"""Parse SubRip (.srt) subtitle output into structured cues for comparison."""

import re
from dataclasses import dataclass
from typing import List, Optional

_TIMING_RE = re.compile(
    r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*'
    r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})'
)


@dataclass
class Cue:
    """
    A single subtitle cue: its timing window and text.

    :param index: The cue's sequence number as written in the file.
    :type index: int
    :param start_ms: Start time in milliseconds.
    :type start_ms: int
    :param end_ms: End time in milliseconds.
    :type end_ms: int
    :param text: The cue's text, newlines preserved and surrounding whitespace stripped.
    :type text: str
    """

    index: int
    start_ms: int
    end_ms: int
    text: str


def _to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    """
    Convert the parts of an SRT timestamp into total milliseconds.

    :param hours: Hours component.
    :type hours: str
    :param minutes: Minutes component.
    :type minutes: str
    :param seconds: Seconds component.
    :type seconds: str
    :param millis: Milliseconds component.
    :type millis: str
    :return: The timestamp in milliseconds.
    :rtype: int
    """
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def parse_srt(content: str) -> List[Cue]:
    """
    Parse SubRip subtitle text into a list of cues.

    Tolerant of a leading BOM, CRLF/CR line endings, and either ',' or '.' as the
    millisecond separator. Blocks without a valid timing line are skipped.

    :param content: Raw .srt file content.
    :type content: str
    :return: The parsed cues, in file order.
    :rtype: List[Cue]
    """
    content = content.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    cues: List[Cue] = []
    for block in re.split(r'\n[ \t]*\n', content.strip()):
        lines = block.split('\n')
        timing_idx: Optional[int] = next(
            (i for i, ln in enumerate(lines) if _TIMING_RE.search(ln)), None)
        if timing_idx is None:
            continue
        match = _TIMING_RE.search(lines[timing_idx])
        if match is None:  # pragma: no cover - guaranteed by the search above
            continue
        start_ms = _to_ms(match.group(1), match.group(2), match.group(3), match.group(4))
        end_ms = _to_ms(match.group(5), match.group(6), match.group(7), match.group(8))
        index = len(cues) + 1
        if timing_idx > 0 and lines[timing_idx - 1].strip().isdigit():
            index = int(lines[timing_idx - 1].strip())
        text = '\n'.join(lines[timing_idx + 1:]).strip()
        cues.append(Cue(index=index, start_ms=start_ms, end_ms=end_ms, text=text))
    return cues
