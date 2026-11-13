"""Archive and Engraving (TMDEV-230): the checks an Archive and Engraving
scene-config must pass before it is written, so an unattended agent cannot ship
an untreated or foreign picture, a face for a real person, a title that runs
off the page, an event off the narration, a point that is off the plate, or a
still page.

An Archive and Engraving video is one installed `ArchiveEngraving` scene
spanning every frame. The agent writes no code for it: `props.archive` holds a
running header and beats timed to the narration's word frames: a dated title
with one red word, one museum card (an engraved plate, a chart with a route, a
person's name card, a row of name cards, or a recreated document) and the
events on it (strike, stamp, magnify, route, timeline, underline). The
renderer's side of this contract is
renderer/remotion/src/scenes/installed/archiveEngraving/contract.ts.

People are name cards: a card has no field for a picture or a face, and a
field of that kind is refused with its reason. The renderer always draws the
footnote "Illustration" under a plate or a chart and "Recreation" under a
document; nothing here can turn them off.

Keep in sync: ZONES, LIMITS, TIMING, the title sizes and the catalogues
mirror contract.ts, and title_layout, push_scale, plate_view, to_window and
ruler_scale mirror stage.ts. mcp/tests/test_archive_engraving.py reads the
TypeScript constants and the style pack, and both sides run the shared cases
in tests/fixtures/archive_engraving_contract.json, so a drift fails a test
instead of a render.

Free of the database and of I/O: the caller passes the config, the
narration's fps and word start frames, the pack's `extra` block and the
video's id.
"""
from __future__ import annotations

import math
import re

from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "ArchiveEngraving"
PROPS_KEY = "archive"
STYLE_ID = "archive_engraving"
TREATMENT = "engraving"

W, H = 1080, 1920
CARD_KINDS = ("plate", "chart", "person", "people", "document")
EVENTS = ("strike", "stamp", "magnify", "route", "timeline", "underline")
EMBLEMS = ("laurel", "quill", "gear", "compass", "scroll", "book", "anchor", "telescope", "scales", "lamp")
FOOTNOTES = {"plate": "Illustration", "chart": "Illustration", "document": "Recreation"}

ZONES = {
    "headerY": 244, "titleLeft": 64, "titleWidth": 952, "dateTop": 280, "titleTop": 336, "withTop": 590,
    "bandBottom": 690, "cardLeft": 90, "cardRight": 990, "cardTop": 700, "cardBottom": 1268,
    "winLeft": 120, "winTop": 726, "winW": 840, "winH": 430,
    "rulerY": 1640, "rulerLeft": 110, "rulerRight": 970, "stampX": 800, "stampY": 1110,
}
TITLE_SIZES = (104, 92, 80, 70)
TITLE_CHAR_W = 0.5
LIMITS = {
    "maxBeats": 32, "minBeatSeconds": 1.5, "firstPersonSeconds": 1.5, "headerChars": 34, "titleChars": 48, "dateChars": 24,
    "withChars": 28, "nameChars": 28, "noteChars": 40, "datesChars": 20, "roleChars": 32, "lineChars": 40,
    "stampChars": 14, "minLines": 1, "maxLines": 6, "minPeople": 2, "maxPeople": 4, "minRoute": 2,
    "maxRoute": 8, "maxInitials": 3, "maxImages": 10, "minYear": 0, "maxYear": 2100, "maxRulerTicks": 8,
    "maxStillSeconds": 3.5,
}
TIMING = {
    "snap": 2, "readFrames": 8, "enter": 10, "dateType": 12, "strike": 15, "withRise": 12, "underline": 12,
    "stamp": 6, "kick": 4, "magnify": 14, "route": 20, "timeline": 20, "rulerFade": 10, "person": 10,
    "connector": 12, "typeRate": 2, "handRate": 1.5, "push": 0.06, "magnifyZoom": 2.5,
}
RULER_STEPS = (1, 2, 5, 10, 20, 25, 50, 100, 200, 500)

