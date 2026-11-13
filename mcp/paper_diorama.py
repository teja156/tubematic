"""Paper Diorama (TMDEV-228): the checks a Paper Diorama scene-config must pass
before it is written, so an unattended agent cannot ship a prop that does not
exist, two props on top of each other, an event off the narration, a prop
standing where the captions or the banner are, or a still stage.

A Paper Diorama video is one installed `PaperDiorama` scene spanning every
frame. The agent writes no code for it: `props.paperDiorama` holds the house
critter's look, any props of its own as paper pieces (`customProps`), and sets
timed to the narration's word frames: a room, a taped banner, the props that
enter named slots, and events (moves, swaps, the critter's expressions,
stamps, rings, routes, labels, a snap zoom). The renderer's side of this
contract is renderer/remotion/src/scenes/installed/paperDiorama/contract.ts.

Keep in sync: COLORS, ROOMS, SLOTS, LEVELS, SCALES, ZONES, CRITTER, LIMITS,
TIMING and the catalogues mirror contract.ts, critter_box mirrors critter.ts,
and pop_scale, slot_box, stage_scale and banner_font_size mirror stage.ts and
PaperDiorama.tsx. mcp/tests/test_paper_diorama.py reads the TypeScript
constants and the style pack, and both sides run the shared cases in
tests/fixtures/paper_diorama_contract.json, so a drift fails a test instead of
a render.

Free of the database and of I/O: the caller passes the config, the
narration's fps and word start frames, and the pack's `extra` block (which
lists the shipped props and their sizes).
"""
from __future__ import annotations

import math
import re

from quiet_windows import awake, uncovered, window_at, window_text

SCENE_SRC = "PaperDiorama"
PROPS_KEY = "paperDiorama"
STYLE_ID = "paper_diorama"

W, H = 1080, 1920
COLORS = (
    "cream", "creamHi", "creamLo", "paper", "tape", "ink", "inkSoft", "white",
    "wood", "woodLo", "woodHi", "brass", "brassLo", "metal", "metalLo",
    "board", "boardLo", "boardHi", "sage", "sageLo", "screen", "screenHi", "screenText",
    "hero", "heroLo", "cap", "capLo", "tag", "purple",
    "go", "goDim", "nogo", "nogoDim", "amber", "amberDim", "yellow", "pink", "sky", "skyLo",
)
ROOMS = {
    "bank-vault": 1450, "courtroom": 1450, "warehouse": 1450, "mission-control": 1440,
    "airport-gate": 1440, "subway-platform": 1440, "diner": 1440, "bedroom-day": 1450,
}
SLOTS = {"l": 190, "cl": 365, "c": 540, "cr": 715, "r": 890}
LEVELS = {"floor": 0, "shelf": 420, "air": 760}
SCALES = {"s": 0.7, "m": 1, "l": 1.35}
ZONES = {"bannerTop": 270, "bannerBottom": 400, "bannerMaxWidth": 860, "stageTop": 430, "stageBottom": 1480}
CRITTER = {
    "size": 240,
    "expressions": ("idle", "happy", "shock", "worried", "squint", "sleep"),
    "accessories": ("none", "cap", "hardhat", "headset", "glasses", "bowtie", "beret", "visor"),
    "bobAmp": 3, "bobPeriod": 36, "blinkEvery": 83, "blinkFrames": 3,
}
CRITTER_COLORS = ("hero", "cap", "sage", "amber", "purple", "pink")
EVENTS = ("exit", "move", "swap", "expr", "hop", "stamp", "ring", "route", "label", "zoom")
ENTERS = ("pop", "slide", "drop")
CUTS = ("cut", "tear")
SHAPES = ("rect", "ellipse", "poly", "text")
FONTS = ("banner", "label", "mono")

