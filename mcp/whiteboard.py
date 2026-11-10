"""Whiteboard (TMDEV-197): the checks a Whiteboard scene-config must pass before
it is written, so an unattended agent cannot ship a board whose writing does not
fit, collides, or cannot keep up with the narration.

A Whiteboard video is one installed `Whiteboard` scene spanning every frame.
The agent writes no code and no coordinates: `props.whiteboard` holds regions
(one screen of board each, visited in order), each with a layout of named slots
and items (text, formulas, doodles from a fixed library, arrows and marks)
timed to the narration's word frames, plus the frame the recap starts. The
renderer's side of this contract is
renderer/remotion/src/scenes/installed/whiteboard/ (contract.ts, layout.ts,
schedule.ts).

Keep in sync: BOARD, SIZES, LIMITS, TIMING, SPEED, FLOOR, LAYOUTS, INKS, MARKS,
GLYPH_EM and the functions below mirror contract.ts, layout.ts and schedule.ts,
operation for operation, so the validator and the renderer agree on every
line break and every frame. mcp/tests/test_whiteboard.py reads the TypeScript
constants and runs the shared cases in tests/fixtures/whiteboard_contract.json
on both sides, so a drift fails a test instead of a render.

Free of the database and of I/O: the caller passes the style, the config, the
narration's word start frames and the pack's doodle list.
"""
from __future__ import annotations

import math
import re

SCENE_SRC = "Whiteboard"
PROPS_KEY = "whiteboard"
STYLE_ID = "whiteboard"

BOARD = {"regionW": 1080, "regionH": 1040, "gapX": 160, "gapY": 240, "bandCenterY": 787, "pad": 10}
SIZES = {"text": 68, "big": 92, "formula": 80, "label": 58, "lineHeight": 1.15}
LIMITS = {
    "minRegions": 2,
    "maxRegions": 6,
    "textLines": 2,
    "labelLines": 2,
    "maxHighlightsPerRegion": 1,
    "maxStillSeconds": 3.5,
    "recapMinSeconds": 2,
    "recapMaxSeconds": 8,
}
TIMING = {"lag": 12, "glide": 42, "snap": 2, "read": 15, "gap": 2, "recapPull": 30, "recapNumberStep": 6}
SPEED = {"text": 1.875, "big": 4, "formula": 2.5, "label": 1.875, "doodle": 30, "arrow": 14, "mark": 12}
FLOOR = {"text": 0.9, "formula": 1.0, "minText": 8, "doodle": 18, "arrow": 8, "mark": 8}
LAYOUTS = {
    "stack": {
        "1": (60, 60, 960, 230),
        "2": (60, 290, 960, 230),
        "3": (60, 520, 960, 230),
        "4": (60, 750, 960, 230),
    },
    "pair": {
        "top": (60, 60, 960, 200),
        "left": (60, 280, 450, 480),
        "right": (570, 280, 450, 480),
        "bottom": (60, 780, 960, 200),
    },
    "compare": {
        "left_title": (60, 60, 450, 150),
        "right_title": (570, 60, 450, 150),
        "left_1": (60, 230, 450, 230),
        "left_2": (60, 470, 450, 230),
        "left_3": (60, 710, 450, 230),
        "right_1": (570, 230, 450, 230),
        "right_2": (570, 470, 450, 230),
        "right_3": (570, 710, 450, 230),
    },
    "focus": {
        "top": (60, 60, 960, 220),
        "center": (60, 300, 960, 440),
        "bottom": (60, 760, 960, 220),
    },
}
INKS = {"black": "#23262c", "blue": "#2a5cb3", "orange": "#d97757"}
MARKS = ("highlight", "underline", "circle", "box", "cross")
ITEM_KINDS = ("text", "formula", "doodle", "arrow") + MARKS
PLACED = ("text", "formula", "doodle")
DOODLE_MAX = 420
DOODLE_MIN = 120
DOODLE_LABEL_GAP = 28
ARROW_CLEAR = 18
# An arrow shorter than this between its two boxes is a tick, not an arrow.
MIN_ARROW = 40
MAX_ITEMS_PER_REGION = 12
MAX_ERRORS = 12
_ID = re.compile(r"^[a-z0-9_]{1,24}$")

