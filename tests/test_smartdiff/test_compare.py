"""Tests for the semantic subtitle comparison / classifier."""

import unittest

from mod_test.smartdiff.compare import smart_diff


def _srt(cues):
    """
    Build SubRip text from (start_ms, end_ms, text) tuples.

    :param cues: Iterable of (start_ms, end_ms, text) tuples.
    :type cues: list
    :return: SubRip-formatted string.
    :rtype: str
    """
    def stamp(ms):
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = []
    for i, (start, end, text) in enumerate(cues, start=1):
        blocks.append(f"{i}\n{stamp(start)} --> {stamp(end)}\n{text}\n")
    return "\n".join(blocks)


_BASE = [(1000, 4000, "Hello world"), (5000, 8000, "Second line")]
_BASE_CAPS = [(1000, 4000, "HELLO WORLD"), (5000, 8000, "SECOND LINE")]


class SmartDiffTests(unittest.TestCase):
    """Classifying the kind of difference between two outputs."""

    def test_identical(self):
        """Equal outputs classify as identical."""
        result = smart_diff(_srt(_BASE), _srt(_BASE))
        self.assertEqual(result["kind"], "identical")

    def test_timing_shift_reports_offset(self):
        """A constant timing offset is reported as timing_shift with offset_ms."""
        shifted = [(s + 500, e + 500, t) for s, e, t in _BASE]
        result = smart_diff(_srt(_BASE), _srt(shifted))
        self.assertEqual(result["kind"], "timing_shift")
        self.assertEqual(result["offset_ms"], 500)

    def test_text_change_only(self):
        """Same timing, different text classifies as text_change."""
        changed = [(1000, 4000, "Hello world"), (5000, 8000, "DIFFERENT")]
        result = smart_diff(_srt(_BASE), _srt(changed))
        self.assertEqual(result["kind"], "text_change")

    def test_missing_cues(self):
        """Fewer cues than expected classifies as missing_cues."""
        result = smart_diff(_srt(_BASE), _srt(_BASE[:1]))
        self.assertEqual(result["kind"], "missing_cues")
        self.assertEqual((result["expected_cues"], result["actual_cues"]), (2, 1))

    def test_extra_cues(self):
        """More cues than expected classifies as extra_cues."""
        more = _BASE + [(9000, 10000, "Third line")]
        result = smart_diff(_srt(_BASE), _srt(more))
        self.assertEqual(result["kind"], "extra_cues")

    def test_mixed_when_text_and_count_differ(self):
        """Both text changes and a count mismatch classify as mixed."""
        other = [(1000, 4000, "CHANGED"), (5000, 8000, "Second line"),
                 (9000, 10000, "Third")]
        result = smart_diff(_srt(_BASE), _srt(other))
        self.assertEqual(result["kind"], "mixed")

    def test_works_on_webvtt_via_autodetect(self):
        """smart_diff auto-detects WebVTT and still classifies a timing shift."""
        base = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
        shifted = "WEBVTT\n\n00:00:01.250 --> 00:00:04.250\nHello\n"
        result = smart_diff(base, shifted)
        self.assertEqual(result["kind"], "timing_shift")
        self.assertEqual(result["offset_ms"], 250)

    def test_whitespace_padding_only(self):
        """Trailing CEA-608 padding differences are flagged as cosmetic, not text."""
        padded = [(1000, 4000, "HELLO WORLD   "), (5000, 8000, "SECOND LINE  ")]
        result = smart_diff(_srt(_BASE_CAPS), _srt(padded))
        self.assertEqual(result["kind"], "whitespace_change")

    def test_formatting_tags_only(self):
        """A styling-tags-only difference is flagged as formatting, not text."""
        styled = [(1000, 4000, "<i>Hello world</i>"), (5000, 8000, "Second line")]
        result = smart_diff(_srt(_BASE), _srt(styled))
        self.assertEqual(result["kind"], "formatting_change")


if __name__ == "__main__":
    unittest.main()
