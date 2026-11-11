"""Draws a sheet of Whiteboard doodles as a PNG, for the authoring agent to look
at before it puts a doodle of its own on a board (TMDEV-197).

No automatic check can tell whether a drawing reads as a bicycle, so the agent
looks: each doodle sits in a labelled cell over a faint 0-100 grid (the box its
coordinates live in), drawn in marker ink on the board colour, beside shipped
doodles at the same scale. Drawn with Pillow from the validated geometry
(whiteboard.expand_doodle): a doodle is lines only, so a sheet takes
milliseconds and needs no browser. The video adds a hand wobble this sheet
leaves out.

Stdlib and Pillow only: server.py imports it beside mascot_sheets.
"""
from __future__ import annotations

import io

import whiteboard

CELL = 300
MARGIN = 30
LABEL_H = 34
SUPERSAMPLE = 2
BOARD = (251, 251, 251)
INK = (35, 38, 44)
GRID = (226, 228, 232)
GRID_STRONG = (205, 208, 214)
REF_INK = (120, 124, 132)
COLUMNS = 4
LINE_WIDTH = 8


def _cell(draw, x0: int, y0: int, strokes, ink, label: str, font, k: int) -> None:
    box = CELL - 2 * MARGIN
    ox, oy = (x0 + MARGIN) * k, (y0 + MARGIN) * k
    scale = box * k / whiteboard.DOODLE_LIMITS["box"]
    for v in range(0, 101, 10):
        colour = GRID_STRONG if v in (0, 50, 100) else GRID
        draw.line([(ox + v * scale, oy), (ox + v * scale, oy + 100 * scale)], fill=colour, width=k)
        draw.line([(ox, oy + v * scale), (ox + 100 * scale, oy + v * scale)], fill=colour, width=k)
    w = LINE_WIDTH * k
    for st in strokes:
        pts = [(ox + x * scale, oy + y * scale) for x, y in st]
        draw.line(pts, fill=ink, width=w, joint="curve")
        for px, py in (pts[0], pts[-1]):  # round caps
            draw.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=ink)
    draw.text(((x0 + MARGIN) * k, (y0 + CELL - 4) * k), label, fill=INK, font=font)


def render_sheet(custom: dict, reference: dict, font) -> bytes:
    """A PNG of every doodle in `custom` ({name: strokes}, already validated),
    then each of `reference` (shipped doodles, labelled as such), in a grid."""
    from PIL import Image, ImageDraw

    cells = [(name, whiteboard.expand_doodle(d), INK, name) for name, d in custom.items()]
    cells += [(name, whiteboard.expand_doodle(d), REF_INK, f"{name} (shipped)") for name, d in reference.items()]
    cols = min(COLUMNS, len(cells))
    rows = -(-len(cells) // cols)
    k = SUPERSAMPLE
    img = Image.new("RGB", (cols * CELL * k, rows * (CELL + LABEL_H) * k), BOARD)
    draw = ImageDraw.Draw(img)
    for i, (_, strokes, ink, label) in enumerate(cells):
        _cell(draw, (i % cols) * CELL, (i // cols) * (CELL + LABEL_H), strokes, ink, label, font, k)
    img = img.resize((cols * CELL, rows * (CELL + LABEL_H)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
