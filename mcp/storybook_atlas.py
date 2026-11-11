"""Storybook Atlas: the checks a Storybook Atlas scene-config must pass before
it is written, so an unattended agent cannot ship a mistimed, crowded or
still video.

A Storybook Atlas video is one installed `StorybookAtlas` scene spanning
every frame. The agent writes no scene code: `props.storybookAtlas` holds the
guide's waistcoat, the cast (people made of knobs), and 3 to 5 chapters, each
a plaque, a backdrop and events timed to the narration's word frames: the
guide and people walking and posing, props from a fixed library (or drawn for
the video), acts, tags, and plates (constellation lettering, a gauge, a
morph). The renderer's side of this contract is
renderer/remotion/src/scenes/installed/storybookAtlas/contract.ts and stage.ts.

Keep in sync: LIMITS, TIMING, STAGE, the catalogues and actor_at mirror
contract.ts and stage.ts. Both sides run the shared cases in
mcp/tests/fixtures/storybook_atlas_contract.json, and the pack's `extra` block
carries the prop catalogue the renderer reads from catalogue.json, so a drift
fails a test instead of a render.

Free of the database and of I/O: the caller passes the style, the config,
the narration's word start frames, and the pack's `extra` block.
"""
from __future__ import annotations

import math
import re

SCENE_SRC = "StorybookAtlas"
PROPS_KEY = "storybookAtlas"
STYLE_ID = "storybook_atlas"

W, H = 1080, 1920

LIMITS = {
    "chapters": (3, 5),
    "chapterMinSeconds": 8,
    "cast": 4,
    "onStage": 2,
    "propsOnStage": 6,
    "title": 18,
    "titleLines": 2,
    "byline": 28,
    "name": 24,
    "tag": 24,
    "words": 2,
    "wordChars": 10,
    "gaugeLabel": 24,
    "quietSeconds": 4,
    "plateSeconds": (2.5, 8),
    "propScale": (0.6, 1.4),
}
TIMING = {
    "onWord": 2, "walkSpeed": 9, "walkHold": 2, "propIn": 10, "act": 48, "cycleHold": 4, "switchFade": 4,
    "tagIn": 6, "plateOpen": 10, "pushFrames": 14, "pushScale": 4, "whiteHold": 2, "dissolve": 5,
    "wipeFrames": 14, "endMargin": 20,
}
STAGE = {
    "left": 60, "right": 1020, "top": 430, "floor": 1344, "wallBase": (620, 1240), "guideHome": 210,
    "plate": {"x": 90, "y": 450, "w": 900, "h": 860},
}
ACTS = ("wobble", "bounce", "shake", "spin", "swing", "pulse", "glow", "switch", "cycle")
PROP_ENTRANCES = ("pop", "drop", "slide", "rise", "fade")
FACINGS = ("left", "right")
ENTERS = ("push", "wipe")
GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
EVENT_TYPES = ("guide", "person", "prop", "act", "tag", "constellation", "gauge", "morph")
PLATE_EVENTS = ("constellation", "gauge", "morph")
# The walk drawings are the scene's; an event names the pose the walk ends in.
WALK_POSES = ("walk1", "walk2", "walk3", "walk4")

# Footprints on the floor, for the checks that two things do not stand in one
# place: half the width of a person's body and of the guide's, at rest.
PERSON_HALF = 80
GUIDE_HALF = 70
# A tag's width: EB Garamond italic at 32 px averages about 14 px a character,
# plus its padding and rule.
TAG_CHAR_PX, TAG_PAD_PX = 14, 32
# Guide and people stand with their feet inside these x limits.
ACTOR_X = (110, 970)

