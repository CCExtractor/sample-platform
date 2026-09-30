"""Tests for the WebVTT (.vtt) parser."""

import unittest

from mod_test.smartdiff.vtt import parse_vtt

_VTT = (
    "WEBVTT\n"
    "\n"
    "NOTE this is a comment\n"
    "\n"
    "1\n"
    "00:00:01.000 --> 00:00:04.000 align:start position:50%\n"
    "Hello world\n"
    "\n"
    "00:05.500 --> 00:08.250\n"
    "Second line\n"
)


class ParseVttTests(unittest.TestCase):
    """Parsing WebVTT content into structured cues."""

    def test_parses_cues_and_skips_metadata(self):
        """The WEBVTT header and NOTE block are skipped; cues are parsed."""
        cues = parse_vtt(_VTT)
        self.assertEqual(len(cues), 2)
        self.assertEqual((cues[0].start_ms, cues[0].end_ms), (1000, 4000))
        self.assertEqual(cues[0].text, "Hello world")

    def test_ignores_trailing_cue_settings(self):
        """Cue settings after the end timestamp do not leak into timing/text."""
        cues = parse_vtt(_VTT)
        self.assertEqual(cues[0].end_ms, 4000)
        self.assertEqual(cues[0].text, "Hello world")

    def test_handles_optional_hours(self):
        """A MM:SS.mmm timestamp without an hours component is parsed correctly."""
        cues = parse_vtt(_VTT)
        self.assertEqual((cues[1].start_ms, cues[1].end_ms), (5500, 8250))


if __name__ == "__main__":
    unittest.main()
