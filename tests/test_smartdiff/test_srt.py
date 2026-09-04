"""Tests for the SubRip (.srt) parser."""

import unittest

from mod_test.smartdiff.srt import parse_srt

_TWO_CUES = (
    "1\n"
    "00:00:01,000 --> 00:00:04,000\n"
    "Hello world\n"
    "\n"
    "2\n"
    "00:00:05,500 --> 00:00:08,250\n"
    "Second line\n"
)


class ParseSrtTests(unittest.TestCase):
    """Parsing SubRip content into structured cues."""

    def test_parses_index_timing_and_text(self):
        """A two-cue file yields two cues with correct ms timing and text."""
        cues = parse_srt(_TWO_CUES)
        self.assertEqual(len(cues), 2)
        self.assertEqual((cues[0].index, cues[0].start_ms, cues[0].end_ms), (1, 1000, 4000))
        self.assertEqual(cues[0].text, "Hello world")
        self.assertEqual((cues[1].start_ms, cues[1].end_ms), (5500, 8250))

    def test_tolerates_crlf_and_bom(self):
        """CRLF line endings and a leading BOM are handled."""
        cues = parse_srt("﻿" + _TWO_CUES.replace("\n", "\r\n"))
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[1].text, "Second line")

    def test_skips_blocks_without_timing(self):
        """A trailing junk block with no timing line is ignored."""
        cues = parse_srt(_TWO_CUES + "\nnot a cue\n")
        self.assertEqual(len(cues), 2)

    def test_multiline_cue_text_preserved(self):
        """Cue text spanning multiple lines is preserved with its newline."""
        content = "1\n00:00:01,000 --> 00:00:02,000\nline one\nline two\n"
        cues = parse_srt(content)
        self.assertEqual(cues[0].text, "line one\nline two")


if __name__ == "__main__":
    unittest.main()
