"""Flat Vector Science (TMDEV-236): the checks a Flat Vector Science
scene-config must pass before it is written, so an unattended agent cannot ship
a shot with two red accents, a prop nobody drew, two props in one spot, a pill
too long for the frame, a readout cut before it can be read, a still video, or
a drawing of its own that uses what the renderer cannot afford.

A Flat Vector Science video is one installed `FlatVectorScience` scene
spanning every frame. `props.flatVector` holds shots timed to the narration's
word frames: a subject with word-lit pills and a measuring rule, a ladder of
ever larger things, a power-of-ten zoom, a descent with a depth counter, a
process in stages. Props come from the library in the style pack's `extra`,
or are drawn for the video as static SVG components in
generated/<video_id>/prop-<name>.tsx (`customProps`). The renderer's side of
this contract is renderer/remotion/src/scenes/installed/flatVector/contract.ts.

Keep in sync: LIMITS, TIMING and GEOMETRY mirror contract.ts and the helpers
mirror contract.ts and stage.ts. The catalogues are read from the pack's
`extra`, which renderer/remotion/flatvector-tools/sync-contract.mjs writes from
the renderer's own library, with the shared cases in
tests/fixtures/flat_vector_science_contract.json.

Free of the database and of I/O: the caller passes the config, the narration's
fps and word start frames, the pack's `extra` block, the video id and the text
of the video's own prop files.
"""
from __future__ import annotations

import re

from bean_explainer import _IMPORT, FORBIDDEN_SOURCE as _BEAN_FORBIDDEN
from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "FlatVectorScience"
PROPS_KEY = "flatVector"
STYLE_ID = "flat_vector_science"

W, H = 1080, 1920
SHOT_KINDS = ("subject", "ladder", "zoom", "descent", "stages")
BACKDROPS = ("abyss", "ocean", "night", "sky", "strata", "inside")
SLOTS = ("center", "left", "right", "top", "bottom")
SIZES = ("s", "m", "l")
CUTS = ("cut", "lens", "flash", "push")

LIMITS = {
    "minShots": 3,
    "maxShots": 12,
    "maxItems": 3,
    "maxPills": 2,
    "maxPillParts": 2,
    "pillChars": 18,
    "labelChars": 14,
    "valueChars": 12,
    "unitChars": 4,
    "minRungs": 2,
    "maxRungs": 5,
    "minLevels": 2,
    "maxLevels": 6,
    "minLayers": 2,
    "maxLayers": 6,
    "minSteps": 2,
    "maxSteps": 5,
    "maxCustomProps": 8,
    "maxValue": 999999999,
    "minShotSeconds": 1.5,
    "maxStillSeconds": 4,
}
TIMING = {
    "snap": 2,
    "pop": 15,
    "pillGrow": 9,
    "pillReveal": 9,
    "light": 5,
    "roll": 24,
    "ruleDraw": 12,
    "rung": 21,
    "lens": 18,
    "push": 12,
    "flash": 6,
    "readFrames": 20,
}
GEOMETRY = {
    "slot": {"center": [540, 930], "left": [300, 960], "right": [780, 900], "top": [540, 700], "bottom": [540, 1150]},
    "size": {"s": 260, "m": 460, "l": 780},
    "readoutTop": 222,
    "stripY": 1260,
    "safeLeft": 70,
    "safeRight": 1010,
    "pillHeight": 76,
    "pillText": 40,
    "capCharWidth": 0.72,
    "pillMaxWidth": 940,
}

MAX_ERRORS = 12
CUSTOM_SIDE = (60, 1000)
_ID = re.compile(r"^[a-z][a-z0-9_]{1,23}\Z")
_CUSTOM_FILE = re.compile(r"^prop-[a-z0-9-]{1,40}\Z")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}\Z")
_ALLOWED_IMPORT = re.compile(r"^(react|\.\./\.\./installed/flatVector/toon)\Z")
# A prop is a still drawing, rasterised once: anything that changes with the
# frame would be frozen at its first value, and state would differ between the
# render's parallel tabs.
FORBIDDEN_SOURCE = _BEAN_FORBIDDEN + (
    (re.compile(r"\buse(CurrentFrame|VideoConfig|State|Ref|Effect|LayoutEffect|Reducer|Memo|Callback)\b"),
     "a hook or the frame: a prop is a still drawing, drawn once and moved by the renderer"),
    (re.compile(r"<text\b|<tspan\b"), "SVG text: the names go in pills, which the renderer draws"),
)

