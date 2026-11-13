"""Process Cast (TMDEV-235): the checks a Process Cast scene-config must pass
before it is written, so an unattended agent cannot ship a mistimed,
off-camera, crowded or still video.

A Process Cast video is one installed `ProcessCast` scene spanning every
frame. `props.processCast` holds the cast (drawn parts with faces), the
stations along the ground line and the events timed to the narration's words:
actors enter, hop between slots and stations, carry and hand over task cards,
split into clones and merge back, join (unit bodies add up), react and look;
props appear at stations; the camera glides or cuts between stations. The
cast never talks. The renderer's side of this contract is
renderer/remotion/src/scenes/installed/processCast/contract.ts and stage.ts.

Keep in sync: the constants, catalogues and helpers mirror contract.ts;
mcp/tests/test_process_cast.py compares them with
tests/fixtures/process_cast_contract.json, which
renderer/remotion/character-tools/sync-contract.mjs writes from the
TypeScript.

Free of the database and of I/O.
"""
from __future__ import annotations

import re

import character_kit as ck
from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "ProcessCast"
PROPS_KEY = "processCast"
STYLE_ID = "process_cast"
LIBRARY_KEY = "props"

W, H = 1080, 1920
LIMITS = {"maxCast": 6, "maxStations": 6, "maxEvents": 120, "nameChars": 14, "signChars": 14, "cardChars": 18,
          "maxUnits": 16, "maxClones": 3, "maxStillSeconds": 3, "minStationSeconds": 1.5}
TIMING = {"enter": 8, "hop": 10, "trip": 20, "glide": 20, "hand": 12, "silhouette": 2, "merge": 12, "minActorGap": 6,
          "mark": 45}
GEOMETRY = {"groundY": 1190, "stationGap": 1080, "slots": [-390, -160, 70], "stageSlots": [-420, -210, 0, 210, 420],
            "furnitureX": 330, "signY": 330, "actorW": 190, "actorH": 250, "unitPx": 80, "stageScale": 0.9,
            "overlapTolerance": 12, "tagStagger": 64, "propScale": 1.5, "focusScale": 1.3, "focusOthers": 0.85}
BODIES = ("bean", "blob", "block", "gem", "units")
TINTS = ("teal", "olive", "coral", "sky", "mustard", "plum", "cream")
ACCESSORIES = ("none", "glasses", "tuft", "sprout", "cap")
FACES = ("neutral", "happy", "curious", "proud", "surprised", "worried", "sad")
MARKS = ("question", "exclaim", "sweat", "check", "cross", "idea")
ENTRANCES = ("pop", "drop", "slide")
CAMERA_MOVES = ("glide", "cut")
EVENT_TYPES = ("enter", "move", "exit", "clone", "merge", "react", "look", "carry", "hand", "prop", "join", "focus",
               "camera")
STATION_KINDS = ("desk", "board", "door", "shelf", "machine", "server", "cell", "stage")
# Furniture widths (contract.ts STATIONS w), for the actor-to-furniture overlap check.
FURNITURE_W = {"desk": 300, "board": 300, "door": 230, "shelf": 280, "machine": 290, "server": 220, "cell": 340, "stage": 0}
CUSTOM = {"maxProps": 8, "minSide": 60, "maxSide": 400, "maxText": 18, "maxActs": 0}
_ALLOWED_IMPORT = re.compile(r"^(react|remotion|\.\./\.\./installed/processCast/(ink|contract))$")
_ALLOWED_TEXT = "react, remotion and ../../installed/processCast/ink (or contract)"
_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

SNAP_FRAMES = 2
MAX_ERRORS = 12
CHANGE_FIX = "cut or glide the camera there, or have an actor enter, hop, react, carry, hand over, clone or merge on that word"
# Events that change too little of the frame to count as a visible change.
SUBTLE = ("look",)


def is_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def clone_id(who: str, n: int) -> str:
    return f"{who}{n + 1}"


