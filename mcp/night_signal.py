"""Night Signal (TMDEV-238): the checks a Night Signal scene-config must pass
before it is written, so an unattended agent cannot ship a scene with two red
threats, a part nobody drew, two things standing in one spot, a card cut
before it can be read, a still video or a scene that starts inside an insert.

A Night Signal video is one installed `NightSignal` scene spanning every
frame. The agent writes no code for it: `props.nightSignal` holds the case
file's number and title and scenes timed to the narration's word frames:
tableaux of pictograms on a ground line, a doorbell camera panel, a phone
screen, a RULE card, a case card and a card of steps. People, animals and
objects come from the library in the style pack's `extra`, or from the
video's own `customParts`, made of the same flat shapes. The renderer's side
of this contract is renderer/remotion/src/scenes/installed/nightSignal/contract.ts.

Keep in sync: LIMITS, TIMING, CAMERA, GEOMETRY and the helpers mirror
contract.ts and stage.ts. The catalogues are read from the pack's `extra`,
which renderer/remotion/nightsignal-tools/sync-contract.mjs writes from the
renderer's own library. mcp/tests/test_night_signal.py runs the shared cases
in tests/fixtures/night_signal_contract.json (written by the same script), so
a drift fails a test instead of a render.

Free of the database and of I/O: the caller passes the config, the narration's
fps and word start frames, the pack's `extra` block and the video id.
"""
from __future__ import annotations

import re

from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "NightSignal"
PROPS_KEY = "nightSignal"
STYLE_ID = "night_signal"

W, H = 1080, 1920
SCENE_KINDS = ("tableau", "camera", "phone", "rule", "case", "steps")
SETTINGS = ("night", "street", "room", "plain")
SLOTS = ("left", "midleft", "center", "midright", "right")
SCREENS = ("message", "link", "qr", "call", "alert")
MARKS = ("check", "cross")
CUTS = ("glitch", "hard")
BUBBLES = ("thought", "speech")
SHAPES = ("circle", "rect", "line", "poly")
TONES = ("ink", "grey", "dim", "core", "red", "hole")

LIMITS = {
    "minScenes": 3,
    "maxScenes": 14,
    "maxItems": 4,
    "maxCustomParts": 6,
    "maxShapes": 40,
    "partBox": 400,
    "fileTitleChars": 16,
    "cameraLabelChars": 22,
    "buttonChars": 6,
    "phoneTitleChars": 12,
    "phoneLines": 3,
    "phoneLineChars": 16,
    "ruleLines": 2,
    "ruleLineChars": 12,
    "caseLabelChars": 10,
    "caseNameChars": 12,
    "minBars": 2,
    "maxBars": 4,
    "stampChars": 10,
    "stepsTitleChars": 20,
    "minSteps": 2,
    "maxSteps": 4,
    "stepChars": 24,
    "minSceneSeconds": 1.5,
    "maxStillSeconds": 5,
}
TIMING = {
    "snap": 2,
    "tearBefore": 2,
    "tearAfter": 1,
    "pop": 10,
    "step": 18,
    "connector": 15,
    "redden": 6,
    "underline": 10,
    "ringStart": 4,
    "ringFrames": 12,
    "slashDelay": 16,
    "slashFrames": 6,
    "mark": 8,
    "stepIn": 8,
    "readFrames": 20,
}
CAMERA = {"push": 1.05}
GEOMETRY = {
    "bandTop": 360,
    "bandHeight": 780,
    "ground": 640,
    "slotX": {"left": 220, "midleft": 390, "center": 540, "midright": 690, "right": 860},
    "cameraScale": 0.62,
    "cameraGround": 470,
    "hudTop": 204,
    "safeLeft": 66,
    "safeRight": 1014,
    "lineWidth": 900,
    "capCharWidth": 0.72,
}

MAX_ERRORS = 12
# Coordinates of a custom part's shapes: x from -HALF to HALF, y from -BOX to 0 (the ground).
_HALF = LIMITS["partBox"] // 2
_PART_ID = re.compile(r"^[a-z][a-z0-9_]{1,23}$")
_CLOCK = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

_BASE = {"kind", "start", "cut"}
_KEYS = {
    "tableau": _BASE | {"setting", "items", "connector", "bubble"},
    "camera": _BASE | {"label", "items", "connector", "button"},
    "phone": _BASE | {"screen", "title", "lines", "mark"},
    "rule": _BASE | {"number", "lines", "icon", "slashAt"},
    "case": _BASE | {"label", "name", "icon", "bars", "stamp"},
    "steps": _BASE | {"title", "steps"},
}
_ITEM_KEYS = {"what", "slot", "at", "threat", "redAt", "face", "to"}


