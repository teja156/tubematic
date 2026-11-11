"""Under the Hood (TMDEV-201): the checks an Under the Hood scene-config must
pass before it is written, so an unattended agent cannot ship a label pinned
off its photograph, a crowded plate, a mistimed cut or a still video.

An Under the Hood video is one installed `UnderTheHood` scene spanning every
frame. The agent writes no code for it: `props.underTheHood` holds plates (a
generated close-up photograph, or a plain dark panel for a chart) and, on
each plate, events timed to the narration's word frames: callouts pinned to a
point of the photograph, outlines, gold field arcs, ticking counters, a big
stat, a line chart, a footnote and the presenter's poses. The renderer's side
of this contract is
renderer/remotion/src/scenes/installed/underTheHood/contract.ts.

Keep in sync: LIMITS, TIMING, GEOMETRY, CAMERA, the catalogues and the box
helpers mirror contract.ts. mcp/tests/test_under_the_hood.py reads the
TypeScript constants and the style pack, and both sides run the shared cases
in tests/fixtures/under_the_hood_contract.json, so a drift fails a test
instead of a render.

Free of the database and of I/O: the caller passes the style, the config,
the narration's fps and word start frames, the pack's `extra` block and the
video id.
"""
from __future__ import annotations

import math
import re

SCENE_SRC = "UnderTheHood"
PROPS_KEY = "underTheHood"
STYLE_ID = "under_the_hood"

W, H = 1080, 1920
LIMITS = {
    "maxImages": 12,
    "maxPlates": 30,
    "maxEventsPerPlate": 16,
    "maxElementsPerPlate": 6,
    "calloutChars": 18,
    "statLabelChars": 22,
    "chipChars": 10,
    "affixChars": 3,
    "chartLabelChars": 24,
    "footnoteChars": 40,
    "maxCounters": 4,
    "maxCounterValue": 99999,
    "minChartPoints": 2,
    "maxChartPoints": 24,
    "minArcs": 3,
    "maxArcs": 9,
    "minPlateSeconds": 1.5,
    "maxStillSeconds": 3.5,
}
TIMING = {
    "fade": 3,
    "zoomOut": 6,
    "zoomIn": 8,
    "snap": 2,
    "minPoseGap": 8,
    "endMargin": 6,
    "readFrames": 20,
    "chipIn": 4,
    "leaderIn": 7,
    "drawOn": 8,
    "arcBend": 20,
    "sparkFrames": 45,
    "tickStep": 4,
    "tickFrames": 16,
    "statCount": 24,
    "chartMin": 30,
    "chartMax": 150,
}
GEOMETRY = {
    "plateTop": 460,
    "plateBottom": 1350,
    "plateCx": 540,
    "plateCy": 905,
    "plateWidth": 1080,
    "fadePx": 90,
    "safeLeft": 60,
    "safeRight": 1020,
    "chipFontPx": 36,
    "chipCharPx": 27,
    "chipPadPx": 22,
    "chipHeight": 60,
    "minLeaderPx": 40,
    "statRight": 1010,
    "statUpperTop": 500,
    "statLowerTop": 1050,
    "statHeight": 260,
    "statFontPx": 170,
    "statCharPx": 104,
    "statLabelCharPx": 24,
    "chartLeft": 90,
    "chartRight": 990,
    "chartTop": 700,
    "chartBottom": 1250,
    "counterLeft": 70,
    "counterTop": 1400,
    "counterWidth": 520,
    "footnoteTop": 1560,
    "presenterLeft": 610,
    "presenterTop": 1380,
    "presenterWidth": 440,
    "presenterHeight": 620,
    "anchorMargin": 20,
    "overlapTolerance": 4,
}
CAMERA = {"push": 0.01, "minZoom": 1, "maxZoom": 3, "through": 4, "enterFrom": 1.25}

EVENT_TYPES = ("callout", "outline", "arcs", "counters", "stat", "chart", "footnote", "pose")
POSES = ("idle", "point", "present", "think", "surprise", "hands_on_head", "thumbs", "shrug", "explain")
TONES = ("white", "blue", "gold")
SHAPES = ("box", "bracket")
ENTRANCES = ("cut", "zoom")
STAT_SLOTS = ("upper", "lower")

