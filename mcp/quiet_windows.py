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