def _seq(v) -> list:
    """v when it is a list, else []: a wrong-typed collection is refused by its own check, never iterated."""
    return v if isinstance(v, list) else []


def is_night_signal_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def library(extra: dict) -> set:
    """Every part name the pack's library holds: people, animals, objects."""
    return set(_seq(extra.get("people"))) | set(_seq(extra.get("animals"))) | set(_seq(extra.get("objects")))


def fit_font_size(text: str, size: int, width: int = GEOMETRY["lineWidth"]) -> int:
    n = max(1, len(text))
    return min(size, int(width // (n * GEOMETRY["capCharWidth"])))


def event_frames(scene: dict) -> list[int]:
    """The frames something new happens in a scene, sorted (contract.ts eventFrames)."""
    T = TIMING
    out = [scene["start"]]
    kind = scene.get("kind")
    if kind in ("tableau", "camera"):
        for it in _seq(scene.get("items")):
            if not isinstance(it, dict):
                continue
            if _int(it.get("at")):
                out.append(it["at"])
            if isinstance(it.get("to"), dict) and _int(it["to"].get("at")):
                out.append(it["to"]["at"])
            if _int(it.get("redAt")):
                out.append(it["redAt"])
        c = scene.get("connector")
        if isinstance(c, dict) and _int(c.get("at")):
            out.append(c["at"])
    if kind == "tableau" and isinstance(scene.get("bubble"), dict) and _int(scene["bubble"].get("at")):
        out.append(scene["bubble"]["at"])
    if kind == "camera" and isinstance(scene.get("button"), dict) and _int(scene["button"].get("crossAt")):
        out.append(scene["button"]["crossAt"])
    if kind == "phone" and isinstance(scene.get("mark"), dict) and _int(scene["mark"].get("at")):
        out.append(scene["mark"]["at"])
    if kind == "rule":
        out.append(scene["slashAt"] if _int(scene.get("slashAt")) else scene["start"] + T["slashDelay"])
    if kind == "case" and isinstance(scene.get("stamp"), dict) and _int(scene["stamp"].get("at")):
        out.append(scene["stamp"]["at"])
    if kind == "steps":
        out.extend(s["at"] for s in _seq(scene.get("steps")) if isinstance(s, dict) and _int(s.get("at")))
    return sorted(set(out))


def quiet_spans(data: dict, total: int) -> list[list[int]]:
    """stage.ts quietSpans: [from, to] between a scene's events and to its end."""
    scenes = data["scenes"]
    spans = []
    for i, s in enumerate(scenes):
        end = scenes[i + 1]["start"] if i + 1 < len(scenes) else total
        frames = [f for f in event_frames(s) if f < end] + [end]
        spans.extend([a, b] for a, b in zip(frames, frames[1:]))
    return spans


def tear_at(data: dict, frame: int):
    """stage.ts tearAt: (index of the scene coming in, progress) or None."""
    b, a = TIMING["tearBefore"], TIMING["tearAfter"]
    for k, s in enumerate(data["scenes"][1:], start=1):
        if s.get("cut", "glitch") != "glitch":
            continue
        if s["start"] - b <= frame <= s["start"] + a:
            return k, (frame - (s["start"] - b) + 0.5) / (b + a + 1)
    return None


def timecode(clock, frame: int, fps: int) -> str:
    """contract.ts timecode: the HUD's "HH:MM:SS:FF"."""
    m = _CLOCK.match(clock or "")
    h, mi = (int(m.group(0)[:2]), int(m.group(0)[3:])) if m else (3, 12)
    secs = (h * 60 + mi) * 60 + frame // fps
    return f"{secs // 3600 % 24:02d}:{secs // 60 % 60:02d}:{secs % 60:02d}:{frame % fps:02d}"


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= limit and v == v.strip()


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Night Signal video is exactly the one NightSignal
    scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_night_signal_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The NightSignal scene draws a whole Night Signal video and is used only when the "
                    "video's visual_style is night_signal (chosen at the topic). Build this video's scenes "
                    "from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Night Signal video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"NightSignal\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"nightSignal\": {...}}}. Put every picture in its scenes.")
    return ""



def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "", quiet=()) -> list[str]:
    """Every problem with the config, one sentence each (at most MAX_ERRORS), or [] when it may be
    written. A value of the wrong type (a list or an object where a name, a number or true/false
    belongs) is reported with the problems found before it, never raised."""
    out: list[str] = []
    try:
        return _check_unguarded(config, fps, word_starts, extra, video_id=video_id, quiet=quiet, _out=out)
    except (TypeError, KeyError, AttributeError, IndexError, ValueError):
        return out[:MAX_ERRORS - 1] + ["A field holds a value of the wrong type (a list or an object where a name, a "
                                       "number or true/false belongs); compare the config with the skill's contract."]