CUSTOM = {"maxProps": 8, "minSide": 60, "maxSide": 700, "maxStates": 4, "maxActs": 4}
_CUSTOM_FILE = re.compile(r"^prop-[a-z0-9-]{1,40}$")
# What a custom prop's source may not contain, and why: each one either cost a
# render many times over on the CPU renderer, makes frames differ between
# renders, cannot be drawn into the prop's bitmap, or reaches outside the drawing.
FORBIDDEN_SOURCE = (
    (re.compile(r"""<filter\b|<fe[A-Z]|(?<![\w.])filter\s*=\s*["'{]|\bfilter\s*:\s*["'`]|style=\{\{[^}]*\bfilter\s*:"""),
     "an SVG filter (blur, shadow, turbulence): the book is flat ink and colour"),
    (re.compile(r"\brequire\s*\("), "require(): a prop names what it uses with import"),
    (re.compile(r"(?i)(linear|radial)Gradient"), "a gradient: the book is flat ink and colour"),
    (re.compile(r"<pattern\b"), "an SVG pattern of its own: use Sh's pen hatching"),
    (re.compile(r"strokeDasharray|stroke-dasharray"), "a dashed stroke"),
    (re.compile(r"Math\.random|Date\.now|new Date\b"), "randomness or the clock: every render must draw the same frames"),
    (re.compile(r"<text\b|<tspan\b"), "SVG text: fonts do not load inside a prop's bitmap; draw writing as ink strokes"),
    (re.compile(r"<image\b|<img\b|<foreignObject\b|dangerouslySetInnerHTML|\bfetch\(|\bimport\("),
     "an image, embedded HTML or a fetch: a prop is drawn from shapes only"),
)
_IMPORT = re.compile(r"""^\s*(?:import|export)\b[^;]*?from\s+["']([^"']+)["']|^\s*import\s+["']([^"']+)["']""", re.M)
_ALLOWED_IMPORT = re.compile(r"^(react|\.\./\.\./installed/storybookAtlas/(ink|palette))$")

_ID = re.compile(r"^[a-z0-9_]{1,24}$")
MAX_ERRORS = 12


def is_storybook_scene(scene) -> bool:
    """Any scene naming StorybookAtlas, whatever its type: the use rule must
    catch a mistyped one too."""
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Storybook Atlas video is exactly the one
    StorybookAtlas scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_storybook_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The StorybookAtlas scene draws a whole Storybook Atlas video and is used only when "
                    "the video's visual_style is storybook_atlas (chosen at the topic). Build this "
                    "video's scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Storybook Atlas video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"StorybookAtlas\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"storybookAtlas\": {...}}}. Put every beat in its chapters.")
    return ""


def wrap_title(title: str) -> list[str]:
    """Split a title into lines of at most LIMITS['title'] characters, at
    spaces: contract.ts's wrapTitle."""
    out: list[str] = []
    line = ""
    for word in title.strip().split():
        nxt = f"{line} {word}" if line else word
        if len(nxt) > LIMITS["title"] and line:
            out.append(line)
            line = word
        else:
            line = nxt
    if line:
        out.append(line)
    return out


# ── the walk rule (stage.ts actorAt) ─────────────────────────────────────────
def nearer_edge(x: float) -> float:
    return -160 if x < W / 2 else W + 160


def walk_frames(a: float, b: float) -> int:
    return math.ceil(abs(b - a) / TIMING["walkSpeed"])


def _walk_x(walk, frame):
    done = frame - walk["at"]
    if done >= walk_frames(walk["from"], walk["to"]):
        return walk["to"]
    return walk["from"] + math.copysign(1, walk["to"] - walk["from"]) * done * TIMING["walkSpeed"]


