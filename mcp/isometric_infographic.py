"""Isometric Infographic (TMDEV-237): the checks an Isometric Infographic
scene-config must pass before it is written, so an unattended agent cannot
ship a board with props stacked on one tile, a prop off the board, a route
that leaves it, a pin on nothing, a still board, or a part of its own that is
not built from the kit's solids.

An Isometric Infographic video is one installed `IsometricInfographic` scene
spanning every frame. `props.isometric` holds a title, an optional readout,
1 to 3 boards (ground areas, props on tile coordinates, routes, movers, pins,
camera moves, lifts, cutaways, explodes, all timed to the narration's word
frames) and an optional legend. Props come from the library in the style
pack's `extra`, or are compositions of the kit's solids (`customProps`). The
renderer's side of this contract is
renderer/remotion/src/scenes/installed/isometric/contract.ts.

Keep in sync: LIMITS, TIMING and GEOMETRY mirror contract.ts and the helpers
mirror contract.ts and stage.ts. The catalogues are read from the pack's
`extra`, which renderer/remotion/isometric-tools/sync-contract.mjs writes, with
the shared cases in tests/fixtures/isometric_infographic_contract.json.

Free of the database and of I/O.
"""
from __future__ import annotations

import re

from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "IsometricInfographic"
PROPS_KEY = "isometric"
STYLE_ID = "isometric_infographic"

W, H = 1080, 1920
BOARD = 10
SOLIDS = ("box", "cyl", "cone", "pyr", "gable")

LIMITS = {
    "minBoards": 1,
    "maxBoards": 3,
    "maxAreas": 8,
    "maxProps": 14,
    "maxRoutes": 3,
    "maxRoutePoints": 8,
    "maxMovers": 4,
    "maxPins": 4,
    "maxCamera": 8,
    "maxLifts": 3,
    "maxCustomProps": 6,
    "maxSolids": 16,
    "titleChars": 22,
    "labelChars": 12,
    "valueChars": 8,
    "unitChars": 4,
    "legendItems": 5,
    "legendChars": 12,
    "maxReadoutSteps": 8,
    "maxCubes": 12,
    "maxValue": 999999,
    "minBoardSeconds": 2,
    "maxStillSeconds": 4,
}
TIMING = {
    "snap": 2,
    "drop": 12,
    "draw": 20,
    "move": 40,
    "pin": 18,
    "glide": 24,
    "lift": 14,
    "cut": 16,
    "roll": 18,
    "legend": 12,
    "readFrames": 20,
}
GEOMETRY = {
    "k": 60,
    "cx": 540,
    "cy": 650,
    "slab": 1.05,
    "zoomMax": 2,
    "bandTop": 590,
    "bandBottom": 1335,
    "titleTop": 236,
    "readoutTop": 330,
    "legendTop": 1640,
    "safeLeft": 70,
    "safeRight": 1010,
}

MAX_ERRORS = 12
_ID = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_BOARD_KEYS = {"start", "areas", "props", "routes", "movers", "pins", "camera", "lifts", "cutaways", "explodes"}


def is_iso_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= limit and v == v.strip()


def grouped(n) -> str:
    s = str(round(abs(n)))
    out = ""
    for i, ch in enumerate(s):
        if i > 0 and (len(s) - i) % 3 == 0:
            out += ","
        out += ch
    return "-" + out if n < 0 else out


def event_frames(b: dict) -> list[int]:
    out = [b["start"]]
    for p in b.get("props") or []:
        if isinstance(p, dict) and _int(p.get("enter")):
            out.append(p["enter"])
    for key in ("routes", "movers", "pins", "camera", "lifts", "cutaways", "explodes"):
        out += [x["at"] for x in b.get(key) or [] if isinstance(x, dict) and _int(x.get("at"))]
    return sorted(set(out))


def quiet_spans(data: dict, total: int) -> list[list[int]]:
    boards = data["boards"]
    extra = [s["at"] for s in (data.get("readout") or {}).get("steps") or [] if isinstance(s, dict) and _int(s.get("at"))]
    leg = data.get("legend")
    if isinstance(leg, dict) and _int(leg.get("at")):
        extra.append(leg["at"])
    spans = []
    for i, b in enumerate(boards):
        end = boards[i + 1]["start"] if i + 1 < len(boards) else total
        frames = sorted(set(event_frames(b) + [f for f in extra if b["start"] <= f < end]))
        frames.append(end)
        spans.extend([a, c] for a, c in zip(frames, frames[1:]))
    return spans