def _check_unguarded(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "",
          quiet=(), _out=None) -> list[str]:
    """Every problem with a Night Signal config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block. `quiet` holds the config's insert windows
    (mcp/quiet_windows.py)."""
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
    scene_cfg = scenes_cfg[0]
    if scene_cfg.get("startFrame") != 0 or scene_cfg.get("durationInFrames") != total:
        err(f"The {SCENE_SRC} scene must start at frame 0 and last totalFrames ({total}) frames.")
    props = scene_cfg.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the case file and the scenes."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    unknown = sorted(set(data) - {"file", "clock", "scenes", "customParts"})
    if unknown:
        err(f"{PROPS_KEY} has unknown field(s) {unknown}; it takes file, clock, scenes and customParts.")

    f = data.get("file")
    if (not isinstance(f, dict) or set(f) - {"number", "title"} or not _int(f.get("number"))
            or not 1 <= f["number"] <= 999 or not _text(f.get("title"), LIMITS["fileTitleChars"])):
        err(f"file must be {{\"number\": 1 to 999, \"title\": 1 to {LIMITS['fileTitleChars']} characters}}: "
            "the case file's number and a short title for the top row.")
    if "clock" in data and not (isinstance(data["clock"], str) and _CLOCK.match(data["clock"])):
        err("clock must be the time the case starts, \"HH:MM\" (24-hour), like \"03:12\".")

    # ── the video's own parts ──
    names = library(extra)
    custom = data.get("customParts", [])
    custom_ids: set[str] = set()
    if not isinstance(custom, list) or len(custom) > LIMITS["maxCustomParts"]:
        err(f"customParts must be a list of at most {LIMITS['maxCustomParts']} parts.")
        custom = []
    for n, part in enumerate(custom):
        _check_part(part, n, names, custom_ids, err)
    parts = names | custom_ids

    # ── the scenes ──
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not LIMITS["minScenes"] <= len(scenes) <= LIMITS["maxScenes"]:
        return errors + [f"scenes must list {LIMITS['minScenes']} to {LIMITS['maxScenes']} scenes."]
    if not all(isinstance(s, dict) and s.get("kind") in SCENE_KINDS for s in scenes):
        return errors + [f"Every scene must be an object whose kind is one of {list(SCENE_KINDS)}."]
    starts = [s.get("start") for s in scenes]
    if not all(_int(v) for v in starts):
        return errors + ["Every scene needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first scene must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Scene starts must increase and stay inside the video."]
    ends = starts[1:] + [total]
    if scenes[0]["kind"] not in ("tableau", "camera", "phone"):
        err("The first scene must be a picture (a tableau, a camera panel or a phone), not a card: the "
            "video opens on what is happening.")

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    min_len = round(LIMITS["minSceneSeconds"] * fps)
    checks = [0]
    sound: list[bool] = []
    for i, s in enumerate(scenes):
        where = f"Scene {i + 1} ({s['kind']})"
        if i and not on_word(starts[i]):
            err(f"{where} starts at frame {starts[i]}, which is not on a word: start a scene within "
                f"{TIMING['snap']} frames of a word's start.")
        if ends[i] - starts[i] < min_len:
            err(f"{where} lasts {ends[i] - starts[i]} frames; a scene needs at least "
                f"{LIMITS['minSceneSeconds']} s ({min_len} frames) to be seen.")
        extra_keys = sorted(set(s) - _KEYS[s["kind"]])
        if extra_keys:
            err(f"{where}: unknown field(s) {extra_keys}; a {s['kind']} takes {sorted(_KEYS[s['kind']])}.")
        if "cut" in s and s["cut"] not in CUTS:
            err(f"{where}: cut must be one of {list(CUTS)} (a glitch tear is the default).")
        before = found[0]
        _check_scene(s, where, starts[i], ends[i], parts, on_word, checks, err)
        sound.append(found[0] == before and not extra_keys)
    if checks[0] > 1:
        err("Green is used once: at most one phone mark of kind \"check\" in a video.")

    _check_quiet(scenes, starts, quiet, err)

    if all(sound):
        still = round(LIMITS["maxStillSeconds"] * fps)
        for a, b in quiet_spans(data, total):
            for x, y in uncovered(a, b, quiet):
                if y - x > still:
                    i = max(k for k, st in enumerate(starts) if st <= x)
                    err(f"Scene {i + 1} ({scenes[i]['kind']}): nothing new happens from frame {x} to {y} "
                        f"({(y - x) / fps:.1f} s); the longest stretch allowed is {LIMITS['maxStillSeconds']} s. "
                        "Time an item, a connector, a bubble or a mark to a word in between, or start the "
                        "next scene sooner.")
    return errors