def actor_at(moves: list[dict], frame: int, start: float | None) -> dict:
    """An actor's x, visibility and whether it is walking at `frame`, given its
    moves in one chapter (sorted by `at`): stage.ts's actorAt."""
    x = start if start is not None else 0
    visible = start is not None
    walk = None
    for m in moves:
        if m["at"] > frame:
            break
        if walk:
            x = _walk_x(walk, m["at"])
            if x == walk["to"] and walk["exit"]:
                visible = False
            walk = None
        if m.get("exit"):
            if visible:
                walk = {"from": x, "to": nearer_edge(x), "at": m["at"], "exit": True}
        elif not visible:
            target = m.get("x", W / 2)
            x = nearer_edge(target)
            visible = True
            walk = {"from": x, "to": target, "at": m["at"], "exit": False}
        elif m.get("x") is not None and m["x"] != x:
            walk = {"from": x, "to": m["x"], "at": m["at"], "exit": False}
    if walk:
        done = frame - walk["at"]
        if done < walk_frames(walk["from"], walk["to"]):
            return {"x": _walk_x(walk, frame), "visible": True, "walking": True}
        x = walk["to"]
        if walk["exit"]:
            visible = False
    return {"x": x, "visible": visible, "walking": False}


def walk_ends(moves: list[dict], start: float | None) -> list[int]:
    """The frames each walk in `moves` arrives (or would have, had nothing cut it short)."""
    out = []
    for m in moves:
        state = actor_at(moves, m["at"], start)
        here = state["x"] if state["visible"] else None
        if m.get("exit") and here is not None:
            out.append(m["at"] + walk_frames(here, nearer_edge(here)))
        elif here is None and not m.get("exit"):
            t = m.get("x", W / 2)
            out.append(m["at"] + walk_frames(nearer_edge(t), t))
        elif m.get("x") is not None and here is not None and m["x"] != here:
            out.append(m["at"] + walk_frames(here, m["x"]))
    return out


def tag_width(text: str) -> float:
    return len(text) * TAG_CHAR_PX + TAG_PAD_PX


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None) -> tuple[list[str], dict]:
    """Problems with config's customProps, and the catalogue with them added
    to the library's. `sources` maps each src to its file's text, or is None
    to skip the source checks (no files to read)."""
    errs: list[str] = []
    catalog = dict(library)
    if custom is None:
        return errs, catalog
    if not isinstance(custom, list) or len(custom) > CUSTOM["maxProps"]:
        return [f"customProps must be a list of at most {CUSTOM['maxProps']} props."], catalog
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
        box = c.get("box")
        if not (isinstance(box, list) and len(box) == 2 and all(_int(v) and CUSTOM["minSide"] <= v <= CUSTOM["maxSide"] for v in box)):
            errs.append(f"{where} ({cid}): box is [width, height] at scale 1, whole pixels from {CUSTOM['minSide']} "
                        f"to {CUSTOM['maxSide']}.")
            continue
        if c.get("place") not in ("floor", "wall"):
            errs.append(f"{where} ({cid}): place must be \"floor\" or \"wall\".")
            continue
        states = c.get("states", 1)
        if not _int(states) or not 1 <= states <= CUSTOM["maxStates"]:
            errs.append(f"{where} ({cid}): states is how many drawings it has, 1 to {CUSTOM['maxStates']}.")
            continue
        acts = c.get("acts", [])
        if (not isinstance(acts, list) or not 1 <= len(acts) <= CUSTOM["maxActs"] or not all(a in ACTS for a in acts)
                or (("switch" in acts or "cycle" in acts) and states < 2)):
            errs.append(f"{where} ({cid}): acts is a list of 1 to {CUSTOM['maxActs']} of {', '.join(ACTS)}; "
                        "switch and cycle need a second state.")
            continue
        portal = c.get("portal")
        if portal is not None and not (isinstance(portal, list) and len(portal) == 2 and all(_num(v) for v in portal)
                                       and abs(portal[0]) <= box[0] / 2 and -box[1] <= portal[1] <= 0):
            errs.append(f"{where} ({cid}): portal is a point inside its box: [x, y] with the base at [0, 0] and y "
                        "negative upward.")
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
                            "and ../../installed/storybookAtlas/ink (or palette).")
            if not re.search(r"export\s+default\b", body):
                errs.append(f"{where} ({cid}): the file must default-export the drawing component.")
        entry = {"box": box, "place": c["place"], "states": states, "acts": acts}
        if portal is not None:
            entry["portal"] = portal
        catalog[cid] = entry
    return errs, catalog