_BASE = {"kind", "start", "backdrop", "cut", "counter"}
_KEYS = {
    "subject": _BASE | {"items", "pills", "rule"},
    "ladder": _BASE | {"rungs"},
    "zoom": _BASE | {"levels"},
    "descent": _BASE | {"label", "unit", "layers"},
    "stages": _BASE | {"steps"},
}


def _seq(v) -> list:
    """v when it is a list, else []: a wrong-typed collection is refused by its own check, never iterated."""
    return v if isinstance(v, list) else []


def is_flat_vector_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def library(extra: dict) -> dict:
    """Every library prop name -> its box, from the pack."""
    return {k: tuple(v) for k, v in (extra.get("boxes") or {}).items()}


def prop_scale(box, size: str) -> float:
    return GEOMETRY["size"][size] / max(box[0], box[1])


def grouped(n) -> str:
    s = str(int(abs(n)))
    out = ""
    for i, ch in enumerate(s):
        if i > 0 and (len(s) - i) % 3 == 0:
            out += ","
        out += ch
    return "-" + out if n < 0 else out


def pill_width(parts) -> int:
    G = GEOMETRY
    chars = sum(len(p["text"]) for p in parts)
    return round(chars * G["pillText"] * G["capCharWidth"] + (len(parts) - 1) * 27 + 60)


def event_frames(shot: dict) -> list[int]:
    out = [shot["start"]]
    c = shot.get("counter")
    if isinstance(c, dict) and _int(c.get("at")):
        out.append(c["at"])
    kind = shot.get("kind")

    def ats(key):
        return [x["at"] for x in _seq(shot.get(key)) if isinstance(x, dict) and _int(x.get("at"))]

    if kind == "subject":
        out += ats("items")
        for p in _seq(shot.get("pills")):
            if isinstance(p, dict):
                out += [x["at"] for x in _seq(p.get("parts")) if isinstance(x, dict) and _int(x.get("at"))]
        r = shot.get("rule")
        if isinstance(r, dict) and _int(r.get("at")):
            out.append(r["at"])
    elif kind == "ladder":
        out += ats("rungs")
    elif kind == "zoom":
        out += ats("levels")
    elif kind == "descent":
        out += ats("layers")
    elif kind == "stages":
        out += ats("steps")
    return sorted(set(out))


def quiet_spans(data: dict, total: int) -> list[list[int]]:
    shots = data["shots"]
    spans = []
    for i, s in enumerate(shots):
        end = shots[i + 1]["start"] if i + 1 < len(shots) else total
        frames = [f for f in event_frames(s) if f < end] + [end]
        spans.extend([a, b] for a, b in zip(frames, frames[1:]))
    return spans


def transition_frames(shot: dict) -> tuple[int, int]:
    """The frames a shot's transition takes before and after its start."""
    cut = shot.get("cut", "cut")
    if cut in ("lens", "push"):
        return TIMING[cut], 0
    if cut == "flash":
        return 0, TIMING["flash"]
    return 0, 0


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= limit and v == v.strip()


def check_scene_use(visual_style: str, scenes: list) -> str:
    uses = [s for s in scenes or [] if is_flat_vector_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The FlatVectorScience scene draws a whole Flat Vector Science video and is used only when "
                    "the video's visual_style is flat_vector_science (chosen at the topic). Build this video's "
                    "scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Flat Vector Science video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"FlatVectorScience\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"flatVector\": {...}}}. Put every shot in its shots.")
    return ""


