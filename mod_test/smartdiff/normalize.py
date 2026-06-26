"""Normalisation that mirrors CCExtractor's own expected-output handling.

CCExtractor's test harness (``tests/extract_expected.py``) compares outputs
after stripping HTML/styling tags, unescaping entities, and trimming trailing
whitespace from each line (CEA-608 captions are space-padded to a fixed grid).
Reusing the same rules lets the smart diff separate a *cosmetic* difference
(padding or styling only) from a real text change.
"""

import re

_TAG_RE = re.compile(r'<[^>]+>')

# Same entities CCExtractor's extract_expected.py unescapes; '&amp;' is applied
# last so an escaped entity like '&amp;lt;' is not double-decoded.
_ENTITIES = (
    ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&#x27;', "'"),
    ('&deg;', '°'), ('&nbsp;', ' '), ('&amp;', '&'),
)


def strip_tags(text: str) -> str:
    """
    Remove HTML/styling tags such as ``<font color=...>`` or ``<i>``.

    :param text: Raw cue text.
    :type text: str
    :return: Text with tags removed.
    :rtype: str
    """
    return _TAG_RE.sub('', text)


def unescape(text: str) -> str:
    """
    Unescape the HTML entities CCExtractor emits.

    :param text: Raw cue text.
    :type text: str
    :return: Text with entities decoded.
    :rtype: str
    """
    for entity, char in _ENTITIES:
        text = text.replace(entity, char)
    return text


def rstrip_lines(text: str) -> str:
    """
    Trim trailing whitespace from each line (CEA-608 padding is cosmetic).

    :param text: Raw cue text.
    :type text: str
    :return: Text with per-line trailing whitespace removed.
    :rtype: str
    """
    return '\n'.join(line.rstrip() for line in text.split('\n'))


def plain(text: str) -> str:
    """
    Fully normalise: unescape entities, strip tags, trim trailing whitespace.

    :param text: Raw cue text.
    :type text: str
    :return: The fully normalised text.
    :rtype: str
    """
    return rstrip_lines(strip_tags(unescape(text)))


def classify_text_pair(expected: str, actual: str) -> str:
    """
    Classify how two cue texts differ, ignoring progressively more cosmetics.

    :param expected: Expected cue text.
    :type expected: str
    :param actual: Actual cue text.
    :type actual: str
    :return: ``match`` (identical), ``whitespace`` (only trailing padding differs),
        ``formatting`` (only tags/entities differ), or ``text`` (a real change).
    :rtype: str
    """
    if expected == actual:
        return 'match'
    if rstrip_lines(expected) == rstrip_lines(actual):
        return 'whitespace'
    if plain(expected) == plain(actual):
        return 'formatting'
    return 'text'
