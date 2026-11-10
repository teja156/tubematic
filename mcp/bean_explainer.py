"""Bean Explainer (TMDEV-198): the checks a Bean Explainer scene-config must
pass before it is written, so an unattended agent cannot ship a mistimed,
crowded or still video.

A Bean Explainer video is one installed `BeanExplainer` scene spanning every
frame. The agent writes no code for it: `props.beanExplainer` holds sections
(header, colour, badge), shots (cuts) and events timed to the narration's
word frames: the bean's poses and faces, props from a fixed library,
labels, marks, impacts, red X strikes and arrows. The renderer's side of this
contract is renderer/remotion/src/scenes/installed/beanExplainer/contract.ts.

Keep in sync: LIMITS, TIMING, GEOMETRY, the catalogues, PROPS, wrap_label
and the box helpers mirror contract.ts. mcp/tests/test_bean_explainer.py
reads the TypeScript constants and the style pack, and both sides run the
shared cases in tests/fixtures/bean_explainer_contract.json, so a drift fails
a test instead of a render.

Free of the database and of I/O: the caller passes the style, the config,
the narration's word start frames and words, and the pack's `extra` block.
"""
from __future__ import annotations

import re

SCENE_SRC = "BeanExplainer"
PROPS_KEY = "beanExplainer"
STYLE_ID = "bean_explainer"

W, H = 1080, 1920
LIMITS = {
    "maxSections": 12,
    "maxShots": 40,
    "maxEventsPerShot": 24,
    "maxElementsPerShot": 6,
    "headerChars": 18,
    "titleChars": 40,
    "labelLineChars": 22,
    "labelLines": 2,
    "maxStillSeconds": 3,
    "minSectionSeconds": 2,
    "minShotSeconds": 1.5,
    "labelEchoWords": 4,
}
TIMING = {
    "carousel": 30,
    "minPoseGap": 8,
    "poseSnap": 2,
    "propIn": 10,
    "drawOn": 15,
    "minImpactGap": 15,
    "endMargin": 6,
    "actFrames": 60,
    "settle": 30,
}
GEOMETRY = {
    "safeLeft": 60,
    "safeRight": 1020,
    "stageTop": 460,
    "floorY": 1300,
    "beanHalfWidth": 150,
    "beanHeight": 780,
    "beanScale": 0.95,
    "beanScaleTwo": 0.8,
    "labelFontPx": 50,
    "labelCharPx": 24,
    "labelLinePx": 60,
    "overlapTolerance": 6,
}
EVENT_TYPES = ("pose", "prop", "act", "label", "mark", "impact", "strike", "arrow")
CAST_IDS = ("narrator", "other")
# The poses whose right arm reaches for the thing `at` names (bean.tsx's blendedPose).
AIM_POSES = ("point", "present", "lean")
LABEL_TONES = ("ink", "red")
PROP_SCALE = (0.5, 1.4)
# A prop the agent draws for one video (contract.ts's CUSTOM).
CUSTOM = {"maxProps": 8, "minSide": 60, "maxSide": 700, "maxText": 40, "maxActs": 4}
_CUSTOM_ACT = re.compile(r"^[a-z]{2,16}$")
_CUSTOM_FILE = re.compile(r"^prop-[a-z0-9-]{1,40}$")
# What a custom prop's source may not contain, and why: each one either cost a
# render many times over on the CPU renderer (TMDEV-196's measurements), makes
# frames differ between renders, or reaches outside the drawing.
FORBIDDEN_SOURCE = (
    (re.compile(r"\bfilter\b|<fe[A-Z]"), "an SVG filter (blur, shadow, turbulence): it multiplies the render time"),
    (re.compile(r"(?i)(linear|radial)Gradient"), "a gradient: it multiplies the render time; use flat fills"),
    (re.compile(r"<pattern\b"), "an SVG pattern: it multiplies the render time; use flat fills"),
    (re.compile(r"strokeDasharray|stroke-dasharray"), "a dashed stroke: it multiplies the render time"),
    (re.compile(r"Math\.random|Date\.now|new Date\b"), "randomness or the clock: every render must draw the same frames"),
    (re.compile(r"<image\b|<img\b|<foreignObject\b|dangerouslySetInnerHTML|\bfetch\(|\bimport\("),
     "an image, embedded HTML or a fetch: a prop is drawn from shapes only"),
)
_IMPORT = re.compile(r"""^\s*import\b[^;]*?from\s+["']([^"']+)["']""", re.M)
_ALLOWED_IMPORT = re.compile(r"^(react|remotion|\.\./\.\./installed/beanExplainer/(props/common|bean|contract))$")
# Prop boxes at scale 1, in frame pixels: (width, height), every pixel the
# drawing can reach (contract.ts says how they are measured). The text limits
# and acts come from the pack; the boxes are geometry only this module needs.
PROP_BOXES = {
    "phone": (260, 440), "browser": (640, 150), "laptop": (460, 340), "sign": (400, 350),
    "document": (330, 410), "note": (300, 310), "speech": (460, 270), "thought": (450, 300),
    "pricetag": (340, 210), "calendar": (320, 340), "envelope": (360, 260),
    "coins": (280, 250), "banknote": (400, 210), "wallet": (340, 270), "piggybank": (390, 310),
    "creditcard": (400, 260), "chartup": (400, 340), "chartdown": (400, 340),
    "brain": (400, 330), "heart": (300, 260), "stomach": (260, 340), "pill": (270, 180),
    "coffee": (310, 390), "water": (210, 340), "bed": (500, 370), "dumbbell": (410, 150),
    "apple": (260, 250),
    "lock": (260, 430), "key": (330, 220), "server": (320, 400), "wifi": (350, 260),
    "bug": (290, 300), "shield": (280, 340), "cursor": (270, 350),
    "clock": (360, 340), "hourglass": (240, 360), "gears": (360, 280), "bulb": (340, 390),
    "cloud": (410, 330), "trophy": (360, 370), "bomb": (330, 340), "magnifier": (260, 350),
}

