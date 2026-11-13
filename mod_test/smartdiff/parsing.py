"""Detect the subtitle format and dispatch to the right parser."""

from typing import List, Optional

from mod_test.smartdiff.srt import Cue, parse_srt
from mod_test.smartdiff.vtt import parse_vtt


def parse_subtitles(content: str, fmt: Optional[str] = None) -> List[Cue]:
    """
    Parse subtitle content into cues, choosing a parser by hint or by content.

    :param content: Raw subtitle file content.
    :type content: str
    :param fmt: Explicit format ('srt' or 'vtt'); auto-detected from content when None.
    :type fmt: Optional[str]
    :return: The parsed cues.
    :rtype: List[Cue]
    """
    chosen = (fmt or '').lower()
    if not chosen:
        head = content.lstrip('﻿').lstrip().upper()
        chosen = 'vtt' if head.startswith('WEBVTT') else 'srt'
    if chosen == 'vtt':
        return parse_vtt(content)
    return parse_srt(content)