def check_scene_use(visual_style: str, scenes: list) -> str:
    uses = [s for s in scenes or [] if is_iso_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The IsometricInfographic scene draws a whole Isometric Infographic video and is used only when "
                    "the video's visual_style is isometric_infographic (chosen at the topic). Build this video's "
                    "scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("An Isometric Infographic video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"IsometricInfographic\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"isometric\": {...}}}. Put every board in its boards.")
    return ""


def _solid_error(sd, colors) -> str:
    if not isinstance(sd, dict) or sd.get("s") not in SOLIDS:
        return f"s must be one of {list(SOLIDS)}."
    keys = {"box": {"s", "x", "y", "z", "w", "d", "h", "c", "layer"}, "gable": {"s", "x", "y", "z", "w", "d", "h", "c"},
            "cyl": {"s", "x", "y", "z", "r", "h", "c"}, "cone": {"s", "x", "y", "z", "r", "h", "c"},
            "pyr": {"s", "x", "y", "z", "r", "h", "c"}}[sd["s"]]
    if set(sd) - keys:
        return f"a {sd['s']} takes {sorted(keys)}."
    if not all(_num(sd.get(k)) and -0.8 <= sd[k] <= 0.8 for k in ("x", "y")):
        return "x and y must be numbers from -0.8 to 0.8 (the prop's own footprint)."
    if "z" in sd and not (_num(sd["z"]) and 0 <= sd["z"] <= 3):
        return "z must be from 0 to 3."
    if not (_num(sd.get("h")) and 0 < sd["h"] <= 3):
        return "h must be above 0 and at most 3."
    sizes = ("w", "d") if sd["s"] in ("box", "gable") else ("r",)
    if not all(_num(sd.get(k)) and 0 < sd[k] <= 1.6 for k in sizes):
        return f"{' and '.join(sizes)} must be above 0 and at most 1.6."
    c = sd.get("c")
    if c not in ("main", "accent") and c not in colors:
        return f"c must be \"main\", \"accent\" or one of {sorted(colors)}."
    if "layer" in sd and not (_int(sd["layer"]) and 0 <= sd["layer"] <= 4):
        return "layer must be a whole number from 0 to 4."
    return ""