def slot_count(kind: str) -> int:
    return len(GEOMETRY["stageSlots"] if kind == "stage" else GEOMETRY["slots"])


def body_size(body: str, units: int = 1) -> tuple[int, int]:
    if body != "units":
        return GEOMETRY["actorW"], GEOMETRY["actorH"]
    n = max(1, min(units, LIMITS["maxUnits"]))
    cols = next(c for c in range(1, 17) if c * c >= n)  # contract.ts's Math.ceil(Math.sqrt(n))
    rows = -(-n // cols)
    return cols * GEOMETRY["unitPx"], rows * GEOMETRY["unitPx"]


def slot_offset(kind: str, slot: int) -> int:
    return (GEOMETRY["stageSlots"] if kind == "stage" else GEOMETRY["slots"])[slot]


def half_width(body: str, units: int, kind: str) -> float:
    w, _ = body_size(body, units)
    return w / 2 * (GEOMETRY["stageScale"] if kind == "stage" else 1)


def crowding(on: dict, kinds: dict) -> str:
    """The first two bodies at one station that overlap, or a body that overlaps
    its station's furniture, as a sentence; "" when everyone has room."""
    tol = GEOMETRY["overlapTolerance"]
    by_station: dict[str, list] = {}
    for who, s in on.items():
        by_station.setdefault(s["station"], []).append((who, s))
    for st, group in by_station.items():
        kind = kinds[st]
        spans = [(who, slot_offset(kind, s["slot"]), half_width(s["body"], s["units"], kind)) for who, s in group]
        for i, (a, xa, ha) in enumerate(spans):
            for b, xb, hb in spans[i + 1:]:
                if abs(xa - xb) < ha + hb - tol:
                    return f"{a} and {b} overlap at {st}: leave a slot between them, or put one at another station"
            if kind != "stage" and xa + ha - tol > GEOMETRY["furnitureX"] - FURNITURE_W[kind] / 2:
                return f"{a} overlaps the {kind} at {st}: put it in a slot further left"
            # the camera centres the station on the frame (W / 2): a wide body in an outer slot can reach past its edge
            if W / 2 + xa - ha < -tol or W / 2 + xa + ha > W + tol:
                return f"{a} reaches past the frame's edge at {st}: put it in a slot nearer the middle"
    return ""


def check_scene_use(visual_style: str, scenes: list) -> str:
    uses = [s for s in scenes or [] if is_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The ProcessCast scene draws a whole Process Cast video and is used only when the video's "
                    "visual_style is process_cast (chosen at the topic). Build this video's scenes from the other "
                    "components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Process Cast video is exactly one scene: {\"type\": \"generated\", \"source\": \"installed\", "
                "\"src\": \"ProcessCast\", \"startFrame\": 0, \"durationInFrames\": <totalFrames>, \"props\": "
                "{\"processCast\": {...}}}. Put every beat in its events.")
    return ""


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None):
    return ck.custom_prop_errors(custom, video_id, library, sources, CUSTOM, _ALLOWED_IMPORT, _ALLOWED_TEXT)