MAX_ERRORS = 12
# A point the agent gives on a plate stays this far (in still pixels) inside the part on screen.
POINT_MARGIN = 30

_IMAGE_SRC = re.compile(r"^/public/([A-Za-z0-9_-]+)/images/treated/([A-Za-z0-9-]+)\.engraving\.png$")
_BEAT_KEYS = {"start", "title", "date", "card", "events"}
_CARD_KEYS = {
    "plate": {"kind", "image", "focus", "name", "note"},
    "chart": {"kind", "image", "focus", "name", "note", "route"},
    "person": {"kind", "name", "dates", "role", "emblem", "initials"},
    "people": {"kind", "people"},
    "document": {"kind", "lines", "hand"},
}
_PERSON_KEYS = {"name", "dates", "role", "emblem", "initials", "at"}
_EVENT_KEYS = {
    "strike": {"word", "with"}, "stamp": {"text"}, "magnify": {"point"}, "route": set(),
    "timeline": {"from", "to"}, "underline": {"word"},
}
# Fields an agent might reach for to show a person or switch a footnote off.
_PICTURE_WORDS = ("image", "face", "photo", "picture", "portrait", "likeness", "src")
_FOOTNOTE_WORDS = ("footnote", "label", "recreation", "illustration", "caption")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _uv(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_num(x) and 0 <= x <= 1 for x in v)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= limit and "\n" not in v


# ── the geometry (mirrors stage.ts) ──────────────────────────────────────────

def clean_word(w: str) -> str:
    """A title word as the agent names it: lower case, letters, digits and hyphens only."""
    return "".join(c for c in w.lower() if c.isalnum() or c == "-")


def title_layout(text: str) -> tuple[int, list[str]]:
    """The title's font size and its lines (stage.ts::titleLayout)."""
    words = text.split()
    lines: list[str] = []
    size = TITLE_SIZES[0]
    for s in TITLE_SIZES:
        size = s

        def fits(t: str) -> bool:
            return len(t) * s * TITLE_CHAR_W <= ZONES["titleWidth"]

        lines, cur = [], ""
        for w in words:
            cand = f"{cur} {w}" if cur else w
            if fits(cand):
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= 2 and all(fits(line) for line in lines):
            return size, lines
    return size, lines


def push_scale(frame: int, start: int, end: int) -> float:
    return 1 + TIMING["push"] * max(0.0, min(1.0, (frame - start) / max(1, end - start)))


def plate_view(scale: float, focus=(0.5, 0.5)) -> tuple[float, float, float, float]:
    s = max(1.0, scale)
    vw = W / s
    vh = vw * ZONES["winH"] / ZONES["winW"]
    x = min(W - vw, max(0.0, focus[0] * W - vw / 2))
    y = min(H - vh, max(0.0, focus[1] * H - vh / 2))
    return (x, y, vw, vh)


def to_window(view, p) -> tuple[float, float]:
    x, y, vw, vh = view
    return (ZONES["winLeft"] + (p[0] * W - x) / vw * ZONES["winW"],
            ZONES["winTop"] + (p[1] * H - y) / vh * ZONES["winH"])


def ruler_scale(years: list[int], max_ticks: int = LIMITS["maxRulerTicks"]):
    """(start, end, step) of the ruler, or None when no step keeps it to max_ticks."""
    if not years:
        return None
    lo, hi = min(years), max(years)
    for step in RULER_STEPS:
        start = math.floor(lo / step) * step - step
        end = math.ceil(hi / step) * step + step
        if (end - start) / step + 1 <= max_ticks:
            return (start, end, step)
    return None


def _on_plate(point, focus, margin=POINT_MARGIN) -> bool:
    """A still point stays inside the part on screen for the whole push."""
    px, py = point[0] * W, point[1] * H
    for scale in (1.0, 1 + TIMING["push"]):
        x, y, vw, vh = plate_view(scale, focus)
        if not (x + margin <= px <= x + vw - margin and y + margin <= py <= y + vh - margin):
            return False
    return True


# ── checks ───────────────────────────────────────────────────────────────────

