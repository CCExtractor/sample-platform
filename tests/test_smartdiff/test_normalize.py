"""Tests for CCExtractor-style normalisation of cue text."""

import unittest

from mod_test.smartdiff.normalize import (ascii_fold, classify_text_pair,
                                          plain, strip_tags, unescape)


class NormalizeTests(unittest.TestCase):
    """Tag stripping, entity unescaping, and cue-text classification."""

    def test_strip_tags(self):
        """HTML/styling tags are removed."""
        self.assertEqual(strip_tags('<font color="#fff">hi</font>'), 'hi')

    def test_unescape_entities(self):
        """Known HTML entities are decoded, including a nested &amp;."""
        self.assertEqual(unescape('a &lt;b&gt; &amp; 30&deg;'), 'a <b> & 30°')

    def test_plain_combines_rules(self):
        """plain() strips tags, unescapes, and rstrips padding together."""
        self.assertEqual(plain('<i>hi &amp; bye</i>   '), 'hi & bye')

    def test_classify_match(self):
        """Identical text classifies as match."""
        self.assertEqual(classify_text_pair('hello', 'hello'), 'match')

    def test_classify_whitespace_only(self):
        """Trailing CEA-608 padding differences classify as whitespace."""
        self.assertEqual(classify_text_pair('HELLO WORLD', 'HELLO WORLD     '), 'whitespace')

    def test_classify_formatting_only(self):
        """A tags-only difference classifies as formatting."""
        self.assertEqual(classify_text_pair('hello', '<i>hello</i>'), 'formatting')

    def test_ascii_fold_decomposes_accents(self):
        """ascii_fold strips accents and drops non-ASCII characters."""
        self.assertEqual(ascii_fold('Voilà café ♪'), 'Voila cafe ')

    def test_classify_encoding_only(self):
        """A non-ASCII/accent-only difference classifies as encoding."""
        self.assertEqual(classify_text_pair('PRÉCIS', 'PRECIS'), 'encoding')

    def test_classify_real_text_change(self):
        """A genuine text change classifies as text."""
        self.assertEqual(classify_text_pair('hello', 'goodbye'), 'text')


if __name__ == "__main__":
    unittest.main()