# A cut (a section or shot start) lands on a word: within this many frames of one.
SNAP_FRAMES = 2
_ID = re.compile(r"^[a-z0-9_]{1,24}$")
MAX_ERRORS = 12


def is_bean_scene(scene) -> bool:
    """Any scene naming BeanExplainer, whatever its type: the use rule must catch
    a mistyped one too."""
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def wrap_label(text: str) -> list[str]:
    """Greedy word wrap at LIMITS['labelLineChars']; same rule as contract.ts."""
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= LIMITS["labelLineChars"]:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def prop_box(prop: str, x: float, y: float, scale: float = 1, boxes: dict | None = None) -> tuple[float, float, float, float]:
    w, h = (boxes or PROP_BOXES)[prop]
    cx, cy, hw, hh = x * W, y * H, w * scale / 2, h * scale / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def label_box(text: str, x: float, y: float) -> tuple[float, float, float, float]:
    lines = wrap_label(text) or [""]
    width = max(len(ln) for ln in lines) * GEOMETRY["labelCharPx"] or GEOMETRY["labelCharPx"]
    height = len(lines) * GEOMETRY["labelLinePx"]
    cx, cy = x * W, y * H
    return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def bean_scale(beans_on_stage: int) -> float:
    return GEOMETRY["beanScaleTwo"] if beans_on_stage > 1 else GEOMETRY["beanScale"]


def bean_box(x: float, scale: float) -> tuple[float, float, float, float]:
    cx = x * W
    return (cx - GEOMETRY["beanHalfWidth"] * scale, GEOMETRY["floorY"] - GEOMETRY["beanHeight"] * scale,
            cx + GEOMETRY["beanHalfWidth"] * scale, GEOMETRY["floorY"])


