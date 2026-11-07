"""
Quote and whitespace normalization for species-related text.

Deliberately has zero imports from species.models (or anything that does),
so models.py can import normalize_species_text() directly without creating
a circular import with asn_utils.py, which already imports from models.py.
"""

import re

# U+2018 ' U+2019 ' U+201A , U+201B ' U+2032 prime, backtick, acute accent,
# U+201C " U+201D " U+201E „ U+201F ‟ U+2033 double-prime, and the straight
# double quote all collapse to a straight single quote.
_QUOTE_CHARS = '‘’‚‛′`´“”„‟″"'
_QUOTE_TRANSLATION = str.maketrans({c: "'" for c in _QUOTE_CHARS})


def normalize_species_text(value, keep_linebreaks=False):
    """
    Normalize quote characters and whitespace. Case is never touched.

    - Every curly/smart quote variant (single and double) and the straight
      double quote become a straight single quote `'`.
    - keep_linebreaks=False (names): leading/trailing whitespace is removed
      and all runs of whitespace collapse to one space.
    - keep_linebreaks=True (free text): leading/trailing whitespace is
      removed and runs of spaces/tabs collapse to one space, but line
      breaks are left alone so paragraphs survive.
    """
    if not value:
        return ''
    value = value.translate(_QUOTE_TRANSLATION)
    if keep_linebreaks:
        value = re.sub(r'[ \t]+', ' ', value)
    else:
        value = re.sub(r'\s+', ' ', value)
    return value.strip()
