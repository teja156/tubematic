"""The looks treat_image bakes into a generated still (TMDEV-229/230/231).

Each treatment turns one still into a new PNG once, on the server, so the
renderer only ever draws a plain image. A per-frame CSS or SVG filter doing the
same work costs 10 to 100 times more in software GL (the collage spike rendered
at about 65 s per video second), which is why none of these happens at render
time.

    print      a grey 45-degree halftone with a white paper border (Editorial Collage)
    sticker    the subject cut out of a plain background, a white die-cut edge
               and a hard shadow, on a transparent ground (Editorial Collage)
    engraving  ink on laid paper: the still mapped from dark ink to warm paper
               with a contrast curve (Archive and Engraving)
    pencil     a graphite line plate drawn from the still's edges over a light
               grey tone, on cream paper (Storybook Reveal's first reveal stage)

Every function takes and returns a PIL image; nothing here reads the database
or spends money. Pillow only: nothing in mcp/ imports numpy
(tests/test_removed_tools.py).
"""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

TREATMENTS = ("print", "sticker", "engraving", "pencil")

# Colours, from the research cards' palettes.
PRINT_INK = (58, 56, 54)          # halftone dots: dark grey, never black
PRINT_PAPER = (224, 220, 218)     # #E0DCDA, Collage's paper white
PRINT_CELL = 9                    # halftone cell, px at 1088 wide
PRINT_BORDER = 0.045              # white border, a fraction of the width
ENGRAVE_INK = (24, 20, 17)        # #181411
ENGRAVE_PAPER = (241, 232, 210)   # #F1E8D2, laid paper
PENCIL_GRAPHITE = (56, 56, 47)    # #38382F
PENCIL_PAPER = (244, 245, 238)    # #F4F5EE
STICKER_EDGE = 14                 # white die-cut edge, px
STICKER_SHADOW = (6, 10)          # hard shadow offset, px
STICKER_SHADOW_ALPHA = 72         # about 0.28
STICKER_TOLERANCE = 34            # how far from the background colour still counts as background


def apply(im: Image.Image, treatment: str) -> Image.Image:
    if treatment not in TREATMENTS:
        raise ValueError(f"unknown treatment {treatment!r}; expected one of {TREATMENTS}")
    return {"print": halftone_print, "sticker": sticker, "engraving": engraving,
            "pencil": pencil}[treatment](im)