def _code_only(src: str) -> str:
    """The source with its comments removed and every string and template literal emptied, so a word
    inside either is never read as code (a `//` in a URL, a `/*` in a string). Regex literals are read as
    code: a prop has no reason to hold one near its export."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c, nxt = src[i], src[i + 1:i + 2]
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(c + c)
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def custom_prop_errors(custom, video_id: str, library_names, sources: dict | None) -> tuple[list[str], dict]:
    """Problems with config's customProps, and their boxes by id. `sources`
    maps each src to its file's text, or is None to skip the source checks."""
    errs: list[str] = []
    boxes: dict[str, tuple] = {}
    if custom is None:
        return errs, boxes
    if not isinstance(custom, list) or len(custom) > LIMITS["maxCustomProps"]:
        return [f"customProps must be a list of at most {LIMITS['maxCustomProps']} props."], boxes
    lo, hi = CUSTOM_SIDE
    for i, c in enumerate(custom):
        where = f"customProps {i + 1}"
        if not isinstance(c, dict) or set(c) - {"id", "src", "box", "light"}:
            errs.append(f"{where} must be {{\"id\", \"src\", \"box\", \"light\"?}}.")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not _ID.match(cid) or cid in library_names or cid in boxes:
            errs.append(f"{where}: id {cid!r} must be lowercase letters, digits or _, and not a library prop or "
                        "another custom prop's id.")
            continue
        src = c.get("src")
        stem = src.split("/", 1)[1] if isinstance(src, str) and "/" in src else ""
        if (not isinstance(src, str) or not _CUSTOM_FILE.match(stem)
                or (video_id and src.split("/", 1)[0] != video_id)):
            errs.append(f"{where} ({cid}): src must be the src write_scene_file returned for this video's "
                        "prop-<name> file (\"<video_id>/prop-<name>\").")
            continue
        box = c.get("box")
        if not (isinstance(box, list) and len(box) == 2 and all(_int(v) and lo <= v <= hi for v in box)):
            errs.append(f"{where} ({cid}): box is [width, height], whole pixels from {lo} to {hi}, holding every "
                        "pixel of the drawing around its centre.")
            continue
        if "light" in c and not (isinstance(c["light"], str) and _COLOR.match(c["light"])):
            errs.append(f"{where} ({cid}): light is the colour of its halo, \"#rrggbb\".")
            continue
        if sources is not None:
            body = sources.get(src)
            if body is None:
                errs.append(f"{where} ({cid}): there is no {src}.tsx; write it with write_scene_file first.")
                continue
            for pattern, why in FORBIDDEN_SOURCE:
                if pattern.search(body):
                    errs.append(f"{where} ({cid}): the drawing uses {why}.")
            named = [next((g for g in groups if g), "") for groups in _IMPORT.findall(body)]
            bad = [m or '""' for m in named if not _ALLOWED_IMPORT.match(m)]
            if bad:
                errs.append(f"{where} ({cid}): it imports {', '.join(sorted(set(bad)))}; a prop imports only react "
                            "and ../../installed/flatVector/toon.")
            # every default export outside comments must be the function: a commented-out one exports nothing,
            # and a decoy cannot cover an "export default null" (the forbidden patterns above read the raw file)
            exports = re.findall(r"\bexport\s+default\s+(\w*)", _code_only(body))
            if not exports or any(e != "function" for e in exports):
                errs.append(f"{where} ({cid}): the file must default-export the drawing as a function "
                            "(\"export default function Name() { ... }\").")
        boxes[cid] = tuple(box)
    return errs, boxes



def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "", sources: dict | None = None, quiet=()) -> list[str]:
    """Every problem with the config, one sentence each (at most MAX_ERRORS), or [] when it may be
    written. A value of the wrong type (a list or an object where a name, a number or true/false
    belongs) is reported with the problems found before it, never raised."""
    out: list[str] = []
    try:
        return _check_unguarded(config, fps, word_starts, extra, video_id=video_id, sources=sources, quiet=quiet, _out=out)
    except (TypeError, KeyError, AttributeError, IndexError, ValueError):
        return out[:MAX_ERRORS - 1] + ["A field holds a value of the wrong type (a list or an object where a name, a "
                                       "number or true/false belongs); compare the config with the skill's contract."]