LIMITS = {
    "maxSets": 24, "minSetSeconds": 1.2, "maxItemsPerSet": 6, "maxEvents": 160,
    "bannerChars": 28, "labelChars": 16, "stampChars": 12, "textChars": 14,
    "maxCustomProps": 8, "maxPieces": 60, "maxPropW": 520, "maxPropH": 620,
    "maxZooms": 3, "maxStillSeconds": 3,
}
TIMING = {
    "snap": 2, "pop": 8, "slide": 10, "drop": 9, "exit": 6, "move": 12, "swap": 2, "hop": 12,
    "stamp": 6, "ring": 9, "route": 18, "label": 6, "zoomIn": 4, "zoomHold": 14, "zoomOut": 12,
    "tear": 12, "zoomScale": 1.18, "readFrames": 8,
}

MAX_ERRORS = 12
# Two things standing at once may overlap by at most this share of the smaller box.
OVERLAP_SHARE = 0.18
# Events that act on something already on stage, and what they may name.
_TARGETS_CRITTER = {"expr", "hop", "move"}
_ID = re.compile(r"^[a-z][a-z0-9-]{0,23}$")
_PROP_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_EVENT_KEYS = {
    "exit": {"target"}, "move": {"target", "to", "level"}, "swap": {"target", "prop"},
    "expr": {"target", "value"}, "hop": {"target"}, "stamp": {"text", "target", "level", "color"},
    "ring": {"target", "color"}, "route": {"from", "target", "color"}, "label": {"target", "text"},
    "zoom": {"target"},
}
_SET_KEYS = {"start", "room", "banner", "cut", "critter", "items", "events"}
_ITEM_KEYS = {"id", "prop", "slot", "level", "scale", "at", "enter"}

# critter.ts: U = size / 10; the box is 11.2 U wide and (2.6 + 7 + 2.2) U tall.
_U = CRITTER["size"] / 10
CRITTER_W = 11.2 * _U
CRITTER_H = (2.6 + 7 + 2.2) * _U


def _k(v):
    """v when it is a string, else None: a list or object from the config
    would raise on a dict lookup, and None is in none of them."""
    return v if isinstance(v, str) else None


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= limit and "\n" not in v


# ── the geometry (mirrors stage.ts and PaperDiorama.tsx) ─────────────────────

def pop_scale(age: float, frames: int = TIMING["pop"]) -> float:
    if age >= frames:
        return 1.0
    k = max(0.0, age / frames)
    return 0.6 + 0.48 * (k / 0.6) if k < 0.6 else 1.08 - 0.08 * ((k - 0.6) / 0.4)


def slot_box(room: str, slot: str, level: str, w: float, h: float) -> tuple[float, float, float, float]:
    """[left, top, right, bottom] of a thing of size (w, h) standing in a slot at a level."""
    cx = SLOTS[slot]
    bottom = ROOMS.get(room, 1440) - LEVELS[level]
    return (cx - w / 2, bottom - h, cx + w / 2, bottom)


def critter_box(room: str, slot: str) -> tuple[float, float, float, float]:
    """The critter's body and legs (its hat room above is left out)."""
    left, top, right, bottom = slot_box(room, slot, "floor", CRITTER_W, CRITTER_H)
    return (left, top + 2.6 * _U, right, bottom)


def stage_scale(zooms: list[int], frame: int) -> float:
    s = 1.0
    up = TIMING["zoomScale"] - 1
    for at in zooms:
        t = frame - at
        if t < 0:
            continue
        if t < TIMING["zoomIn"]:
            s += up * (t / TIMING["zoomIn"])
        elif t < TIMING["zoomIn"] + TIMING["zoomHold"]:
            s += up
        else:
            k = max(0.0, min(1.0, (t - TIMING["zoomIn"] - TIMING["zoomHold"]) / TIMING["zoomOut"]))
            s += up * (1 - (2 * k * k if k < 0.5 else 1 - (-2 * k + 2) ** 2 / 2))
    return s


def banner_font_size(text: str) -> int:
    return max(34, min(62, math.floor(ZONES["bannerMaxWidth"] / max(1, len(text) * 0.74))))