def prop_box(spec: dict, x: float, y: float | None, scale: float) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of a placed prop, in frame pixels."""
    w, h = spec["box"]
    base = STAGE["floor"] if spec["place"] == "floor" else (y if y is not None else 900)
    return (x - w * scale / 2, base - h * scale, x + w * scale / 2, base)


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "",
          sources: dict | None = None) -> list[str]:
    """Every problem with a Storybook Atlas config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block. A config's customProps join the library for this video;
    `sources` maps their src to the file's text (None skips the source checks)."""
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the guide, the cast and the chapters."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    custom_errs, catalog = custom_prop_errors(data.get("customProps"), video_id, extra["props"], sources)
    for e in custom_errs:
        err(e)

    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["onWord"] for w in snaps)

    # ── the guide and the cast ──
    guide = data.get("guide")
    if not isinstance(guide, dict) or guide.get("coat") not in extra["coats"]:
        err(f"guide must be {{\"coat\": ...}} with coat one of {', '.join(extra['coats'])}.")
    cast = data.get("cast", [])
    people: dict[str, dict] = {}
    if not isinstance(cast, list) or len(cast) > LIMITS["cast"]:
        err(f"cast must be a list of at most {LIMITS['cast']} people.")
        cast = []
    for i, c in enumerate(cast):
        where = f"cast {i + 1}"
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not _ID.match(c["id"]) or c["id"] in people:
            err(f"{where}: id must be lowercase letters, digits or _, and different from every other cast id.")
            continue
        name = c.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= LIMITS["name"]:
            err(f"cast {c['id']}: name is the text on their tag, 1 to {LIMITS['name']} characters.")
        for knob, values in extra["knobs"].items():
            if c.get(knob) not in values:
                err(f"cast {c['id']}: {knob} must be one of {', '.join(values)}.")
        people[c["id"]] = c

    # ── chapters ──
    chapters = data.get("chapters")
    lo, hi = LIMITS["chapters"]
    if not isinstance(chapters, list) or not lo <= len(chapters) <= hi:
        return errors + [f"chapters must be a list of {lo} to {hi} chapters."]
    starts = []
    for i, ch in enumerate(chapters):
        s = ch.get("start") if isinstance(ch, dict) else None
        starts.append(s if _int(s) else -1)
    if starts[0] != 0:
        err("The first chapter must start at frame 0.")
    min_len = round(LIMITS["chapterMinSeconds"] * fps)
    spans = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else total
        spans.append((s, end))
        if i > 0 and (s <= starts[i - 1] or not on_word(s)):
            err(f"Chapter {i + 1} must start after chapter {i} and within {TIMING['onWord']} frames of a word's "
                "first frame.")
        if end - s < min_len:
            err(f"Chapter {i + 1} lasts {(end - s) / fps:.1f} s; a chapter lasts at least "
                f"{LIMITS['chapterMinSeconds']} s.")

    still = round(LIMITS["quietSeconds"] * fps)
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            err(f"Chapter {i + 1} must be an object.")
            continue
        _check_chapter(ch, i, spans[i], chapters, spans, catalog, people, extra, fps, on_word, still, err)
    return errors


