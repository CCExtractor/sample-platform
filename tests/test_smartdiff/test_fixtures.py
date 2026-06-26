"""Golden-fixture tests against a real CCExtractor CEA-608 sample output."""

import os
import unittest

from mod_test.smartdiff.compare import smart_diff
from mod_test.smartdiff.srt import parse_srt

_FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'cea608_real.srt')


def _load():
    """
    Read the vendored real CCExtractor sample.

    :return: The raw .srt content.
    :rtype: str
    """
    with open(_FIXTURE, encoding='utf-8') as handle:
        return handle.read()


class RealSampleTests(unittest.TestCase):
    """Exercise the smart diff on genuine CCExtractor output, not synthetic strings."""

    def test_parses_real_sample(self):
        """The real sample parses into its two CEA-608 cues."""
        cues = parse_srt(_load())
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].start_ms, 5956)

    def test_identical_against_itself(self):
        """The real sample compared with itself is identical."""
        raw = _load()
        self.assertEqual(smart_diff(raw, raw)["kind"], "identical")

    def test_constant_shift_on_real_sample(self):
        """Shifting every timestamp by a constant is detected as timing_shift."""
        raw = _load()
        shifted = (raw
                   .replace('00:00:05,956', '00:00:06,206')
                   .replace('00:00:07,955', '00:00:08,205')
                   .replace('00:00:13,913', '00:00:14,163')
                   .replace('00:00:15,080', '00:00:15,330'))
        result = smart_diff(raw, shifted)
        self.assertEqual(result["kind"], "timing_shift")
        self.assertEqual(result["offset_ms"], 250)

    def test_depadding_is_cosmetic_on_real_sample(self):
        """Stripping the CEA-608 trailing padding is flagged as cosmetic only."""
        raw = _load()
        depadded = '\n'.join(line.rstrip() for line in raw.split('\n'))
        result = smart_diff(raw, depadded)
        self.assertIn(result["kind"], ("identical", "whitespace_change"))


if __name__ == "__main__":
    unittest.main()