def _check_part(part, n, names, ids, err) -> None:
    where = f"customParts {n + 1}"
    if not isinstance(part, dict) or set(part) != {"id", "shapes"}:
        err(f"{where} must be {{\"id\", \"shapes\"}}.")
        return
    pid = part["id"]
    if not isinstance(pid, str) or not _PART_ID.match(pid) or pid in names or pid in ids:
        err(f"{where}: id must be a short lower-case name of its own (letters, digits, _), not a library name.")
        return
    ids.add(pid)
    shapes = part["shapes"]
    if not isinstance(shapes, list) or not 1 <= len(shapes) <= LIMITS["maxShapes"]:
        err(f"{where} ({pid}): shapes must list 1 to {LIMITS['maxShapes']} shapes.")
        return
    for k, sh in enumerate(shapes):
        problem = _shape_error(sh)
        if problem:
            err(f"{where} ({pid}) shape {k + 1}: {problem}")
            return


def _in_box(x, y) -> bool:
    return _num(x) and _num(y) and -_HALF <= x <= _HALF and -LIMITS["partBox"] <= y <= 0


def _shape_error(sh) -> str:
    if not isinstance(sh, dict) or sh.get("shape") not in SHAPES:
        return f"shape must be one of {list(SHAPES)}."
    if sh.get("tone") not in TONES:
        return f"tone must be one of {list(TONES)}."
    kind = sh["shape"]
    keys = {"circle": {"shape", "cx", "cy", "r", "tone"}, "rect": {"shape", "x", "y", "w", "h", "r", "tone"},
            "line": {"shape", "points", "width", "tone"}, "poly": {"shape", "points", "tone"}}[kind]
    if set(sh) - keys:
        return f"a {kind} takes {sorted(keys)}."
    box = f"inside the part's box (x from -{_HALF} to {_HALF}, y from -{LIMITS['partBox']} to 0, the ground)"
    if kind == "circle":
        cx, cy, r = sh.get("cx"), sh.get("cy"), sh.get("r")
        if (not all(_num(v) for v in (cx, cy, r)) or not 0 < r <= _HALF
                or not _in_box(cx - r, cy - r) or not _in_box(cx + r, cy + r)):
            return f"a circle needs cx, cy and r (1 to {_HALF}) with the whole circle {box}."
    elif kind == "rect":
        x, y, w, h = sh.get("x"), sh.get("y"), sh.get("w"), sh.get("h")
        if (not all(_num(v) for v in (x, y, w, h)) or w <= 0 or h <= 0
                or not _in_box(x, y) or not _in_box(x + w, y + h)):
            return f"a rect needs x, y, w and h (w and h above 0) with all four corners {box}."
        if "r" in sh and (not _num(sh["r"]) or sh["r"] < 0):
            return "a rect's r (corner radius) must be 0 or more."
    else:
        pts = sh.get("points")
        lo, hi = (2, 12) if kind == "line" else (3, 16)
        if (not isinstance(pts, list) or not lo <= len(pts) <= hi
                or not all(isinstance(p, list) and len(p) == 2 and _in_box(p[0], p[1]) for p in pts)):
            return f"a {kind} needs {lo} to {hi} points [x, y] {box}."
        if kind == "line":
            wd = sh.get("width")
            if not _num(wd) or not 2 <= wd <= 60:
                return "a line needs a width from 2 to 60."
            # the stroke's sides and top count; a cap may sink into the ground line it stands on
            if not all(_in_box(p[0] - wd / 2, p[1] - wd / 2) and _in_box(p[0] + wd / 2, p[1]) for p in pts):
                return f"a line's points, with half its width to each side and above, must stay {box}."
    return ""


