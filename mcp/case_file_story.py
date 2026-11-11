"""Case File Story (TMDEV-202): the checks a Case File Story scene-config must
pass before it is written, so an unattended agent cannot ship a meter that
does not fit its cell, a card that is cut before it can be read, a mistimed
punch-in, a still video or a story with no consequence before its choice.

A Case File Story video is one installed `CaseFileStory` scene spanning every
frame. The agent writes no code for it: `props.caseFile` holds an accent, two
or three meters (the HUD) and beats timed to the narration's word frames: shots
(a generated painted still, pushed in slowly, with an optional punch-in), a
count card, a bars card, a term card with a stamp, and the closing choice. The
renderer's side of this contract is
renderer/remotion/src/scenes/installed/caseFileStory/contract.ts.

Keep in sync: LIMITS, TIMING, CAMERA, GEOMETRY, the catalogues and the helpers
mirror contract.ts (quiet_spans mirrors stage.ts). mcp/tests/test_case_file_story.py
reads the TypeScript constants and the style pack, and both sides run the
shared cases in tests/fixtures/case_file_story_contract.json, so a drift fails
a test instead of a render.

Free of the database and of I/O: the caller passes the config, the narration's
fps and word start frames, the pack's `extra` block and the video id.
"""
from __future__ import annotations

import math
import re

SCENE_SRC = "CaseFileStory"
PROPS_KEY = "caseFile"
STYLE_ID = "case_file_story"
# The per-video sheet of the lead, made from the shipped house sheet. It is a
# reference for the other stills and never a picture in the video.
LEAD_NAME = "lead"
HOUSE_REFERENCE = "house"

W, H = 1080, 1920
ACCENTS = {"pink": "#E8327A", "amber": "#F2A33A", "teal": "#2FB5A6", "red": "#E5484D"}
BEAT_TYPES = ("shot", "count", "bars", "term", "choice")
METER_KINDS = ("money", "count", "percent")
ICONS = ("bill", "coin", "envelope", "person", "box", "card", "phone", "document", "key", "goldbar")

LIMITS = {
    "maxImages": 16,
    "minMeters": 2,
    "maxMeters": 3,
    "maxBeats": 48,
    "meterLabelChars": 12,
    "maxValue": 999999999,
    "titleChars": 26,
    "unitChars": 26,
    "resultChars": 14,
    "minBars": 2,
    "maxBars": 6,
    "barLabelChars": 6,
    "thresholdLabelChars": 24,
    "payoffChars": 30,
    "termChars": 18,
    "definitionChars": 110,
    "stampChars": 16,
    "citationChars": 34,
    "optionChars": 9,
    "minShotSeconds": 1,
    "maxStillSeconds": 4,
}
TIMING = {
    "snap": 2,
    "cardFade": 4,
    "hudDissolve": 2,
    "punchMargin": 12,
    "readFrames": 20,
    "countStart": 10,
    "countFrames": 36,
    "resultDelay": 12,
    "barStep": 8,
    "payoffDelay": 11,
    "definitionDelay": 20,
    "stampDelay": 25,
    "stampIn": 4,
    "citationDelay": 10,
    "optionFirst": 8,
    "optionStep": 20,
    "panelCount": 12,
}
CAMERA = {"push": 0.025, "punch": 1.5, "focusU": 0.5, "focusV": 0.45}
GEOMETRY = {
    "safeLeft": 60,
    "safeRight": 1020,
    "hudTop": 232,
    "hudHeight": 106,
    "hudGap": 11,
    "hudRadius": 15,
    "cardBottom": 1240,
    "chartLeft": 130,
    "chartRight": 950,
    "chartTop": 520,
    "chartBottom": 1010,
    "barGap": 26,
    "gridCols": 8,
    "gridRows": 5,
    "gridLeft": 150,
    "gridTop": 470,
    "gridCell": 98,
    "termWidth": 920,
    "termSize": 112,
    "termCharWidth": 0.62,
    "optionTop": 1500,
    "optionHeight": 150,
    "optionGap": 30,
}