def _check_chapter(ch, i, span, chapters, spans, catalog, people, extra, fps, on_word, still, err) -> None:
    where = f"Chapter {i + 1}"
    start, end = span
    title = ch.get("title")
    if not isinstance(title, str) or not title.strip():
        err(f"{where}: title is the plaque's title.")
    else:
        lines = wrap_title(title)
        if len(lines) > LIMITS["titleLines"] or any(len(line) > LIMITS["title"] for line in lines):
            err(f"{where}: the title must fit {LIMITS['titleLines']} lines of {LIMITS['title']} characters.")
    byline = ch.get("byline")
    if not isinstance(byline, str) or not 1 <= len(byline.strip()) <= LIMITS["byline"]:
        err(f"{where}: byline is the plaque's small italic line (a place or a date), 1 to {LIMITS['byline']} characters.")
    if ch.get("backdrop") not in extra["backdrops"]:
        err(f"{where}: backdrop must be one of {', '.join(extra['backdrops'])}.")
    if i > 0 and ch.get("enter", "wipe") not in ENTERS:
        err(f"{where}: enter must be one of {', '.join(ENTERS)}.")
    events = ch.get("events")
    if not isinstance(events, list) or not events:
        err(f"{where}: events must list what happens in the chapter.")
        return
    evs = []
    for k, e in enumerate(events):
        if not isinstance(e, dict) or e.get("type") not in EVENT_TYPES or not _int(e.get("at")):
            err(f"{where}, event {k + 1}: an event is an object with a type ({', '.join(EVENT_TYPES)}) and a whole-"
                "number frame `at`.")
            continue
        evs.append(e)
    evs.sort(key=lambda e: e["at"])
    last = end - TIMING["endMargin"]
    for e in evs:
        if not start <= e["at"] < last:
            err(f"{where}: the {e['type']} at frame {e['at']} must come from frame {start} to {last - 1} (no later "
                f"than {TIMING['endMargin']} frames before the chapter ends).")
        elif not on_word(e["at"]):
            err(f"{where}: the {e['type']} at frame {e['at']} must start within {TIMING['onWord']} frames of a "
                "word's first frame.")

    # plates first: they hold the stage while they are open
    plates = []
    for e in evs:
        if e["type"] not in PLATE_EVENTS:
            continue
        until = e.get("until")
        lo, hi = LIMITS["plateSeconds"]
        if not _int(until) or not lo * fps <= until - e["at"] <= hi * fps:
            err(f"{where}: the {e['type']} at frame {e['at']} needs `until`, {lo} to {hi} s after it starts.")
            continue
        if until + TIMING["plateOpen"] > end - TIMING["endMargin"] // 2:
            err(f"{where}: the {e['type']} at frame {e['at']} must close before the chapter ends.")
        for p in plates:
            if e["at"] < p[1] + TIMING["plateOpen"]:
                err(f"{where}: the {e['type']} at frame {e['at']} opens before the plate at frame {p[0]} has closed.")
        plates.append((e["at"], until))
        _check_plate(e, where, catalog, err)

    def in_plate(f: int) -> bool:
        return any(a <= f < u + TIMING["plateOpen"] for a, u in plates)

    placed: dict[str, dict] = {}
    guide_moves, moves = [], {}
    for e in evs:
        t = e["type"]
        if t in PLATE_EVENTS:
            continue
        if in_plate(e["at"]):
            err(f"{where}: the {t} at frame {e['at']} comes while a plate is open; nothing else happens on stage then.")
        if t == "guide":
            if not _check_actor(e, where, "the guide", [p for p in extra["guidePoses"] if p not in WALK_POSES], err):
                continue
            guide_moves.append(e)
        elif t == "person":
            who = e.get("who")
            if who not in people:
                err(f"{where}: the person at frame {e['at']} names {who!r}, who is not in the cast.")
                continue
            if not e.get("exit") and not _check_actor(e, where, who, [p for p in extra["personPoses"] if p not in WALK_POSES], err):
                continue
            moves.setdefault(who, []).append(e)
        elif t == "prop":
            _check_prop(e, where, catalog, placed, err)
        elif t == "act":
            p = placed.get(e.get("id"))
            if not p:
                err(f"{where}: the act at frame {e['at']} names {e.get('id')!r}, which is not on stage yet.")
            elif e["at"] < p["at"] + TIMING["propIn"]:
                err(f"{where}: the act at frame {e['at']} starts before {e['id']} has landed (frame "
                    f"{p['at'] + TIMING['propIn']}).")
            elif e.get("act") not in catalog[p["prop"]]["acts"]:
                err(f"{where}: {p['prop']} can do {', '.join(catalog[p['prop']]['acts'])}, not {e.get('act')!r}.")
        elif t == "tag":
            text = e.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= LIMITS["tag"]:
                err(f"{where}: the tag at frame {e['at']} needs text of 1 to {LIMITS['tag']} characters.")
            elif e.get("on") not in placed:
                err(f"{where}: the tag at frame {e['at']} goes on {e.get('on')!r}, which is not a prop on stage yet.")
            else:
                placed[e["on"]]["tag"] = text

    if len(placed) > LIMITS["propsOnStage"]:
        err(f"{where} puts {len(placed)} props on stage; at most {LIMITS['propsOnStage']} keep a page readable.")

    # people on stage at once, and where everyone comes to rest
    ends = {w: walk_ends(m, None) for w, m in moves.items()}
    guide_ends = walk_ends(guide_moves, STAGE["guideHome"])
    checkpoints = sorted({e["at"] for e in evs} | {f for fs in ends.values() for f in fs} | set(guide_ends))
    for f in checkpoints:
        if not start <= f < end:
            continue
        here = {w: actor_at(m, f, None) for w, m in moves.items()}
        on = [w for w, s in here.items() if s["visible"]]
        if len(on) > LIMITS["onStage"]:
            err(f"{where}: at frame {f} there are {len(on)} people on stage; at most {LIMITS['onStage']}.")
            break
        g = actor_at(guide_moves, f, STAGE["guideHome"])
        props_now = [p for p in placed.values() if p["at"] <= f]
        _check_layout(where, f, here, g, props_now, catalog, people, err)

    # a push leaves through the previous chapter's door or porthole
    if i > 0 and chapters[i].get("enter", "wipe") == "push":
        prev = chapters[i - 1].get("events") if isinstance(chapters[i - 1], dict) else None
        cut = start - TIMING["pushFrames"]
        portals = [e for e in prev or [] if isinstance(e, dict) and e.get("type") == "prop"
                   and catalog.get(e.get("prop"), {}).get("portal") and _int(e.get("at")) and e["at"] + TIMING["propIn"] <= cut]
        if not portals:
            err(f"{where} enters with a push, which goes through a prop with a portal (a door, a porthole...) on "
                f"stage in chapter {i} by frame {cut}; place one, or enter with a wipe.")

    # nothing new for too long
    changes = sorted({start} | {e["at"] for e in evs} | {f for fs in ends.values() for f in fs} | set(guide_ends)
                     | {u + TIMING["plateOpen"] for _, u in plates} | {e["thenAt"] for e in evs if _int(e.get("thenAt"))})
    changes = [c for c in changes if start <= c < end] + [end]
    for a, b in zip(changes, changes[1:]):
        if in_plate(a):
            continue
        if b - a > still:
            err(f"{where}: nothing changes on stage from frame {a} to {b} ({(b - a) / fps:.1f} s); something "
                f"should happen at least every {LIMITS['quietSeconds']} s.")
            break


