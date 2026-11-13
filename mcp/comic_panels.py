"""Comic Panels (TMDEV-234): the checks a Comic Panels scene-config must pass
before it is written, so an unattended agent cannot ship a mistimed, crowded,
cut-off or still video.

A Comic Panels video is one installed `ComicPanels` scene spanning every
frame. `props.comicPanels` holds the cast, the pages (a layout of 3 or 4
panels and a title each) and, in each panel, items timed to the narration:
characters, props, balloons, caption boxes, sound effects, speed lines and
hits; an optional splash frame pulls the camera back to the whole page. The
renderer's side of this contract is
renderer/remotion/src/scenes/installed/comicPanels/contract.ts and stage.ts.

Keep in sync: the constants, catalogues and box helpers mirror contract.ts;
mcp/tests/test_comic_panels.py compares them with
tests/fixtures/comic_panels_contract.json, which
renderer/remotion/character-tools/sync-contract.mjs writes from the
TypeScript.

Free of the database and of I/O.
"""
from __future__ import annotations

import math
import re

import character_kit as ck
from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "ComicPanels"
PROPS_KEY = "comicPanels"
STYLE_ID = "comic_panels"
LIBRARY_KEY = "props"

LIMITS = {"maxPages": 3, "maxCast": 4, "maxItemsPerPanel": 8, "titleChars": 28, "balloonChars": 40,
          "captionChars": 40, "sfxChars": 10, "maxStillSeconds": 3, "minPanelSeconds": 1.5, "echoWords": 5}
TIMING = {"inkIn": 18, "read": 18, "pop": 10, "minItemGap": 4, "hit": 8, "pullBack": 20, "endMargin": 6}
LAYOUTS = {
    "stack3": [[24, 140, 952, 500], [24, 660, 952, 500], [24, 1180, 952, 496]],
    "stack4": [[24, 140, 952, 370], [24, 530, 952, 370], [24, 920, 952, 370], [24, 1310, 952, 366]],
    "2+1": [[24, 140, 466, 760], [510, 140, 466, 760], [24, 920, 952, 756]],
    "1+2": [[24, 140, 952, 760], [24, 920, 466, 756], [510, 920, 466, 756]],
    "2+2": [[24, 140, 466, 760], [510, 140, 466, 760], [24, 920, 466, 756], [510, 920, 466, 756]],
}
TONES = ("cream", "pink", "blue", "yellow", "green", "dark")
CAST_KINDS = ("hero", "person", "villain")
HAIRS = ("spiky", "bob", "bun", "short", "bald", "curly")
OUTFITS = ("blue", "red", "green", "yellow", "purple", "grey")
SKINS = ("light", "tan", "brown", "dark")
POSES = ("stand", "point", "panic", "cheer", "think", "type", "shrug", "facepalm")
FACES = ("neutral", "happy", "shocked", "worried", "angry", "smug", "sad", "grin")
BALLOONS = ("speech", "thought", "shout")
LINES = ("speed", "focus")
ITEM_TYPES = ("actor", "prop", "balloon", "caption", "sfx", "lines", "hit")
SCALE = (0.5, 1.6)
ACTOR = {"w": 260, "h": 300}
# How far a character reaches from its centre in each pose (contract.ts POSE_REACH): hands and hair count.
POSE_REACH = {"stand": {"side": 135, "up": 180}, "point": {"side": 180, "up": 180}, "panic": {"side": 150, "up": 180},
              "cheer": {"side": 140, "up": 210}, "think": {"side": 135, "up": 180}, "type": {"side": 135, "up": 180},
              "shrug": {"side": 180, "up": 180}, "facepalm": {"side": 135, "up": 180}}
CUSTOM = {"maxProps": 8, "minSide": 60, "maxSide": 500, "maxText": 24, "maxActs": 0}
# Prop boxes at scale 1, in page units (contract.ts PROPS w and h).
PROP_BOXES = {
    "phone": (150, 260), "laptop": (300, 220), "inbox": (420, 220), "login": (340, 260), "browser": (420, 120),
    "monitor": (320, 260), "server": (160, 260), "lock": (120, 160), "key": (170, 90), "shield": (150, 180),
    "bug": (160, 150), "virus": (160, 160), "cell": (180, 180), "bomb": (160, 170), "money": (200, 120),
    "document": (160, 210), "envelope": (200, 140), "rocket": (140, 260), "planet": (220, 220), "clock": (150, 160),
    "sign": (260, 160), "door": (180, 300),
}
_ALLOWED_IMPORT = re.compile(r"^(react|remotion|\.\./\.\./installed/comicPanels/(ink|contract))$")
_ALLOWED_TEXT = "react, remotion and ../../installed/comicPanels/ink (or contract)"
_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