def _check_unguarded(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "",
          sources: dict | None = None, quiet=(), _out=None) -> list[str]:
    """Every problem with a Flat Vector Science config, one sentence each (at
    most MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block; `sources` maps customProps' src to the file's text (None
    skips the source checks). `quiet` holds the config's insert windows."""
    errors: list[str] = _out if _out is not None else []
    found = [0]

    def err(msg: str) -> None:
        found[0] += 1
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    total = config.get("totalFrames")
    scenes_cfg = _seq(config.get("scenes"))
    use = check_scene_use(STYLE_ID, scenes_cfg)
    if use:
        return [use]
    sc = scenes_cfg[0]
    if sc.get("startFrame") != 0 or sc.get("durationInFrames") != total:
        err(f"The {SCENE_SRC} scene must start at frame 0 and last totalFrames ({total}) frames.")
    props = sc.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the shots."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    unknown = sorted(set(data) - {"shots", "customProps"})
    if unknown:
        err(f"{PROPS_KEY} has unknown field(s) {unknown}; it takes shots and customProps.")

    lib = library(extra)
    cerrs, cboxes = custom_prop_errors(data.get("customProps"), video_id, set(lib), sources)
    for e in cerrs:
        err(e)
    boxes = {**lib, **cboxes}

    shots = data.get("shots")
    if not isinstance(shots, list) or not LIMITS["minShots"] <= len(shots) <= LIMITS["maxShots"]:
        return errors + [f"shots must list {LIMITS['minShots']} to {LIMITS['maxShots']} shots."]
    if not all(isinstance(s, dict) and s.get("kind") in SHOT_KINDS for s in shots):
        return errors + [f"Every shot must be an object whose kind is one of {list(SHOT_KINDS)}."]
    starts = [s.get("start") for s in shots]
    if not all(_int(v) for v in starts):
        return errors + ["Every shot needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first shot must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Shot starts must increase and stay inside the video."]
    ends = starts[1:] + [total]
    if shots[0].get("cut", "cut") != "cut":
        err("The first shot arrives on a cut: it is on screen from frame 0.")

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    min_len = round(LIMITS["minShotSeconds"] * fps)
    sound: list[bool] = []
    for i, s in enumerate(shots):
        where = f"Shot {i + 1} ({s['kind']})"
        if i and not on_word(starts[i]):
            err(f"{where} starts at frame {starts[i]}, which is not on a word: start a shot within "
                f"{TIMING['snap']} frames of a word's start.")
        if ends[i] - starts[i] < min_len:
            err(f"{where} lasts {ends[i] - starts[i]} frames; a shot needs at least {LIMITS['minShotSeconds']} s "
                f"({min_len} frames).")
        extra_keys = sorted(set(s) - _KEYS[s["kind"]])
        if extra_keys:
            err(f"{where}: unknown field(s) {extra_keys}; a {s['kind']} takes {sorted(_KEYS[s['kind']])}.")
        if s.get("backdrop") not in BACKDROPS:
            err(f"{where}: backdrop must be one of {list(BACKDROPS)}.")
        if "cut" in s and s["cut"] not in CUTS:
            err(f"{where}: cut must be one of {list(CUTS)}.")
        before = found[0]
        _check_shot(s, where, starts[i], ends[i], i, boxes, on_word, err)
        sound.append(found[0] == before and not extra_keys)

    _check_quiet(shots, starts, quiet, err)

    if all(sound):
        still = round(LIMITS["maxStillSeconds"] * fps)
        for a, b in quiet_spans(data, total):
            for x, y in uncovered(a, b, quiet):
                if y - x > still:
                    i = max(k for k, st in enumerate(starts) if st <= x)
                    err(f"Shot {i + 1} ({shots[i]['kind']}): nothing new arrives from frame {x} to {y} "
                        f"({(y - x) / fps:.1f} s); the longest stretch allowed is {LIMITS['maxStillSeconds']} s. "
                        "Time a prop, a pill part, a rule, a counter, a rung, a level, a layer or a stage to a word "
                        "in between, or start the next shot sooner.")
    return errors


