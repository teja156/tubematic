"""Mid-century How-To (TMDEV-233): the checks a Mid-century How-To
scene-config must pass before it is written, so an unattended agent cannot
ship a mistimed, crowded or still video.

A Mid-century How-To video is one installed `MidcenturyHowTo` scene spanning
every frame. The agent writes no code for it unless it draws an object the
library lacks: `props.midcenturyHowTo` holds the title, the steps (header,
tag, ground colour), an optional summary card, and shots (cuts) of events
timed to the narration's word frames: the presenter's poses, objects from the
library, their acts, presses, check and cross medallions, insets and labels.
The renderer's side of this contract is
renderer/remotion/src/scenes/installed/midcenturyHowTo/contract.ts and
stage.ts.

Keep in sync: LIMITS, TIMING, GEOMETRY, the catalogues and the box helpers
mirror contract.ts and stage.ts. mcp/tests/test_midcentury_howto.py compares
them with tests/fixtures/midcentury_howto_contract.json, which
renderer/remotion/character-tools/sync-contract.mjs writes from the
TypeScript, so a drift fails a test instead of a render.

Free of the database and of I/O: the caller passes the config, the
narration's word start frames and words, and the pack's `extra` block.
"""
from __future__ import annotations

import math
import re

import character_kit as ck
from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "MidcenturyHowTo"
PROPS_KEY = "midcenturyHowTo"
STYLE_ID = "midcentury_howto"
# The pack `extra` key that holds the library custom props join.
LIBRARY_KEY = "objects"

W, H = 1080, 1920
LIMITS = {
    "minSteps": 2, "maxSteps": 6, "maxShots": 30, "maxEventsPerShot": 20, "maxElementsPerShot": 4,
    "titleChars": 30, "kickerChars": 22, "headerChars": 18, "tagChars": 26, "labelChars": 22, "insetChars": 10,
    "maxStillSeconds": 3, "minShotSeconds": 1.5, "minStepSeconds": 3, "minIntroSeconds": 1.5,
    "minSummarySeconds": 2, "labelEchoWords": 4,
}
TIMING = {
    "objectIn": 8, "minPoseGap": 8, "poseBlend": 4, "pressLead": 6, "pressHold": 12, "pressReturn": 8,
    "minPressGap": 16, "actFrames": 20, "pop": 8, "endMargin": 6, "headerIn": 12,
}
GEOMETRY = {
    "safeLeft": 60, "safeRight": 1020, "stageTop": 600, "introStageTop": 860, "floorY": 1385,
    "presenterX": 205, "presenterHalfWidth": 150, "presenterHeight": 820, "shoulderDx": 52, "shoulderDy": -588,
    "armReach": 430, "labelFontPx": 40, "labelCharPx": 22, "labelHeightPx": 64, "insetRadius": 120,
    "overlapTolerance": 6,
}
GROUNDS = ("mustard", "blue", "olive", "rose", "sea")
EVENT_TYPES = ("pose", "object", "act", "press", "check", "cross", "inset", "label")
POSES = ("stand", "present", "point", "thumbsup", "wave", "think", "shrug", "hips")
SUMMARY_POSES = ("stand", "thumbsup", "wave", "hips")
AIM_POSES = ("present", "point")
FACES = ("neutral", "smile", "grin", "worried", "surprised", "proud")
OUTFITS = ("coral", "teal", "mustard", "blue")
HAIRS = ("dark", "red", "blond", "grey")
SIDES = ("left", "right", "none")
ENTRANCES = ("pop", "drop", "slide", "rise")
OBJECT_SCALE = (0.5, 1.5)
CUSTOM = {"maxProps": 8, "minSide": 60, "maxSide": 700, "maxText": 80, "maxActs": 4}
# Object boxes at scale 1, in frame pixels (contract.ts's OBJECTS w and h).
OBJECT_BOXES = {
    "phone": (320, 560), "laptop": (540, 420), "window": (600, 440), "qr": (270, 270), "keypad": (380, 470),
    "password": (560, 160), "toggle": (280, 150), "button": (360, 160), "app": (240, 270), "router": (440, 290),
    "lock": (230, 310), "key": (320, 170), "shield": (250, 300), "usb": (320, 150), "battery": (320, 170),
    "envelope": (360, 250), "document": (310, 390), "checklist": (360, 420), "card": (390, 250),
    "sign": (380, 270), "calendar": (300, 330), "clock": (300, 300), "bulb": (230, 330), "gear": (290, 290),
    "magnifier": (300, 310), "bell": (270, 290), "cloud": (380, 250), "trash": (250, 310), "table": (480, 300),
}
_ALLOWED_IMPORT = re.compile(r"^(react|remotion|\.\./\.\./installed/midcenturyHowTo/(cel|contract))$")
_ALLOWED_TEXT = "react, remotion and ../../installed/midcenturyHowTo/cel (or contract)"