def _overlap(a, b) -> float:
    """Overlap of two boxes as a share of the smaller one's area."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return (w * h) / small if small > 0 else 0.0


# ── checks ───────────────────────────────────────────────────────────────────

def is_paper_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Paper Diorama video is exactly the one
    PaperDiorama scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_paper_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The PaperDiorama scene draws a whole Paper Diorama video and is used only when the "
                    "video's visual_style is paper_diorama (chosen at the topic). Build this video's scenes "
                    "from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Paper Diorama video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"PaperDiorama\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"paperDiorama\": {...}}}. Put every set in its sets.")
    return ""


def prop_errors(name: str, prop) -> list[str]:
    """What is wrong with one custom prop's pieces, one sentence each."""
    where = f"customProps.{name}"
    if not isinstance(prop, dict) or set(prop) - {"w", "h", "pieces"}:
        return [f"{where} must be {{w, h, pieces}}."]
    w, h, pieces = prop.get("w"), prop.get("h"), prop.get("pieces")
    if not (_num(w) and _num(h) and 20 <= w <= LIMITS["maxPropW"] and 20 <= h <= LIMITS["maxPropH"]):
        return [f"{where}: w and h must be numbers from 20 to {LIMITS['maxPropW']} wide and "
                f"{LIMITS['maxPropH']} tall."]
    if not isinstance(pieces, list) or not 1 <= len(pieces) <= LIMITS["maxPieces"]:
        return [f"{where}: pieces must list 1 to {LIMITS['maxPieces']} pieces."]
    out = []
    for i, p in enumerate(pieces):
        at = f"{where} piece {i + 1}"
        if not isinstance(p, dict) or p.get("shape") not in SHAPES:
            out.append(f"{at}: shape must be one of {list(SHAPES)}.")
            continue
        for key in ("fill", "shade", "hi"):
            if (key == "fill" or key in p) and p.get(key) not in COLORS:
                out.append(f"{at}: {key} must be a colour name from the palette ({', '.join(COLORS[:6])}, ...).")
        for key in ("shadeH", "hiH"):
            if key in p and not (_num(p[key]) and 0 < p[key] <= 1):
                out.append(f"{at}: {key} must be a share of the piece's height, above 0 and at most 1.")
        if "rot" in p and not (_num(p["rot"]) and -180 <= p["rot"] <= 180):
            out.append(f"{at}: rot must be degrees from -180 to 180.")
        shape = p["shape"]
        if shape == "poly":
            pts = p.get("points")
            if not (isinstance(pts, list) and 3 <= len(pts) <= 40 and all(
                    isinstance(q, list) and len(q) == 2 and all(_num(v) for v in q) for q in pts)):
                out.append(f"{at}: points must list 3 to 40 [x, y] pairs.")
                continue
            box = (min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts))
        elif shape == "text":
            if not _text(p.get("text"), LIMITS["textChars"]):
                out.append(f"{at}: text must be 1 to {LIMITS['textChars']} characters on one line.")
                continue
            if p.get("font", "label") not in FONTS:
                out.append(f"{at}: font must be one of {list(FONTS)}.")
            size = p.get("size", 30)
            if not (_num(size) and 12 <= size <= 140):
                out.append(f"{at}: size must be 12 to 140 px.")
                continue
            if not (_num(p.get("x")) and _num(p.get("y"))):
                out.append(f"{at}: text needs x and y, its centre.")
                continue
            half = len(p["text"]) * size * 0.62 / 2
            box = (p["x"] - half, p["y"] - size * 0.6, p["x"] + half, p["y"] + size * 0.6)
        else:
            vals = [p.get(k) for k in ("x", "y", "w", "h")]
            if not all(_num(v) for v in vals) or vals[2] <= 0 or vals[3] <= 0:
                out.append(f"{at}: a {shape} needs x, y and a positive w and h.")
                continue
            if "r" in p and not (_num(p["r"]) and p["r"] >= 0):
                out.append(f"{at}: r must be 0 or more.")
            box = (vals[0], vals[1], vals[0] + vals[2], vals[1] + vals[3])
        if box[0] < -1 or box[1] < -1 or box[2] > w + 1 or box[3] > h + 1:
            out.append(f"{at}: it reaches outside the prop's {w:g} x {h:g} box.")
    return out