def _overlap(a, b) -> bool:
    t = GEOMETRY["overlapTolerance"]
    return a[0] < b[2] - t and b[0] < a[2] - t and a[1] < b[3] - t and b[1] < a[3] - t


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Bean Explainer video is exactly the one
    BeanExplainer scene, and no other video uses it. "" when the scenes obey it.
    The renderer loads the scene only as a generated-type entry from the
    installed source; any other entry would render nothing."""
    uses = [s for s in scenes or [] if is_bean_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The BeanExplainer scene draws a whole Bean Explainer video and is used only when "
                    "the video's visual_style is bean_explainer (chosen at the topic). Build this "
                    "video's scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Bean Explainer video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"BeanExplainer\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"beanExplainer\": {...}}}. Put every beat in its shots.")
    return ""


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None) -> tuple[list[str], dict, dict]:
    """Problems with config's customProps, and the prop catalogue and boxes
    with them added to the library's. `sources` maps each src to its file's
    text, or is None to skip the source checks (no files to read)."""
    errs: list[str] = []
    catalog, boxes = dict(library), dict(PROP_BOXES)
    if custom is None:
        return errs, catalog, boxes
    if not isinstance(custom, list) or len(custom) > CUSTOM["maxProps"]:
        return [f"customProps must be a list of at most {CUSTOM['maxProps']} props."], catalog, boxes
    for i, c in enumerate(custom):
        where = f"customProps {i + 1}"
        if not isinstance(c, dict):
            errs.append(f"{where} must be an object.")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not _ID.match(cid) or cid in catalog:
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
        w, h = c.get("w"), c.get("h")
        if not (_int(w) and _int(h) and CUSTOM["minSide"] <= w <= CUSTOM["maxSide"]
                and CUSTOM["minSide"] <= h <= CUSTOM["maxSide"]):
            errs.append(f"{where} ({cid}): w and h are its box at scale 1, whole pixels from {CUSTOM['minSide']} "
                        f"to {CUSTOM['maxSide']}.")
            continue
        text = c.get("text", 0)
        if not _int(text) or not 0 <= text <= CUSTOM["maxText"]:
            errs.append(f"{where} ({cid}): text is the most characters its text slot takes, 0 to {CUSTOM['maxText']}.")
            continue
        acts = c.get("acts", [])
        if (not isinstance(acts, list) or len(acts) > CUSTOM["maxActs"]
                or not all(isinstance(a, str) and _CUSTOM_ACT.match(a) for a in acts)):
            errs.append(f"{where} ({cid}): acts is a list of at most {CUSTOM['maxActs']} lowercase names.")
            continue
        if sources is not None:
            body = sources.get(src)
            if body is None:
                errs.append(f"{where} ({cid}): there is no {src}.tsx; write it with write_scene_file first.")
                continue
            for pattern, why in FORBIDDEN_SOURCE:
                if pattern.search(body):
                    errs.append(f"{where} ({cid}): the drawing uses {why}.")
            bad = [m for m in _IMPORT.findall(body) if not _ALLOWED_IMPORT.match(m)]
            if bad:
                errs.append(f"{where} ({cid}): it imports {', '.join(sorted(set(bad)))}; a prop imports only react, "
                            "remotion and ../../installed/beanExplainer/props/common (or bean, contract).")
            if not re.search(r"export\s+default\b", body):
                errs.append(f"{where} ({cid}): the file must default-export the drawing component.")
        catalog[cid] = {"text": text, "acts": acts}
        boxes[cid] = (w, h)
    return errs, catalog, boxes


def check(config: dict, fps: int, word_starts: list[int], words: list[str], extra: dict,
          video_id: str = "", sources: dict | None = None) -> list[str]:
    """Every problem with a Bean Explainer config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block; `words` is the narration's text, word by word. A config's
    customProps join the library for this video; `sources` maps their src to
    the file's text (None skips the source checks)."""
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
    data = (scene.get("props") or {}).get(PROPS_KEY)
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the sections, shots and cast."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    custom_errs, catalog, boxes = custom_prop_errors(data.get("customProps"), video_id, extra["props"], sources)
    for e in custom_errs:
        err(e)
    extra = {**extra, "props": catalog, "boxes": boxes}

    still = round(LIMITS["maxStillSeconds"] * fps)
    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return not snaps or any(abs(frame - w) <= SNAP_FRAMES for w in snaps)

    # ── the whole video ──
    if "field" in data and data["field"] not in extra["fields"]:
        err(f"field must be one of {', '.join(extra['fields'])}.")
    if "title" in data and (not isinstance(data["title"], str) or len(data["title"]) > LIMITS["titleChars"]):
        err(f"title must be text of at most {LIMITS['titleChars']} characters.")
    if "list" in data and not isinstance(data["list"], bool):
        err("list must be true or false.")
    is_list = data.get("list") is True

    cast = data.get("cast")
    cast_ids: list[str] = []
    if not isinstance(cast, list) or not 1 <= len(cast) <= 2:
        err("cast must list one or two beans: the narrator, and optionally one other.")
        cast = []
    tints = []
    for i, c in enumerate(cast):
        if not isinstance(c, dict) or c.get("id") not in CAST_IDS:
            err(f"cast {i + 1}: id must be one of {', '.join(CAST_IDS)}.")
            continue
        cast_ids.append(c["id"])
        if c.get("accessory", "none") not in extra["accessories"]:
            err(f"cast {c['id']}: accessory must be one of {', '.join(extra['accessories'])}.")
        if c.get("tint", "cream") not in extra["tints"]:
            err(f"cast {c['id']}: tint must be one of {', '.join(extra['tints'])}.")
        tints.append(c.get("tint", "cream"))
    if cast_ids and cast_ids[0] != "narrator":
        err("The first cast member must be the narrator.")
    if len(set(cast_ids)) != len(cast_ids):
        err("Each cast id may appear once.")
    if len(tints) == 2 and tints[0] == tints[1]:
        err("The two beans need different tints, or the viewer cannot tell them apart.")

    shots = data.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= LIMITS["maxShots"]:
        return errors + [f"shots must list 1 to {LIMITS['maxShots']} shots."]
    starts = [s.get("start") if isinstance(s, dict) else None for s in shots]
    if not all(_int(v) for v in starts):
        return errors + ["Every shot needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first shot must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Shot starts must increase and stay inside the video."]
    ends = starts[1:] + [total]
    for i, (a, b) in enumerate(zip(starts, ends)):
        if i and not on_word(a):
            err(f"Shot {i + 1} cuts at frame {a}, which is not on a word: start a shot within "
                f"{SNAP_FRAMES} frames of a word's start.")
        if b - a < LIMITS["minShotSeconds"] * fps:
            err(f"Shot {i + 1} lasts {b - a} frames; a shot needs at least {LIMITS['minShotSeconds']} s.")

    sections = data.get("sections")
    if not isinstance(sections, list) or len(sections) > LIMITS["maxSections"]:
        err(f"sections must be a list of at most {LIMITS['maxSections']}.")
        sections = []
    if is_list and len(sections) < 2:
        err("list is true, so sections must name at least two items: the carousel runs between sections.")
    content_start: dict[int, int] = {}   # shot index -> first frame its events may use
    sec_starts = []
    for i, sec in enumerate(sections):
        where = f"Section {i + 1}"
        if not isinstance(sec, dict) or not _int(sec.get("start")):
            err(f"{where} needs a whole-number start frame.")
            continue
        s0 = sec["start"]
        sec_starts.append(s0)
        header = sec.get("header")
        if not isinstance(header, str) or not header.strip() or len(header) > LIMITS["headerChars"]:
            err(f"{where}: header must be text of 1 to {LIMITS['headerChars']} characters.")
        if sec.get("color") not in extra["section_colors"]:
            err(f"{where}: color must be one of {', '.join(extra['section_colors'])}.")
        if sec.get("badge") not in extra["props"]:
            err(f"{where}: badge must be a prop from the library or the video's customProps.")
        if s0 not in starts:
            err(f"{where} starts at frame {s0}, where no shot starts: a section change is a cut, "
                "so start a shot there too.")
        else:
            content_start[starts.index(s0)] = s0 + (TIMING["carousel"] if is_list and i > 0 else 0)
    if any(b <= a for a, b in zip(sec_starts, sec_starts[1:])):
        err("Section starts must increase.")
    for a, b in zip(sec_starts, sec_starts[1:] + [total]):
        if b - a < LIMITS["minSectionSeconds"] * fps:
            err(f"The section at frame {a} lasts {b - a} frames; a section needs at least "
                f"{LIMITS['minSectionSeconds']} s.")

    narration = [_norm(w) for w in words]
    echo = LIMITS["labelEchoWords"]
    runs = {tuple(narration[i:i + echo]) for i in range(max(0, len(narration) - echo + 1))}

    changes = set(starts) | set(sec_starts)
    for i, shot in enumerate(shots):
        _check_shot(shot, i, starts[i], ends[i], content_start.get(i, starts[i]), cast_ids, extra,
                    on_word, runs, changes, err)
    if is_list:
        changes |= {s0 + TIMING["carousel"] for s0 in sec_starts[1:]}
    marks = sorted(c for c in changes if 0 <= c < total) + [total]
    prev = 0
    for c in marks:
        if c - prev > still:
            err(f"Nothing changes from frame {prev} to {c} ({(c - prev) / fps:.1f} s); the longest still "
                f"stretch allowed is {LIMITS['maxStillSeconds']} s. Add a pose, a prop, a label or a cut.")
        prev = c
    return errors