SNAP_FRAMES = 2
MAX_ERRORS = 12
# A panel item may reach this far past its panel's edge before it is cut off (a bust is cut at the bottom on purpose).
EDGE_TOLERANCE = 8
CHANGE_FIX = "start the next panel or page there, or a character, prop, balloon, sound effect or hit on that word"
SUBTLE = ("caption",)


def is_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def item_box(rect, x: float, y: float, w: float, h: float, scale: float = 1) -> tuple:
    cx, cy = rect[0] + x * rect[2], rect[1] + y * rect[3]
    return (cx - w * scale / 2, cy - h * scale / 2, cx + w * scale / 2, cy + h * scale / 2)


def actor_box(rect, x: float, y: float, pose: str, scale: float = 1) -> tuple:
    cx, cy = rect[0] + x * rect[2], rect[1] + y * rect[3]
    r = POSE_REACH.get(pose, POSE_REACH["stand"])
    return (cx - r["side"] * scale, cy - r["up"] * scale, cx + r["side"] * scale, cy + ACTOR["h"] / 2 * scale)


def balloon_size(text: str) -> tuple[int, int]:
    lines = min(3, max(1, -(-len(text) // 16)))
    chars = min(16, len(text))
    return max(140, chars * 20 + 70), lines * 46 + 60


def _js_round(v: float) -> int:
    return int(math.floor(v + 0.5))


def sfx_size(text: str) -> tuple[int, int]:
    """The capitals and the burst behind them, both centred on the item (contract.ts sfxSize)."""
    n = max(1, len(text))
    r = (60 + n * 7) * 1.15
    return _js_round(max(n * 46, 2 * r) + 20), _js_round(max(110, 2 * r * 0.78) + 20)


def check_scene_use(visual_style: str, scenes: list) -> str:
    uses = [s for s in scenes or [] if is_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The ComicPanels scene draws a whole Comic Panels video and is used only when the video's "
                    "visual_style is comic_panels (chosen at the topic). Build this video's scenes from the other "
                    "components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Comic Panels video is exactly one scene: {\"type\": \"generated\", \"source\": \"installed\", "
                "\"src\": \"ComicPanels\", \"startFrame\": 0, \"durationInFrames\": <totalFrames>, \"props\": "
                "{\"comicPanels\": {...}}}. Put every beat in its pages and panels.")
    return ""


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None):
    return ck.custom_prop_errors(custom, video_id, library, sources, CUSTOM, _ALLOWED_IMPORT, _ALLOWED_TEXT)


def check(config: dict, fps: int, word_starts: list[int], words: list[str], extra: dict,
          video_id: str = "", sources: dict | None = None, quiet=()) -> list[str]:
    """Every problem with a Comic Panels config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written."""
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    if not isinstance(config, dict) or not isinstance(config.get("scenes"), list):
        return ["The config must be an object whose scenes is a list."]
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the cast and the pages."]
    if not ck.is_int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    custom_errs, catalog, custom_boxes = custom_prop_errors(data.get("customProps"), video_id, extra[LIBRARY_KEY], sources)
    for e in custom_errs:
        err(e)
    boxes = {**PROP_BOXES, **custom_boxes}
    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return frame == 0 or not snaps or any(abs(frame - w) <= SNAP_FRAMES for w in snaps)

    cast = data.get("cast")
    if not isinstance(cast, list) or not 1 <= len(cast) <= LIMITS["maxCast"]:
        return errors + [f"cast must list 1 to {LIMITS['maxCast']} characters."]
    cast_ids = set()
    for i, c in enumerate(cast):
        where = f"cast {i + 1}"
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not _ID.match(c["id"]) or c["id"] in cast_ids:
            err(f"{where}: id must be a unique lowercase name starting with a letter.")
            continue
        cast_ids.add(c["id"])
        if c.get("kind") not in CAST_KINDS:
            err(f"{where} ({c['id']}): kind must be one of {', '.join(CAST_KINDS)}.")
        for key, allowed in (("hair", HAIRS), ("outfit", OUTFITS), ("skin", SKINS)):
            if key in c and c[key] not in allowed:
                err(f"{where} ({c['id']}): {key} must be one of {', '.join(allowed)}.")
    if sum(1 for c in cast if isinstance(c, dict) and c.get("kind") == "hero") > 1:
        err("Only one character may be the house hero.")

    pages = data.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= LIMITS["maxPages"]:
        return errors + [f"pages must list 1 to {LIMITS['maxPages']} pages."]
    page_starts = [p.get("start") if isinstance(p, dict) else None for p in pages]
    if not all(ck.is_int(s) for s in page_starts):
        return errors + ["Every page needs a whole-number start frame."]
    if page_starts[0] != 0:
        err("The first page must start at frame 0.")
    if any(b <= a for a, b in zip(page_starts, page_starts[1:])) or page_starts[-1] >= total:
        return errors + ["Page starts must increase and stay inside the video."]
    splash = data.get("splash")
    if splash is not None and (not ck.is_int(splash) or splash <= page_starts[-1] or splash >= total
                               or total - splash < LIMITS["minPanelSeconds"] * fps):
        err(f"splash must be a whole frame on the last page, at least {LIMITS['minPanelSeconds']} s before the end.")
        splash = None

    runs = ck.echo_runs(words, LIMITS["echoWords"])
    changes: set[int] = set(page_starts) | ({splash} if splash is not None else set())
    # A page whose panels could not be read adds none of its changes, so the still check would only repeat its error.
    broken = False
    for pi, page in enumerate(pages):
        p_end = page_starts[pi + 1] if pi + 1 < len(pages) else (splash if splash is not None else total)
        where = f"Page {pi + 1}"
        if pi and not on_word(page_starts[pi]):
            err(f"{where} starts at frame {page_starts[pi]}, which is not on a word.")
        w = window_at(page_starts[pi], quiet) if pi else None
        if w:
            err(f"{where} starts inside an insert ({window_text(w)}); start it at {w[1]} or before {w[0]}.")
        layout = page.get("layout")
        if not isinstance(layout, str) or layout not in LAYOUTS:
            err(f"{where}: layout must be one of {', '.join(LAYOUTS)}.")
            broken = True
            continue
        if "title" in page and (not isinstance(page["title"], str) or not page["title"].strip()
                                or len(page["title"]) > LIMITS["titleChars"]):
            err(f"{where}: title must be text of 1 to {LIMITS['titleChars']} characters.")
        panels = page.get("panels")
        rects = LAYOUTS[layout]
        if not isinstance(panels, list) or len(panels) != len(rects):
            err(f"{where}: a {layout} page has {len(rects)} panels; list exactly that many.")
            broken = True
            continue
        starts = [p.get("start") if isinstance(p, dict) else None for p in panels]
        if not all(ck.is_int(s) for s in starts):
            err(f"{where}: every panel needs a whole-number start frame.")
            broken = True
            continue
        if starts[0] < page_starts[pi] or any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= p_end:
            err(f"{where}: panel starts must increase, from the page's start, and stay on the page "
                f"(before frame {p_end}).")
            broken = True
            continue
        ends = starts[1:] + [p_end]
        hits: list[int] = []  # the camera shakes for the whole page, so hits are spaced across its panels
        for k, (panel, a, b) in enumerate(zip(panels, starts, ends)):
            _check_panel(panel, f"{where}, panel {k + 1}", rects[k], a, b, catalog, boxes, cast_ids, fps, on_word,
                         runs, changes, quiet, err, hits)

    if broken:
        return errors
    still = round(LIMITS["maxStillSeconds"] * fps)
    prev = 0
    for c in sorted(c for c in changes if 0 <= c < total) + [total]:
        for a, b in uncovered(prev, c, quiet):
            if b - a > still:
                err(f"Nothing changes from frame {a} to {b} ({(b - a) / fps:.1f} s); the longest still stretch allowed "
                    f"is {LIMITS['maxStillSeconds']} s. Add a balloon, a sound effect, a character or the next panel.")
        prev = c
    return errors


def _inside(box, rect, bottom_free=False) -> bool:
    t = EDGE_TOLERANCE
    return (box[0] >= rect[0] - t and box[2] <= rect[0] + rect[2] + t and box[1] >= rect[1] - t
            and (bottom_free or box[3] <= rect[1] + rect[3] + t))


def _no_cover(box, others: list, at: str, err) -> None:
    if any(ck.overlap(box, other, 4) for other in others):
        err(f"{at}: it overlaps a balloon or sound effect already in this panel; move one of them.")
    others.append(box)


def _check_panel(panel, where, rect, start, end, catalog, boxes, cast_ids, fps, on_word, runs, changes, quiet, err,
                 hits):
    if not isinstance(panel, dict):
        err(f"{where} must be an object.")
        return
    if panel.get("start") and not on_word(start):
        err(f"{where} starts at frame {start}, which is not on a word.")
    w = window_at(start, quiet) if start else None
    if w:
        err(f"{where} starts inside an insert ({window_text(w)}); start it at {w[1]} or before {w[0]}.")
    changes.add(start)
    if end - start < LIMITS["minPanelSeconds"] * fps:
        err(f"{where} is read for {end - start} frames; a panel needs at least {LIMITS['minPanelSeconds']} s.")
    if panel.get("tone", "cream") not in TONES:
        err(f"{where}: tone must be one of {', '.join(TONES)}.")
    items = panel.get("items")
    if not isinstance(items, list) or len(items) > LIMITS["maxItemsPerPanel"]:
        err(f"{where}: items must be a list of at most {LIMITS['maxItemsPerPanel']}.")
        return
    frames = [it.get("frame") if isinstance(it, dict) else None for it in items]
    if not all(ck.is_int(f) for f in frames):
        err(f"{where}: every item needs a whole-number frame.")
        return
    if any(b < a for a, b in zip(frames, frames[1:])):
        err(f"{where}: list the items in frame order.")
    last = end - TIMING["endMargin"]
    named: set[str] = set()
    # Balloons and sound effects are the panel's words: two of them may not cover each other.
    words_boxes: list[tuple] = []
    prev_f = None
    for it, f in zip(items, frames):
        it = {k: (v if not isinstance(v, (list, dict)) else None) for k, v in it.items()}
        t = it.get("type")
        at = f"{where}, the {t or 'item'} at frame {f}"
        if t not in ITEM_TYPES:
            err(f"{at}: type must be one of {', '.join(ITEM_TYPES)}.")
            continue
        if f < start or f > last:
            err(f"{at}: it must appear while its panel is read, from frame {start} to {last}.")
            continue
        if f != start and not on_word(f):
            err(f"{at}: items appear on words; move it within {SNAP_FRAMES} frames of a word's start.")
        w = window_at(f, quiet)
        if w:
            err(f"{at} starts inside an insert ({window_text(w)}); move it to {w[1]} or later, or before {w[0]}.")
        if prev_f is not None and f != prev_f and f - prev_f < TIMING["minItemGap"]:
            err(f"{at}: it comes {f - prev_f} frames after the item before; items in a panel are at least "
                f"{TIMING['minItemGap']} frames apart, or on the same frame.")
        prev_f = f
        if t not in SUBTLE:
            changes.add(f)
        xy_ok = ck.is_num(it.get("x")) and ck.is_num(it.get("y")) and 0 <= it["x"] <= 1 and 0 <= it["y"] <= 1
        if t in ("actor", "prop", "balloon", "sfx") and not xy_ok:
            err(f"{at}: x and y must be numbers from 0 to 1, fractions of its panel.")
            continue
        sc = it.get("scale", 1)
        if t in ("actor", "prop") and (not ck.is_num(sc) or not SCALE[0] <= sc <= SCALE[1]):
            err(f"{at}: scale must be from {SCALE[0]} to {SCALE[1]}.")
            continue
        if t == "actor":
            if it.get("who") not in cast_ids:
                err(f"{at}: who must be a cast id.")
                continue
            if it.get("pose") not in POSES:
                err(f"{at}: pose must be one of {', '.join(POSES)}.")
            if it.get("face") not in FACES:
                err(f"{at}: face must be one of {', '.join(FACES)}.")
            box = actor_box(rect, it["x"], it["y"], it.get("pose"), sc)
            if not _inside(box, rect, bottom_free=True):
                err(f"{at}: the character (its hands and hair included, in this pose) reaches past its panel's top or "
                    "sides; move it in or scale it down.")
            named.add(it.get("id") or it["who"])
        elif t == "prop":
            prop = it.get("prop")
            if not isinstance(prop, str) or prop not in catalog:
                err(f"{at}: prop must be from the library or the video's customProps.")
                continue
            limit = catalog[prop]["text"]
            text = it.get("text")
            if text is not None and (limit == 0 or not isinstance(text, str) or len(text) > limit):
                err(f"{at}: the {prop} prop " + ("has no text slot." if limit == 0 else f"takes at most {limit} characters."))
            bw, bh = boxes[prop]
            if not _inside(item_box(rect, it["x"], it["y"], bw, bh, sc), rect):
                err(f"{at}: the {prop} reaches past its panel's edge; move it in or scale it down.")
            named.add(it.get("id") or prop)
        elif t == "balloon":
            text = it.get("text")
            if it.get("kind") not in BALLOONS:
                err(f"{at}: kind must be one of {', '.join(BALLOONS)}.")
            if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["balloonChars"]:
                err(f"{at}: text must be 1 to {LIMITS['balloonChars']} characters.")
                continue
            if it.get("to") not in named:
                err(f"{at}: to must name a character or prop already in this panel (its id, or its cast id or prop name).")
            bw, bh = balloon_size(text)
            box = item_box(rect, it["x"], it["y"], bw, bh)
            if not _inside(box, rect):
                err(f"{at}: the balloon reaches past its panel's edge; move it in or shorten the line.")
            _no_cover(box, words_boxes, at, err)
        elif t == "caption":
            text = it.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["captionChars"]:
                err(f"{at}: text must be 1 to {LIMITS['captionChars']} characters.")
            elif ck.echoes(text, runs, LIMITS["echoWords"]):
                err(f"{at}: the caption box repeats the narration word for word; the captions already show those "
                    "words, so set the scene or the time instead.")
        elif t == "sfx":
            text = it.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["sfxChars"]:
                err(f"{at}: text must be a sound of 1 to {LIMITS['sfxChars']} characters.")
                continue
            sw, sh = sfx_size(text)
            box = item_box(rect, it["x"], it["y"], sw, sh)
            if not _inside(box, rect):
                err(f"{at}: the sound effect reaches past its panel's edge; move it in or shorten it.")
            _no_cover(box, words_boxes, at, err)
        elif t == "lines":
            if it.get("kind") not in LINES:
                err(f"{at}: kind must be one of {', '.join(LINES)}.")
        elif t == "hit":
            if hits and f - hits[-1] < TIMING["hit"]:
                err(f"{at}: two hits within {TIMING['hit']} frames blur into one shake.")
            hits.append(f)
    if not any(isinstance(i, dict) and i.get("type") in ("actor", "prop") for i in items):
        err(f"{where} has no character or prop; a panel needs a picture, not words alone.")


# ── what the audit and the picture checks read ────────────────────────────────

def _data(config: dict) -> dict:
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_scene(scenes[0]):
        return {}
    d = (scenes[0].get("props") or {}).get(PROPS_KEY)
    return d if isinstance(d, dict) else {}


def audit_windows(config: dict) -> list[tuple[int, int]]:
    """(first, end) for the text-layout audit: each panel while it is read, once the camera has arrived."""
    data = _data(config)
    total = config.get("totalFrames") if ck.is_int(config.get("totalFrames")) else 0
    starts = [pn.get("start") for pg in data.get("pages") or [] if isinstance(pg, dict)
              for pn in pg.get("panels") or [] if isinstance(pn, dict) and ck.is_int(pn.get("start"))]
    if ck.is_int(data.get("splash")):
        starts.append(data["splash"])
    starts = sorted(set(starts))
    windows = [(a, b) for a, b in zip(starts, starts[1:] + [total]) if b > a]
    return ck.sample_windows(windows, max(TIMING["read"], TIMING["inkIn"]) + TIMING["pop"], TIMING["endMargin"])


def change_frames(data: dict) -> list[int]:
    frames = [data.get("splash")]
    for pg in data.get("pages") or []:
        frames.append(pg.get("start") if isinstance(pg, dict) else None)
        for pn in (pg.get("panels") or []) if isinstance(pg, dict) else []:
            frames.append(pn.get("start") if isinstance(pn, dict) else None)
            for it in (pn.get("items") or []) if isinstance(pn, dict) else []:
                if isinstance(it, dict) and it.get("type") not in SUBTLE:
                    frames.append(it.get("frame"))
    return [f for f in frames if ck.is_int(f)]


def first_frame_problem(data: dict) -> str | None:
    pages = data.get("pages") or []
    panels = (pages[0].get("panels") or []) if pages and isinstance(pages[0], dict) else []
    items = (panels[0].get("items") or []) if panels and isinstance(panels[0], dict) else []
    if not (panels and panels[0].get("start") == 0
            and any(isinstance(i, dict) and i.get("type") in ("actor", "prop") and ck.is_int(i.get("frame"))
                    and i["frame"] <= 3 for i in items)):
        return ("the first panel has no character or prop by frame 3, so the video opens on an empty page. Start "
                "panel 1 at frame 0 with the first sentence's subject in it")
    return None


def sample_text(data: dict, prop_id) -> str:
    for pg in data.get("pages") or []:
        for pn in (pg.get("panels") or []) if isinstance(pg, dict) else []:
            for it in (pn.get("items") or []) if isinstance(pn, dict) else []:
                if isinstance(it, dict) and it.get("type") == "prop" and it.get("prop") == prop_id \
                        and isinstance(it.get("text"), str):
                    return it["text"]
    return ""