def is_archive_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: an Archive and Engraving video is exactly the one
    ArchiveEngraving scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_archive_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The ArchiveEngraving scene draws a whole Archive and Engraving video and is used only when "
                    "the video's visual_style is archive_engraving (chosen at the topic). Build this video's "
                    "scenes from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("An Archive and Engraving video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"ArchiveEngraving\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"archive\": {...}}}. Put every beat in its beats.")
    return ""


def _unknown(keys, allowed, where, err, what) -> None:
    bad = sorted(set(keys) - allowed)
    if not bad:
        return
    if any(any(w in k.lower() for w in _PICTURE_WORDS) for k in bad) and what in ("a person", "a person card"):
        err(f"{where}: a person is a name card and has no picture or face: {bad} cannot be given. Show the "
            "person with an emblem or initials; put a place or a machine of their work on a plate instead.")
    elif any(any(w in k.lower() for w in _FOOTNOTE_WORDS) for k in bad):
        err(f"{where}: unknown field(s) {bad}. The footnotes \"Illustration\" (plate, chart) and \"Recreation\" "
            "(document) are drawn on every card of the kind and cannot be changed or hidden.")
    else:
        err(f"{where}: unknown field(s) {bad}; {what} takes {sorted(allowed)}.")


def _person_errors(p, where, err, people: bool) -> None:
    what = "a person" if people else "a person card"
    _unknown(p, _PERSON_KEYS if people else _CARD_KEYS["person"], where, err, what)
    if not _text(p.get("name"), LIMITS["nameChars"]):
        err(f"{where}: name must be 1 to {LIMITS['nameChars']} characters.")
    if not _text(p.get("dates"), LIMITS["datesChars"]):
        err(f"{where}: dates must be 1 to {LIMITS['datesChars']} characters, such as \"1815-1852\".")
    if not _text(p.get("role"), LIMITS["roleChars"]):
        err(f"{where}: role must be 1 to {LIMITS['roleChars']} characters.")
    emblem, initials = p.get("emblem"), p.get("initials")
    if (emblem is None) == (initials is None):
        err(f"{where}: give an emblem (one of {list(EMBLEMS)}) or initials, one of the two.")
    elif emblem is not None and emblem not in EMBLEMS:
        err(f"{where}: emblem must be one of {list(EMBLEMS)}.")
    elif initials is not None and not (isinstance(initials, str) and 1 <= len(initials) <= LIMITS["maxInitials"]
                                       and initials.isalpha() and initials.isupper()):
        err(f"{where}: initials must be 1 to {LIMITS['maxInitials']} capital letters, such as \"AL\".")