def custom_prop_errors(custom, library, colors) -> tuple[list[str], dict]:
    errs: list[str] = []
    parts: dict[str, float] = {}
    if custom is None:
        return errs, parts
    if not isinstance(custom, list) or len(custom) > LIMITS["maxCustomProps"]:
        return [f"customProps must be a list of at most {LIMITS['maxCustomProps']} props."], parts
    for i, c in enumerate(custom):
        where = f"customProps {i + 1}"
        if not isinstance(c, dict) or set(c) != {"id", "solids", "main", "height"}:
            errs.append(f"{where} must be {{\"id\", \"solids\", \"main\", \"height\"}}.")
            continue
        cid = c["id"]
        if not isinstance(cid, str) or not _ID.match(cid) or cid in library or cid in parts:
            errs.append(f"{where}: id {cid!r} must be lowercase letters, digits or _, and not a library prop.")
            continue
        if c["main"] not in colors:
            errs.append(f"{where} ({cid}): main must be one of {sorted(colors)}.")
            continue
        if not (_num(c["height"]) and 0 < c["height"] <= 3):
            errs.append(f"{where} ({cid}): height (where a pin sits) must be above 0 and at most 3.")
            continue
        solids = c["solids"]
        if not isinstance(solids, list) or not 1 <= len(solids) <= LIMITS["maxSolids"]:
            errs.append(f"{where} ({cid}): solids must list 1 to {LIMITS['maxSolids']} solids.")
            continue
        bad = next(((k, e) for k, sd in enumerate(solids) if (e := _solid_error(sd, colors))), None)
        if bad:
            errs.append(f"{where} ({cid}) solid {bad[0] + 1}: {bad[1]}")
            continue
        parts[cid] = c["height"]
    return errs, parts


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "", quiet=()) -> list[str]:
    """Every problem with an Isometric Infographic config, one sentence each
    (at most MAX_ERRORS), or [] when it may be written."""
    errors: list[str] = []
    found = [0]

    def err(msg: str) -> None:
        found[0] += 1
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    total = config.get("totalFrames")
    scenes_cfg = config.get("scenes") or []
    use = check_scene_use(STYLE_ID, scenes_cfg)
    if use:
        return [use]
    sc = scenes_cfg[0]
    if sc.get("startFrame") != 0 or sc.get("durationInFrames") != total:
        err(f"The {SCENE_SRC} scene must start at frame 0 and last totalFrames ({total}) frames.")
    props = sc.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the title and the boards."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    unknown = sorted(set(data) - {"title", "readout", "boards", "legend", "customProps"})
    if unknown:
        err(f"{PROPS_KEY} has unknown field(s) {unknown}; it takes title, readout, boards, legend and customProps.")
    if not _text(data.get("title"), LIMITS["titleChars"]):
        err(f"title must be 1 to {LIMITS['titleChars']} characters.")

    colors = set(extra.get("colors") or [])
    library = set(extra.get("props") or [])
    cerrs, custom = custom_prop_errors(data.get("customProps"), library, colors)
    for e in cerrs:
        err(e)
    names = library | set(custom)
    rooms = set(extra.get("rooms") or [])
    stacks = set(extra.get("stacks") or [])

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    def timed(obj, key, where, lo, hi, what) -> bool:
        v = obj.get(key) if isinstance(obj, dict) else None
        if not _int(v) or not lo <= v < hi:
            err(f"{where}: {key} must be a frame from {lo} to {hi - 1} ({what}).")
            return False
        if not on_word(v):
            err(f"{where}: {key} {v} is not on a word; put it within {TIMING['snap']} frames of a word's start.")
            return False
        return True

    boards = data.get("boards")
    if not isinstance(boards, list) or not LIMITS["minBoards"] <= len(boards) <= LIMITS["maxBoards"]:
        return errors + [f"boards must list {LIMITS['minBoards']} to {LIMITS['maxBoards']} boards."]
    if not all(isinstance(b, dict) and _int(b.get("start")) for b in boards):
        return errors + ["Every board needs a whole-number start frame."]
    starts = [b["start"] for b in boards]
    if starts[0] != 0:
        err("The first board must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Board starts must increase and stay inside the video."]
    ends = starts[1:] + [total]
    min_len = round(LIMITS["minBoardSeconds"] * fps)
    sound: list[bool] = []
    for i, b in enumerate(boards):
        before = found[0]
        where = f"Board {i + 1}"
        if i and not on_word(starts[i]):
            err(f"{where} starts at frame {starts[i]}, which is not on a word.")
        if ends[i] - starts[i] < min_len:
            err(f"{where} lasts {ends[i] - starts[i]} frames; a board needs at least {LIMITS['minBoardSeconds']} s.")
        extra_keys = sorted(set(b) - _BOARD_KEYS)
        if extra_keys:
            err(f"{where}: unknown field(s) {extra_keys}; a board takes {sorted(_BOARD_KEYS)}.")
        _check_board(b, where, starts[i], ends[i], names, rooms, stacks, colors, timed, err, set(extra.get("areas") or []))
        sound.append(found[0] == before)

    ro = data.get("readout")
    if ro is not None:
        if not isinstance(ro, dict) or set(ro) - {"label", "unit", "steps", "cubes"}:
            err("readout takes label, unit, steps and cubes.")
        else:
            if not _text(ro.get("label"), LIMITS["labelChars"]):
                err(f"readout.label must be 1 to {LIMITS['labelChars']} characters.")
            if not isinstance(ro.get("unit"), str) or len(ro["unit"]) > LIMITS["unitChars"]:
                err(f"readout.unit must be at most {LIMITS['unitChars']} characters.")
            steps = ro.get("steps")
            if not isinstance(steps, list) or not 1 <= len(steps) <= LIMITS["maxReadoutSteps"]:
                err(f"readout.steps must list 1 to {LIMITS['maxReadoutSteps']} steps.")
            else:
                prev, reds = -1, 0
                for n, s in enumerate(steps):
                    w = f"readout step {n + 1}"
                    if not isinstance(s, dict) or set(s) - {"value", "at", "red"}:
                        err(f"{w} takes value, at and red.")
                        continue
                    if not (_num(s.get("value")) and 0 <= s["value"] <= LIMITS["maxValue"]):
                        err(f"{w}: value must be a number from 0 to {LIMITS['maxValue']}.")
                    if timed(s, "at", w, prev + 1, total, "the frame it rolls to its value"):
                        prev = s["at"]
                    reds += bool(s.get("red"))
                if reds > 1:
                    err("The readout turns red once: at most one step with red.")
            cubes = ro.get("cubes")
            if cubes is not None:
                if (not isinstance(cubes, dict) or set(cubes) != {"per", "color"} or cubes.get("color") not in colors
                        or not (_num(cubes.get("per")) and cubes["per"] > 0)):
                    err(f"readout.cubes must be {{\"per\": a number above 0, \"color\": one of {sorted(colors)}}}.")
                elif isinstance(steps, list) and any(isinstance(s, dict) and _num(s.get("value"))
                                                     and s["value"] / cubes["per"] > LIMITS["maxCubes"] for s in steps):
                    err(f"readout.cubes.per is too small: a value would need more than {LIMITS['maxCubes']} cubes.")
    leg = data.get("legend")
    if leg is not None:
        items = leg.get("items") if isinstance(leg, dict) else None
        if (not isinstance(leg, dict) or set(leg) != {"at", "items"} or not isinstance(items, list)
                or not 1 <= len(items) <= LIMITS["legendItems"]
                or not all(isinstance(x, dict) and set(x) == {"color", "label"} and x["color"] in colors
                           and _text(x.get("label"), LIMITS["legendChars"]) for x in items)):
            err(f"legend must be {{\"at\", \"items\": 1 to {LIMITS['legendItems']} {{\"color\", \"label\": 1 to "
                f"{LIMITS['legendChars']} characters}}}}.")
        else:
            timed(leg, "at", "legend", 0, total, "the frame it rises in")
            # Jost 600 capitals at 40 px with 3 px spacing run about 28 px a letter; each entry adds its diamond and gaps
            if sum(len(x["label"]) for x in items) * 28 + 72 * len(items) - 40 > GEOMETRY["safeRight"] - GEOMETRY["safeLeft"]:
                err("The legend is too wide for the frame; shorten its labels or drop an entry.")

    for i, b in enumerate(boards):
        for f in event_frames(b)[1:] + ([b["start"]] if i else []):
            w = window_at(f, quiet)
            if w:
                err(f"Board {i + 1}: something happens at frame {f}, inside an insert ({window_text(w)}), where the "
                    f"scene is hidden; time it to a word at {w[1]} or later, or before {w[0]}.")
                break
    for f in [s.get("at") for s in (ro or {}).get("steps") or [] if isinstance(s, dict)] + ([leg.get("at")] if isinstance(leg, dict) else []):
        w = window_at(f, quiet) if _int(f) else None
        if w:
            err(f"The readout or the legend changes at frame {f}, inside an insert ({window_text(w)}); move it out of the window.")
            break

    if all(sound) and not cerrs:
        still = round(LIMITS["maxStillSeconds"] * fps)
        for a, c in quiet_spans(data, total):
            for x, y in uncovered(a, c, quiet):
                if y - x > still:
                    i = max(k for k, st in enumerate(starts) if st <= x)
                    err(f"Board {i + 1}: nothing new happens from frame {x} to {y} ({(y - x) / fps:.1f} s); the longest "
                        f"stretch allowed is {LIMITS['maxStillSeconds']} s. Time a prop, a route, a mover, a pin, a "
                        "camera move, a lift, a cutaway or a readout step to a word in between.")
    return errors