def _grey(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA"):
        ground = Image.new("RGB", im.size, (255, 255, 255))
        ground.paste(im.convert("RGBA"), mask=im.convert("RGBA").getchannel("A"))
        im = ground
    return ImageOps.autocontrast(im.convert("L"), cutoff=1)


def halftone_print(im: Image.Image) -> Image.Image:
    """A grey 45-degree dot screen, each dot sized by the darkness under it,
    framed by a white paper border."""
    grey = _grey(im)
    w, h = grey.size
    cell = max(4, round(PRINT_CELL * w / 1088))
    turned = grey.rotate(45, expand=True, fillcolor=255, resample=Image.BICUBIC)
    tw, th = turned.size
    cols, rows = -(-tw // cell), -(-th // cell)
    means = turned.resize((cols, rows), Image.BOX)
    screen = Image.new("L", (cols * cell, rows * cell), 255)
    draw = ImageDraw.Draw(screen)
    px = means.load()
    half = cell / 2
    for y in range(rows):
        for x in range(cols):
            dark = 1 - px[x, y] / 255
            if dark < 0.04:
                continue
            r = half * 1.42 * dark ** 0.5      # area follows darkness; 1.42 lets full cells touch
            cx, cy = x * cell + half, y * cell + half
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
    back = screen.rotate(-45, expand=True, fillcolor=255, resample=Image.BICUBIC)
    bw, bh = back.size
    left, top = (bw - w) // 2, (bh - h) // 2
    dots = back.crop((left, top, left + w, top + h))
    inked = ImageOps.colorize(dots, black=PRINT_INK, white=PRINT_PAPER)
    border = round(w * PRINT_BORDER)
    framed = Image.new("RGB", (w, h), PRINT_PAPER)
    framed.paste(inked.resize((w - 2 * border, h - 2 * border), Image.LANCZOS), (border, border))
    return framed


# The cut-out is found on a quarter-size copy (a flood fill is a Python loop),
# then sharpened against the full-size "close to the background" mask.
_MASK_SCALE = 4


def _flood_from_border(mask: Image.Image) -> Image.Image:
    """`mask` is 255 where a pixel may be background. Returns 255 where such a
    pixel is joined to the picture's border by other such pixels."""
    w, h = mask.size
    work = mask.copy()
    seeds = [(x, 0) for x in range(0, w, 3)] + [(x, h - 1) for x in range(0, w, 3)] \
        + [(0, y) for y in range(0, h, 3)] + [(w - 1, y) for y in range(0, h, 3)]
    for xy in seeds:
        if work.getpixel(xy) == 255:
            ImageDraw.floodfill(work, xy, 128)
    return work.point(lambda v: 255 if v == 128 else 0)


def _background_mask(rgb: Image.Image) -> Image.Image:
    """255 where a pixel is background: close to the colour of the border and
    joined to the border. Only a plain background comes out clean, which is
    why the Collage skill asks for an isolated object on a plain ground."""
    rgb = rgb.convert("RGB")
    w, h = rgb.size
    border = [rgb.getpixel((x, y)) for x in range(0, w, 7) for y in (0, h - 1)] \
        + [rgb.getpixel((x, y)) for y in range(0, h, 7) for x in (0, w - 1)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg))
    r, g, b = diff.split()
    total = ImageChops.add(ImageChops.add(r, g), b)        # clipped at 255, plenty above the tolerance
    near = total.point(lambda v: 255 if v <= STICKER_TOLERANCE else 0)
    small = near.resize((max(1, w // _MASK_SCALE), max(1, h // _MASK_SCALE)), Image.BOX)
    small = small.point(lambda v: 255 if v >= 128 else 0)
    joined = _flood_from_border(small).resize((w, h), Image.NEAREST)
    # grow the coarse region one cell so its edge reaches the true edge, then keep only near pixels
    joined = joined.filter(ImageFilter.MaxFilter(2 * _MASK_SCALE + 1))
    return ImageChops.multiply(joined, near)


def _grow(mask: Image.Image, px: int) -> Image.Image:
    """Dilate a 0/255 mask by about px: blur, then any trace of the shape counts."""
    if px <= 0:
        return mask
    return mask.filter(ImageFilter.GaussianBlur(px / 2)).point(lambda v: 255 if v > 8 else 0)


def _solid(mask: Image.Image) -> Image.Image:
    """Drop specks and fill holes: a hole is a gap the border cannot reach."""
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    w, h = mask.size
    small = ImageOps.invert(mask).resize((max(1, w // _MASK_SCALE), max(1, h // _MASK_SCALE)), Image.BOX)
    small = small.point(lambda v: 255 if v >= 250 else 0)
    outside = _flood_from_border(small).resize((w, h), Image.NEAREST)
    return ImageChops.lighter(mask, ImageOps.invert(outside))


def sticker(im: Image.Image) -> Image.Image:
    """The subject on a transparent ground with a white die-cut edge and a hard
    shadow. A still that already has transparency keeps its own alpha; an
    opaque one has its plain background keyed out from the borders."""
    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda v: 255 if v > 127 else 0)
    if alpha.getextrema()[0] == 255:                       # opaque: key out the ground
        alpha = ImageOps.invert(_background_mask(rgba))
    alpha = _solid(alpha)
    if alpha.getbbox() is None:
        raise ValueError("no subject found: the whole picture matched its background colour")
    w, h = rgba.size
    pad = STICKER_EDGE + max(STICKER_SHADOW) + 4
    canvas = (w + 2 * pad, h + 2 * pad)

    def placed(mask: Image.Image) -> Image.Image:
        out = Image.new("L", canvas, 0)
        out.paste(mask, (pad, pad))
        return out

    subject_mask = placed(alpha)
    edge = _grow(subject_mask, STICKER_EDGE).filter(ImageFilter.GaussianBlur(0.8))
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas, (23, 23, 22, 0))
    shadow.putalpha(edge.point(lambda v: v * STICKER_SHADOW_ALPHA // 255))
    out.alpha_composite(shadow, STICKER_SHADOW)
    white = Image.new("RGBA", canvas, (250, 248, 244, 0))
    white.putalpha(edge)
    out.alpha_composite(white)
    subject = Image.new("RGBA", canvas, (0, 0, 0, 0))
    subject.paste(rgba, (pad, pad))
    subject.putalpha(subject_mask.filter(ImageFilter.GaussianBlur(0.8)))
    out.alpha_composite(subject)
    return out.crop(out.getbbox())


def engraving(im: Image.Image) -> Image.Image:
    """Ink on laid paper: an S-curve on the tones, then dark ink to warm paper."""
    grey = _grey(im)
    curve = [round(255 * (0.5 - 0.5 * math.cos(math.pi * (v / 255) ** 1.1))) for v in range(256)]
    return ImageOps.colorize(grey.point(curve), black=ENGRAVE_INK, white=ENGRAVE_PAPER)


def pencil(im: Image.Image) -> Image.Image:
    """A graphite plate: the still's edges as soft pencil lines over a pale grey
    tone of the same picture, on cream paper. It lines up with the colour still
    pixel for pixel, so the colour can flood over it."""
    grey = _grey(im)
    # a median filter takes the paper's grain out first, which would otherwise come back as speckle
    soft = grey.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    edges = soft.filter(ImageFilter.FIND_EDGES)
    # a fixed curve, never a contrast stretch (that turns the paper's faint noise into speckle):
    # an edge under 8 is paper, a stronger one a pencil line that darkens with it
    lines = edges.point(lambda e: 255 if e < 8 else max(30, 255 - (e - 8) * 9))
    tone = grey.point(lambda v: 255 if v > 225 else 196 + round(v * 59 / 255))   # a light wash on the shapes, clean paper
    plate = ImageChops.darker(lines, tone)
    return ImageOps.colorize(plate, black=PENCIL_GRAPHITE, white=PENCIL_PAPER)