def _check_actor(e, where, name, poses, err) -> bool:
    ok = True
    x = e.get("x")
    if x is not None and not (_num(x) and ACTOR_X[0] <= x <= ACTOR_X[1]):
        err(f"{where}: {name} at frame {e['at']}: x is where the feet stop, {ACTOR_X[0]} to {ACTOR_X[1]}.")
        ok = False
    if "pose" in e and e["pose"] not in poses:
        err(f"{where}: {name} at frame {e['at']}: pose must be one of {', '.join(poses)}.")
        ok = False
    if "facing" in e and e["facing"] not in FACINGS:
        err(f"{where}: {name} at frame {e['at']}: facing must be left or right.")
        ok = False
    return ok


def _check_prop(e, where, catalog, placed, err) -> None:
    pid, prop = e.get("id"), e.get("prop")
    if not isinstance(pid, str) or not _ID.match(pid) or pid in placed:
        err(f"{where}: the prop at frame {e['at']} needs an id of its own (lowercase letters, digits or _).")
        return
    spec = catalog.get(prop)
    if not spec:
        err(f"{where}: {prop!r} is not in the prop library or the video's customProps.")
        return
    scale = e.get("scale", 1)
    lo, hi = LIMITS["propScale"]
    if not _num(scale) or not lo <= scale <= hi:
        err(f"{where}: {pid}'s scale must be from {lo} to {hi}.")
        return
    if e.get("enter", "pop") not in PROP_ENTRANCES:
        err(f"{where}: {pid}'s enter must be one of {', '.join(PROP_ENTRANCES)}.")
    x, y = e.get("x"), e.get("y")
    if not _num(x):
        err(f"{where}: {pid} needs x, the middle of its base in frame pixels.")
        return
    if spec["place"] == "wall":
        lo, hi = STAGE["wallBase"]
        if not _num(y) or not lo <= y <= hi:
            err(f"{where}: {pid} hangs on the wall: y is its base line, {lo} to {hi}.")
            return
    box = prop_box(spec, x, y if spec["place"] == "wall" else None, scale)
    if box[0] < STAGE["left"] or box[2] > STAGE["right"] or box[1] < STAGE["top"]:
        err(f"{where}: {pid} at x {x} reaches outside the stage (x {STAGE['left']} to {STAGE['right']}, below "
            f"y {STAGE['top']}); move it or make it smaller.")
        return
    placed[pid] = {"at": e["at"], "prop": prop, "box": box, "x": x, "place": spec["place"], "tag": None}