def _check_shot(shot, i, start, end, content, cast_ids, extra, on_word, runs, changes, err) -> None:
    where = f"Shot {i + 1}"
    events = shot.get("events") if isinstance(shot, dict) else None
    if not isinstance(events, list) or len(events) > LIMITS["maxEventsPerShot"]:
        err(f"{where}: events must be a list of at most {LIMITS['maxEventsPerShot']}.")
        return
    last = end - TIMING["endMargin"]
    frames = [e.get("frame") if isinstance(e, dict) else None for e in events]
    if not all(_int(f) for f in frames):
        err(f"{where}: every event needs a whole-number frame.")
        return
    if any(b < a for a, b in zip(frames, frames[1:])):
        err(f"{where}: list the events in frame order.")
    props: dict[str, dict] = {}     # instance id -> prop event
    labels: list[tuple] = []
    bean_x: dict[str, list[tuple[int, float]]] = {}   # who -> [(frame, x)] as the bean moves
    bean_first: dict[str, int] = {}
    last_pose: dict[str, int] = {}
    last_impact = None
    elements = 0
    for e, f in zip(events, frames):
        t = e.get("type")
        at = f"{where}, the {t or 'event'} at frame {f}"
        if t not in EVENT_TYPES:
            err(f"{at}: type must be one of {', '.join(EVENT_TYPES)}.")
            continue
        if f < content:
            reason = "after the badge carousel" if content > start else "inside its shot"
            err(f"{at}: it starts before frame {content}; events in this shot must start {reason}.")
            continue
        if f > last:
            err(f"{at}: it is too close to the cut at frame {end} to be seen (frame {last} is the last).")
            continue
        changes.add(f)
        if t == "pose":
            who = e.get("who")
            if who not in cast_ids:
                err(f"{at}: who must be a cast id ({', '.join(cast_ids)}).")
                continue
            for key, allowed in (("pose", extra["poses"]), ("face", extra["faces"])):
                if e.get(key) not in allowed:
                    err(f"{at}: {key} must be one of {', '.join(allowed)}.")
            if "look" in e and e["look"] not in extra["looks"]:
                err(f"{at}: look must be one of {', '.join(extra['looks'])}.")
            if not on_word(f):
                err(f"{at}: a pose swaps on a word; move it within {SNAP_FRAMES} frames of a word's start.")
            if who in last_pose and f - last_pose[who] < TIMING["minPoseGap"]:
                err(f"{at}: it comes {f - last_pose[who]} frames after this bean's last pose; swaps closer "
                    f"than {TIMING['minPoseGap']} frames read as a twitch.")
            last_pose[who] = f
            if "x" in e:
                if not _num(e["x"]) or not 0.1 <= e["x"] <= 0.9:
                    err(f"{at}: x must be a number from 0.1 to 0.9.")
                else:
                    bean_x.setdefault(who, []).append((f, e["x"]))
            elif who not in bean_first:
                err(f"{at}: the bean's first pose in a shot needs x (where it stands, 0.1 to 0.9).")
            bean_first.setdefault(who, f)
            target = e.get("at")
            if target is not None and e.get("pose") not in AIM_POSES:
                err(f"{at}: at aims the arm of a {', '.join(AIM_POSES)} pose; the {e.get('pose')!r} pose "
                    "does not reach for anything, so leave at out or change the pose.")
            elif target is not None and target not in props and target not in bean_first:
                err(f"{at}: at names {target!r}, which is not on stage yet.")
        elif t == "prop":
            prop = e.get("prop")
            if prop not in extra["props"]:
                err(f"{at}: prop must be from the library or the video's customProps.")
                continue
            pid = e.get("id", prop)
            if not isinstance(pid, str) or not _ID.match(pid) or pid in props:
                err(f"{at}: id {pid!r} must be lowercase letters, digits or _, and unique in the shot "
                    "(give a second copy of a prop its own id).")
                continue
            if not (_num(e.get("x")) and _num(e.get("y")) and 0 <= e["x"] <= 1 and 0 <= e["y"] <= 1):
                err(f"{at}: x and y must be numbers from 0 to 1 (the prop's centre).")
                continue
            sc = e.get("scale", 1)
            if not _num(sc) or not PROP_SCALE[0] <= sc <= PROP_SCALE[1]:
                err(f"{at}: scale must be from {PROP_SCALE[0]} to {PROP_SCALE[1]}.")
                continue
            if "enter" in e and e["enter"] not in extra["entrances"]:
                err(f"{at}: enter must be one of {', '.join(extra['entrances'])}.")
            limit = extra["props"][prop]["text"]
            text = e.get("text")
            if text is not None:
                if limit == 0:
                    err(f"{at}: the {prop} prop has no text slot.")
                elif not isinstance(text, str) or len(text) > limit:
                    err(f"{at}: the {prop}'s text must be at most {limit} characters.")
            props[pid] = {**e, "box": prop_box(prop, e["x"], e["y"], sc, extra.get("boxes"))}
            elements += 1
        elif t == "act":
            target = props.get(e.get("target"))
            if not target:
                err(f"{at}: target must name a prop already on stage in this shot.")
                continue
            acts = extra["props"][target["prop"]]["acts"]
            if e.get("act") not in acts:
                err(f"{at}: the {target['prop']} prop's acts are {', '.join(acts) or 'none'}.")
            elif f < target["frame"] + TIMING["propIn"]:
                err(f"{at}: an act starts once its prop has landed, {TIMING['propIn']} frames after it appears.")
        elif t == "label":
            text = e.get("text")
            if not isinstance(text, str) or not text.strip():
                err(f"{at}: text must be non-empty.")
                continue
            lines = wrap_label(text)
            if len(lines) > LIMITS["labelLines"] or any(len(ln) > LIMITS["labelLineChars"] for ln in lines):
                err(f"{at}: a label is at most {LIMITS['labelLines']} lines of {LIMITS['labelLineChars']} "
                    "characters; name the thing, the captions carry the sentence.")
            norm = [_norm(w) for w in text.split()]
            echo = LIMITS["labelEchoWords"]
            if any(tuple(norm[k:k + echo]) in runs for k in range(max(0, len(norm) - echo + 1))):
                err(f"{at}: the label repeats the narration word for word; the captions already show "
                    "those words, so name the thing instead.")
            if "tone" in e and e["tone"] not in LABEL_TONES:
                err(f"{at}: tone must be one of {', '.join(LABEL_TONES)}.")
            if not (_num(e.get("x")) and _num(e.get("y"))):
                err(f"{at}: x and y must be numbers from 0 to 1 (the label's centre).")
                continue
            labels.append((f, label_box(text, e["x"], e["y"]), text))
            elements += 1
        elif t == "mark":
            if e.get("who") not in bean_first:
                err(f"{at}: who must be a bean already posed in this shot.")
            if e.get("mark") not in extra["marks"]:
                err(f"{at}: mark must be one of {', '.join(extra['marks'])}.")
        elif t == "impact":
            if "strength" in e and e["strength"] not in (1, 2, 3):
                err(f"{at}: strength must be 1, 2 or 3.")
            if last_impact is not None and f - last_impact < TIMING["minImpactGap"]:
                err(f"{at}: two impacts within {TIMING['minImpactGap']} frames blur into one shake.")
            last_impact = f
        elif t == "strike":
            if e.get("target") not in props:
                err(f"{at}: target must name a prop already on stage in this shot.")
        elif t == "arrow":
            for end_key in ("from", "to"):
                if e.get(end_key) not in props and e.get(end_key) not in bean_first:
                    err(f"{at}: {end_key} must name a prop or a bean already on stage in this shot.")
    if elements > LIMITS["maxElementsPerShot"]:
        err(f"{where} puts {elements} props and labels on stage; at most "
            f"{LIMITS['maxElementsPerShot']} fit. Cut to a new shot to make room.")
    _check_layout(where, end, props, labels, bean_x, err)