MAX_ERRORS = 12

_IMAGE_SRC = re.compile(r"^/public/([A-Za-z0-9_-]+)/images/([A-Za-z0-9-]+)\.(png|jpe?g|webp)$")
_METER_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

_KEYS = {
    "shot": {"type", "start", "image", "focus", "punch", "set", "hud", "panel"},
    "count": {"type", "start", "title", "unit", "icon", "to", "kind", "result", "resultFrame"},
    "bars": {"type", "start", "title", "kind", "threshold", "bars", "payoff", "payoffFrame"},
    "term": {"type", "start", "term", "definition", "stamp", "citation", "definitionFrame", "stampFrame"},
    "choice": {"type", "start", "image", "focus", "options", "optionFrames"},
}


def is_case_file_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


# ── the renderer's helpers, mirrored ─────────────────────────────────────────
def format_value(kind: str, value: int) -> str:
    """A meter or card number as it is drawn. Whole-number arithmetic only: a
    million or more is shown in millions with one decimal, cut, never rounded up."""
    v = max(0, int(value))
    if kind == "percent":
        return f"{v}%"
    if v >= 1000000:
        tenths = v // 100000
        whole, frac = tenths // 10, tenths % 10
        text = f"{whole}M" if frac == 0 else f"{whole}.{frac}M"
    else:
        text = f"{v:,}"
    return f"${text}" if kind == "money" else text


def hud_cells(n: int) -> list[tuple[float, float]]:
    """The (left, width) of each of `n` equal meter cells across the safe width."""
    g = GEOMETRY
    width = (g["safeRight"] - g["safeLeft"] - g["hudGap"] * (n - 1)) / n
    return [(g["safeLeft"] + i * (width + g["hudGap"]), width) for i in range(n)]


def shot_scale(t: float, fps: int, punch_after) -> float:
    push = 1 + (CAMERA["push"] * max(0, t)) / fps
    return push * CAMERA["punch"] if punch_after is not None and t >= punch_after else push


def shot_view(scale: float, u: float, v: float) -> tuple[float, float, float, float]:
    """The part of the frame-sized still on screen at `scale` about [u, v], as
    (x, y, width, height) in frame pixels, kept inside the still."""
    s = max(1, scale)
    vw, vh = W / s, H / s
    x = min(W - vw, max(0, u * W - vw / 2))
    y = min(H - vh, max(0, v * H - vh / 2))
    return (x, y, vw, vh)


def term_font_size(term: str) -> int:
    g = GEOMETRY
    return min(g["termSize"], math.floor(g["termWidth"] / (max(1, len(term)) * g["termCharWidth"])))


def bar_layout(values: list, threshold) -> dict:
    """The bars of a bars card as (x, y, width, height) and the threshold line's y."""
    g = GEOMETRY
    top = max(threshold, *values, 1) * 1.15
    span = g["chartBottom"] - g["chartTop"]
    n = len(values)
    width = (g["chartRight"] - g["chartLeft"] - g["barGap"] * (n - 1)) / n
    bars = []
    for i, v in enumerate(values):
        h = (max(0, v) / top) * span
        bars.append((g["chartLeft"] + i * (width + g["barGap"]), g["chartBottom"] - h, width, h))
    return {"bars": bars, "lineY": g["chartBottom"] - (threshold / top) * span}


def part_frames(beat: dict) -> list[int]:
    """The frames at which a beat's parts appear, in order, first its own
    start. Parts the agent did not time fall on the TIMING defaults."""
    t = TIMING
    kind, start = beat["type"], beat["start"]
    if kind == "shot":
        return [start, beat["punch"]["frame"]] if beat.get("punch") else [start]
    if kind == "count":
        counted = start + t["countStart"] + t["countFrames"]
        result = beat.get("resultFrame")
        return [start, counted, result if result is not None else counted + t["resultDelay"]]
    if kind == "bars":
        bars = [b["frame"] for b in beat["bars"]]
        payoff = beat.get("payoffFrame")
        return [start, *bars, payoff if payoff is not None else bars[-1] + t["payoffDelay"]]
    if kind == "term":
        definition = beat.get("definitionFrame")
        definition = definition if definition is not None else start + t["definitionDelay"]
        stamp = beat.get("stampFrame")
        stamp = stamp if stamp is not None else definition + t["stampDelay"]
        frames = [start, definition, stamp]
        return frames + [stamp + t["stampIn"] + t["citationDelay"]] if beat.get("citation") else frames
    frames = beat.get("optionFrames") or [start + t["optionFirst"], start + t["optionFirst"] + t["optionStep"]]
    return [start, frames[0], frames[1]]