def _timed(obj, key, where, start, end, on_word, err, what, low=None) -> bool:
    """A frame field: a whole number in the scene, on a word. True when it is sound."""
    v = obj.get(key) if isinstance(obj, dict) else None
    lo = start if low is None else low
    if not _int(v) or not lo <= v < end:
        err(f"{where}: {key} must be a frame from {lo} to {end - 1} ({what}).")
        return False
    if not on_word(v):
        err(f"{where}: {key} {v} is not on a word; put it within {TIMING['snap']} frames of a word's start.")
        return False
    return True


def _check_items(s, where, start, end, parts, on_word, err) -> set:
    items = s.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= LIMITS["maxItems"]:
        err(f"{where}: items must list 1 to {LIMITS['maxItems']} people, animals or things.")
        return set()
    slots: set[str] = set()
    threats = 0
    for n, it in enumerate(items):
        w = f"{where} item {n + 1}"
        if not isinstance(it, dict) or set(it) - _ITEM_KEYS:
            err(f"{w} must be an object with {sorted(_ITEM_KEYS)}.")
            continue
        if it.get("what") not in parts:
            err(f"{w}: what {it.get('what')!r} is not a library part or one of this video's customParts.")
        if it.get("slot") not in SLOTS:
            err(f"{w}: slot must be one of {list(SLOTS)}.")
            continue
        if it["slot"] in slots:
            err(f"{w}: two things stand in the {it['slot']} slot; give each its own slot.")
        slots.add(it["slot"])
        if "at" in it:
            _timed(it, "at", w, start, end, on_word, err, "the frame it pops in on")
        if it.get("threat") is not None and not isinstance(it.get("threat"), bool):
            err(f"{w}: threat must be true or false.")
        if it.get("threat"):
            threats += 1
        if "redAt" in it:
            if not it.get("threat"):
                err(f"{w}: redAt is for the threat; set threat true or drop redAt.")
            else:
                _timed(it, "redAt", w, it.get("at", start) if _int(it.get("at")) else start, end, on_word, err,
                       "the frame it turns red on")
        if "face" in it and it["face"] not in ("left", "right"):
            err(f"{w}: face must be \"left\" or \"right\".")
        if "to" in it:
            to = it["to"]
            if not isinstance(to, dict) or set(to) != {"slot", "at"} or to.get("slot") not in SLOTS:
                err(f"{w}: to must be {{\"slot\": one of {list(SLOTS)}, \"at\": a frame}}.")
            elif to["slot"] == it["slot"]:
                err(f"{w}: to names the slot it already stands in.")
            elif _timed(to, "at", f"{w} to", start, end, on_word, err, "the frame its step starts on"):
                if _int(it.get("at")) and to["at"] < it["at"]:
                    err(f"{w}: its step starts at frame {to['at']}, before it appears at {it['at']}.")
    # a step may not end on a slot another item holds
    for n, it in enumerate(items):
        if isinstance(it, dict) and isinstance(it.get("to"), dict) and it["to"].get("slot") in slots - {it.get("slot")}:
            err(f"{where} item {n + 1}: its step ends in the {it['to']['slot']} slot, where something already stands.")
    if threats > 1:
        err(f"{where}: {threats} items are the threat; red marks one thing in a scene.")
    return slots


def _check_connector(s, where, start, end, slots, on_word, err) -> None:
    c = s.get("connector")
    if c is None:
        return
    if not isinstance(c, dict) or set(c) != {"from", "to", "at"}:
        err(f"{where}: connector must be {{\"from\", \"to\", \"at\"}}.")
        return
    if c.get("from") not in slots or c.get("to") not in slots or c["from"] == c["to"]:
        err(f"{where}: a connector joins two different slots that hold items.")
        return
    _timed(c, "at", f"{where} connector", start, end, on_word, err, "the frame it starts to draw")