def _timed(obj, key, where, start, end, on_word, err, what, low=None) -> bool:
    v = obj.get(key) if isinstance(obj, dict) else None
    lo = start if low is None else low
    if not _int(v) or not lo <= v < end:
        err(f"{where}: {key} must be a frame from {lo} to {end - 1} ({what}).")
        return False
    if not on_word(v):
        err(f"{where}: {key} {v} is not on a word; put it within {TIMING['snap']} frames of a word's start.")
        return False
    return True


def _check_list(s, key, lo, hi, fields, where, start, end, boxes, on_word, err, needs_what=True) -> list:
    items = s.get(key)
    if not isinstance(items, list) or not lo <= len(items) <= hi:
        err(f"{where}: {key} must list {lo} to {hi} entries.")
        return []
    prev = start - 1
    for n, x in enumerate(items):
        w = f"{where} {key[:-1]} {n + 1}"
        if not isinstance(x, dict) or set(x) - fields:
            err(f"{w} takes {sorted(fields)}.")
            return []
        if (needs_what or "what" in x) and x.get("what") not in boxes:
            err(f"{w}: what {x.get('what')!r} is not a library prop or one of this video's customProps.")
        if "red" in x and not isinstance(x["red"], bool):
            err(f"{w}: red must be true or false.")
        if _timed(x, "at", w, start, end, on_word, err, "the frame it arrives", low=prev + 1):
            prev = x["at"]
    return items