# A cut, a step, a pose or a press lands on a word: within this many frames of one.
SNAP_FRAMES = 2
MAX_ERRORS = 12
CHANGE_FIX = "start a new step or shot there, or a press, check, inset, act or new object on that word"
# Events that change too little of the frame to count as a visible change.
SUBTLE = ("label",)


def is_scene(scene) -> bool:
    """Any scene naming MidcenturyHowTo, whatever its type: the use rule must catch a mistyped one too."""
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


# ── geometry: contract.ts's helpers ───────────────────────────────────────────

def object_box(obj: str, x: float, y: float, scale: float = 1, boxes: dict | None = None) -> tuple:
    w, h = (boxes or OBJECT_BOXES)[obj]
    cx, cy, hw, hh = x * W, y * H, w * scale / 2, h * scale / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def label_box(text: str, x: float, y: float) -> tuple:
    width = max(len(text), 1) * GEOMETRY["labelCharPx"] + 90
    cx, cy = x * W, y * H
    return (cx - width / 2, cy - GEOMETRY["labelHeightPx"] / 2, cx + width / 2, cy + GEOMETRY["labelHeightPx"] / 2)


def inset_box(x: float, y: float) -> tuple:
    r, cx, cy = GEOMETRY["insetRadius"], x * W, y * H
    return (cx - r, cy - r, cx + r, cy + r)


def presenter_feet_x(side: str) -> float:
    return W - GEOMETRY["presenterX"] if side == "right" else GEOMETRY["presenterX"]


def presenter_box(side: str) -> tuple:
    cx = presenter_feet_x(side)
    return (cx - GEOMETRY["presenterHalfWidth"], GEOMETRY["floorY"] - GEOMETRY["presenterHeight"],
            cx + GEOMETRY["presenterHalfWidth"], GEOMETRY["floorY"])


def shoulder_at(side: str) -> tuple:
    dx = -GEOMETRY["shoulderDx"] if side == "right" else GEOMETRY["shoulderDx"]
    return (presenter_feet_x(side) + dx, GEOMETRY["floorY"] + GEOMETRY["shoulderDy"])


def in_reach(side: str, px: float, py: float) -> bool:
    if side == "none":
        return False
    sx, sy = shoulder_at(side)
    return math.hypot(px - sx, py - sy) <= GEOMETRY["armReach"]


def screen_lines(text: str) -> list[str]:
    return [s.strip() for s in text.split("|") if s.strip()][:4]


def press_point(obj: str, x: float, y: float, scale: float, act: str | None) -> tuple:
    """stage.ts's pressPoint, with x and y in frame pixels."""
    dy = 0.0
    m = re.fullmatch(r"row([1-3])", act or "")
    if m:
        i = int(m.group(1)) - 1
        dy = {"phone": -80 + 108 * i, "laptop": -57 + 70.5 * i, "window": -9 + 85.7 * i}.get(obj, 0.0)
    elif obj == "keypad":
        dy = 40.0
    return (x, y + dy * scale)