def check(config: dict, fps: int, word_starts: list[int], words: list[str], extra: dict,
          video_id: str = "", sources: dict | None = None, quiet=()) -> list[str]:
    """Every problem with a Process Cast config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written."""
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the cast, the stations and the events."]
    if not ck.is_int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    custom_errs, catalog, _ = custom_prop_errors(data.get("customProps"), video_id, extra[LIBRARY_KEY], sources)
    for e in custom_errs:
        err(e)
    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return frame == 0 or not snaps or any(abs(frame - w) <= SNAP_FRAMES for w in snaps)

    # ── the cast and the stations ──
    cast = data.get("cast")
    if not isinstance(cast, list) or not 1 <= len(cast) <= LIMITS["maxCast"]:
        return errors + [f"cast must list 1 to {LIMITS['maxCast']} actors."]
    actors: dict[str, dict] = {}
    for i, c in enumerate(cast):
        where = f"cast {i + 1}"
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not _ID.match(c["id"]) or c["id"] in actors:
            err(f"{where}: id must be a unique lowercase name (letters, digits, _), starting with a letter.")
            continue
        if re.search(r"\d$", c["id"]):
            err(f"{where} ({c['id']}): an id may not end in a digit; a clone of it is named with one.")
        if c.get("body") not in BODIES:
            err(f"{where} ({c['id']}): body must be one of {', '.join(BODIES)}.")
        if c.get("tint") not in TINTS:
            err(f"{where} ({c['id']}): tint must be one of {', '.join(TINTS)}.")
        if c.get("accessory", "none") not in ACCESSORIES:
            err(f"{where} ({c['id']}): accessory must be one of {', '.join(ACCESSORIES)}.")
        if "name" in c and (not isinstance(c["name"], str) or not c["name"].strip() or len(c["name"]) > LIMITS["nameChars"]):
            err(f"{where} ({c['id']}): name must be text of 1 to {LIMITS['nameChars']} characters.")
        units = c.get("units", 1)
        if c.get("body") == "units":
            if not ck.is_int(units) or not 1 <= units <= LIMITS["maxUnits"]:
                err(f"{where} ({c['id']}): units must be a whole number from 1 to {LIMITS['maxUnits']}.")
                units = 1
        elif "units" in c:
            err(f"{where} ({c['id']}): units is for a units body only.")
        actors[c["id"]] = {**c, "units": units if ck.is_int(units) else 1}
    stations = data.get("stations")
    if not isinstance(stations, list) or not 1 <= len(stations) <= LIMITS["maxStations"]:
        return errors + [f"stations must list 1 to {LIMITS['maxStations']} stations."]
    st_index: dict[str, int] = {}
    for i, s in enumerate(stations):
        where = f"station {i + 1}"
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not _ID.match(s["id"]) or s["id"] in st_index \
                or s["id"] in actors:
            err(f"{where}: id must be a unique lowercase name, not also a cast id.")
            continue
        if s.get("kind") not in STATION_KINDS:
            err(f"{where} ({s['id']}): kind must be one of {', '.join(STATION_KINDS)}.")
        if not isinstance(s.get("sign"), str) or not s["sign"].strip() or len(s["sign"]) > LIMITS["signChars"]:
            err(f"{where} ({s['id']}): sign must be text of 1 to {LIMITS['signChars']} characters.")
        st_index[s["id"]] = i
    kinds = {sid: stations[i].get("kind") if stations[i].get("kind") in STATION_KINDS else "stage"
             for sid, i in st_index.items()}

    # ── the events, played forward ──
    events = data.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= LIMITS["maxEvents"]:
        return errors + [f"events must list 1 to {LIMITS['maxEvents']} events."]
    frames = [e.get("frame") if isinstance(e, dict) else None for e in events]
    if not all(ck.is_int(f) for f in frames):
        return errors + ["Every event needs a whole-number frame."]
    if any(b < a for a, b in zip(frames, frames[1:])):
        err("List the events in frame order.")
    last_ok = total - TIMING["enter"]

    on: dict[str, dict] = {}    # actor id (clones too) -> {station, slot, busy_until, last, card, units, clones}
    first = stations[0].get("id") if isinstance(stations[0], dict) else None
    cam = {"station": first if isinstance(first, str) else None, "at": -10**6}
    leaving: dict[tuple, int] = {}  # (station, slot) -> the frame an exiting actor is gone from it
    changes: set[int] = {0}
    seen_stations = {cam["station"]}

    def present(who) -> dict | None:
        return on.get(who) if isinstance(who, str) else None

    def free_slot(station: str, slot, f: int, who: str = "") -> str:
        if not ck.is_int(slot) or not 0 <= slot < slot_count(kinds[station]):
            return f"slot must be a whole number from 0 to {slot_count(kinds[station]) - 1} at a {kinds[station]} station"
        taken = [a for a, s in on.items() if a != who and s["station"] == station and s["slot"] == slot]
        if not taken and leaving.get((station, slot), -1) > f:
            return f"slot {slot} at {station} is still being left until frame {leaving[(station, slot)]}"
        return f"slot {slot} at {station} is taken by {taken[0]}" if taken else ""

    def at_camera(station: str, f: int) -> bool:
        return station == cam["station"]

    if not any(isinstance(e, dict) and e.get("type") == "enter" and e.get("frame") == 0 for e in events):
        err("Nothing enters at frame 0, so the video opens on an empty station. Bring the first actor in at frame 0.")

    for e, f in zip(events, frames):
        if isinstance(e, dict):
            # an id or a name that is not text matches nothing, and must not crash a lookup
            e = {k: (v if not isinstance(v, (list, dict)) else None) for k, v in e.items()}
        t = e.get("type") if isinstance(e, dict) else None
        at = f"The {t or 'event'} at frame {f}"
        if t not in EVENT_TYPES:
            err(f"{at}: type must be one of {', '.join(EVENT_TYPES)}.")
            continue
        if not 0 <= f <= last_ok:
            err(f"{at}: it must start between frame 0 and {last_ok} (an event closer to the end is cut before it is seen).")
            continue
        w = window_at(f, quiet)
        if w:
            err(f"{at} starts inside an insert ({window_text(w)}), where the stage is hidden; move it to a word at "
                f"{w[1]} or later, or before {w[0]}.")
        if not on_word(f):
            err(f"{at}: events land on words; move it within {SNAP_FRAMES} frames of a word's start.")
        if t not in SUBTLE:
            changes.add(f)
        who = e.get("who")
        if t == "camera":
            st = e.get("station")
            if st not in st_index:
                err(f"{at}: station must be one of the stations ({', '.join(st_index)}).")
                continue
            if e.get("move", "glide") not in CAMERA_MOVES:
                err(f"{at}: move must be glide or cut.")
            if f - cam["at"] < LIMITS["minStationSeconds"] * fps:
                err(f"{at}: the camera moved {f - cam['at']} frames ago; it stays at a station at least "
                    f"{LIMITS['minStationSeconds']} s.")
            if st == cam["station"]:
                err(f"{at}: the camera is already at {st}.")
            cam = {"station": st, "at": f}
            seen_stations.add(st)
            continue
        if t == "prop":
            st = e.get("station")
            if st not in st_index:
                err(f"{at}: station must be one of the stations.")
                continue
            prop = e.get("prop")
            if not isinstance(prop, str) or prop not in catalog:
                err(f"{at}: prop must be from the library or the video's customProps.")
                continue
            limit = catalog[prop]["text"]
            text = e.get("text")
            if text is not None and (limit == 0 or not isinstance(text, str) or len(text) > limit):
                err(f"{at}: the {prop} prop " + ("has no text slot." if limit == 0 else f"takes at most {limit} characters."))
            if not at_camera(st, f):
                err(f"{at}: the camera is at {cam['station']}, so a prop at {st} appears off screen; show it where "
                    "the camera is.")
            continue
        if t == "focus":
            if who != "" and not present(who):
                err(f"{at}: who must be an actor on stage, or \"\" to end the focus.")
            elif who and not at_camera(on[who]["station"], f):
                err(f"{at}: {who} is off screen.")
            continue
        if t == "hand":
            a, b = present(e.get("from")), present(e.get("to"))
            if not a or not b or a is b:
                err(f"{at}: from and to must be two different actors on stage.")
                continue
            if not a["card"]:
                err(f"{at}: {e['from']} holds no card to hand over (give it one with carry first).")
            if a["station"] != b["station"]:
                err(f"{at}: a card is handed between two actors at the same station.")
            elif not at_camera(a["station"], f):
                err(f"{at}: it happens off screen, at {a['station']}.")
            b["card"], a["card"] = a["card"], ""
            for s in (a, b):
                s["busy_until"] = max(s["busy_until"], f + TIMING["hand"])
            continue
        # every other event names one actor
        if t == "enter":
            if who not in actors:
                err(f"{at}: who must be a cast id ({', '.join(actors)}).")
                continue
            if who in on:
                err(f"{at}: {who} is already on stage.")
                continue
            st = e.get("station")
            if st not in st_index:
                err(f"{at}: station must be one of the stations.")
                continue
            slot_err = free_slot(st, e.get("slot"), f)
            if slot_err:
                err(f"{at}: {slot_err}.")
                continue
            if e.get("from", "pop") not in ENTRANCES:
                err(f"{at}: from must be one of {', '.join(ENTRANCES)}.")
            if not at_camera(st, f):
                err(f"{at}: the camera is at {cam['station']}, so {who} would enter off screen.")
            on[who] = {"station": st, "slot": e["slot"], "busy_until": f + TIMING["enter"], "last": f, "card": "",
                       "units": actors[who]["units"], "body": actors[who].get("body"), "clones": [], "of": ""}
            crowd = crowding(on, kinds)
            if crowd:
                err(f"{at}: {crowd}.")
            continue
        s = present(who)
        if not s:
            err(f"{at}: who must be an actor on stage (one that has entered, or a clone named like {who or 'id'}2).")
            continue
        if f < s["busy_until"] and t not in ("react", "look"):
            err(f"{at}: {who} is still busy until frame {s['busy_until']} (entering, hopping or handing over); "
                "only a reaction or a look may come sooner.")
        elif f - s["last"] < TIMING["minActorGap"] and t not in ("react", "look"):
            err(f"{at}: it comes {f - s['last']} frames after {who}'s last change; closer than "
                f"{TIMING['minActorGap']} frames reads as a twitch.")
        if not at_camera(s["station"], f) and t != "move":
            err(f"{at}: {who} is at {s['station']} and the camera is at {cam['station']}, so it happens off screen.")
        s["last"] = f
        if t == "move":
            st = e.get("station")
            if st not in st_index:
                err(f"{at}: station must be one of the stations.")
                continue
            slot_err = free_slot(st, e.get("slot"), f, who)
            if slot_err:
                err(f"{at}: {slot_err}.")
                continue
            trip = st != s["station"]
            if trip and not (at_camera(s["station"], f) or at_camera(st, f)):
                err(f"{at}: {who} travels between two stations the camera shows neither of.")
            s["busy_until"] = f + (TIMING["trip"] if trip else TIMING["hop"])
            s["station"], s["slot"] = st, e["slot"]
        elif t == "exit":
            # the renderer draws it leaving for TIMING["enter"] frames: its slot (and its clones') is not free yet
            for gone in [who, *s["clones"]]:
                g = on.pop(gone, None)
                if g:
                    leaving[(g["station"], g["slot"])] = f + TIMING["enter"]
        elif t == "clone":
            n = e.get("count")
            if s["of"]:
                err(f"{at}: {who} is a clone; only an original actor splits.")
                continue
            if not ck.is_int(n) or not 2 <= n <= LIMITS["maxClones"]:
                err(f"{at}: count is how many there are after the split, 2 to {LIMITS['maxClones']}.")
                continue
            free = [k for k in range(slot_count(kinds[s["station"]]))
                    if not any(o["station"] == s["station"] and o["slot"] == k for o in on.values())]
            if len(free) < n - 1:
                err(f"{at}: {s['station']} has {len(free)} free slots; {n - 1} clones need {n - 1}.")
                continue
            for k in range(1, n):
                cid = clone_id(who, k)
                if cid in on:
                    err(f"{at}: {cid} is already on stage; merge the clones first.")
                    break
                on[cid] = {**s, "slot": free[k - 1], "busy_until": f + TIMING["enter"], "card": "", "clones": [],
                           "of": who}
                s["clones"].append(cid)
        elif t == "merge":
            if not s["clones"]:
                err(f"{at}: {who} has no clones on stage to merge.")
                continue
            for cid in s["clones"]:
                on.pop(cid, None)
            s["clones"] = []
            s["busy_until"] = f + TIMING["merge"]
        elif t == "join":
            o = present(e.get("with"))
            if not o or e.get("with") == who:
                err(f"{at}: with must be another actor on stage.")
                continue
            if s["body"] != "units" or o["body"] != "units":
                err(f"{at}: only two units bodies join (their cubes add up).")
                continue
            if o["station"] != s["station"]:
                err(f"{at}: the two must stand at the same station.")
                continue
            if s["units"] + o["units"] > LIMITS["maxUnits"]:
                err(f"{at}: together they make {s['units'] + o['units']} units; at most {LIMITS['maxUnits']}.")
            s["units"] += o["units"]
            on.pop(e["with"], None)
            s["busy_until"] = f + TIMING["merge"]
        if t in ("move", "clone", "join"):
            crowd = crowding(on, kinds)
            if crowd:
                err(f"{at}: {crowd}.")
        if t == "react":
            if e.get("face") not in FACES:
                err(f"{at}: face must be one of {', '.join(FACES)}.")
            if "mark" in e and e["mark"] not in MARKS:
                err(f"{at}: mark must be one of {', '.join(MARKS)}.")
        elif t == "look":
            target = e.get("at")
            if not (target == "front" or target in st_index or target in on):
                err(f"{at}: at must be an actor on stage, a station or \"front\".")
        elif t == "carry":
            text = e.get("text")
            if not isinstance(text, str) or len(text) > LIMITS["cardChars"]:
                err(f"{at}: text is the card's words, at most {LIMITS['cardChars']} characters (\"\" puts it down).")
                continue
            s["card"] = text

    for sid in st_index:
        if sid not in seen_stations:
            err(f"The camera never shows station {sid}; glide there, or leave the station out.")

    still = round(LIMITS["maxStillSeconds"] * fps)
    prev = 0
    for c in sorted(c for c in changes if 0 <= c < total) + [total]:
        for a, b in uncovered(prev, c, quiet):
            if b - a > still:
                err(f"Nothing changes from frame {a} to {b} ({(b - a) / fps:.1f} s); the longest still stretch allowed "
                    f"is {LIMITS['maxStillSeconds']} s. Add a reaction, a hop, a card or a camera move.")
        prev = c
    return errors