def _check_board(b, where, start, end, names, rooms, stacks, colors, timed, err, area_kinds=()) -> None:
    L = LIMITS
    areas = b.get("areas")
    if not isinstance(areas, list) or len(areas) > L["maxAreas"]:
        err(f"{where}: areas must list at most {L['maxAreas']} areas.")
        areas = []
    for n, a in enumerate(areas):
        r = a.get("rect") if isinstance(a, dict) else None
        if (not isinstance(a, dict) or set(a) != {"kind", "rect"} or not isinstance(r, list) or len(r) != 4
                or not all(_num(v) and 0 <= v <= BOARD for v in r) or r[0] >= r[2] or r[1] >= r[3]):
            err(f"{where} area {n + 1} must be {{\"kind\", \"rect\": [x0, y0, x1, y1]}}, tiles from 0 to {BOARD}, "
                "x0 < x1 and y0 < y1.")
        elif a["kind"] not in area_kinds:
            err(f"{where} area {n + 1}: kind must be one of {sorted(area_kinds)}.")
    props = b.get("props")
    ids: dict[str, dict] = {}
    if not isinstance(props, list) or not 1 <= len(props) <= L["maxProps"]:
        err(f"{where}: props must list 1 to {L['maxProps']} props.")
        props = []
    for n, p in enumerate(props):
        w = f"{where} prop {n + 1}"
        if not isinstance(p, dict) or set(p) - {"id", "what", "at", "color", "scale", "enter"}:
            err(f"{w} takes id, what, at, color, scale and enter.")
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not _ID.match(pid) or pid in ids:
            err(f"{w}: id must be a short lowercase name of its own.")
            continue
        if p.get("what") not in names:
            err(f"{w} ({pid}): what {p.get('what')!r} is not a library prop or one of this video's customProps.")
        at = p.get("at")
        if not (isinstance(at, list) and len(at) == 2 and all(_num(v) and 0.4 <= v <= BOARD - 0.4 for v in at)):
            err(f"{w} ({pid}): at must be [x, y] in tiles, from 0.4 to {BOARD - 0.4} (on the board).")
            continue
        if any(abs(q["at"][0] - at[0]) < 0.6 and abs(q["at"][1] - at[1]) < 0.6 for q in ids.values()):
            err(f"{w} ({pid}) stands on the same tile as another prop; move it at least 0.6 tiles away.")
        if "color" in p and p["color"] not in colors:
            err(f"{w} ({pid}): color must be one of {sorted(colors)}.")
        if "scale" in p and not (_num(p["scale"]) and 0.6 <= p["scale"] <= 1.6):
            err(f"{w} ({pid}): scale must be from 0.6 to 1.6.")
        if "enter" in p:
            timed(p, "enter", f"{w} ({pid})", start, end, "the frame it lands on")
        ids[pid] = p
    routes = b.get("routes", [])
    rids: set[str] = set()
    if not isinstance(routes, list) or len(routes) > L["maxRoutes"]:
        err(f"{where}: routes must list at most {L['maxRoutes']} routes.")
        routes = []
    for n, r in enumerate(routes):
        w = f"{where} route {n + 1}"
        pts = r.get("points") if isinstance(r, dict) else None
        if (not isinstance(r, dict) or set(r) != {"id", "points", "color", "at"} or not isinstance(r.get("id"), str)
                or not _ID.match(r["id"]) or r["id"] in rids or not isinstance(pts, list)
                or not 2 <= len(pts) <= L["maxRoutePoints"]
                or not all(isinstance(q, list) and len(q) == 2 and all(_num(v) and 0 <= v <= BOARD for v in q) for q in pts)):
            err(f"{w} must be {{\"id\", \"points\": 2 to {L['maxRoutePoints']} [x, y] on the board, \"color\", \"at\"}}.")
            continue
        if r["color"] not in colors:
            err(f"{w}: color must be one of {sorted(colors)}.")
        rids.add(r["id"])
        timed(r, "at", w, start, end, "the frame it starts to draw ahead")
    movers = b.get("movers", [])
    if not isinstance(movers, list) or len(movers) > L["maxMovers"]:
        err(f"{where}: movers must list at most {L['maxMovers']} movers.")
        movers = []
    route_at = {r["id"]: r.get("at") for r in routes if isinstance(r, dict) and r.get("id") in rids}
    for n, m in enumerate(movers):
        w = f"{where} mover {n + 1}"
        if not isinstance(m, dict) or set(m) - {"route", "what", "color", "at", "back"} or m.get("route") not in rids:
            err(f"{w} must be {{\"route\": one of the board's routes, \"what\", \"color\"?, \"at\", \"back\"?}}.")
            continue
        if m.get("what") not in set(names):
            err(f"{w}: what {m.get('what')!r} is not a library prop or one of this video's customProps.")
        if "color" in m and m["color"] not in colors:
            err(f"{w}: color must be one of {sorted(colors)}.")
        ra = route_at.get(m["route"])
        if timed(m, "at", w, start, end, "the frame it sets off") and _int(ra) and m["at"] < ra and not m.get("back"):
            err(f"{w} sets off at frame {m['at']}, before its route starts to draw at {ra}: the line leads every move.")
    pins = b.get("pins", [])
    if not isinstance(pins, list) or len(pins) > L["maxPins"]:
        err(f"{where}: pins must list at most {L['maxPins']} pins.")
        pins = []
    for n, p in enumerate(pins):
        w = f"{where} pin {n + 1}"
        if not isinstance(p, dict) or set(p) - {"on", "label", "value", "unit", "at", "side"} or p.get("on") not in ids:
            err(f"{w} must be {{\"on\": a prop id of the board, \"label\", \"value\"?, \"unit\"?, \"at\", \"side\"?}}.")
            continue
        if not _text(p.get("label"), L["labelChars"]):
            err(f"{w}: label must be 1 to {L['labelChars']} characters.")
        if "value" in p and not _text(p["value"], L["valueChars"]):
            err(f"{w}: value must be 1 to {L['valueChars']} characters.")
        if "unit" in p and not (isinstance(p["unit"], str) and len(p["unit"]) <= L["unitChars"]):
            err(f"{w}: unit must be at most {L['unitChars']} characters.")
        if "side" in p and p["side"] not in ("left", "right"):
            err(f"{w}: side must be \"left\" or \"right\".")
        timed(p, "at", w, start, end, "the frame it builds")
    cams = b.get("camera", [])
    if not isinstance(cams, list) or len(cams) > L["maxCamera"]:
        err(f"{where}: camera must list at most {L['maxCamera']} moves.")
        cams = []
    prev = start - 1
    for n, c in enumerate(cams):
        w = f"{where} camera move {n + 1}"
        if not isinstance(c, dict) or set(c) - {"at", "focus", "zoom"} or ("focus" in c and c["focus"] not in ids):
            err(f"{w} must be {{\"at\", \"focus\"?: a prop id, \"zoom\"?: 1 to {GEOMETRY['zoomMax']}}}.")
            continue
        if "zoom" in c and not (_num(c["zoom"]) and 1 <= c["zoom"] <= GEOMETRY["zoomMax"]):
            err(f"{w}: zoom must be from 1 to {GEOMETRY['zoomMax']}.")
        if timed(c, "at", w, prev + 1, end, "the frame the camera starts to move"):
            prev = c["at"]
    for key, allowed, what in (("lifts", None, "lifts"), ("cutaways", rooms, "a building that opens"),
                               ("explodes", stacks, "a stack that separates")):
        lst = b.get(key, [])
        if not isinstance(lst, list) or len(lst) > L["maxLifts"]:
            err(f"{where}: {key} must list at most {L['maxLifts']}.")
            continue
        for n, e in enumerate(lst):
            w = f"{where} {key[:-1]} {n + 1}"
            fields = {"prop", "at", "inside"} if key == "cutaways" else {"prop", "at"}
            if not isinstance(e, dict) or set(e) != fields or e.get("prop") not in ids:
                err(f"{w} must be {sorted(fields)} with prop one of the board's prop ids.")
                continue
            if allowed is not None and ids[e["prop"]].get("what") not in allowed:
                err(f"{w}: {e['prop']} ({ids[e['prop']].get('what')}) is not {what}; use one of {sorted(allowed)}.")
            if key == "cutaways" and (not isinstance(e["inside"], list) or not 1 <= len(e["inside"]) <= 3
                                      or not all(x in names for x in e["inside"])):
                err(f"{w}: inside must list 1 to 3 props shown inside it.")
            timed(e, "at", w, start, end, f"the frame the {key[:-1]} starts")


def board_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every board, for the text-layout audit: sampled once
    its first pin has built, or a second after it starts."""
    scenes_cfg = config.get("scenes") or []
    if len(scenes_cfg) != 1 or not is_iso_scene(scenes_cfg[0]):
        return []
    data = (scenes_cfg[0].get("props") or {}).get(PROPS_KEY) or {}
    boards = [b for b in data.get("boards") or [] if isinstance(b, dict) and _int(b.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    out = []
    for b, end in zip(boards, [n["start"] for n in boards[1:]] + [total]):
        pins = [p["at"] for p in b.get("pins") or [] if isinstance(p, dict) and _int(p.get("at"))]
        settled = (min(pins) if pins else b["start"]) + TIMING["pin"] + 2
        if end > b["start"]:
            out.append((min(settled, end - 1), end))
    return out