def blink_at(frame: int, seed: int) -> bool:
    period = 98 + (seed % 23)
    return ((frame // 2) * 2 + (seed % period)) % period < 2


# ── the checks ────────────────────────────────────────────────────────────────

def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Mid-century How-To video is exactly the one
    MidcenturyHowTo scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The MidcenturyHowTo scene draws a whole Mid-century How-To video and is used only when the "
                    "video's visual_style is midcentury_howto (chosen at the topic). Build this video's scenes "
                    "from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Mid-century How-To video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"MidcenturyHowTo\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"midcenturyHowTo\": {...}}}. Put every beat in its shots.")
    return ""


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None):
    return ck.custom_prop_errors(custom, video_id, library, sources, CUSTOM, _ALLOWED_IMPORT, _ALLOWED_TEXT)


def check(config: dict, fps: int, word_starts: list[int], words: list[str], extra: dict,
          video_id: str = "", sources: dict | None = None, quiet=()) -> list[str]:
    """Every problem with a Mid-century How-To config, one sentence each (at
    most MAX_ERRORS), or [] when it may be written. `extra` is the style
    pack's catalogue block; `words` is the narration, word by word. A config's
    customProps join the library for this video; `sources` maps their src to
    the file's text (None skips the source checks). `quiet` holds the config's
    insert windows (mcp/quiet_windows.py)."""
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
    sp = scene.get("props")
    data = sp.get(PROPS_KEY) if isinstance(sp, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the title, steps and shots."]
    if not ck.is_int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    library = extra[LIBRARY_KEY]
    custom_errs, catalog, custom_boxes = custom_prop_errors(data.get("customProps"), video_id, library, sources)
    for e in custom_errs:
        err(e)
    boxes = {**OBJECT_BOXES, **custom_boxes}

    still = round(LIMITS["maxStillSeconds"] * fps)
    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return frame == 0 or not snaps or any(abs(frame - w) <= SNAP_FRAMES for w in snaps)

    # ── the whole video ──
    title = data.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > LIMITS["titleChars"]:
        err(f"title must be text of 1 to {LIMITS['titleChars']} characters: the task, as the running title.")
    if "kicker" in data and (not isinstance(data["kicker"], str) or len(data["kicker"]) > LIMITS["kickerChars"]):
        err(f"kicker must be text of at most {LIMITS['kickerChars']} characters.")
    pres = data.get("presenter", {})
    if not isinstance(pres, dict):
        err("presenter must be an object: {outfit, hair}.")
        pres = {}
    if pres.get("outfit", "coral") not in extra["outfits"]:
        err(f"presenter.outfit must be one of {', '.join(extra['outfits'])}.")
    if pres.get("hair", "dark") not in extra["hairs"]:
        err(f"presenter.hair must be one of {', '.join(extra['hairs'])}.")

    shots = data.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= LIMITS["maxShots"]:
        return errors + [f"shots must list 1 to {LIMITS['maxShots']} shots."]
    starts = [s.get("start") if isinstance(s, dict) else None for s in shots]
    if not all(ck.is_int(v) for v in starts):
        return errors + ["Every shot needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first shot must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Shot starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    steps = data.get("steps")
    if not isinstance(steps, list) or not LIMITS["minSteps"] <= len(steps) <= LIMITS["maxSteps"]:
        return errors + [f"steps must list {LIMITS['minSteps']} to {LIMITS['maxSteps']} steps."]
    step_starts = []
    for i, st in enumerate(steps):
        where = f"Step {i + 1}"
        if not isinstance(st, dict) or not ck.is_int(st.get("start")):
            return errors + [f"{where} needs a whole-number start frame."]
        step_starts.append(st["start"])
        header = st.get("header")
        if not isinstance(header, str) or not header.strip() or len(header) > LIMITS["headerChars"]:
            err(f"{where}: header must be text of 1 to {LIMITS['headerChars']} characters.")
        if "tag" in st and (not isinstance(st["tag"], str) or len(st["tag"]) > LIMITS["tagChars"]):
            err(f"{where}: tag must be text of at most {LIMITS['tagChars']} characters.")
        if st.get("ground") not in extra["grounds"]:
            err(f"{where}: ground must be one of {', '.join(extra['grounds'])}.")
        if st["start"] not in starts:
            err(f"{where} starts at frame {st['start']}, where no shot starts: a step is a cut, so start a "
                "shot there too.")
        elif not on_word(st["start"]):
            err(f"{where} starts at frame {st['start']}, which is not on a word.")
    if any(b <= a for a, b in zip(step_starts, step_starts[1:])):
        return errors + ["Step starts must increase."]
    if step_starts[0] < LIMITS["minIntroSeconds"] * fps:
        err(f"Step 1 starts at frame {step_starts[0]}: the video opens on the title card for at least "
            f"{LIMITS['minIntroSeconds']} s (the first sentence or two, on why the task matters).")
    summary = data.get("summary")
    if summary is not None:
        if not ck.is_int(summary) or summary <= step_starts[-1] or summary >= total:
            err("summary must be a whole frame after the last step's start and inside the video.")
            summary = None
        elif summary not in starts:
            err(f"The summary starts at frame {summary}, where no shot starts; start a shot there too.")
        elif total - summary < LIMITS["minSummarySeconds"] * fps:
            err(f"The summary lasts {total - summary} frames; it needs at least {LIMITS['minSummarySeconds']} s.")
    for i, a in enumerate(step_starts):
        b = step_starts[i + 1] if i + 1 < len(step_starts) else (summary if summary is not None else total)
        if b - a < LIMITS["minStepSeconds"] * fps:
            err(f"Step {i + 1} lasts {b - a} frames; a step needs at least {LIMITS['minStepSeconds']} s.")

    runs = ck.echo_runs(words, LIMITS["labelEchoWords"])
    changes = set(starts) | set(step_starts) | ({summary} if summary is not None else set())
    for i, (a, b) in enumerate(zip(starts, ends)):
        if i and not on_word(a):
            err(f"Shot {i + 1} cuts at frame {a}, which is not on a word: start a shot within {SNAP_FRAMES} frames "
                "of a word's start.")
        if b - a < LIMITS["minShotSeconds"] * fps:
            err(f"Shot {i + 1} lasts {b - a} frames; a shot needs at least {LIMITS['minShotSeconds']} s.")
        w = window_at(a, quiet) if a else None
        if w:
            err(f"Shot {i + 1} cuts at frame {a}, inside an insert ({window_text(w)}), where the stage is hidden; "
                f"cut at {w[1]} or before {w[0]}.")
        kind = "summary" if summary is not None and a >= summary else "intro" if a < step_starts[0] else "step"
        _check_shot(shots[i], i, a, b, kind, catalog, boxes, extra, on_word, runs, changes, quiet, err)

    marks = sorted(c for c in changes if 0 <= c < total) + [total]
    prev = 0
    for c in marks:
        for a, b in uncovered(prev, c, quiet):
            if b - a > still:
                err(f"Nothing changes from frame {a} to {b} ({(b - a) / fps:.1f} s); the longest still stretch "
                    f"allowed is {LIMITS['maxStillSeconds']} s. Add a pose, an object, a press or a cut.")
        prev = c
    return errors


def _check_shot(shot, i, start, end, kind, catalog, boxes, extra, on_word, runs, changes, quiet, err) -> None:
    where = f"Shot {i + 1}"
    if not isinstance(shot, dict):
        err(f"{where} must be an object.")
        return
    side = shot.get("presenter", "left")
    if side not in SIDES:
        err(f"{where}: presenter must be one of {', '.join(SIDES)}.")
        return
    if kind == "summary" and side != "right":
        # the renderer always stands the presenter on the right of the summary card
        if "presenter" in shot:
            err(f"{where} is the summary card, which lists the steps on the left: the presenter stands on the "
                "right (leave presenter out, or set it to right).")
        side = "right"
    events = shot.get("events")
    if not isinstance(events, list) or len(events) > LIMITS["maxEventsPerShot"]:
        err(f"{where}: events must be a list of at most {LIMITS['maxEventsPerShot']}.")
        return
    last = end - TIMING["endMargin"]
    frames = [e.get("frame") if isinstance(e, dict) else None for e in events]
    if not all(ck.is_int(f) for f in frames):
        err(f"{where}: every event needs a whole-number frame.")
        return
    if any(b < a for a, b in zip(frames, frames[1:])):
        err(f"{where}: list the events in frame order.")
    top = GEOMETRY["introStageTop"] if kind == "intro" else GEOMETRY["stageTop"]
    objects: dict[str, dict] = {}
    elements: list[tuple[str, tuple]] = []   # (name, box) of labels and insets
    last_pose = None
    last_press = None
    count = 0
    for e, f in zip(events, frames):
        t = e.get("type")
        at = f"{where}, the {t or 'event'} at frame {f}"
        if t not in EVENT_TYPES:
            err(f"{at}: type must be one of {', '.join(EVENT_TYPES)}.")
            continue
        if f < start or f > last:
            err(f"{at}: it must start inside its shot, from frame {start} to {last} (an event closer to the "
                "cut is cut before it is seen).")
            continue
        w = window_at(f, quiet)
        if w:
            err(f"{at} starts inside an insert ({window_text(w)}), where the stage is hidden; move it to a word "
                f"at {w[1]} or later, or before {w[0]}.")
        if kind == "summary" and t != "pose":
            err(f"{at}: the summary card lists the steps by itself; only the presenter's poses go in its shot.")
            continue
        changes.add(f)
        if t == "pose":
            if side == "none":
                err(f"{at}: this shot has no presenter (presenter is none), so it has no poses.")
                continue
            if e.get("pose") not in extra["poses"]:
                err(f"{at}: pose must be one of {', '.join(extra['poses'])}.")
            elif kind == "summary" and e["pose"] not in SUMMARY_POSES:
                err(f"{at}: on the summary card the presenter keeps his arms clear of the step list: pose must be "
                    f"one of {', '.join(SUMMARY_POSES)}.")
            if e.get("face") not in extra["faces"]:
                err(f"{at}: face must be one of {', '.join(extra['faces'])}.")
            if not on_word(f):
                err(f"{at}: a pose changes on a word; move it within {SNAP_FRAMES} frames of a word's start.")
            if last_pose is not None and f - last_pose < TIMING["minPoseGap"]:
                err(f"{at}: it comes {f - last_pose} frames after the last pose; poses closer than "
                    f"{TIMING['minPoseGap']} frames read as a twitch.")
            last_pose = f
            target = e.get("at")
            if target is not None:
                if not isinstance(target, str):
                    err(f"{at}: at must name an object on stage (text).")
                elif e.get("pose") not in AIM_POSES:
                    err(f"{at}: at aims the hand of a {' or '.join(AIM_POSES)} pose; leave it out of a "
                        f"{e.get('pose')!r} pose.")
                elif target not in objects:
                    err(f"{at}: at names {target!r}, which is not on stage yet in this shot.")
        elif t == "object":
            obj = e.get("object")
            if not isinstance(obj, str) or obj not in catalog:
                err(f"{at}: object must be from the library or the video's customProps.")
                continue
            oid = e.get("id", obj)
            if not isinstance(oid, str) or not ck.ID.match(oid) or oid in objects:
                err(f"{at}: id {oid!r} must be lowercase letters, digits or _, and unique in the shot (give a "
                    "second copy of an object its own id).")
                continue
            if not (ck.is_num(e.get("x")) and ck.is_num(e.get("y")) and 0 <= e["x"] <= 1 and 0 <= e["y"] <= 1):
                err(f"{at}: x and y must be numbers from 0 to 1 (the object's centre).")
                continue
            sc = e.get("scale", 1)
            if not ck.is_num(sc) or not OBJECT_SCALE[0] <= sc <= OBJECT_SCALE[1]:
                err(f"{at}: scale must be from {OBJECT_SCALE[0]} to {OBJECT_SCALE[1]}.")
                continue
            if "enter" in e and e["enter"] not in extra["entrances"]:
                err(f"{at}: enter must be one of {', '.join(extra['entrances'])}.")
            limit = catalog[obj]["text"]
            text = e.get("text")
            if text is not None:
                if limit == 0:
                    err(f"{at}: the {obj} object has no text slot.")
                elif not isinstance(text, str) or len(text) > limit:
                    err(f"{at}: the {obj}'s text must be at most {limit} characters.")
            box = object_box(obj, e["x"], e["y"], sc, boxes)
            objects[oid] = {**e, "box": box, "scale": sc}
            count += 1
            if not (box[0] >= GEOMETRY["safeLeft"] and box[2] <= GEOMETRY["safeRight"]
                    and box[1] >= top and box[3] <= GEOMETRY["floorY"] + 20):
                err(f"{at}: the {oid} object reaches outside the stage (from y {top} down to the floor, inside "
                    "the side margins); move or shrink it.")
            if side != "none" and ck.overlap(box, presenter_box(side), GEOMETRY["overlapTolerance"]):
                err(f"{at}: the {oid} object overlaps the presenter on the {side}; move it to the other side "
                    "of the stage.")
        elif t in ("act", "press", "check", "cross", "inset"):
            target = objects.get(e.get("target")) if isinstance(e.get("target"), str) else None
            if not target:
                err(f"{at}: target must name an object already on stage in this shot.")
                continue
            if f < target["frame"] + TIMING["objectIn"]:
                err(f"{at}: it starts once its object has landed, {TIMING['objectIn']} frames after it appears.")
            if t == "act":
                acts = catalog[target["object"]]["acts"]
                if e.get("act") not in acts:
                    err(f"{at}: the {target['object']} object's acts are {', '.join(acts) or 'none'}.")
            elif t == "press":
                if not on_word(f):
                    err(f"{at}: a press lands on a word; move it within {SNAP_FRAMES} frames of a word's start.")
                if f - TIMING["pressLead"] < start:
                    err(f"{at}: the hand pulls back {TIMING['pressLead']} frames before it presses, so a press "
                        f"starts at frame {start + TIMING['pressLead']} of its shot or later.")
                if last_press is not None and f - last_press < TIMING["minPressGap"]:
                    err(f"{at}: it comes {f - last_press} frames after the last press; presses need "
                        f"{TIMING['minPressGap']} frames between them.")
                last_press = f
            elif t == "inset":
                text = e.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["insetChars"]:
                    err(f"{at}: text must be a short number or word, 1 to {LIMITS['insetChars']} characters.")
                if not (ck.is_num(e.get("x")) and ck.is_num(e.get("y"))):
                    err(f"{at}: x and y must be numbers from 0 to 1 (the inset's centre).")
                    continue
                box = inset_box(e["x"], e["y"])
                elements.append((f"the inset {text!r}", box))
                count += 1
                _check_element(at, box, top, side, objects, err)
        elif t == "label":
            text = e.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["labelChars"]:
                err(f"{at}: text must be 1 to {LIMITS['labelChars']} characters; name the thing, the captions carry "
                    "the sentence.")
                continue
            if ck.echoes(text, runs, LIMITS["labelEchoWords"]):
                err(f"{at}: the label repeats the narration word for word; the captions already show those words, "
                    "so name the thing instead.")
            if not (ck.is_num(e.get("x")) and ck.is_num(e.get("y"))):
                err(f"{at}: x and y must be numbers from 0 to 1 (the label's centre).")
                continue
            box = label_box(text, e["x"], e["y"])
            elements.append((f"the label {text!r}", box))
            count += 1
            _check_element(at, box, top, side, objects, err)
    if count > LIMITS["maxElementsPerShot"]:
        err(f"{where} puts {count} objects, labels and insets on stage; at most {LIMITS['maxElementsPerShot']} "
            "fit. Cut to a new shot to make room.")
    for k, (name, box) in enumerate(elements):
        for name2, box2 in elements[k + 1:]:
            if ck.overlap(box, box2, GEOMETRY["overlapTolerance"]):
                err(f"{where}: {name} and {name2} overlap.")


def _check_element(at, box, top, side, objects, err) -> None:
    """A label or an inset: inside the stage, clear of the presenter and of every object on stage."""
    if not (box[0] >= GEOMETRY["safeLeft"] and box[2] <= GEOMETRY["safeRight"] and box[1] >= top
            and box[3] <= GEOMETRY["floorY"] + 20):
        err(f"{at}: it reaches outside the stage; move it.")
    if side != "none" and ck.overlap(box, presenter_box(side), GEOMETRY["overlapTolerance"]):
        err(f"{at}: it overlaps the presenter; move it.")
    for oid, o in objects.items():
        if ck.overlap(box, o["box"], GEOMETRY["overlapTolerance"]):
            err(f"{at}: it overlaps the {oid} object; move it clear (an inset joins its object by a line).")


# ── what the audit and the picture checks read ────────────────────────────────

def _data(config: dict) -> dict:
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_scene(scenes[0]):
        return {}
    d = (scenes[0].get("props") or {}).get(PROPS_KEY)
    return d if isinstance(d, dict) else {}


def audit_windows(config: dict) -> list[tuple[int, int]]:
    """(first, end) of every shot for the text-layout audit, sampled once its
    header and pops have settled. [] when the config is not one."""
    data = _data(config)
    starts = [s.get("start") for s in data.get("shots") or [] if isinstance(s, dict) and ck.is_int(s.get("start"))]
    total = config.get("totalFrames") if ck.is_int(config.get("totalFrames")) else 0
    windows = [(a, b) for a, b in zip(starts, starts[1:] + [total]) if b > a]
    return ck.sample_windows(windows, TIMING["headerIn"] + 2, TIMING["endMargin"])


def change_frames(data: dict) -> list[int]:
    """Every frame at which something visible starts changing."""
    frames = [s.get("start") for s in data.get("shots") or []] + [s.get("start") for s in data.get("steps") or []]
    frames.append(data.get("summary"))
    for s in data.get("shots") or []:
        for e in s.get("events") or []:
            if e.get("type") not in SUBTLE:
                frames.append(e.get("frame"))
    return [f for f in frames if ck.is_int(f)]


def sample_text(data: dict, prop_id) -> str:
    """The text a video gives one of its own props first, for render_style_props to draw it with."""
    for shot in data.get("shots") or []:
        for e in shot.get("events") or [] if isinstance(shot, dict) else []:
            if isinstance(e, dict) and e.get("type") == "object" and e.get("object") == prop_id \
                    and isinstance(e.get("text"), str):
                return e["text"]
    return ""


def first_frame_problem(data: dict) -> str | None:
    shots = data.get("shots") or []
    events = shots[0].get("events") or [] if shots else []
    if not any(e.get("type") == "object" and ck.is_int(e.get("frame")) and e["frame"] <= 3 for e in events):
        return ("the title card has no object on stage until after frame 3, so the video opens on the title "
                "alone. Bring in the object the video is about at frame 0")
    return None
