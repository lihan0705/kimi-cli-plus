from __future__ import annotations

import random
import re
import string
import unicodedata

_NEWLINE_RE = re.compile(r"[\r\n]+")


def sanitize_unicode(text: str) -> str:
    """
    Sanitize Unicode text to mitigate hidden character attacks and JSON parsing errors.
    Ported from Claude Code's implementation.

    This function:
    1. Applies NFKC normalization.
    2. Removes dangerous Unicode categories: Cf (format), Co (private use), Cn (unassigned).
    3. Specifically strips known problematic ranges (Zero-width spaces, LTR/RTL marks, BOM, etc.).
    """
    if not text:
        return text

    # NFKC normalization
    current = unicodedata.normalize("NFKC", text)

    # Remove dangerous categories: Cf (Format), Co (Private Use), Cn (Unassigned)
    # We use a character-by-character filter because standard 're' doesn't support \p{Cf}
    current = "".join(ch for ch in current if unicodedata.category(ch) not in {"Cf", "Co", "Cn"})

    # Explicitly strip problematic ranges as a secondary defense
    # - \u200B-\u200F: Zero-width space, LTR/RTL marks
    # - \u202A-\u202E: Directional formatting
    # - \u2066-\u2069: Directional isolates
    # - \uFEFF: BOM
    # - \uE000-\uF8FF: Private Use Area
    problematic_pattern = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\ue000-\uf8ff]")
    current = problematic_pattern.sub("", current)

    return current


def shorten_middle(text: str, width: int, remove_newline: bool = True) -> str:
    """Shorten the text by inserting ellipsis in the middle."""
    if len(text) <= width:
        return text
    if remove_newline:
        text = _NEWLINE_RE.sub(" ", text)
    return text[: width // 2] + "..." + text[-width // 2 :]


def random_string(length: int = 8) -> str:
    """Generate a random string of fixed length."""
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for _ in range(length))