def _check_scene(s, where, start, end, parts, on_word, checks, err) -> None:
    L, T = LIMITS, TIMING
    kind = s["kind"]
    last = [start]

    def timed(obj, key, w, what, low=None, lasts=0):
        # `lasts`: the frames its animation runs after `key` (draw.ts), so the read window starts once it is done
        if _timed(obj, key, w, start, end, on_word, err, what, low):
            last[0] = max(last[0], obj[key] + lasts)

    if kind in ("tableau", "camera"):
        if kind == "tableau" and s.get("setting") not in SETTINGS:
            err(f"{where}: setting must be one of {list(SETTINGS)}.")
        if kind == "camera":
            if not _text(s.get("label"), L["cameraLabelChars"]):
                err(f"{where}: label must be 1 to {L['cameraLabelChars']} characters (\"CAM 02 / FRONT DOOR\").")
            b = s.get("button")
            if b is not None:
                if not isinstance(b, dict) or set(b) - {"text", "crossAt"} or not _text(b.get("text"), L["buttonChars"]):
                    err(f"{where}: button must be {{\"text\": 1 to {L['buttonChars']} characters, \"crossAt\"?: a frame}}.")
                elif "crossAt" in b:
                    timed(b, "crossAt", f"{where} button", "the frame the red stroke crosses it out")
        slots = _check_items(s, where, start, end, parts, on_word, err)
        _check_connector(s, where, start, end, slots, on_word, err)
        bub = s.get("bubble")
        if bub is not None:
            if kind != "tableau" or not isinstance(bub, dict) or set(bub) - {"over", "icon", "kind", "at"}:
                err(f"{where}: bubble must be {{\"over\", \"icon\", \"kind\"?, \"at\"}}.")
            else:
                if bub.get("over") not in slots:
                    err(f"{where}: the bubble must sit over a slot that holds an item.")
                if bub.get("icon") not in parts:
                    err(f"{where}: the bubble's icon {bub.get('icon')!r} is not a library part or a customParts id.")
                if "kind" in bub and bub["kind"] not in BUBBLES:
                    err(f"{where}: the bubble's kind must be one of {list(BUBBLES)}.")
                _timed(bub, "at", f"{where} bubble", start, end, on_word, err, "the frame it pops")
    elif kind == "phone":
        if s.get("screen") not in SCREENS:
            err(f"{where}: screen must be one of {list(SCREENS)}.")
        if not _text(s.get("title"), L["phoneTitleChars"]):
            err(f"{where}: title must be 1 to {L['phoneTitleChars']} characters.")
        lines = s.get("lines")
        if (not isinstance(lines, list) or not 1 <= len(lines) <= L["phoneLines"]
                or not all(_text(x, L["phoneLineChars"]) for x in lines)):
            err(f"{where}: lines must list 1 to {L['phoneLines']} lines of 1 to {L['phoneLineChars']} characters.")
        m = s.get("mark")
        if m is not None:
            if not isinstance(m, dict) or set(m) != {"kind", "at"} or m.get("kind") not in MARKS:
                err(f"{where}: mark must be {{\"kind\": one of {list(MARKS)}, \"at\": a frame}}.")
            else:
                if m["kind"] == "check":
                    checks[0] += 1
                timed(m, "at", f"{where} mark", "the frame the mark lands", lasts=T["mark"])
        # line i slides in from 4 + 8i frames after the start, over 10 frames (draw.ts::phone)
        if isinstance(lines, list) and lines:
            last[0] = max(last[0], start + 4 + 8 * (len(lines) - 1) + 10)
    elif kind == "rule":
        if not _int(s.get("number")) or not 1 <= s["number"] <= 99:
            err(f"{where}: number must be a whole number from 1 to 99.")
        lines = s.get("lines")
        if (not isinstance(lines, list) or not 1 <= len(lines) <= L["ruleLines"]
                or not all(_text(x, L["ruleLineChars"]) for x in lines)):
            err(f"{where}: lines must list 1 or {L['ruleLines']} lines of 1 to {L['ruleLineChars']} characters.")
        if s.get("icon") not in parts:
            err(f"{where}: icon {s.get('icon')!r} is not a library part or a customParts id.")
        if "slashAt" in s:
            timed(s, "slashAt", where, "the frame the red slash crosses the icon", low=start + T["ringStart"] + T["ringFrames"],
                  lasts=T["slashFrames"])
        else:
            last[0] = start + T["slashDelay"] + T["slashFrames"]
    elif kind == "case":
        if not _text(s.get("label"), L["caseLabelChars"]):
            err(f"{where}: label must be 1 to {L['caseLabelChars']} characters (\"WITNESS\").")
        if not _text(s.get("name"), L["caseNameChars"]):
            err(f"{where}: name must be 1 to {L['caseNameChars']} characters.")
        if s.get("icon") not in parts:
            err(f"{where}: icon {s.get('icon')!r} is not a library part or a customParts id.")
        if not _int(s.get("bars")) or not L["minBars"] <= s["bars"] <= L["maxBars"]:
            err(f"{where}: bars must be a whole number from {L['minBars']} to {L['maxBars']}.")
        st = s.get("stamp")
        if st is not None:
            if not isinstance(st, dict) or set(st) != {"text", "at"} or not _text(st.get("text"), L["stampChars"]):
                err(f"{where}: stamp must be {{\"text\": 1 to {L['stampChars']} characters, \"at\": a frame}}.")
            else:
                timed(st, "at", f"{where} stamp", "the frame the stamp lands", lasts=T["mark"])
        # bar i draws from 4 + 5i frames after the start, over 8 frames (draw.ts::caseCard)
        if _int(s.get("bars")) and L["minBars"] <= s["bars"] <= L["maxBars"]:
            last[0] = max(last[0], start + 4 + 5 * (s["bars"] - 1) + 8)
    elif kind == "steps":
        if not _text(s.get("title"), L["stepsTitleChars"]):
            err(f"{where}: title must be 1 to {L['stepsTitleChars']} characters.")
        steps = s.get("steps")
        if (not isinstance(steps, list) or not L["minSteps"] <= len(steps) <= L["maxSteps"]
                or not all(isinstance(x, dict) and set(x) == {"text", "at"} and _text(x.get("text"), L["stepChars"])
                           for x in steps)):
            err(f"{where}: steps must list {L['minSteps']} to {L['maxSteps']} steps, each "
                f"{{\"text\": 1 to {L['stepChars']} characters, \"at\": a frame}}.")
        else:
            prev = start - 1
            for n, x in enumerate(steps):
                timed(x, "at", f"{where} step {n + 1}", "the frame it appears", low=prev + 1, lasts=T["stepIn"])
                prev = x["at"] if _int(x["at"]) else prev
    if kind in ("phone", "rule", "case", "steps") and end - last[0] < T["readFrames"]:
        err(f"{where}: its last part has finished arriving at frame {last[0]}, {end - last[0]} frames before the scene ends; "
            f"leave at least {T['readFrames']} frames to read it.")