def _check_shot(s, where, start, end, index, boxes, on_word, err) -> None:
    L, T = LIMITS, TIMING
    kind = s["kind"]
    reds = 0
    last = start
    c = s.get("counter")
    if c is not None:
        if not isinstance(c, dict) or set(c) - {"label", "value", "unit", "at", "from", "red"}:
            err(f"{where}: counter takes label, value, unit, at, from and red.")
        else:
            if not _text(c.get("label"), L["labelChars"]):
                err(f"{where}: the counter's label must be 1 to {L['labelChars']} characters.")
            if not _num(c.get("value")) or not 0 <= c["value"] <= L["maxValue"]:
                err(f"{where}: the counter's value must be a number from 0 to {L['maxValue']}.")
            if "from" in c and (not _num(c["from"]) or not 0 <= c["from"] <= L["maxValue"]):
                err(f"{where}: the counter's from must be a number from 0 to {L['maxValue']}.")
            if not isinstance(c.get("unit"), str) or len(c["unit"]) > L["unitChars"]:
                err(f"{where}: the counter's unit must be at most {L['unitChars']} characters (\"m\", \"km\", \"°C\").")
            if _timed(c, "at", f"{where} counter", start, end, on_word, err, "the frame it starts to roll"):
                last = max(last, c["at"] + T["roll"])
            if "red" in c and not isinstance(c["red"], bool):
                err(f"{where}: the counter's red must be true or false.")
            reds += c.get("red") is True
    if kind == "subject":
        items = s.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= L["maxItems"]:
            err(f"{where}: items must list 1 to {L['maxItems']} props.")
            items = []
        slots: set[str] = set()
        for n, it in enumerate(items):
            w = f"{where} item {n + 1}"
            if not isinstance(it, dict) or set(it) - {"what", "slot", "size", "at", "flip"}:
                err(f"{w} takes what, slot, size, at and flip.")
                continue
            if it.get("what") not in boxes:
                err(f"{w}: what {it.get('what')!r} is not a library prop or one of this video's customProps.")
            if it.get("slot") not in SLOTS:
                err(f"{w}: slot must be one of {list(SLOTS)}.")
            elif it["slot"] in slots:
                err(f"{w}: two props stand in the {it['slot']} slot; give each its own slot.")
            else:
                slots.add(it["slot"])
            if it.get("size") not in SIZES:
                err(f"{w}: size must be one of {list(SIZES)}.")
            if "at" in it:
                _timed(it, "at", w, start, end, on_word, err, "the frame it pops in")
            if "flip" in it and not isinstance(it["flip"], bool):
                err(f"{w}: flip must be true or false.")
        pills = s.get("pills", [])
        if not isinstance(pills, list) or len(pills) > L["maxPills"]:
            err(f"{where}: pills must list at most {L['maxPills']} pills.")
            pills = []
        for n, p in enumerate(pills):
            w = f"{where} pill {n + 1}"
            if not isinstance(p, dict) or set(p) != {"on", "parts"}:
                err(f"{w} must be {{\"on\": a slot, \"parts\": [...]}}.")
                continue
            if p.get("on") not in slots:
                err(f"{w}: on must be the slot of one of the shot's items.")
            parts = p.get("parts")
            if (not isinstance(parts, list) or not 1 <= len(parts) <= L["maxPillParts"]
                    or not all(isinstance(x, dict) and set(x) - {"text", "at", "red"} == set() and _text(x.get("text"), L["pillChars"])
                               for x in parts)):
                err(f"{w}: parts must list 1 or {L['maxPillParts']} parts, each {{\"text\": 1 to {L['pillChars']} "
                    "characters, \"at\": a frame, \"red\"?: true}}.")
                continue
            if pill_width(parts) > GEOMETRY["pillMaxWidth"]:
                err(f"{w} is too wide for the frame; shorten its words.")
            prev = start - 1
            for k, x in enumerate(parts):
                if _timed(x, "at", f"{w} part {k + 1}", start, end, on_word, err, "the frame its word lights", low=prev + 1):
                    prev = x["at"]
                    # the pill grows from 3 frames after its first word and its text is revealed from 7; each later
                    # word lights over T["light"] frames on its own word (FlatVectorScience.tsx)
                    last = max(last, x["at"] + (7 + T["pillReveal"] if k == 0 else T["light"]))
                if "red" in x and not isinstance(x["red"], bool):
                    err(f"{w} part {k + 1}: red must be true or false.")
                reds += x.get("red") is True
        r = s.get("rule")
        if r is not None:
            if not isinstance(r, dict) or set(r) != {"beside", "label", "at"} or r.get("beside") not in slots:
                err(f"{where}: rule must be {{\"beside\": the slot of an item, \"label\", \"at\"}}.")
            else:
                if not _text(r.get("label"), L["valueChars"]):
                    err(f"{where}: the rule's label must be 1 to {L['valueChars']} characters (\"16 M\").")
                if _timed(r, "at", f"{where} rule", start, end, on_word, err, "the frame it draws"):
                    last = max(last, r["at"] + T["ruleDraw"])
    elif kind == "ladder":
        rungs = _check_list(s, "rungs", L["minRungs"], L["maxRungs"], {"what", "label", "value", "at", "red"},
                            where, start, end, boxes, on_word, err)
        for n, r in enumerate(rungs):
            if not _text(r.get("label"), L["labelChars"]) or not _text(r.get("value"), L["valueChars"]):
                err(f"{where} rung {n + 1}: label 1 to {L['labelChars']} characters and value 1 to {L['valueChars']}.")
        reds += sum(bool(r.get("red")) for r in rungs)
        last = max([last] + [r["at"] + T["rung"] for r in rungs if _int(r.get("at"))])
    elif kind == "zoom":
        levels = _check_list(s, "levels", L["minLevels"], L["maxLevels"], {"what", "label", "at", "red"},
                             where, start, end, boxes, on_word, err)
        for n, lv in enumerate(levels):
            if not _text(lv.get("label"), L["valueChars"]):
                err(f"{where} level {n + 1}: label must be 1 to {L['valueChars']} characters (\"10 KM\").")
        reds += sum(bool(lv.get("red")) for lv in levels)
        last = max([last] + [lv["at"] + T["rung"] for lv in levels if _int(lv.get("at"))])
    elif kind == "descent":
        if not _text(s.get("label"), L["labelChars"]):
            err(f"{where}: label must be 1 to {L['labelChars']} characters (\"DEPTH\").")
        if not isinstance(s.get("unit"), str) or len(s["unit"]) > L["unitChars"]:
            err(f"{where}: unit must be at most {L['unitChars']} characters.")
        layers = _check_list(s, "layers", L["minLayers"], L["maxLayers"], {"name", "value", "at", "what", "red"},
                             where, start, end, boxes, on_word, err, needs_what=False)
        prev = 0
        for n, lv in enumerate(layers):
            if not _text(lv.get("name"), L["labelChars"]):
                err(f"{where} layer {n + 1}: name must be 1 to {L['labelChars']} characters.")
            v = lv.get("value")
            if not _num(v) or not prev < v <= L["maxValue"]:
                err(f"{where} layer {n + 1}: value must be deeper than the layer before (above {prev}), at most "
                    f"{L['maxValue']}.")
            else:
                prev = v
        reds += sum(bool(lv.get("red")) for lv in layers)
        last = max([last] + [lv["at"] + T["rung"] for lv in layers if _int(lv.get("at"))])
    elif kind == "stages":
        steps = _check_list(s, "steps", L["minSteps"], L["maxSteps"], {"what", "label", "at", "red"},
                            where, start, end, boxes, on_word, err)
        for n, st in enumerate(steps):
            if not _text(st.get("label"), L["labelChars"]):
                err(f"{where} step {n + 1}: label must be 1 to {L['labelChars']} characters.")
        reds += sum(bool(st.get("red")) for st in steps)
        last = max([last] + [st["at"] + T["rung"] for st in steps if _int(st.get("at"))])
    if reds > 1:
        err(f"{where}: {reds} things are red; red marks one number or word in a shot.")
    # a subject's pill words light as they are spoken, so they need only finish lighting before the cut;
    # the scale shots' last arrival is the payoff and is held to be read
    need = 1 if kind == "subject" else T["readFrames"]
    if end - last < need or end < last:
        err(f"{where}: its last part settles at frame {last}, {end - last} frames before the shot ends; leave at "
            f"least {need} frame{'s' if need > 1 else ''} after it settles.")