def _timed(v, start, end, on_word) -> str:
    """Why a frame of a beat's part is off, or ""."""
    if not _int(v) or not start <= v <= end - TIMING["readFrames"]:
        return (f"must be a frame inside its beat, at least {TIMING['readFrames']} frames before the beat ends")
    if v != start and not on_word(v):
        return f"is frame {v}, which is not on a word"
    return ""


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "", quiet=()) -> list[str]:
    """Every problem with an Archive and Engraving config, one sentence each (at
    most MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block. `quiet` holds the config's insert windows
    (mcp/quiet_windows.py)."""
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    del extra  # the catalogues are this module's own constants; the pack only lists them
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the header and the beats."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    _unknown(data, {"header", "beats"}, PROPS_KEY, err, PROPS_KEY)
    if not _text(data.get("header"), LIMITS["headerChars"]):
        err(f"header must be 1 to {LIMITS['headerChars']} characters on one line (the running header, such as "
            "\"Histories of Computing\").")

    beats = data.get("beats")
    if not isinstance(beats, list) or not 1 <= len(beats) <= LIMITS["maxBeats"] \
            or not all(isinstance(b, dict) for b in beats):
        return errors + [f"beats must list 1 to {LIMITS['maxBeats']} beats."]
    starts = [b.get("start") for b in beats]
    if not all(_int(v) for v in starts):
        return errors + ["Every beat needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first beat must start at frame 0: the video opens on its page.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Beat starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    images: set[str] = set()
    change_frames: list[list[int]] = []
    for i, b in enumerate(beats):
        where = f"Beat {i + 1}"
        start, end = starts[i], ends[i]
        _unknown(b, _BEAT_KEYS, where, err, "a beat")
        if i and not on_word(start):
            err(f"{where} starts at frame {start}, which is not on a word: start a beat within "
                f"{TIMING['snap']} frames of a word's start.")
        if (end - start) < LIMITS["minBeatSeconds"] * fps:
            err(f"{where} lasts {(end - start) / fps:.1f} s; a beat needs at least {LIMITS['minBeatSeconds']} s "
                "to be read. Merge it with the beat before or after.")
        changes = [start]

        # the title
        title = b.get("title")
        words: list[str] = []
        if not isinstance(title, dict) or set(title) != {"text", "red"}:
            err(f"{where}: title must be {{\"text\", \"red\"}}: the title and the one word of it drawn in red.")
        elif not _text(title["text"], LIMITS["titleChars"]):
            err(f"{where}: title.text must be 1 to {LIMITS['titleChars']} characters on one line.")
        else:
            words = [clean_word(w) for w in title["text"].split()]
            red = title["red"]
            if not isinstance(red, str) or len(red.split()) != 1 or clean_word(red) not in words:
                err(f"{where}: title.red must be one word of the title (it is drawn in red).")
            _, lines = title_layout(title["text"])
            if len(lines) > 2:
                err(f"{where}: the title {title['text']!r} does not fit two lines even at the smallest size; "
                    "use fewer or shorter words.")
        if "date" in b and not _text(b.get("date"), LIMITS["dateChars"]):
            err(f"{where}: date must be 1 to {LIMITS['dateChars']} characters, such as \"9 September 1947\".")

        # the card
        card = b.get("card")
        kind = card.get("kind") if isinstance(card, dict) else None
        focus = [0.5, 0.5]
        if kind not in CARD_KINDS:
            err(f"{where}: card must be an object whose kind is one of {list(CARD_KINDS)}.")
            card, kind = {}, None
        elif kind in ("plate", "chart"):
            _unknown(card, _CARD_KEYS[kind], f"{where}, card", err, f"a {kind} card")
            src = card.get("image")
            m = _IMAGE_SRC.match(src) if isinstance(src, str) else None
            if not m or (video_id and m.group(1) != video_id):
                err(f"{where}: image must be an engraving of this video, the public_path treat_image returned "
                    f"(/public/{video_id or '<video_id>'}/images/treated/<name>.engraving.png). Make the still "
                    "with generate_image, then treat_image(video_id, name, \"engraving\").")
            else:
                images.add(src)
            if "focus" in card:
                if _uv(card["focus"]):
                    focus = card["focus"]
                else:
                    err(f"{where}: focus must be [u, v], each from 0 to 1 (fractions of the still from its top left).")
            if not _text(card.get("name"), LIMITS["nameChars"]):
                err(f"{where}: name must be 1 to {LIMITS['nameChars']} characters (the small-caps line under the plate).")
            if "note" in card and not _text(card.get("note"), LIMITS["noteChars"]):
                err(f"{where}: note must be 1 to {LIMITS['noteChars']} characters.")
            if kind == "chart":
                route = card.get("route")
                if not (isinstance(route, list) and LIMITS["minRoute"] <= len(route) <= LIMITS["maxRoute"]
                        and all(_uv(p) for p in route)):
                    err(f"{where}: route must list {LIMITS['minRoute']} to {LIMITS['maxRoute']} [u, v] points on the chart.")
                elif not all(_on_plate(p, focus) for p in route):
                    err(f"{where}: a route point is outside the part of the chart on screen; move the focus toward "
                        "the route or the points inward (the window shows a wide band of the still).")
        elif kind == "person":
            _person_errors(card, f"{where}, card", err, people=False)
        elif kind == "people":
            _unknown(card, _CARD_KEYS["people"], f"{where}, card", err, "a people card")
            people = card.get("people")
            if not (isinstance(people, list) and LIMITS["minPeople"] <= len(people) <= LIMITS["maxPeople"]
                    and all(isinstance(p, dict) for p in people)):
                err(f"{where}: people must list {LIMITS['minPeople']} to {LIMITS['maxPeople']} people.")
            else:
                last = start - 1
                for n, p in enumerate(people):
                    at = f"{where}, person {n + 1}"
                    _person_errors(p, at, err, people=True)
                    why = _timed(p.get("at"), start, end, on_word)
                    if why:
                        err(f"{at}: at {why}.")
                    elif p["at"] <= last:
                        err(f"{at}: people arrive in order, each on a later word than the one before.")
                    else:
                        if n == 0 and p["at"] - start > round(LIMITS["firstPersonSeconds"] * fps):
                            err(f"{at} arrives {(p['at'] - start) / fps:.1f} s into the beat, which leaves the "
                                f"card empty; bring the first person in within {LIMITS['firstPersonSeconds']} s "
                                "of the beat's start (the beat's first word is fine).")
                        last = p["at"]
                        changes.append(p["at"])
        elif kind == "document":
            _unknown(card, _CARD_KEYS["document"], f"{where}, card", err, "a document card")
            if "hand" in card and not isinstance(card["hand"], bool):
                err(f"{where}: hand must be true (handwritten) or false (typed).")
            lines = card.get("lines")
            if not (isinstance(lines, list) and LIMITS["minLines"] <= len(lines) <= LIMITS["maxLines"]
                    and all(isinstance(ln, dict) for ln in lines)):
                err(f"{where}: lines must list {LIMITS['minLines']} to {LIMITS['maxLines']} lines, each "
                    "{\"text\", \"at\"}.")
            else:
                last = start - 1
                for n, ln in enumerate(lines):
                    at = f"{where}, line {n + 1}"
                    _unknown(ln, {"text", "at"}, at, err, "a line")
                    if not _text(ln.get("text"), LIMITS["lineChars"]):
                        err(f"{at}: text must be 1 to {LIMITS['lineChars']} characters.")
                    why = _timed(ln.get("at"), start, end, on_word)
                    if why:
                        err(f"{at}: at {why}.")
                    elif ln["at"] <= last:
                        err(f"{at}: lines write on in order, each on a later word than the one before.")
                    else:
                        last = ln["at"]
                        changes.append(ln["at"])

        # the events
        events = b.get("events", [])
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            err(f"{where}: events must be a list of objects.")
            events = []
        counts: dict[str, int] = {}
        underlined: set[str] = set()
        for n, e in enumerate(events):
            do = e.get("do")
            at = f"{where}, event {n + 1} ({do})"
            if do not in EVENTS:
                err(f"{where}, event {n + 1}: do must be one of {list(EVENTS)}.")
                continue
            _unknown(e, _EVENT_KEYS[do] | {"at", "do"}, at, err, f"a {do} event")
            why = _timed(e.get("at"), start, end, on_word)
            if why:
                err(f"{at}: at {why}.")
                continue
            changes.append(e["at"])
            counts[do] = counts.get(do, 0) + 1
            if do in ("strike", "underline"):
                w = e.get("word")
                if not isinstance(w, str) or len(w.split()) != 1 or clean_word(w) not in words:
                    err(f"{at}: word must be one word of this beat's title.")
                elif do == "underline":
                    if clean_word(w) in underlined:
                        err(f"{at}: {w!r} is already underlined in this beat.")
                    underlined.add(clean_word(w))
                if do == "strike" and not _text(e.get("with"), LIMITS["withChars"]):
                    err(f"{at}: with must be 1 to {LIMITS['withChars']} characters: the words that replace the "
                        "struck one, in italic under the title.")
            elif do == "stamp":
                t = e.get("text")
                if not _text(t, LIMITS["stampChars"]) or t != t.upper():
                    err(f"{at}: text must be 1 to {LIMITS['stampChars']} capital letters, such as \"DISPROVED\".")
            elif do == "magnify":
                if kind not in ("plate", "chart"):
                    err(f"{at}: magnify needs a plate or a chart card.")
                elif not _uv(e.get("point")):
                    err(f"{at}: point must be [u, v], each from 0 to 1, on the still.")
                elif not _on_plate(e["point"], focus):
                    err(f"{at}: the point is outside the part of the still on screen; move it, or the card's focus.")
            elif do == "route":
                if kind != "chart":
                    err(f"{at}: route draws a chart card's route; this beat's card is not a chart.")
            elif do == "timeline":
                ys = [e.get("from"), e.get("to")]
                if not all(_int(y) and LIMITS["minYear"] <= y <= LIMITS["maxYear"] for y in ys):
                    err(f"{at}: from and to must be years from {LIMITS['minYear']} to {LIMITS['maxYear']}.")
        for do in ("strike", "stamp", "magnify"):
            if counts.get(do, 0) > 1:
                err(f"{where}: at most one {do} event per beat.")
        if kind == "chart" and counts.get("route", 0) != 1:
            err(f"{where}: a chart card's route is drawn by one route event on a word; give it one.")
        change_frames.append(sorted(set(changes)))

    if len(images) > LIMITS["maxImages"]:
        err(f"The beats use {len(images)} different engravings; a video may use at most {LIMITS['maxImages']}. "
            "Show one engraving again with another focus.")
    # Every span of years from minYear to maxYear fits the ruler (its largest step is 500
    # years), so a timeline event's years need no check beyond their range.

    for i, frames in enumerate(change_frames):
        for f in frames:
            if f == 0:
                continue
            w = window_at(f, quiet)
            if w:
                what = "starts" if f == starts[i] else "has an event, a person or a line"
                err(f"Beat {i + 1} {what} at frame {f}, inside an insert ({window_text(w)}), where the page is "
                    "hidden. Move it to a word before or after the insert.")

    if not errors:
        still = round(LIMITS["maxStillSeconds"] * fps)
        for i, frames in enumerate(change_frames):
            marks = frames + [ends[i]]
            for a, c in (g for x, y in zip(marks, marks[1:]) for g in uncovered(x, y, quiet)):
                if c - a > still:
                    err(f"Beat {i + 1}: nothing new happens from frame {a} to {c} ({(c - a) / fps:.1f} s); the "
                        f"longest stretch allowed is {LIMITS['maxStillSeconds']} s. Add an event on a word in "
                        "between (an underline, a stamp, a magnify), or start the next beat sooner.")
    return errors


def beat_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every beat of an Archive and Engraving config, for the
    text-layout audit to sample each like a scene: from the frame its last
    event, person or line has played out. [] when the config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_archive_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    beats = [b for b in data.get("beats") or [] if isinstance(b, dict) and _int(b.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    longest = max(TIMING["strike"], TIMING["withRise"] + 4, TIMING["route"], TIMING["timeline"],
                  TIMING["magnify"], TIMING["enter"])
    windows = []
    for b, end in zip(beats, [n["start"] for n in beats[1:]] + [total]):
        settled = b["start"] + TIMING["enter"]
        for e in b.get("events") or []:
            if isinstance(e, dict) and _int(e.get("at")):
                settled = max(settled, e["at"] + longest)
        card = b.get("card") if isinstance(b.get("card"), dict) else {}
        for p in card.get("people") or []:
            if isinstance(p, dict) and _int(p.get("at")):
                settled = max(settled, p["at"] + TIMING["connector"])
        hand = card.get("hand") is True
        for ln in card.get("lines") or []:
            if isinstance(ln, dict) and _int(ln.get("at")) and isinstance(ln.get("text"), str):
                rate = TIMING["handRate"] if hand else TIMING["typeRate"]
                settled = max(settled, ln["at"] + math.ceil(len(ln["text"]) / rate))
        if end > b["start"]:
            windows.append((min(settled + 2, end - 1), end))
    return windows