def _check_layout(where, f, here, guide, props, catalog, people, err) -> None:
    floor = [p for p in props if p["place"] == "floor"]
    wall = [p for p in props if p["place"] == "wall"]
    for k, a in enumerate(props):
        for b in props[k + 1:]:
            if a["place"] == b["place"] and _overlap(a["box"], b["box"]):
                err(f"{where}: at frame {f}, {a.get('prop')} and {b.get('prop')} overlap; give each its own place.")
                return
    standing = [(w, s["x"], PERSON_HALF) for w, s in here.items() if s["visible"] and not s["walking"]]
    if guide["visible"] and not guide["walking"]:
        standing.append(("the guide", guide["x"], GUIDE_HALF))
    for k, (n1, x1, h1) in enumerate(standing):
        for n2, x2, h2 in standing[k + 1:]:
            if abs(x1 - x2) < h1 + h2:
                err(f"{where}: at frame {f}, {n1} (x {x1:g}) and {n2} (x {x2:g}) stand in the same place; keep "
                    f"them {h1 + h2} px apart.")
                return
        for p in floor:
            if x1 + h1 > p["box"][0] and x1 - h1 < p["box"][2]:
                err(f"{where}: at frame {f}, {n1} needs the floor from x {x1 - h1:g} to {x1 + h1:g}, which "
                    f"{p['prop']} covers (x {p['box'][0]:g} to {p['box'][2]:g}); stand beside it.")
                return
    # tags under things on the floor (names and prop tags) must not cover each other
    tags = [(w, s["x"], people[w]["name"]) for w, s in here.items() if s["visible"] and not s["walking"]]
    tags += [(p["prop"], p["x"], p["tag"]) for p in floor if p["tag"]]
    for k, (n1, x1, t1) in enumerate(tags):
        for n2, x2, t2 in tags[k + 1:]:
            need = (tag_width(t1) + tag_width(t2)) / 2
            if abs(x1 - x2) < need:
                err(f"{where}: at frame {f}, the tags under {n1} and {n2} overlap: they need {need:g} px between "
                    f"their middles and have {abs(x1 - x2):g}; move them apart or shorten one.")
                return
    for p in wall:
        if not p["tag"]:
            continue
        w = tag_width(p["tag"])
        tag = (p["x"] - w / 2, p["box"][3] + 12, p["x"] + w / 2, p["box"][3] + 60)
        for q in wall:
            if q is not p and _overlap(tag, q["box"]):
                err(f"{where}: at frame {f}, the tag under {p['prop']} covers {q['prop']}.")
                return