def quiet_spans(data: dict, total: int) -> list[list[int]]:
    """The stretches in which nothing new appears apart from the slow push:
    from each part of a beat to the next, and from the last part to its end."""
    beats = data["beats"]
    spans = []
    for i, b in enumerate(beats):
        end = beats[i + 1]["start"] if i + 1 < len(beats) else total
        frames = part_frames(b) + [end]
        spans.extend([a, c] for a, c in zip(frames, frames[1:]))
    return spans


# ── the checks ───────────────────────────────────────────────────────────────
def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _uv(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_num(x) and 0 <= x <= 1 for x in v)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and bool(v.strip()) and len(v) <= limit and "\n" not in v


def _caps(v) -> bool:
    return isinstance(v, str) and v == v.upper()


def _value_error(kind: str, v) -> str:
    """Why `v` cannot be shown as a `kind` number, or ""."""
    if not _int(v) or not 0 <= v <= LIMITS["maxValue"]:
        return f"must be a whole number from 0 to {LIMITS['maxValue']}"
    if kind == "percent" and v > 100:
        return "is a percentage, so at most 100"
    return ""


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Case File Story video is exactly the one
    CaseFileStory scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_case_file_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The CaseFileStory scene draws a whole Case File Story video and is used only when "
                    "the video's visual_style is case_file_story (chosen at the topic). Build this "
                    "video's scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Case File Story video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"CaseFileStory\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"caseFile\": {...}}}. Put every beat in its beats.")
    return ""


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "") -> list[str]:
    """Every problem with a Case File Story config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block."""
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the accent, the meters and the beats."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]

    accents = list(extra.get("accents") or ACCENTS)
    if data.get("accent") not in accents:
        err(f"accent must be one of {accents}.")

    # ── the meters ──
    hud = data.get("hud")
    if (not isinstance(hud, list) or not LIMITS["minMeters"] <= len(hud) <= LIMITS["maxMeters"]
            or not all(isinstance(m, dict) for m in hud)):
        return errors + [f"hud must list {LIMITS['minMeters']} or {LIMITS['maxMeters']} meters, each "
                         "{id, label, kind, value}."]
    meters: dict[str, str] = {}
    for n, m in enumerate(hud):
        where = f"Meter {n + 1}"
        mid, kind = m.get("id"), m.get("kind")
        if not isinstance(mid, str) or not _METER_ID.match(mid) or mid in meters:
            err(f"{where}: id must be a short lower-case name of its own (letters, digits, _), like \"cash\".")
            continue
        if kind not in METER_KINDS:
            err(f"{where} ({mid}): kind must be one of {list(METER_KINDS)}.")
            continue
        meters[mid] = kind
        if not _text(m.get("label"), LIMITS["meterLabelChars"]) or not _caps(m.get("label")):
            err(f"{where} ({mid}): label must be 1 to {LIMITS['meterLabelChars']} characters in capitals.")
        problem = _value_error(kind, m.get("value"))
        if problem:
            err(f"{where} ({mid}): value {problem}.")

    # ── the beats ──
    beats = data.get("beats")
    if not isinstance(beats, list) or not 1 <= len(beats) <= LIMITS["maxBeats"]:
        return errors + [f"beats must list 1 to {LIMITS['maxBeats']} beats."]
    if not all(isinstance(b, dict) and b.get("type") in BEAT_TYPES for b in beats):
        return errors + [f"Every beat must be an object whose type is one of {list(BEAT_TYPES)}."]
    starts = [b.get("start") for b in beats]
    if not all(_int(v) for v in starts):
        return errors + ["Every beat needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first beat must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Beat starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    if beats[0]["type"] != "shot":
        err("The first beat must be a shot: the story opens in its scene, not on a card.")
    kinds = [b["type"] for b in beats]
    if kinds.count("choice") != 1 or kinds[-1] != "choice":
        err("The video ends on the choice: exactly one beat of type \"choice\", and it is the last.")
    elif "term" not in kinds:
        err("The consequence comes before the choice: add a term card (the name of what happened, its "
            "definition and a stamp) before the last beat.")

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    images: set[str] = set()
    sound: list[bool] = []
    for i, b in enumerate(beats):
        where = f"Beat {i + 1} ({b['type']})"
        if i and not on_word(starts[i]):
            err(f"{where} starts at frame {starts[i]}, which is not on a word: start a beat within "
                f"{TIMING['snap']} frames of a word's start.")
        extra_keys = sorted(set(b) - _KEYS[b["type"]])
        if extra_keys:
            err(f"{where}: unknown field(s) {extra_keys}; a {b['type']} takes {sorted(_KEYS[b['type']])}.")
        before = len(errors)
        _check_beat(b, where, starts[i], ends[i], fps, meters, video_id, images, on_word, extra, err)
        sound.append(len(errors) == before and not extra_keys)
    if len(images) > LIMITS["maxImages"]:
        err(f"The beats use {len(images)} different stills; a video may use at most {LIMITS['maxImages']}. "
            "Reuse a still with another focus or a punch-in instead of a new one.")

    # ── nothing may sit still for long ──
    if all(sound):
        still = round(LIMITS["maxStillSeconds"] * fps)
        for i, b in enumerate(beats):
            frames = part_frames(b) + [ends[i]]
            for a, c in zip(frames, frames[1:]):
                if c - a > still:
                    fix = ("Add a punch-in, or cut to another shot or a card sooner." if b["type"] == "shot"
                           else "Time its parts to later words, or start the next beat sooner.")
                    err(f"Beat {i + 1} ({b['type']}): nothing new appears from frame {a} to {c} "
                        f"({(c - a) / fps:.1f} s); the longest stretch allowed is "
                        f"{LIMITS['maxStillSeconds']} s. {fix}")
    return errors


def _check_image(b, where, video_id, images, err) -> None:
    src = b.get("image")
    m = _IMAGE_SRC.match(src) if isinstance(src, str) else None
    if not m or (video_id and m.group(1) != video_id):
        err(f"{where}: image must be a still of this video, the public_path generate_image returned "
            f"(/public/{video_id or '<video_id>'}/images/<name>.png).")
        return
    if m.group(2) == LEAD_NAME:
        err(f"{where}: \"{LEAD_NAME}\" is the lead's reference sheet, not a picture for the video. "
            "Generate a still of the scene with reference=\"lead\" and use that.")
        return
    images.add(src)
    if "focus" in b and not _uv(b["focus"]):
        err(f"{where}: focus must be [u, v], each from 0 to 1 (fractions of the still from its top left).")


def _timed(b, where, key, low, end, on_word, err, what) -> None:
    """An optional part frame: a whole number from `low` up, before the beat's end, on a word."""
    if key not in b:
        return
    f = b[key]
    if not _int(f) or not low <= f < end:
        err(f"{where}: {key} must be a frame from {low} to {end - 1} ({what}).")
    elif not on_word(f):
        err(f"{where}: {key} {f} is not on a word; put it within {TIMING['snap']} frames of a word's start.")


def _check_beat(b, where, start, end, fps, meters, video_id, images, on_word, extra, err) -> None:
    L, T = LIMITS, TIMING
    kind = b["type"]

    def readable(last: int) -> None:
        if last + T["readFrames"] > end:
            err(f"{where}: its last part appears at frame {last} and the beat ends at {end}; it needs "
                f"{T['readFrames']} frames on screen to be read. Start the next beat later or this one earlier.")

    if kind == "shot":
        _check_image(b, where, video_id, images, err)
        if end - start < L["minShotSeconds"] * fps:
            err(f"{where} lasts {end - start} frames; a shot needs at least {L['minShotSeconds']} s.")
        if "punch" in b:
            p = b["punch"]
            if not isinstance(p, dict) or set(p) != {"frame", "at"} or not _int(p.get("frame")) or not _uv(p.get("at")):
                err(f"{where}: punch must be {{\"frame\": <frame>, \"at\": [u, v]}}.")
            elif not start + T["punchMargin"] <= p["frame"] <= end - T["punchMargin"]:
                err(f"{where}: the punch-in at frame {p['frame']} must be at least {T['punchMargin']} frames "
                    f"after the shot starts ({start}) and before it ends ({end}).")
            elif not on_word(p["frame"]):
                err(f"{where}: the punch-in at frame {p['frame']} is not on a word; put it within "
                    f"{T['snap']} frames of the word it lands on.")
        if "hud" in b and not isinstance(b["hud"], bool):
            err(f"{where}: hud must be true or false.")
        changed = b.get("set", {})
        if not isinstance(changed, dict):
            err(f"{where}: set must be an object of meter id to its new value.")
            changed = {}
        for mid, v in changed.items():
            if mid not in meters:
                err(f"{where}: set names the meter {mid!r}, which hud does not list ({sorted(meters)}).")
                continue
            problem = _value_error(meters[mid], v)
            if problem:
                err(f"{where}: set.{mid} {problem}.")
        if "panel" in b:
            if b["panel"] not in changed:
                err(f"{where}: panel shows a meter counting to a new value, so name a meter this shot's "
                    "set changes.")
            elif b.get("hud") is False:
                err(f"{where}: panel needs the meter row; remove \"hud\": false or the panel.")
        return

    if kind == "choice":
        _check_image(b, where, video_id, images, err)
        opts = b.get("options")
        if (not isinstance(opts, list) or len(opts) != 2 or not all(_text(o, L["optionChars"]) and _caps(o) for o in opts)
                or opts[0] == opts[1]):
            err(f"{where}: options must be two different labels of 1 to {L['optionChars']} characters in "
                "capitals, in the order the narration says them.")
        frames = b.get("optionFrames")
        if frames is not None:
            if (not isinstance(frames, list) or len(frames) != 2 or not all(_int(f) for f in frames)
                    or not start <= frames[0] < frames[1] < end):
                err(f"{where}: optionFrames must be two frames in order, from {start} to {end - 1}.")
                return
            for f in frames:
                if not on_word(f):
                    err(f"{where}: optionFrames {f} is not on a word; put each button on the word that says it.")
        readable(part_frames(b)[-1])
        return

    if not _text(b.get("title") if kind != "term" else b.get("term"), L["titleChars"] if kind != "term" else L["termChars"]):
        name, limit = ("term", L["termChars"]) if kind == "term" else ("title", L["titleChars"])
        err(f"{where}: {name} must be 1 to {limit} characters.")

    if kind == "count":
        if "unit" in b and not _text(b["unit"], L["unitChars"]):
            err(f"{where}: unit must be 1 to {L['unitChars']} characters, or left out.")
        icons = list(extra.get("icons") or ICONS)
        if b.get("icon") not in icons:
            err(f"{where}: icon must be one of {icons}.")
        if b.get("kind") not in METER_KINDS:
            err(f"{where}: kind must be one of {list(METER_KINDS)}.")
        elif _value_error(b["kind"], b.get("to")) or b.get("to") == 0:
            err(f"{where}: to (what the counter climbs to) {_value_error(b['kind'], b.get('to')) or 'must be more than 0'}.")
        if not _text(b.get("result"), L["resultChars"]):
            err(f"{where}: result must be 1 to {L['resultChars']} characters (what the count comes to).")
        counted = start + T["countStart"] + T["countFrames"]
        _timed(b, where, "resultFrame", counted, end, on_word, err, "after the counter stops")
        if not _int(b.get("resultFrame", 0)):
            return
        readable(part_frames(b)[-1])
        return

    if kind == "bars":
        if b.get("kind") not in METER_KINDS:
            err(f"{where}: kind must be one of {list(METER_KINDS)}.")
            return
        th = b.get("threshold")
        if (not isinstance(th, dict) or set(th) != {"value", "label"} or _value_error(b["kind"], th.get("value"))
                or th.get("value") == 0 or not _text(th.get("label"), L["thresholdLabelChars"])):
            err(f"{where}: threshold must be {{\"value\": <whole number above 0>, \"label\": <1 to "
                f"{L['thresholdLabelChars']} characters>}}.")
        bars = b.get("bars")
        if not isinstance(bars, list) or not L["minBars"] <= len(bars) <= L["maxBars"]:
            err(f"{where}: bars must list {L['minBars']} to {L['maxBars']} bars.")
            return
        ok = True
        for n, bar in enumerate(bars):
            if (not isinstance(bar, dict) or set(bar) != {"label", "value", "frame"}
                    or not _text(bar.get("label"), L["barLabelChars"]) or _value_error(b["kind"], bar.get("value"))
                    or not _int(bar.get("frame"))):
                err(f"{where}: bar {n + 1} must be {{\"label\": <1 to {L['barLabelChars']} characters>, "
                    "\"value\": <whole number>, \"frame\": <the frame of the word that counts it>}.")
                ok = False
        if not ok:
            return
        frames = [bar["frame"] for bar in bars]
        if frames[0] < start or frames[-1] >= end or any(c - a < T["barStep"] for a, c in zip(frames, frames[1:])):
            err(f"{where}: bar frames must run in order inside the beat ({start} to {end - 1}), at least "
                f"{T['barStep']} frames apart.")
            return
        for f in frames:
            if not on_word(f):
                err(f"{where}: the bar at frame {f} is not on a word; each bar appears on the word that counts it.")
        if not _text(b.get("payoff"), L["payoffChars"]):
            err(f"{where}: payoff must be 1 to {L['payoffChars']} characters (the line the bars add up to).")
        _timed(b, where, "payoffFrame", frames[-1] + 1, end, on_word, err, "after the last bar")
        if not _int(b.get("payoffFrame", 0)):
            return
        readable(part_frames(b)[-1])
        return

    # term
    if not _caps(b.get("term")):
        err(f"{where}: term must be in capitals.")
    if not _text(b.get("definition"), L["definitionChars"]):
        err(f"{where}: definition must be 1 to {L['definitionChars']} characters, one plain sentence.")
    if not _text(b.get("stamp"), L["stampChars"]) or not _caps(b.get("stamp")):
        err(f"{where}: stamp must be 1 to {L['stampChars']} characters in capitals (what it is: a crime, a "
            "breach, a red flag).")
    if "citation" in b and not _text(b["citation"], L["citationChars"]):
        err(f"{where}: citation must be 1 to {L['citationChars']} characters, or left out.")
    _timed(b, where, "definitionFrame", start, end, on_word, err, "inside the card")
    if not _int(b.get("definitionFrame", 0)):
        return
    definition = part_frames(b)[1]
    _timed(b, where, "stampFrame", definition + 1, end, on_word, err, "after the definition")
    if not _int(b.get("stampFrame", 0)):
        return
    readable(part_frames(b)[-1])


def beat_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every beat of a Case File Story config, for the
    text-layout audit to sample each like a scene: a shot from its cut, a card
    or the choice from the frame its last part appears (its text builds part
    by part). [] when the config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_case_file_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    beats = [b for b in data.get("beats") or [] if isinstance(b, dict) and _int(b.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    windows = []
    for b, end in zip(beats, [n["start"] for n in beats[1:]] + [total]):
        settled = b["start"]
        if b.get("type") in ("count", "bars", "term", "choice"):
            try:
                settled = max(settled, part_frames(b)[-1] + TIMING["stampIn"])
            except (KeyError, TypeError, IndexError):
                pass
        if end > b["start"]:
            windows.append((min(settled, end - 1), end))
    return windows