def _check_quiet(scenes, starts, quiet, err) -> None:
    """Nothing of the style starts inside an insert, where the scene is hidden."""
    for i, s in enumerate(scenes):
        where = f"Scene {i + 1} ({s['kind']})"
        # a glitch tear runs on tearAfter frames past its scene's start, so a scene that starts just before
        # an insert would flash and tear under it; the frames before the start ride the insert's own way out
        torn = i and (s.get("cut") or "glitch") == "glitch"
        b = starts[i] + (TIMING["tearAfter"] if torn else 0)
        w = next((x for x in (window_at(f, quiet) for f in range(starts[i], b + 1)) if x), None) if starts[i] else None
        if w:
            err(f"{where} starts at frame {starts[i]}, and its tear runs to {b}, inside an insert ({window_text(w)}), "
                f"where the scene is hidden; start it at {w[1]} or before {w[0] - (b - starts[i])}.")
            continue
        for f in event_frames(s)[1:]:
            w = window_at(f, quiet)
            if w:
                err(f"{where}: something happens at frame {f}, inside an insert ({window_text(w)}), where the "
                    f"scene is hidden; time it to a word at {w[1]} or later, or before {w[0]}.")
                break


def scene_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every scene of a Night Signal config, for the
    text-layout audit to sample each: a picture from just after its tear, a
    card from its last part. [] when the config is not one."""
    scenes_cfg = _seq(config.get("scenes"))
    if len(scenes_cfg) != 1 or not is_night_signal_scene(scenes_cfg[0]):
        return []
    data = (scenes_cfg[0].get("props") or {}).get(PROPS_KEY) or {}
    scenes = [s for s in _seq(data.get("scenes")) if isinstance(s, dict) and _int(s.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    out = []
    for s, end in zip(scenes, [n["start"] for n in scenes[1:]] + [total]):
        settled = s["start"] + TIMING["tearAfter"] + 1
        if s.get("kind") in ("rule", "case", "steps", "phone"):
            try:
                settled = max(settled, event_frames(s)[-1] + TIMING["mark"])
            except (KeyError, TypeError):
                pass
        if end > s["start"]:
            out.append((min(settled, end - 1), end))
    return out
