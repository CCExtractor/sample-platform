"""Golden-fixture tests against real CCExtractor output, plus input robustness.

The fixtures are genuine CCExtractor outputs (not synthetic strings):
- ``cea608_real.srt``: a CEA-608 broadcast caption sample (trailing padding).
- ``dvb_spanish_real.srt``: a DVB Spanish sample with ``<font>`` colour tags and
  accented characters. Both were security-scanned before vendoring (no paths,
  IPs, emails, URLs, or secrets) and are valid UTF-8.
"""

import os
import unittest

from mod_test.smartdiff.compare import smart_diff
from mod_test.smartdiff.normalize import ascii_fold, strip_tags
from mod_test.smartdiff.srt import Cue, parse_srt

_FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def _load(name):
    """
    Read a vendored fixture as UTF-8.

    :param name: Fixture file name.
    :type name: str
    :return: The file content.
    :rtype: str
    """
    with open(os.path.join(_FIXTURES, name), encoding='utf-8') as handle:
        return handle.read()


def _emit(cues):
    """
    Serialise cues back to SubRip text (for building timing-shifted variants).

    :param cues: The cues to serialise.
    :type cues: list
    :return: SubRip-formatted text.
    :rtype: str
    """
    def stamp(ms):
        hours, ms = divmod(ms, 3600000)
        minutes, ms = divmod(ms, 60000)
        seconds, ms = divmod(ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

    return "\n".join(f"{i}\n{stamp(c.start_ms)} --> {stamp(c.end_ms)}\n{c.text}\n"
                     for i, c in enumerate(cues, 1))


class Cea608RealTests(unittest.TestCase):
    """Smart diff on a genuine CEA-608 broadcast caption sample."""

    def test_parses_real_sample(self):
        """The real sample parses into its two CEA-608 cues."""
        cues = parse_srt(_load('cea608_real.srt'))
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].start_ms, 5956)

    def test_identical_against_itself(self):
        """The real sample compared with itself is identical."""
        raw = _load('cea608_real.srt')
        self.assertEqual(smart_diff(raw, raw)['kind'], 'identical')

    def test_depadding_is_cosmetic(self):
        """Stripping the CEA-608 trailing padding is flagged as cosmetic only."""
        raw = _load('cea608_real.srt')
        depadded = '\n'.join(line.rstrip() for line in raw.split('\n'))
        self.assertIn(smart_diff(raw, depadded)['kind'],
                      ('identical', 'whitespace_change'))


class DvbSpanishRealTests(unittest.TestCase):
    """Smart diff on a real DVB Spanish output (font colour tags + accents)."""

    def test_parses_with_tags_and_accents(self):
        """The fixture has 13 cues carrying both font tags and non-ASCII text."""
        cues = parse_srt(_load('dvb_spanish_real.srt'))
        self.assertEqual(len(cues), 13)
        self.assertTrue(any('<font' in c.text for c in cues))
        self.assertTrue(any(ord(ch) > 127 for c in cues for ch in c.text))

    def test_identical(self):
        """The fixture compared with itself is identical."""
        raw = _load('dvb_spanish_real.srt')
        self.assertEqual(smart_diff(raw, raw)['kind'], 'identical')

    def test_constant_timing_shift(self):
        """Shifting every cue by +500 ms is detected with the exact offset."""
        cues = parse_srt(_load('dvb_spanish_real.srt'))
        shifted = [Cue(c.index, c.start_ms + 500, c.end_ms + 500, c.text) for c in cues]
        result = smart_diff(_emit(cues), _emit(shifted))
        self.assertEqual(result['kind'], 'timing_shift')
        self.assertEqual(result['offset_ms'], 500)

    def test_font_tags_are_formatting_only(self):
        """Removing the <font> colour tags is classified as formatting, not text."""
        raw = _load('dvb_spanish_real.srt')
        self.assertEqual(smart_diff(raw, strip_tags(raw))['kind'], 'formatting_change')

    def test_accent_folding_is_encoding(self):
        """Folding the accented characters is classified as an encoding difference."""
        raw = _load('dvb_spanish_real.srt')
        self.assertEqual(smart_diff(raw, ascii_fold(raw))['kind'], 'encoding_change')

    def test_dropped_cues_are_missing(self):
        """Dropping the last three cues is reported as missing_cues."""
        cues = parse_srt(_load('dvb_spanish_real.srt'))
        result = smart_diff(_emit(cues), _emit(cues[:-3]))
        self.assertEqual(result['kind'], 'missing_cues')


class RobustnessTests(unittest.TestCase):
    """Malformed or hostile input must classify cleanly, never crash."""

    def test_parser_survives_garbage(self):
        """The parser returns a list for empty, junk, and control-byte input."""
        for junk in ['', 'not a subtitle', '\x00\x01\x02', '1\nno timing line\n']:
            self.assertIsInstance(parse_srt(junk), list)

    def test_smart_diff_on_empty_inputs(self):
        """Two empty inputs are identical, not an error."""
        self.assertEqual(smart_diff('', '')['kind'], 'identical')

    def test_smart_diff_garbage_vs_real(self):
        """Garbage against a real sample classifies without raising."""
        result = smart_diff('garbage with no cues', _load('dvb_spanish_real.srt'))
        self.assertIn('kind', result)


if __name__ == "__main__":
    unittest.main()