# ── what the audit and the picture checks read ────────────────────────────────

def _data(config: dict) -> dict:
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_scene(scenes[0]):
        return {}
    d = (scenes[0].get("props") or {}).get(PROPS_KEY)
    return d if isinstance(d, dict) else {}


def audit_windows(config: dict) -> list[tuple[int, int]]:
    """(first, end) for the text-layout audit: each stretch the camera holds a
    station, sampled once it has arrived and the entrances have settled."""
    data = _data(config)
    total = config.get("totalFrames") if ck.is_int(config.get("totalFrames")) else 0
    starts = [0] + [e["frame"] for e in data.get("events") or []
                    if isinstance(e, dict) and e.get("type") == "camera" and ck.is_int(e.get("frame"))]
    windows = [(a, b) for a, b in zip(starts, starts[1:] + [total]) if b > a]
    return ck.sample_windows(windows, TIMING["glide"] + TIMING["enter"], TIMING["enter"])


def change_frames(data: dict) -> list[int]:
    return [e.get("frame") for e in data.get("events") or []
            if isinstance(e, dict) and e.get("type") not in SUBTLE and ck.is_int(e.get("frame"))]


def first_frame_problem(data: dict) -> str | None:
    if not any(isinstance(e, dict) and e.get("type") == "enter" and ck.is_int(e.get("frame")) and e["frame"] <= 3
               for e in data.get("events") or []):
        return ("no actor enters by frame 3, so the video opens on an empty station. Bring the first actor in at "
                "frame 0")
    return None


def sample_text(data: dict, prop_id) -> str:
    for e in data.get("events") or []:
        if isinstance(e, dict) and e.get("type") == "prop" and e.get("prop") == prop_id and isinstance(e.get("text"), str):
            return e["text"]
    return ""