# A bean that changes x hops there over this many frames (stage.ts).
HOP_FRAMES = 8


def bean_spans(moves: list[tuple[int, float]], end: int, scale: float) -> list[tuple[int, int, tuple]]:
    """Where one bean stands over a shot: (from, to, box) spans, to exclusive.
    A hop covers the boxes at both ends for its HOP_FRAMES, so a prop it sweeps
    through is caught; a spot the bean has left is free again."""
    spans = []
    for k, (f, x) in enumerate(moves):
        nxt = moves[k + 1][0] if k + 1 < len(moves) else end
        box = bean_box(x, scale)
        if k:
            px = moves[k - 1][1]
            if px != x:
                prev = bean_box(px, scale)
                sweep = (min(prev[0], box[0]), box[1], max(prev[2], box[2]), box[3])
                spans.append((f, min(f + HOP_FRAMES, nxt), sweep))
                f = min(f + HOP_FRAMES, nxt)
        if f < nxt:
            spans.append((f, nxt, box))
    return spans


def _check_layout(where, end, props, labels, bean_x, err) -> None:
    g = GEOMETRY
    scale = bean_scale(len(bean_x) or 1)
    beans = [(who, a, b, box) for who, moves in bean_x.items() for a, b, box in bean_spans(moves, end, scale)]

    def inside(box) -> bool:
        return (box[0] >= g["safeLeft"] and box[2] <= g["safeRight"]
                and box[1] >= g["stageTop"] and box[3] <= g["floorY"] + 20)

    def meets_bean(name, since, box) -> None:
        # an element is on stage from `since` to the cut; a bean only where it stands then
        for who, a, b, bbox in beans:
            if b > since and _overlap(box, bbox):
                err(f"{where}: {name} overlaps the {who} bean (from frame {max(a, since)}); move one of them.")
                return

    for who, _, _, box in beans:
        if box[0] < g["safeLeft"] or box[2] > g["safeRight"]:
            err(f"{where}: the {who} bean stands partly outside the frame's safe zone; move its x inward.")
            break
    if len(bean_x) == 2:
        (w1, m1), (w2, m2) = bean_x.items()
        for a1, b1, x1 in bean_spans(m1, end, scale):
            if any(a1 < b2 and a2 < b1 and _overlap(x1, x2) for a2, b2, x2 in bean_spans(m2, end, scale)):
                err(f"{where}: the {w1} and {w2} beans overlap; stand them further apart.")
                break
    for pid, p in props.items():
        if not inside(p["box"]):
            err(f"{where}: the {pid} prop reaches outside the stage (between the header and the floor, "
                "inside the side margins); move or shrink it.")
        meets_bean(f"the {pid} prop", p["frame"], p["box"])
    for k, (since, box, text) in enumerate(labels):
        if not inside(box):
            err(f"{where}: the label {text!r} reaches outside the stage.")
        for pid, p in props.items():
            if _overlap(box, p["box"]):
                err(f"{where}: the label {text!r} overlaps the {pid} prop.")
        meets_bean(f"the label {text!r}", since, box)
        for _, other, text2 in labels[k + 1:]:
            if _overlap(box, other):
                err(f"{where}: the labels {text!r} and {text2!r} overlap.")


def shot_windows(config: dict) -> list[tuple[int, int]]:
    """(start, end) of every shot of a Bean Explainer config, for the text-layout
    audit to sample each like a scene. [] when the config is not one. A shot
    that opens a list section starts after the badge carousel, where its events
    may first appear: sampled earlier, the audit would measure the carousel."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_bean_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    starts = [s.get("start") for s in data.get("shots") or [] if isinstance(s, dict) and _int(s.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    carousel = set()
    if data.get("list") is True:
        secs = [s.get("start") for s in data.get("sections") or [] if isinstance(s, dict) and _int(s.get("start"))]
        carousel = set(secs[1:])
    return [(a + (TIMING["carousel"] if a in carousel else 0), b)
            for a, b in zip(starts, starts[1:] + [total]) if b > a + (TIMING["carousel"] if a in carousel else 0)]