def _check_quiet(shots, starts, quiet, err) -> None:
    """Nothing of the style starts inside an insert, and no transition runs into one."""
    for i, s in enumerate(shots):
        where = f"Shot {i + 1} ({s['kind']})"
        before, after = transition_frames(s)
        if i:
            for f in (starts[i] - before, starts[i], starts[i] + after):
                w = window_at(f, quiet)
                if w:
                    err(f"{where} starts (or its transition runs) at frame {f}, inside an insert ({window_text(w)}), "
                        f"where the scene is hidden; start it after {w[1] + before} or before {w[0] - after}.")
                    break
            else:
                pass
        for f in event_frames(s)[1:]:
            w = window_at(f, quiet)
            if w:
                err(f"{where}: something arrives at frame {f}, inside an insert ({window_text(w)}), where the scene is "
                    f"hidden; time it to a word at {w[1]} or later, or before {w[0]}.")
                break


def shot_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every shot, for the text-layout audit: a shot is
    sampled once its first pill, title or readout has grown in."""
    scenes_cfg = _seq(config.get("scenes"))
    if len(scenes_cfg) != 1 or not is_flat_vector_scene(scenes_cfg[0]):
        return []
    data = (scenes_cfg[0].get("props") or {}).get(PROPS_KEY) or {}
    shots = [s for s in _seq(data.get("shots")) if isinstance(s, dict) and _int(s.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    out = []
    for s, end in zip(shots, [n["start"] for n in shots[1:]] + [total]):
        try:
            frames = event_frames(s)
        except (KeyError, TypeError):
            frames = [s["start"]]
        settled = (frames[1] if len(frames) > 1 else s["start"]) + TIMING["pillGrow"] + TIMING["pillReveal"] + 3
        if end > s["start"]:
            out.append((min(settled, end - 1), end))
    return out