GLYPH_EM = {
    " ": 0.385, "!": 0.478, "\"": 0.484, "#": 0.78, "$": 0.592, "%": 0.991, "&": 0.786, "'": 0.22,
    "(": 0.478, ")": 0.53, "*": 0.375, "+": 0.6, ",": 0.262, "-": 0.531, ".": 0.237, "/": 0.282,
    "0": 0.513, "1": 0.302, "2": 0.583, "3": 0.547, "4": 0.545, "5": 0.506, "6": 0.542, "7": 0.472,
    "8": 0.59, "9": 0.506, ":": 0.246, ";": 0.306, "<": 0.475, "=": 0.672, ">": 0.616, "?": 0.608,
    "@": 1.078, "A": 0.63, "B": 0.624, "C": 0.617, "D": 0.666, "E": 0.551, "F": 0.542, "G": 0.597,
    "H": 0.651, "I": 0.309, "J": 0.486, "K": 0.602, "L": 0.546, "M": 0.756, "N": 0.631, "O": 0.619,
    "P": 0.549, "Q": 0.659, "R": 0.601, "S": 0.552, "T": 0.544, "U": 0.595, "V": 0.532, "W": 0.785,
    "X": 0.585, "Y": 0.561, "Z": 0.646, "[": 0.463, "\\": 0.6, "]": 0.521, "^": 0.422, "_": 0.619,
    "`": 0.258, "a": 0.51, "b": 0.567, "c": 0.489, "d": 0.539, "e": 0.488, "f": 0.435, "g": 0.481,
    "h": 0.563, "i": 0.26, "j": 0.26, "k": 0.493, "l": 0.266, "m": 0.819, "n": 0.554, "o": 0.456,
    "p": 0.538, "q": 0.519, "r": 0.362, "s": 0.467, "t": 0.451, "u": 0.486, "v": 0.422, "w": 0.71,
    "x": 0.474, "y": 0.52, "z": 0.48, "{": 0.462, "|": 0.456, "}": 0.626, "~": 0.586, " ": 0.385,
    "¡": 0.425, "¢": 0.545, "£": 0.732, "¤": 0.6, "¥": 0.615, "¦": 0.455, "§": 0.529, "¨": 0.335,
    "©": 0.708, "ª": 0.536, "«": 0.426, "¬": 0.496, "®": 0.671, "¯": 0.377, "°": 0.421, "±": 0.6,
    "²": 0.335, "³": 0.3, "´": 0.266, "µ": 0.439, "¶": 0.592, "·": 0.237, "¸": 0.301, "¹": 0.161,
    "º": 0.452, "»": 0.833, "¼": 0.823, "½": 0.858, "¾": 0.962, "¿": 0.396, "À": 0.631, "Á": 0.631,
    "Â": 0.631, "Ã": 0.631, "Ä": 0.631, "Å": 0.631, "Æ": 0.899, "Ç": 0.629, "È": 0.551, "É": 0.551,
    "Ê": 0.551, "Ë": 0.551, "Ì": 0.309, "Í": 0.309, "Î": 0.309, "Ï": 0.309, "Ð": 0.649, "Ñ": 0.631,
    "Ò": 0.619, "Ó": 0.619, "Ô": 0.619, "Õ": 0.619, "Ö": 0.619, "×": 0.433, "Ø": 0.619, "Ù": 0.578,
    "Ú": 0.578, "Û": 0.578, "Ü": 0.578, "Ý": 0.561, "Þ": 0.535, "ß": 0.599, "à": 0.518, "á": 0.518,
    "â": 0.518, "ã": 0.518, "ä": 0.518, "å": 0.518, "æ": 0.77, "ç": 0.493, "è": 0.454, "é": 0.454,
    "ê": 0.454, "ë": 0.454, "ì": 0.26, "í": 0.26, "î": 0.26, "ï": 0.26, "ð": 0.452, "ñ": 0.552,
    "ò": 0.452, "ó": 0.452, "ô": 0.452, "õ": 0.452, "ö": 0.452, "÷": 0.6, "ø": 0.452, "ù": 0.479,
    "ú": 0.479, "û": 0.479, "ü": 0.479, "ý": 0.52, "þ": 0.526, "ÿ": 0.52, "ı": 0.26, "Œ": 0.95,
    "œ": 0.906, "ʼ": 0.325, "ˆ": 0.354, "˚": 0.236, "˜": 0.414, "–": 0.624, "—": 0.968, "‘": 0.352,
    "’": 0.352, "‚": 0.346, "“": 0.606, "”": 0.595, "„": 0.569, "•": 0.237, "…": 0.795, "‹": 0.609,
    "›": 0.604, "⁄": 0.823, "€": 0.634, "™": 0.729,
}