def check(config: dict, fps: int, word_starts: list[int], extra: dict, quiet=(), silences=()) -> list[str]:
    """Every problem with a Paper Diorama config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block (`props`: the shipped props and their sizes). `quiet`
    holds the config's insert windows (mcp/quiet_windows.py)."""
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    total = config.get("totalFrames")
    scenes = config.get("scenes") or []
    use = check_scene_use(STYLE_ID, scenes)
    if use:
        return [use]
    scene = scenes[0]
    if scene.get("startFrame") != 0 or scene.get("durationInFrames") != total:
        err(f"The {SCENE_SRC} scene must start at frame 0 and last totalFrames ({total}) frames.")
    scene_props = scene.get("props")
    data = scene_props.get(PROPS_KEY) if isinstance(scene_props, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the critter, any customProps and the sets."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    unknown = sorted(set(data) - {"critter", "customProps", "sets"})
    if unknown:
        err(f"{PROPS_KEY} has unknown field(s) {unknown}; it takes critter, customProps and sets.")

    critter = data.get("critter", {})
    if not isinstance(critter, dict) or set(critter) - {"color", "acc"}:
        err("critter must be {color, acc}.")
    else:
        if critter.get("color", "hero") not in CRITTER_COLORS:
            err(f"critter.color must be one of {list(CRITTER_COLORS)}.")
        if critter.get("acc", "none") not in CRITTER["accessories"]:
            err(f"critter.acc must be one of {list(CRITTER['accessories'])}.")

    library = dict(extra.get("props") or {})
    sizes: dict[str, tuple[float, float]] = {n: (wh[0], wh[1]) for n, wh in library.items()}
    custom = data.get("customProps", {})
    if not isinstance(custom, dict) or len(custom) > LIMITS["maxCustomProps"]:
        err(f"customProps must be an object of at most {LIMITS['maxCustomProps']} props.")
        custom = {}
    for name, prop in custom.items():
        if not isinstance(name, str) or not _PROP_NAME.match(name):
            err(f"customProps: {name!r} must be a short lower-case name (letters, digits, hyphens).")
            continue
        if name in library:
            err(f"customProps: {name!r} is a shipped prop; give your own prop another name.")
            continue
        problems = prop_errors(name, prop)
        for p in problems:
            err(p)
        if not problems:
            sizes[name] = (prop["w"], prop["h"])

    sets = data.get("sets")
    if not isinstance(sets, list) or not 1 <= len(sets) <= LIMITS["maxSets"] \
            or not all(isinstance(s, dict) for s in sets):
        return errors + [f"sets must list 1 to {LIMITS['maxSets']} sets."]
    starts = [s.get("start") for s in sets]
    if not all(_int(v) for v in starts):
        return errors + ["Every set needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first set must start at frame 0: the video opens in its room.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Set starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    events_total = 0
    zooms_total = 0
    change_frames: list[list[int]] = []
    for i, s in enumerate(sets):
        where = f"Set {i + 1}"
        start, end = starts[i], ends[i]
        extra_keys = sorted(set(s) - _SET_KEYS)
        if extra_keys:
            err(f"{where}: unknown field(s) {extra_keys}; a set takes {sorted(_SET_KEYS)}.")
        if i and not on_word(start):
            err(f"{where} starts at frame {start}, which is not on a word: start a set within "
                f"{TIMING['snap']} frames of a word's start.")
        if (end - start) < LIMITS["minSetSeconds"] * fps:
            err(f"{where} lasts {(end - start) / fps:.1f} s; a set needs at least {LIMITS['minSetSeconds']} s "
                "to be read. Merge it with the set before or after.")
        room = s.get("room")
        if _k(room) not in ROOMS:
            err(f"{where}: room must be one of {list(ROOMS)}.")
            room = "diner"
        if not _text(s.get("banner"), LIMITS["bannerChars"]):
            err(f"{where}: banner must be 1 to {LIMITS['bannerChars']} characters on one line.")
        if s.get("cut", "cut") not in CUTS:
            err(f"{where}: cut must be one of {list(CUTS)}.")
        cr = s.get("critter")
        cr_slot = None
        if cr is not None:
            if not isinstance(cr, dict) or set(cr) - {"slot", "face", "expr"} or _k(cr.get("slot")) not in SLOTS:
                err(f"{where}: critter must be null or {{slot, face, expr}} with slot one of {list(SLOTS)}.")
            else:
                cr_slot = cr["slot"]
                if not _int(cr.get("face", 1)) or cr.get("face", 1) not in (1, -1):
                    err(f"{where}: critter.face must be 1 (facing right) or -1 (facing left).")
                if cr.get("expr", "idle") not in CRITTER["expressions"]:
                    err(f"{where}: critter.expr must be one of {list(CRITTER['expressions'])}.")

        items = s.get("items", [])
        if not isinstance(items, list) or len(items) > LIMITS["maxItemsPerSet"] \
                or not all(isinstance(it, dict) for it in items):
            err(f"{where}: items must list at most {LIMITS['maxItemsPerSet']} props.")
            items = []
        ids: dict[str, dict] = {}
        changes = [start]
        for it in items:
            iid = it.get("id")
            at = f"{where}, item {iid!r}"
            if not isinstance(iid, str) or not _ID.match(iid) or iid in ids or iid == "critter":
                err(f"{where}: every item needs an id of its own (lower-case letters, digits, hyphens).")
                continue
            ids[iid] = it
            bad = sorted(set(it) - _ITEM_KEYS)
            if bad:
                err(f"{at}: unknown field(s) {bad}; an item takes {sorted(_ITEM_KEYS)}.")
            if _k(it.get("prop")) not in sizes:
                err(f"{at}: prop {it.get('prop')!r} is neither a shipped prop nor one of your customProps.")
            if _k(it.get("slot")) not in SLOTS or _k(it.get("level", "floor")) not in LEVELS \
                    or _k(it.get("scale", "m")) not in SCALES:
                err(f"{at}: slot must be one of {list(SLOTS)}, level one of {list(LEVELS)}, "
                    f"scale one of {list(SCALES)}.")
            if it.get("enter", "pop") not in ENTERS:
                err(f"{at}: enter must be one of {list(ENTERS)}.")
            a = it.get("at")
            if not _int(a) or not start <= a <= end - TIMING["readFrames"]:
                err(f"{at}: at must be a frame inside its set, at least {TIMING['readFrames']} frames before "
                    "the set ends.")
            elif a != start and not on_word(a):
                err(f"{at} enters at frame {a}, which is not on a word.")
            else:
                changes.append(a)

        events = s.get("events", [])
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            err(f"{where}: events must be a list of objects.")
            events = []
        events_total += len(events)
        exits: dict[str, int] = {}
        moves: dict[str, list[tuple[int, str, str]]] = {}
        # In frame order, as the renderer reads them: whether a prop has left
        # depends on when its exit is, not where the exit sits in the list.
        for n, e in sorted(enumerate(events), key=lambda p: p[1].get("at") if _int(p[1].get("at")) else -1):
            kind = e.get("do")
            at = f"{where}, event {n + 1} ({kind})"
            if kind not in EVENTS:
                err(f"{where}, event {n + 1}: do must be one of {list(EVENTS)} "
                    "(a prop enters through its item's at).")
                continue
            bad = sorted(set(e) - {"at", "do"} - _EVENT_KEYS[kind])
            if bad:
                err(f"{at}: unknown field(s) {bad}; it takes {sorted(_EVENT_KEYS[kind] | {'at', 'do'})}.")
            f = e.get("at")
            if not _int(f) or not start <= f <= end - TIMING["readFrames"]:
                err(f"{at}: at must be a frame inside its set, at least {TIMING['readFrames']} frames before "
                    "the set ends.")
                continue
            if not on_word(f):
                err(f"{at} is at frame {f}, which is not on a word.")
                continue
            changes.append(f)
            tgt = e.get("target")
            if kind == "stamp" and tgt is None:
                pass
            elif tgt == "critter":
                if kind not in _TARGETS_CRITTER:
                    err(f"{at}: the critter takes only {sorted(_TARGETS_CRITTER)}.")
                elif cr_slot is None:
                    err(f"{at}: this set has no critter.")
            elif kind == "expr":
                err(f"{at}: expr changes the critter's face: target \"critter\".")
            elif _k(tgt) not in ids:
                err(f"{at}: target must be an item of this set{', or the critter' if kind in _TARGETS_CRITTER else ''}.")
                continue
            else:
                it = ids[tgt]
                if _int(it.get("at")) and f < it["at"]:
                    err(f"{at}: {tgt!r} has not entered yet (it enters at frame {it['at']}).")
                if tgt in exits and f >= exits[tgt]:
                    err(f"{at}: {tgt!r} has already left (it exits at frame {exits[tgt]}).")
            if kind == "exit" and _k(tgt) in ids:
                exits[tgt] = f
            if kind == "move":
                if _k(e.get("to")) not in SLOTS or _k(e.get("level", "floor")) not in LEVELS:
                    err(f"{at}: to must be one of {list(SLOTS)} and level one of {list(LEVELS)}.")
                elif _k(tgt) in ids:
                    moves.setdefault(tgt, []).append((f, e["to"], e.get("level", ids[tgt].get("level", "floor"))))
                elif tgt == "critter" and cr_slot:
                    moves.setdefault("critter", []).append((f, e["to"], "floor"))   # the critter walks the floor
            if kind == "swap":
                if _k(e.get("prop")) not in sizes:
                    err(f"{at}: prop {e.get('prop')!r} is neither a shipped prop nor one of your customProps.")
                elif _k(tgt) in ids and _k(ids[tgt].get("prop")) in sizes and sizes[e["prop"]] != sizes[ids[tgt]["prop"]]:
                    err(f"{at}: swap to a prop of the same size ({sizes[ids[tgt]['prop']][0]:g} x "
                        f"{sizes[ids[tgt]['prop']][1]:g}), such as its other state; {e['prop']!r} is "
                        f"{sizes[e['prop']][0]:g} x {sizes[e['prop']][1]:g}.")
            if kind == "expr" and e.get("value") not in CRITTER["expressions"]:
                err(f"{at}: value must be one of {list(CRITTER['expressions'])}.")
            if kind == "stamp":
                if not _text(e.get("text"), LIMITS["stampChars"]):
                    err(f"{at}: text must be 1 to {LIMITS['stampChars']} characters.")
                if _k(e.get("level", "shelf")) not in LEVELS:
                    err(f"{at}: level must be one of {list(LEVELS)}.")
            if kind == "label" and not _text(e.get("text"), LIMITS["labelChars"]):
                err(f"{at}: text must be 1 to {LIMITS['labelChars']} characters.")
            if kind == "route":
                src = e.get("from")
                if _k(src) not in ids or src == tgt:
                    err(f"{at}: from must be another item of this set, the route's start.")
                elif _int(ids[src].get("at")) and f < ids[src]["at"]:
                    err(f"{at}: {src!r} has not entered yet.")
            if "color" in e and e["color"] not in COLORS:
                err(f"{at}: color must be a colour name from the palette.")
            if kind == "zoom":
                zooms_total += 1

        # ── nothing stands on anything else, or in the banner or the captions ──
        placed = []   # (label, box, from, to)
        if cr_slot:
            # The critter moves like an item, so each place it stands is checked.
            spots = [(start, cr_slot, "floor")] + sorted(moves.get("critter", []))
            for j, (f0, slot, _) in enumerate(spots):
                f1 = spots[j + 1][0] if j + 1 < len(spots) else end
                box = critter_box(room, slot)
                if box[0] < 0 or box[2] > W:
                    err(f"{where}: at slot {slot} the critter runs off the {'left' if box[0] < 0 else 'right'} edge.")
                placed.append(("the critter", box, f0, f1))
        for iid, it in ids.items():
            if _k(it.get("prop")) not in sizes or _k(it.get("slot")) not in SLOTS \
                    or _k(it.get("level", "floor")) not in LEVELS or _k(it.get("scale", "m")) not in SCALES:
                continue
            k = SCALES[it.get("scale", "m")]
            w, h = sizes[it["prop"]][0] * k, sizes[it["prop"]][1] * k
            begin = it["at"] if _int(it.get("at")) else start
            stop = exits.get(iid, end)
            spots = [(begin, it["slot"], it.get("level", "floor"))] + sorted(moves.get(iid, []))
            for j, (f0, slot, level) in enumerate(spots):
                f1 = spots[j + 1][0] if j + 1 < len(spots) else stop
                box = slot_box(room, slot, level, w, h)
                if box[0] < 0 or box[2] > W:
                    err(f"{where}, item {iid!r}: at slot {slot} it runs off the {'left' if box[0] < 0 else 'right'} "
                        "edge; use a slot nearer the middle or a smaller scale.")
                if box[1] < ZONES["stageTop"]:
                    err(f"{where}, item {iid!r}: at level {level} its top reaches the banner; use a lower level "
                        "or a smaller scale.")
                placed.append((f"item {iid!r}", box, f0, f1))
        for a in range(len(placed)):
            for b in range(a + 1, len(placed)):
                la, ba, fa0, fa1 = placed[a]
                lb, bb, fb0, fb1 = placed[b]
                if fa0 < fb1 and fb0 < fa1 and _overlap(ba, bb) > OVERLAP_SHARE:
                    err(f"{where}: {la} and {lb} stand on top of each other (frames {max(fa0, fb0)}-"
                        f"{min(fa1, fb1) - 1}); give one of them another slot or level, or a smaller scale.")
        change_frames.append(sorted(set(changes)))

    if events_total > LIMITS["maxEvents"]:
        err(f"The sets hold {events_total} events; a video may hold at most {LIMITS['maxEvents']}.")
    if zooms_total > LIMITS["maxZooms"]:
        err(f"The video snaps the camera {zooms_total} times; at most {LIMITS['maxZooms']}, for the hits that "
            "matter most.")

    _check_quiet(starts, change_frames, quiet, err)

    if not errors:
        still = round(LIMITS["maxStillSeconds"] * fps)
        for i, frames in enumerate(change_frames):
            marks = frames + [ends[i]]
            for a, c in (g for x, y in zip(marks, marks[1:]) for g in uncovered(x, y, quiet)):
                if awake(a, c, silences) > still:   # a silent pause inside the stretch is not counted
                    err(f"Set {i + 1}: nothing new happens from frame {a} to {c} ({(c - a) / fps:.1f} s); the "
                        f"longest stretch allowed is {LIMITS['maxStillSeconds']} s. Add an event on a word in "
                        "between (a label, a ring, a hop, a swap), or start the next set sooner.")
    return errors


def _check_quiet(starts, change_frames, quiet, err) -> None:
    """Nothing of the diorama starts inside an insert window, where the stage is
    hidden: no set, no entrance and no event."""
    for i, frames in enumerate(change_frames):
        for f in frames:
            if f == 0:
                continue
            w = window_at(f, quiet)
            if w:
                what = "starts" if f == starts[i] else "has an entrance or an event"
                err(f"Set {i + 1} {what} at frame {f}, inside an insert ({window_text(w)}), where the stage "
                    "is hidden. Move it to a word before or after the insert.")


def beat_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every set of a Paper Diorama config, for the
    text-layout audit to sample each like a scene: from the frame its last
    entrance or event has played out, so labels and stamps are on screen. []
    when the config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_paper_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    sets = [s for s in data.get("sets") or [] if isinstance(s, dict) and _int(s.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    windows = []
    for s, end in zip(sets, [n["start"] for n in sets[1:]] + [total]):
        marks = [s["start"]] + [it.get("at") for it in s.get("items") or [] if isinstance(it, dict)] \
            + [e.get("at") for e in s.get("events") or [] if isinstance(e, dict)]
        last = max((m for m in marks if _int(m)), default=s["start"])
        settled = last + max(TIMING["pop"], TIMING["stamp"], TIMING["label"]) + 2
        if end > s["start"]:
            windows.append((min(max(settled, s["start"]), end - 1), end))
    return windows
