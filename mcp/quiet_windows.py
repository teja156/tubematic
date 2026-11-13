"""Insert windows as the main style's validators see them (TMDEV-224).

While an insert plays, the main style's layer is hidden, so the main style's
data stays quiet there: nothing of it starts inside a window, and its
"nothing changes for too long" rule does not count a window as still (the
insert is what changes on screen then). Each window is (a, b), frames a to
b - 1, sorted, as mcp/inserts.py's windows() returns them.

Shared by the whole-video main styles (whiteboard, bean_explainer,
storybook_atlas, under_the_hood, case_file_story); free of the database and of I/O.
"""
from __future__ import annotations


def window_at(frame: int, quiet) -> tuple[int, int] | None:
    """The window `frame` falls in (a <= frame < b), or None."""
    return next(((a, b) for a, b in quiet if a <= frame < b), None)


def window_text(window: tuple[int, int]) -> str:
    """A window as its first and last frame, the way messages name it."""
    return f"{window[0]}-{window[1] - 1}"


def uncovered(a: int, c: int, quiet) -> list[tuple[int, int]]:
    """The parts of frames a to c that no window covers, in order: the
    stretches a stillness rule measures. Without windows, [(a, c)]."""
    out = []
    x = a
    for wa, wb in quiet:
        if wb <= x or wa >= c:
            continue
        if wa > x:
            out.append((x, wa))
        x = max(x, wb)
    if x < c:
        out.append((x, c))
    return out


# A gap between two spoken words at least this long (frames) is a pause the
# script asked for: [pause] or [long pause] voiced as silence.
MIN_SILENCE = 12


def silent_windows(words, min_gap: int = MIN_SILENCE) -> list[tuple[int, int]]:
    """The stretches of the narration with no word in them, as windows
    (end of one word, start of the next), for gaps of at least `min_gap`.

    A style's stillness rule measures how long nothing new happens. Events
    sit on words, so nothing can be placed inside a pause, and a stage that
    holds through the silence has not stalled: the rule skips these stretches,
    as it skips an insert's window. `words` is the timeline's word list."""
    spans = []
    for w in words or []:
        try:
            spans.append((int(w["startFrame"]), int(w["endFrame"])))
        except (KeyError, TypeError, ValueError):
            continue
    spans.sort()
    return [(a_end, b_start) for (_, a_end), (b_start, _) in zip(spans, spans[1:]) if b_start - a_end >= min_gap]


def merged(*lists) -> list[tuple[int, int]]:
    """Several window lists as one, sorted and without overlaps, the shape
    `uncovered` reads."""
    out: list[list[int]] = []
    for a, b in sorted(w for lst in lists for w in (lst or ())):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]