def _js_round(x: float) -> int:
    """JavaScript's Math.round (half up), which Python's round (half to even) is not."""
    return math.floor(x + 0.5)


def text_width(s: str, size: float) -> float:
    em = 0.0
    for ch in s:
        em += GLYPH_EM.get(ch, 0.75)
    return em * size


def wrap_text(text: str, size: float, width: float) -> list[str]:
    """Greedy word wrap, as contract.ts wrapText."""
    lines: list[str] = []
    cur = ""
    for w in text.split():
        nxt = f"{cur} {w}" if cur else w
        if cur and text_width(nxt, size) > width:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines


def _inked(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def item_natural(it: dict) -> int:
    kind = it["kind"]
    if kind == "text":
        return _js_round(_inked(it["text"]) * (SPEED["big"] if it.get("big") else SPEED["text"]))
    if kind == "formula":
        return _js_round(_inked(it["text"]) * SPEED["formula"])
    if kind == "doodle":
        return SPEED["doodle"] + _js_round(_inked(it.get("label") or "") * SPEED["label"])
    if kind == "arrow":
        return SPEED["arrow"]
    return SPEED["mark"]


def item_floor(it: dict) -> int:
    kind = it["kind"]
    if kind == "text":
        return max(FLOOR["minText"], _js_round(_inked(it["text"]) * FLOOR["text"]))
    if kind == "formula":
        return max(FLOOR["minText"], _js_round(_inked(it["text"]) * FLOOR["formula"]))
    if kind == "doodle":
        label = it.get("label")
        return FLOOR["doodle"] + (max(FLOOR["minText"], _js_round(_inked(label) * FLOOR["text"])) if label else 0)
    if kind == "arrow":
        return FLOOR["arrow"]
    return FLOOR["mark"]


# ── layout (layout.ts) ────────────────────────────────────────────────────────

def region_origin(i: int) -> tuple[int, int]:
    row = i // 2
    col = i % 2 if row % 2 == 0 else 1 - (i % 2)
    return col * (BOARD["regionW"] + BOARD["gapX"]), row * (BOARD["regionH"] + BOARD["gapY"])


def _lh(size: float) -> float:
    return size * SIZES["lineHeight"]


def _line(text: str, x: float, y: float, size: float) -> dict:
    return {"text": text, "x": x, "y": y, "size": size, "width": text_width(text, size)}


def _union(rects: list[tuple]) -> tuple:
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return (x0, y0, x1 - x0, y1 - y0)


def _line_rect(l: dict) -> tuple:
    return (l["x"], l["y"], l["width"], _lh(l["size"]))


def text_line_cap(big: bool, h: float) -> int:
    size = SIZES["big"] if big else SIZES["text"]
    fit = math.floor((h - 2 * BOARD["pad"]) / _lh(size))
    return min(1 if big else LIMITS["textLines"], fit)


def place_item(it: dict, slot: tuple) -> dict:
    """bbox, lines and doodle box of one placed item, as layout.ts placeItem."""
    sx, sy, sw, sh = slot
    inner_w = sw - 2 * BOARD["pad"]
    cx = sx + sw / 2
    kind = it["kind"]
    if kind in ("text", "formula"):
        size = SIZES["formula"] if kind == "formula" else SIZES["big"] if it.get("big") else SIZES["text"]
        raw = [it["text"].strip()] if kind == "formula" else wrap_text(it["text"], size, inner_w)
        top = sy + (sh - len(raw) * _lh(size)) / 2
        lines = [_line(t, cx - text_width(t, size) / 2, top + i * _lh(size), size) for i, t in enumerate(raw)]
        return {"bbox": _union([_line_rect(l) for l in lines]), "lines": lines, "doodle": None}
    inner = min(inner_w, sh - 2 * BOARD["pad"])
    label = it.get("label")
    if not label:
        size = min(DOODLE_MAX, inner - 20)
        cy = sy + sh / 2
        return {"bbox": (cx - size / 2, cy - size / 2, size, size), "lines": [],
                "doodle": {"cx": cx, "cy": cy, "size": size}}
    if sw >= 1.8 * sh:
        size = min(DOODLE_MAX, sh - 2 * BOARD["pad"] - 20)
        label_w = inner_w - size - DOODLE_LABEL_GAP
        raw = wrap_text(label, SIZES["label"], label_w)
        widest = max(text_width(l, SIZES["label"]) for l in raw)
        group_w = size + DOODLE_LABEL_GAP + widest
        left = cx - group_w / 2
        cy = sy + sh / 2
        top = cy - (len(raw) * _lh(SIZES["label"])) / 2
        lines = [_line(t, left + size + DOODLE_LABEL_GAP, top + i * _lh(SIZES["label"]), SIZES["label"])
                 for i, t in enumerate(raw)]
        return {"bbox": _union([(left, cy - size / 2, size, size)] + [_line_rect(l) for l in lines]),
                "lines": lines, "doodle": {"cx": left + size / 2, "cy": cy, "size": size}}
    raw = wrap_text(label, SIZES["label"], inner_w)
    label_h = len(raw) * _lh(SIZES["label"])
    size = min(DOODLE_MAX, inner_w - 20, sh - 2 * BOARD["pad"] - label_h - 16)
    group_h = size + 16 + label_h
    top = sy + (sh - group_h) / 2
    lines = [_line(t, cx - text_width(t, SIZES["label"]) / 2, top + size + 16 + i * _lh(SIZES["label"]), SIZES["label"])
             for i, t in enumerate(raw)]
    return {"bbox": _union([(cx - size / 2, top, size, size)] + [_line_rect(l) for l in lines]),
            "lines": lines, "doodle": {"cx": cx, "cy": top + size / 2, "size": size}}


def fit_problem(it: dict, slot: tuple) -> str:
    """Why an item does not fit its slot, or "", as layout.ts fitProblem."""
    sx, _, sw, sh = slot
    inner_w = sw - 2 * BOARD["pad"]
    p = place_item(it, slot)
    too_wide = next((l for l in p["lines"] if l["width"] > inner_w + 0.5), None)
    if it["kind"] == "formula":
        return "is too long for one line in this slot" if too_wide else ""
    if it["kind"] == "text":
        cap = text_line_cap(bool(it.get("big")), sh)
        if too_wide:
            return f'has a word too long for this slot ("{too_wide["text"]}")'
        if len(p["lines"]) > cap:
            return f"needs {len(p['lines'])} lines; this slot holds {cap}"
        return ""
    if not it.get("label"):
        return ""
    if len(p["lines"]) > LIMITS["labelLines"]:
        return f"label needs {len(p['lines'])} lines; at most {LIMITS['labelLines']}"
    if too_wide or any(l["x"] + l["width"] > sx + sw - BOARD["pad"] + 0.5 for l in p["lines"]):
        return "label is too long for this slot"
    if (p["doodle"] or {}).get("size", 0) < DOODLE_MIN:
        return "label leaves the doodle too small; shorten it or use a bigger slot"
    return ""


def _grow(r: tuple, d: float) -> tuple:
    return (r[0] - d, r[1] - d, r[2] + 2 * d, r[3] + 2 * d)


def _center(r: tuple) -> tuple:
    return (r[0] + r[2] / 2, r[1] + r[3] / 2)


def _clip_t(p: tuple, q: tuple, r: tuple):
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - r[0]), (dx, r[0] + r[2] - p[0]), (-dy, p[1] - r[1]), (dy, r[1] + r[3] - p[1])):
        if pp == 0:
            if qq < 0:
                return None
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return (t0, t1) if t0 <= t1 else None