# Events drawn on the photograph, so a plate without one cannot have them.
ON_IMAGE = ("callout", "outline", "arcs")
# Events that put an element in the plate band, counted against maxElementsPerPlate.
ELEMENTS = ("callout", "outline", "arcs", "stat", "chart")
# Events whose text must stay up long enough to be read.
READ = ("callout", "stat", "chart", "footnote")

MAX_ERRORS = 12
# An image src is the public_path generate_image returned for this video.
_IMAGE_SRC = re.compile(r"^/public/([A-Za-z0-9_-]+)/images/([A-Za-z0-9-]+)\.(png|jpe?g|webp)$")


def is_uth_scene(scene) -> bool:
    """Any scene naming UnderTheHood, whatever its type: the use rule must catch
    a mistyped one too."""
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def plate_scale(plate: dict, t: float, fps: int) -> float:
    """The camera scale of a plate `t` frames after it starts, before any transition."""
    return plate.get("zoom", 1) * (1 + CAMERA["push"] * max(0, t) / fps)


def project_at(plate: dict, s: float, u: float, v: float) -> tuple[float, float]:
    """Where the photograph's point [u, v] is in the frame at camera scale `s`."""
    fu, fv = plate.get("focus") or (0.5, 0.5)
    a = plate.get("aspect", 1)
    g = GEOMETRY
    return (g["plateCx"] + (u - fu) * g["plateWidth"] * s,
            g["plateCy"] + (v - fv) * g["plateWidth"] * a * s)


def image_box(plate: dict, s: float) -> tuple[float, float, float, float]:
    x0, y0 = project_at(plate, s, 0, 0)
    x1, y1 = project_at(plate, s, 1, 1)
    return (x0, y0, x1, y1)


def chip_box(text: str, chip) -> tuple[float, float, float, float]:
    """A callout chip's box, centred on its chip point (frame fractions)."""
    g = GEOMETRY
    w = len(text) * g["chipCharPx"] + 2 * g["chipPadPx"]
    cx, cy = chip[0] * W, chip[1] * H
    return (cx - w / 2, cy - g["chipHeight"] / 2, cx + w / 2, cy + g["chipHeight"] / 2)


def stat_text(value, decimals: int = 0, prefix: str = "", suffix: str = "") -> str:
    """The text a stat shows when it has counted to `value` (JS toFixed rounding)."""
    return f"{prefix}{_to_fixed(value, decimals)}{suffix}"


def _to_fixed(value, decimals: int) -> str:
    # JavaScript's toFixed rounds half away from zero on the decimal it sees;
    # Python's format rounds half to even. Match the renderer.
    q = 10 ** decimals
    n = math.floor(abs(value) * q + 0.5) / q
    return f"{'-' if value < 0 and n else ''}{n:.{decimals}f}"


def stat_box(e: dict) -> tuple[float, float, float, float]:
    """A stat block's box: the numeral and its label, right-aligned."""
    g = GEOMETRY
    numeral = len(stat_text(e["value"], e.get("decimals", 0), e.get("prefix", ""), e.get("suffix", ""))) * g["statCharPx"]
    label = len(e["label"]) * g["statLabelCharPx"]
    w = max(numeral, label)
    top = g["statUpperTop"] if e.get("place") == "upper" else g["statLowerTop"]
    return (g["statRight"] - w, top, g["statRight"], top + g["statHeight"])


