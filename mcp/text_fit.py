"""How wide a line of Barlow 700 text is, estimated from the shape of each
character (TMDEV-239/240). Code Scenes and Format Packs cap their texts by
these widths: a character count cannot tell "iiii" from "WWWW", and a text that
passes a count can still run out of its box or wrap to more lines than the
layout made room for.

Keep in sync: renderer/remotion/src/scenes/installed/fitText.ts, which sizes
and wraps the same texts in the renderer. Both run the shared cases in
tests/fixtures/text_fit_contract.json. The widths are on the wide side of
Barlow's real advances, so a text the estimate fits always fits.

Free of I/O.
"""
from __future__ import annotations

NARROW = "iIjlt.,:;'!|`"
SEMI = "fr()[]{}\"/\\-"
WIDE = "MWmw@%"


# The characters every bundled font of these styles draws: the intersection of
# the character maps of renderer/remotion/public/fonts/ barlow-latin-600/700,
# jetbrains-mono-latin-500/700 and ibm-plex-mono-latin-400/700, less control,
# invisible and combining characters. Read from the font files (fontTools
# getBestCmap); a new or changed font file means reading them again.
SUPPORTED_RANGES = (
    (0x0020, 0x007E), (0x00A0, 0x00AC), (0x00AE, 0x00FF), (0x0131, 0x0131), (0x0152, 0x0153),
    (0x02BC, 0x02BC), (0x02C6, 0x02C6), (0x02DA, 0x02DA), (0x02DC, 0x02DC), (0x2013, 0x2014),
    (0x2018, 0x201A), (0x201C, 0x201E), (0x2022, 0x2022), (0x2026, 0x2026), (0x2032, 0x2033),
    (0x2039, 0x203A), (0x2044, 0x2044), (0x20AC, 0x20AC), (0x2122, 0x2122), (0x2212, 0x2212),
    (0x2215, 0x2215),
)


def _supported(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in SUPPORTED_RANGES)


def unsupported_chars(text: str) -> list[str]:
    """Characters the bundled fonts (Barlow, JetBrains Mono, IBM Plex Mono,
    their Latin files) do not all draw: other scripts, emoji, arrows, most
    letters beyond Latin-1, combining and invisible characters, control
    characters. The browser would draw them in a fallback
    font of another width, or not at all, so these styles refuse them and the
    estimate below only ever measures characters it knows."""
    return [c for c in text if not _supported(c)]


def char_em(ch: str) -> float:
    if ch == " ":
        return 0.26
    if ord(ch) > 0xFFFF:
        return 1.25  # an emoji or other astral character
    if ch in NARROW:
        return 0.3
    if ch in SEMI:
        return 0.38
    if ch in WIDE:
        return 0.92
    if "A" <= ch <= "Z":
        return 0.66
    if "0" <= ch <= "9":
        return 0.58
    if "a" <= ch <= "z":
        return 0.55
    return 0.7


def width(text: str, size: float, letter_spacing: float = 0) -> float:
    return sum(char_em(c) for c in text) * size + letter_spacing * len(text)


def fit_size(text: str, max_width: float, base: int, minimum: int, letter_spacing: float = 0) -> int:
    """The largest whole size up to `base` at which `text` fits, never under
    `minimum` (fitText.ts fitFontSize)."""
    for size in range(base, minimum, -1):
        if width(text, size, letter_spacing) <= max_width:
            return size
    return minimum


def fits_at(text: str, max_width: float, size: int, letter_spacing: float = 0) -> bool:
    return width(text, size, letter_spacing) <= max_width


def wrap_count(text: str, size: float, max_width: float) -> int:
    """Lines `text` takes wrapped greedily at word breaks in `max_width`, a word
    wider than a line broken where it reaches the edge (fitText.ts wrapCount).
    The browser wraps the same text in at most as many lines."""
    words = text.split()
    if not words:
        return 1
    space = width(" ", size)
    lines, used = 1, 0.0
    for word in words:
        w = width(word, size)
        if used and used + space + w <= max_width:
            used += space + w
            continue
        if used:
            lines += 1
        used = 0.0
        for ch in word:
            cw = width(ch, size)
            if used and used + cw > max_width:
                lines += 1
                used = 0.0
            used += cw
    return lines