def segment_hits_rect(p: tuple, q: tuple, r: tuple) -> bool:
    return _clip_t(p, q, r) is not None


def arrow_ends(a: tuple, b: tuple) -> tuple:
    ca, cb = _center(a), _center(b)
    ta = _clip_t(ca, cb, _grow(a, ARROW_CLEAR))
    tb = _clip_t(ca, cb, _grow(b, ARROW_CLEAR))
    s = ta[1] if ta else 0
    e = tb[0] if tb else 1

    def at(t):
        return (ca[0] + (cb[0] - ca[0]) * t, ca[1] + (cb[1] - ca[1]) * t)
    return at(s), at(e)


# ── timing (schedule.ts) ──────────────────────────────────────────────────────

def recap_min_frames(region_count: int) -> int:
    """Frames the recap needs for the pull-back, every region's number to pop
    and the last to be seen: Whiteboard.tsx pops number i at recapPull +
    i * recapNumberStep."""
    return TIMING["recapPull"] + (region_count - 1) * TIMING["recapNumberStep"] + TIMING["read"]


def region_leave(regions: list, recap: int, i: int) -> int:
    return regions[i + 1]["startFrame"] if i + 1 < len(regions) else recap


def schedule(regions: list, recap: int) -> list[dict]:
    """{region, item, start, dur, deadline} per item, as schedule.ts (plus the
    deadline, which the validator needs to say what is too tight)."""
    out = []
    for ri, region in enumerate(regions):
        leave = region_leave(regions, recap, ri)
        items = region["items"]
        for k, it in enumerate(items):
            start = it["at"] + TIMING["lag"]
            nxt = items[k + 1] if k + 1 < len(items) else None
            deadline = nxt["at"] + TIMING["lag"] - TIMING["gap"] if nxt else leave - TIMING["read"]
            dur = max(1, min(item_natural(it), max(item_floor(it), deadline - start)))
            out.append({"region": ri, "item": it, "start": start, "dur": dur, "deadline": deadline,
                        "last": nxt is None})
    return out