def _words_ok(words) -> bool:
    return (isinstance(words, list) and 1 <= len(words) <= LIMITS["words"]
            and all(isinstance(w, str) and 1 <= len(w) <= LIMITS["wordChars"] and all(ch in GLYPHS for ch in w.upper())
                    for w in words))


def _check_plate(e, where, catalog, err) -> None:
    t = e["type"]
    if t == "constellation":
        if not _words_ok(e.get("words")):
            err(f"{where}: the constellation at frame {e['at']} needs words: 1 or 2 words of 1 to "
                f"{LIMITS['wordChars']} letters or digits (no spaces or punctuation).")
        if "then" in e:
            then_at = e.get("thenAt")
            if not _words_ok(e["then"]):
                err(f"{where}: the constellation's then must be 1 or 2 words of letters or digits.")
            elif not _int(then_at) or not e["at"] + 45 <= then_at <= e["until"] - 30:
                err(f"{where}: the constellation's thenAt must be at least 1.5 s after it starts and 1 s before it ends.")
    elif t == "gauge":
        label, mx = e.get("label"), e.get("max")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= LIMITS["gaugeLabel"]:
            err(f"{where}: the gauge at frame {e['at']} needs a label of 1 to {LIMITS['gaugeLabel']} characters.")
        if not (_num(mx) and mx > 0 and _num(e.get("from")) and _num(e.get("to"))
                and 0 <= e["from"] <= mx and 0 <= e["to"] <= mx):
            err(f"{where}: the gauge at frame {e['at']} needs max above 0, and from and to between 0 and max.")
        elif "danger" in e and not (_num(e["danger"]) and 0 < e["danger"] < mx):
            err(f"{where}: the gauge's danger mark must be between 0 and max.")
    elif t == "morph":
        prop, word = e.get("prop"), e.get("word")
        if (prop is None) == (word is None):
            err(f"{where}: the morph at frame {e['at']} becomes either a prop or a word, one of the two.")
        elif prop is not None and prop not in catalog:
            err(f"{where}: the morph at frame {e['at']} becomes {prop!r}, which is not a library or custom prop.")
        elif word is not None and not (isinstance(word, str) and 1 <= len(word) <= LIMITS["wordChars"] and " " not in word):
            err(f"{where}: the morph's word must be one word of 1 to {LIMITS['wordChars']} characters.")


def chapter_windows(config: dict) -> list[tuple[int, int]]:
    """The stretches the text-layout audit samples as if each were a scene:
    each chapter cut at every event, plates included as their own stretch."""
    out: list[tuple[int, int]] = []
    scenes = config.get("scenes") or []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) if scenes and isinstance(scenes[0], dict) else None
    if not isinstance(data, dict):
        return out
    chapters = [c for c in data.get("chapters") or [] if isinstance(c, dict) and _int(c.get("start"))]
    total = config.get("totalFrames") or 0
    for i, ch in enumerate(chapters):
        start = ch["start"]
        end = chapters[i + 1]["start"] if i + 1 < len(chapters) else total
        cuts = sorted({start, end} | {e["at"] for e in ch.get("events") or [] if isinstance(e, dict) and _int(e.get("at"))
                                      and start < e["at"] < end})
        out.extend((a, b) for a, b in zip(cuts, cuts[1:]) if b > a)
    return out