def leader_start(box, target) -> tuple[float, float]:
    """The point on a chip's edge where its leader starts: the middle of the side facing the target."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    if target[0] < box[0]:
        return (box[0], cy)
    if target[0] > box[2]:
        return (box[2], cy)
    return (cx, box[1] if target[1] < cy else box[3])


def overlaps(a, b) -> bool:
    t = GEOMETRY["overlapTolerance"]
    return a[0] < b[2] - t and b[0] < a[2] - t and a[1] < b[3] - t and b[1] < a[3] - t


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _uv(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_num(x) and 0 <= x <= 1 for x in v)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and bool(v.strip()) and len(v) <= limit


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: an Under the Hood video is exactly the one
    UnderTheHood scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_uth_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The UnderTheHood scene draws a whole Under the Hood video and is used only when "
                    "the video's visual_style is under_the_hood (chosen at the topic). Build this "
                    "video's scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("An Under the Hood video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"UnderTheHood\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"underTheHood\": {...}}}. Put every beat in its plates.")
    return ""


def plate_images(config: dict) -> list[str]:
    """The image src of every plate that has one, in plate order (repeats kept)."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_uth_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    return [p["image"] for p in data.get("plates") or [] if isinstance(p, dict) and isinstance(p.get("image"), str)]


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "") -> list[str]:
    """Every problem with an Under the Hood config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block. A plate's `aspect` must already be filled in (the server
    reads it from the photograph's file); absent means square."""
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the plates and their events."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]

    plates = data.get("plates")
    if not isinstance(plates, list) or not 1 <= len(plates) <= LIMITS["maxPlates"]:
        return errors + [f"plates must list 1 to {LIMITS['maxPlates']} plates."]
    if not all(isinstance(p, dict) for p in plates):
        return errors + ["Every plate must be an object."]
    starts = [p.get("start") for p in plates]
    if not all(_int(v) for v in starts):
        return errors + ["Every plate needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first plate must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Plate starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    images: set[str] = set()
    sound: list[bool] = []   # plates whose own fields passed, so their camera can be used
    for i, p in enumerate(plates):
        where = f"Plate {i + 1}"
        if i and not on_word(starts[i]):
            err(f"{where} cuts at frame {starts[i]}, which is not on a word: start a plate within "
                f"{TIMING['snap']} frames of a word's start.")
        if ends[i] - starts[i] < LIMITS["minPlateSeconds"] * fps:
            err(f"{where} lasts {ends[i] - starts[i]} frames; a plate needs at least "
                f"{LIMITS['minPlateSeconds']} s.")
        sound.append(_check_plate(p, i, plates, starts, ends, fps, video_id, images, sound, err))
    if len(images) > LIMITS["maxImages"]:
        err(f"The plates use {len(images)} different photographs; a video may use at most "
            f"{LIMITS['maxImages']}. Reuse a photograph with another focus or zoom instead of a new one.")

    # ── events ──
    changes = set(starts)
    last_pose = None
    for i, p in enumerate(plates):
        if not sound[i]:
            continue
        # a zoom-through takes what is pinned to this plate away zoomOut frames before the cut
        nxt = plates[i + 1] if i + 1 < len(plates) else {}
        seen_until = ends[i] - (TIMING["zoomOut"] if nxt.get("enter") == "zoom" else 0)
        last_pose = _check_events(p, i, starts[i], seen_until, fps, extra, on_word, changes, last_pose, err)

    still = round(LIMITS["maxStillSeconds"] * fps)
    prev = 0
    for c in sorted(c for c in changes if 0 <= c < total) + [total]:
        if c - prev > still:
            err(f"Nothing new happens from frame {prev} to {c} ({(c - prev) / fps:.1f} s); the longest "
                f"stretch allowed is {LIMITS['maxStillSeconds']} s. Add a callout, an outline, a pose, a "
                "counter or a new plate.")
        prev = c
    return errors


def _check_plate(p, i, plates, starts, ends, fps, video_id, images, sound, err) -> bool:
    """Check one plate's own fields; True when its camera can be used."""
    where = f"Plate {i + 1}"
    g = GEOMETRY
    image = p.get("image")
    if image is not None:
        m = _IMAGE_SRC.match(image) if isinstance(image, str) else None
        if not m or (video_id and m.group(1) != video_id):
            err(f"{where}: image must be the public_path generate_image returned for this video "
                "(\"/public/<video_id>/images/<name>.png\").")
            return False
        images.add(image)
    for key in ("focus", "zoom", "through", "aspect", "enter"):
        if key in p and image is None and key != "enter":
            err(f"{where}: {key} applies to a photograph, and this plate has none.")
            return False
    if "focus" in p and not _uv(p["focus"]):
        err(f"{where}: focus must be [u, v], each from 0 to 1.")
        return False
    if "zoom" in p and not (_num(p["zoom"]) and CAMERA["minZoom"] <= p["zoom"] <= CAMERA["maxZoom"]):
        err(f"{where}: zoom must be from {CAMERA['minZoom']} to {CAMERA['maxZoom']}.")
        return False
    if "aspect" in p and not (_num(p["aspect"]) and 0.25 <= p["aspect"] <= 4):
        err(f"{where}: aspect must be the photograph's height over its width.")
        return False
    enter = p.get("enter", "cut")
    if enter not in ENTRANCES:
        err(f"{where}: enter must be one of {', '.join(ENTRANCES)}.")
        return False
    if enter == "zoom":
        prev = plates[i - 1] if i else None
        if not prev or not isinstance(prev.get("image"), str):
            err(f"{where}: a zoom entrance rushes into a point of the previous plate's photograph, so it "
                "needs a previous plate with one.")
        elif not sound[i - 1]:
            pass   # the previous plate's own problem is already reported
        elif not _uv(p.get("through")):
            err(f"{where}: a zoom entrance needs through: the [u, v] of the previous plate's photograph "
                "the camera rushes into.")
        else:
            at = project_at(prev, plate_scale(prev, starts[i] - TIMING["zoomOut"] - starts[i - 1], fps), *p["through"])
            if not _inside_band(at):
                err(f"{where}: through {p['through']} is outside the visible part of the previous plate's "
                    "photograph when the zoom starts.")
    elif "through" in p:
        err(f"{where}: through is only for enter \"zoom\".")
    if image is None:
        return True
    # The photograph must cover the band from the first frame: the push only enlarges it.
    box = image_box(p, plate_scale(p, 0, fps))
    if box[0] > 0.5 or box[2] < W - 0.5 or box[1] > g["plateTop"] + 0.5 or box[3] < g["plateBottom"] - 0.5:
        err(f"{where}: at this focus and zoom the photograph does not cover the plate band, so its edge "
            "would show. Move focus toward the middle or raise zoom.")
    return True


def _inside_band(pt, margin: float = 0) -> bool:
    g = GEOMETRY
    return (g["safeLeft"] + margin <= pt[0] <= g["safeRight"] - margin
            and g["plateTop"] + margin <= pt[1] <= g["plateBottom"] - margin)


def _box_in_band(box) -> bool:
    g = GEOMETRY
    return (box[0] >= g["safeLeft"] and box[2] <= g["safeRight"]
            and box[1] >= g["plateTop"] + 8 and box[3] <= g["plateBottom"] - 8)


def _check_events(p, i, start, end, fps, extra, on_word, changes, last_pose, err):
    where = f"Plate {i + 1}"
    events = p.get("events", [])
    if not isinstance(events, list) or len(events) > LIMITS["maxEventsPerPlate"]:
        err(f"{where}: events must be a list of at most {LIMITS['maxEventsPerPlate']}.")
        return last_pose
    frames = [e.get("frame") if isinstance(e, dict) else None for e in events]
    if not all(_int(f) for f in frames):
        err(f"{where}: every event needs a whole-number frame.")
        return last_pose
    if any(b < a for a, b in zip(frames, frames[1:])):
        err(f"{where}: list the events in frame order.")
    has_image = isinstance(p.get("image"), str)
    g = GEOMETRY
    margin = g["anchorMargin"]
    s_end = plate_scale(p, end - start, fps)
    boxes: list[tuple[str, tuple]] = []   # (name, box) of chips, stats and the chart in the band
    elements = 0
    once: set[str] = set()
    for e, f in zip(events, frames):
        t = e.get("type")
        at = f"{where}, the {t or 'event'} at frame {f}"
        if t not in EVENT_TYPES:
            err(f"{at}: type must be one of {', '.join(EVENT_TYPES)}.")
            continue
        if not start <= f <= end - TIMING["endMargin"]:
            err(f"{at}: it must start inside its plate (frames {start} to {end - TIMING['endMargin']}).")
            continue
        if t in READ and f > end - TIMING["readFrames"]:
            err(f"{at}: its text appears {end - f} frames before the plate ends, too late to be read; "
                f"start it at least {TIMING['readFrames']} frames before the cut.")
            continue
        if t in ON_IMAGE and not has_image:
            err(f"{at}: a {t} is drawn on the photograph, and this plate has none.")
            continue
        changes.add(f)
        if t in ELEMENTS:
            elements += 1
        s_at = plate_scale(p, f - start, fps)

        def pinned(uv, name: str) -> bool:
            for s, when in ((s_at, "when it appears"), (s_end, "by the end of the plate")):
                if not _inside_band(project_at(p, s, *uv), margin):
                    err(f"{at}: {name} {uv} is outside the visible part of the photograph {when}; "
                        "the slow push moves points away from the focus.")
                    return False
            return True

        if t == "pose":
            if e.get("pose") not in extra["poses"]:
                err(f"{at}: pose must be one of {', '.join(extra['poses'])}.")
            if not on_word(f):
                err(f"{at}: a pose swaps on a word; move it within {TIMING['snap']} frames of a word's start.")
            if last_pose is not None and f - last_pose < TIMING["minPoseGap"]:
                err(f"{at}: it comes {f - last_pose} frames after the last pose; swaps closer than "
                    f"{TIMING['minPoseGap']} frames read as a twitch.")
            last_pose = f
        elif t == "callout":
            text, chip, tone = e.get("text"), e.get("chip"), e.get("tone", "white")
            if not _text(text, LIMITS["calloutChars"]):
                err(f"{at}: text must be 1 to {LIMITS['calloutChars']} characters: name the part.")
                continue
            if tone not in TONES:
                err(f"{at}: tone must be one of {', '.join(TONES)}.")
            if not _uv(e.get("at")) or not _uv(chip):
                err(f"{at}: at (the point on the photograph, [u, v]) and chip (the label's centre in the "
                    "frame, [x, y] fractions) must each be two numbers from 0 to 1.")
                continue
            box = chip_box(text, chip)
            if not _box_in_band(box):
                err(f"{at}: the {text!r} chip reaches outside the plate band (y {g['plateTop']} to "
                    f"{g['plateBottom']} px, x {g['safeLeft']} to {g['safeRight']} px); move chip.")
                continue
            if not pinned(e["at"], "at"):
                continue
            for s in (s_at, s_end):
                target = project_at(p, s, *e["at"])
                a = leader_start(box, target)
                if math.hypot(target[0] - a[0], target[1] - a[1]) < g["minLeaderPx"]:
                    err(f"{at}: the {text!r} chip sits on the point it labels; move it at least "
                        f"{g['minLeaderPx']} px away so its line shows.")
                    break
            boxes.append((f"the {text!r} chip", box))
        elif t == "outline":
            r = e.get("region")
            if not (isinstance(r, list) and len(r) == 4 and all(_num(x) and 0 <= x <= 1 for x in r)
                    and r[0] < r[2] and r[1] < r[3]):
                err(f"{at}: region must be [u0, v0, u1, v1] with u0 < u1 and v0 < v1, each from 0 to 1.")
                continue
            if e.get("tone", "blue") not in TONES:
                err(f"{at}: tone must be one of {', '.join(TONES)}.")
            if e.get("shape", "box") not in SHAPES:
                err(f"{at}: shape must be one of {', '.join(SHAPES)}.")
            pinned([r[0], r[1]], "the region's top-left") and pinned([r[2], r[3]], "the region's bottom-right")
        elif t == "arcs":
            if not _uv(e.get("from")) or not _uv(e.get("to")):
                err(f"{at}: from and to must each be [u, v], from 0 to 1.")
                continue
            n = e.get("count", 7)
            if not _int(n) or not LIMITS["minArcs"] <= n <= LIMITS["maxArcs"]:
                err(f"{at}: count must be {LIMITS['minArcs']} to {LIMITS['maxArcs']}.")
            pinned(e["from"], "from") and pinned(e["to"], "to")
        elif t == "counters":
            if "counters" in once:
                err(f"{at}: a plate has one counter row; put the values in the first one.")
                continue
            once.add("counters")
            vals = e.get("values")
            if (not isinstance(vals, list) or not 1 <= len(vals) <= LIMITS["maxCounters"]
                    or not all(isinstance(v, dict) and all(_int(v.get(k)) and 0 <= v[k] <= LIMITS["maxCounterValue"]
                                                           for k in ("from", "to")) for v in vals)):
                err(f"{at}: values must list 1 to {LIMITS['maxCounters']} {{from, to}} whole numbers from 0 to "
                    f"{LIMITS['maxCounterValue']}.")
        elif t == "stat":
            if "stat" in once:
                err(f"{at}: a plate has one stat.")
                continue
            once.add("stat")
            if not _num(e.get("value")) or not _num(e.get("from", 0)):
                err(f"{at}: value (and from, when given) must be numbers.")
                continue
            dec = e.get("decimals", 0)
            if not _int(dec) or not 0 <= dec <= 2:
                err(f"{at}: decimals must be 0, 1 or 2.")
                continue
            bad = _affix_errors(e)
            if bad:
                err(f"{at}: {bad}")
                continue
            if not _text(e.get("label"), LIMITS["statLabelChars"]):
                err(f"{at}: label must be 1 to {LIMITS['statLabelChars']} characters.")
                continue
            if "chip" in e and not _text(e["chip"], LIMITS["chipChars"]):
                err(f"{at}: chip must be 1 to {LIMITS['chipChars']} characters.")
                continue
            if e.get("place", "lower") not in STAT_SLOTS:
                err(f"{at}: place must be one of {', '.join(STAT_SLOTS)}.")
                continue
            box = stat_box(e)
            if box[0] < g["safeLeft"]:
                err(f"{at}: the stat is too wide for the frame; shorten its label or its numeral.")
                continue
            boxes.append(("the stat", box))
        elif t == "chart":
            if has_image:
                err(f"{at}: a chart draws on a plain dark plate; give it a plate with no image.")
                continue
            if "chart" in once:
                err(f"{at}: a plate has one chart.")
                continue
            once.add("chart")
            pts = e.get("points")
            if (not isinstance(pts, list) or not LIMITS["minChartPoints"] <= len(pts) <= LIMITS["maxChartPoints"]
                    or not all(_num(v) for v in pts)):
                err(f"{at}: points must list {LIMITS['minChartPoints']} to {LIMITS['maxChartPoints']} numbers.")
                continue
            dur = e.get("duration", 88)
            if not _int(dur) or not TIMING["chartMin"] <= dur <= TIMING["chartMax"]:
                err(f"{at}: duration must be {TIMING['chartMin']} to {TIMING['chartMax']} frames.")
            elif f + dur > end - TIMING["endMargin"]:
                err(f"{at}: the chart is still drawing when its plate ends; start it earlier or shorten duration.")
            dec = e.get("decimals", 0)
            if not _int(dec) or not 0 <= dec <= 2:
                err(f"{at}: decimals must be 0, 1 or 2.")
            bad = _affix_errors(e)
            if bad:
                err(f"{at}: {bad}")
            if not _text(e.get("label"), LIMITS["chartLabelChars"]):
                err(f"{at}: label (the axis) must be 1 to {LIMITS['chartLabelChars']} characters.")
            if "chip" in e and not _text(e["chip"], LIMITS["chipChars"]):
                err(f"{at}: chip must be 1 to {LIMITS['chipChars']} characters.")
            boxes.append(("the chart", (g["chartLeft"], g["chartTop"] - 260, g["chartRight"], g["chartBottom"])))
        elif t == "footnote":
            if "footnote" in once:
                err(f"{at}: a plate has one footnote.")
                continue
            once.add("footnote")
            if not _text(e.get("text"), LIMITS["footnoteChars"]):
                err(f"{at}: text must be 1 to {LIMITS['footnoteChars']} characters.")
    if elements > LIMITS["maxElementsPerPlate"]:
        err(f"{where} puts {elements} callouts, outlines, arcs, stats and charts on screen; at most "
            f"{LIMITS['maxElementsPerPlate']} fit. Cut to a new plate to make room.")
    for k, (name, box) in enumerate(boxes):
        for name2, box2 in boxes[k + 1:]:
            if overlaps(box, box2):
                err(f"{where}: {name} overlaps {name2}; move one of them.")
    return last_pose


def _affix_errors(e: dict) -> str:
    for key in ("prefix", "suffix"):
        if key in e and not (isinstance(e[key], str) and len(e[key]) <= LIMITS["affixChars"]):
            return f"{key} must be text of at most {LIMITS['affixChars']} characters (a unit or a sign)."
    return ""


def plate_windows(config: dict) -> list[tuple[int, int]]:
    """(start, end) of every plate of an Under the Hood config, for the
    text-layout audit to sample each like a scene. [] when the config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_uth_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    starts = [p.get("start") for p in data.get("plates") or [] if isinstance(p, dict) and _int(p.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    return [(a, b) for a, b in zip(starts, starts[1:] + [total]) if b > a]