# ── the checks ────────────────────────────────────────────────────────────────

def is_whiteboard_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Whiteboard video is exactly the one Whiteboard
    scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes if is_whiteboard_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The Whiteboard scene draws a whole Whiteboard video and is used only when the "
                    "video's visual_style is whiteboard (chosen at the topic). Build this video's "
                    "scenes from the other components.")
        return ""
    if (len(scenes) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Whiteboard video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"Whiteboard\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"whiteboard\": {...}}}. Put everything on its regions.")
    return ""


def _near_word(frame: int, word_starts: list[int]) -> tuple[bool, int]:
    if not word_starts:
        return True, frame
    nearest = min(word_starts, key=lambda w: abs(frame - w))
    return abs(frame - nearest) <= TIMING["snap"], nearest


def check(config: dict, fps: int, word_starts: list[int], doodles: list[str]) -> list[str]:
    """Every problem with a Whiteboard config's one scene, as messages that
    name the region and item and what to change. [] when it is sound.
    Call after check_scene_use passed for a whiteboard video."""
    errs: list[str] = []

    def err(msg: str) -> None:
        if len(errs) < MAX_ERRORS:
            errs.append(msg)

    total = config.get("totalFrames")
    scene = config["scenes"][0]
    if scene.get("startFrame") != 0 or scene.get("durationInFrames") != total:
        err(f"The Whiteboard scene must start at frame 0 and last totalFrames ({total}) frames.")
    props = scene.get("props")
    wb = props.get(PROPS_KEY) if isinstance(props, dict) else None
    if not isinstance(wb, dict) or not isinstance(wb.get("regions"), list):
        return errs + ["props.whiteboard must be {\"regions\": [...], \"recapFrame\": <frame>}."]
    regions = wb["regions"]
    recap = wb.get("recapFrame")
    if not LIMITS["minRegions"] <= len(regions) <= LIMITS["maxRegions"]:
        return errs + [f"{len(regions)} regions; a board has {LIMITS['minRegions']} to {LIMITS['maxRegions']}. "
                       "Merge or split steps of the argument."]
    if not all(isinstance(r, dict) and _int(r.get("startFrame")) for r in regions):
        return errs + ["Every region needs a whole-number startFrame."]
    if not _int(recap) or not _int(total):
        return errs + ["recapFrame (and totalFrames) must be whole numbers."]
    starts = [r["startFrame"] for r in regions]
    if starts[0] != 0:
        err("The first region must start at frame 0.")
    for i in range(1, len(starts)):
        if starts[i] <= starts[i - 1]:
            return errs + ["Regions must start in increasing order."]

    min_region = TIMING["glide"] + int(LIMITS["recapMinSeconds"] * fps)
    for i, r in enumerate(regions):
        leave = region_leave(regions, recap, i)
        where = f"Region {i + 1} (frames {r['startFrame']}-{leave - 1})"
        if i > 0:
            ok, nearest = _near_word(r["startFrame"], word_starts)
            if not ok:
                err(f"{where} starts at frame {r['startFrame']}, which is not on a word; start it on the "
                    f"first word of its sentence (the nearest word starts at {nearest}).")
        if leave - r["startFrame"] < min_region:
            err(f"{where} lasts {leave - r['startFrame']} frames; a region needs at least {min_region} "
                "(the camera's glide plus 2 seconds). Merge it with a neighbour.")
        _check_region(r, i, where, doodles, word_starts, err)

    ok, nearest = _near_word(recap, word_starts)
    if recap <= starts[-1]:
        err("recapFrame must come after the last region starts.")
    elif not ok:
        err(f"recapFrame {recap} is not on a word; start the recap on a word (the nearest starts at {nearest}).")
    recap_len = total - recap
    recap_min = max(int(LIMITS["recapMinSeconds"] * fps), recap_min_frames(len(regions)))
    if not recap_min <= recap_len <= int(LIMITS["recapMaxSeconds"] * fps):
        err(f"The recap lasts {recap_len} frames (recapFrame {recap} to the end at {total}); with "
            f"{len(regions)} regions it must last {recap_min} frames to {LIMITS['recapMaxSeconds']} seconds, "
            "so every region's number has popped and been seen. Start it on the closing sentence.")
    if errs:
        return errs

    # Timing: the marker must be able to draw every item, one at a time.
    events = list(starts) + [recap]
    for s in schedule(regions, recap):
        it = s["item"]
        floor = item_floor(it)
        events.append(s["start"])
        room = s["deadline"] - s["start"]
        if room < floor:
            until = ("before the next item starts" if not s["last"] else
                     f"before the camera leaves the region ({TIMING['read']} frames are kept for reading it)")
            err(f"Region {s['region'] + 1}, item {it['id']!r} (at {it['at']}): the marker needs at least "
                f"{floor} frames to draw it but has {max(0, room)} {until}. Time it to an earlier word, "
                "give what follows a later word, or shorten its text.")
    still = int(LIMITS["maxStillSeconds"] * fps)
    events.sort()
    for a, b in zip(events, events[1:]):
        if b - a > still:
            err(f"Nothing new happens between frames {a} and {b}; something must start (an item or a "
                f"region) at least every {LIMITS['maxStillSeconds']} seconds. Add an item or a mark.")
            break
    return errs


def _check_region(region: dict, ri: int, where: str, doodles: list[str], word_starts: list[int], err) -> None:
    layout = _str(region.get("layout"))
    if layout not in LAYOUTS:
        err(f"{where}: layout {layout!r} is not one of {sorted(LAYOUTS)}.")
        return
    slots = LAYOUTS[layout]
    items = region.get("items")
    if not isinstance(items, list) or not items:
        err(f"{where}: items must be a non-empty list.")
        return
    if len(items) > MAX_ITEMS_PER_REGION:
        err(f"{where} has {len(items)} items; at most {MAX_ITEMS_PER_REGION}. Split it into two regions.")
    seen: dict[str, dict] = {}
    placed: dict[str, tuple] = {}
    used_slots: set[str] = set()
    highlights = 0
    prev_at = None
    earliest = region["startFrame"] + (TIMING["glide"] - TIMING["lag"] if ri > 0 else 0)
    for it in items:
        if not isinstance(it, dict):
            err(f"{where}: every item must be an object.")
            continue
        iid = it.get("id")
        if not isinstance(iid, str) or not _ID.match(iid):
            err(f"{where}: item id {iid!r} must be 1-24 lowercase letters, digits or underscores.")
            continue
        if iid in seen:
            err(f"{where}: item id {iid!r} is used twice.")
            continue
        what = f"{where}, item {iid!r}"
        kind = _str(it.get("kind"))
        if kind not in ITEM_KINDS:
            err(f"{what}: kind {kind!r} is not one of {list(ITEM_KINDS)}.")
            continue
        at = it.get("at")
        if not _int(at):
            err(f"{what}: at must be a whole frame number (a word's startFrame).")
            continue
        ok, nearest = _near_word(at, word_starts)
        if not ok:
            err(f"{what}: at {at} is not on a word; use the startFrame of the word it illustrates "
                f"(the nearest starts at {nearest}).")
        if prev_at is not None and at <= prev_at:
            err(f"{what}: items draw one at a time in the order listed, so each at must be later than "
                f"the previous item's ({prev_at}).")
        if at < earliest:
            err(f"{what}: at {at} is before the camera has reached this region; the first item can be "
                f"at frame {earliest} at the earliest (a later word).")
        prev_at = at
        ink = it.get("ink")
        if ink is not None and not isinstance(ink, str):
            err(f"{what}: ink must be one of {sorted(INKS)}.")
        elif kind == "highlight":
            if ink is not None:
                err(f"{what}: a highlight is always yellow; leave out ink.")
        elif ink is not None and ink not in INKS:
            err(f"{what}: ink {ink!r} is not one of {sorted(INKS)}.")

        if kind in PLACED:
            slot = _str(it.get("slot"))
            if slot not in slots:
                err(f"{what}: slot {slot!r} is not a slot of the {layout} layout ({', '.join(slots)}).")
                continue
            if slot in used_slots:
                err(f"{what}: slot {slot!r} is already used in this region.")
                continue
            used_slots.add(slot)
            text_key = "label" if kind == "doodle" else "text"
            text = it.get(text_key)
            if kind == "doodle":
                if _str(it.get("doodle")) not in doodles:
                    err(f"{what}: doodle {it.get('doodle')!r} is not in the library; pick one of the listed names.")
                    continue
                if text is not None and (not isinstance(text, str) or not text.strip()):
                    err(f"{what}: label, when present, must be a short phrase.")
                    continue
            elif not isinstance(text, str) or not text.strip():
                err(f"{what}: text must be a short phrase.")
                continue
            if kind == "text" and "big" in it and not isinstance(it["big"], bool):
                err(f"{what}: big must be true or false.")
                continue
            if isinstance(text, str):
                missing = sorted({ch for ch in text if ch not in GLYPH_EM})
                if missing:
                    err(f"{what}: the board's handwriting font has no {' '.join(missing)}; write it "
                        "in words or plain characters (x, ->, sqrt).")
                    continue
            problem = fit_problem(it, slots[slot])
            if problem:
                err(f"{what} {problem}.")
                continue
            placed[iid] = place_item(it, slots[slot])["bbox"]
        elif kind == "arrow":
            a, b = _str(it.get("from")), _str(it.get("to"))
            if a not in placed or b not in placed or a == b:
                err(f"{what}: an arrow goes from one earlier text, formula or doodle item of this region "
                    "to another (from and to are their ids).")
            else:
                p, q = arrow_ends(placed[a], placed[b])
                if math.hypot(q[0] - p[0], q[1] - p[1]) < MIN_ARROW:
                    err(f"{what}: {a!r} and {b!r} are too close for an arrow between them.")
                else:
                    # Every other placed item of the region, drawn before the
                    # arrow or after it: an arrow through either is unreadable.
                    crossed = next((o["id"] for o in items
                                    if isinstance(o, dict) and o.get("id") not in (a, b) and _placeable(o, slots)
                                    and segment_hits_rect(p, q, place_item(o, slots[o["slot"]])["bbox"])), None)
                    if crossed:
                        err(f"{what}: the arrow from {a!r} to {b!r} would cross {crossed!r}. Connect "
                            "neighbouring slots, or move the items.")
        else:
            target = _str(it.get("target"))
            tkind = seen.get(target, {}).get("kind") if target else None
            if target not in placed:
                err(f"{what}: target must be the id of an earlier text, formula or doodle item of this region.")
            elif kind in ("highlight", "underline") and tkind not in ("text", "formula"):
                err(f"{what}: {'a highlight' if kind == 'highlight' else 'an underline'} goes on text or a "
                    f"formula, not a {tkind}.")
            if kind == "highlight":
                highlights += 1
                if highlights > LIMITS["maxHighlightsPerRegion"]:
                    err(f"{what}: one highlight per region; it marks the one phrase that matters.")
        seen[iid] = it


def _str(v):
    """v when it is a string, else None, so a list or an object where a name
    belongs is reported as a wrong value instead of raising."""
    return v if isinstance(v, str) else None


def _placeable(it: dict, slots: dict) -> bool:
    """Whether an item is well-formed enough to place, for the arrow-crossing
    check (a malformed one has its own error)."""
    kind = _str(it.get("kind"))
    if kind not in PLACED or _str(it.get("slot")) not in slots:
        return False
    if kind == "doodle":
        return it.get("label") is None or (isinstance(it.get("label"), str) and it["label"].strip() != "")
    return isinstance(it.get("text"), str) and it["text"].strip() != ""


def region_windows(config: dict) -> list[tuple[int, int]]:
    """(start, end) of each region and of the recap, for the text audit: one
    whole-video scene would otherwise be sampled as a single scene."""
    try:
        wb = config["scenes"][0]["props"][PROPS_KEY]
        starts = [r["startFrame"] for r in wb["regions"]] + [wb["recapFrame"]]
        total = config["totalFrames"]
    except (KeyError, IndexError, TypeError):
        return []
    return [(s, starts[i + 1] if i + 1 < len(starts) else total) for i, s in enumerate(starts)]
