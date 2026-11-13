"""Editorial Collage (TMDEV-229): the checks an Editorial Collage scene-config
must pass before it is written, so an unattended agent cannot ship an
untreated or foreign picture, a face for a real person, a headline that runs
off its paper, an event off the narration, a glide or an event inside an
insert, or a still desk.

An Editorial Collage video is one installed `EditorialCollage` scene spanning
every frame. The agent writes no code for it: `props.collage` holds stations
timed to the narration's word frames: an optional headline (a torn clipping, a
black label bar or a black card) over one hero (a halftone print, a cut-out
sticker, a typed index card, a counting figure or a small stack of prints) and
the events on them (circle, underline, highlight, stamp, arrow, strike). The
code lays the stations out on the desk and glides the camera between them;
the agent writes no coordinate. The renderer's side of this contract is
renderer/remotion/src/scenes/installed/editorialCollage/contract.ts.

A real person is never pictured: no field takes a face, and a field of that
kind is refused with its reason. The renderer always paints the note
"Illustration" on a print and "Recreation" on a recreation index card;
nothing here can turn them off.

Keep in sync: ZONES, DESK, HEADLINE, LIMITS, TIMING and the catalogues mirror
contract.ts, and stepped, station_center, camera_at, headline_layout,
typed_chars, type_frames and figure_text mirror stage.ts.
mcp/tests/test_editorial_collage.py reads the TypeScript constants and the
style pack, and both sides run the shared cases in
tests/fixtures/editorial_collage_contract.json, so a drift fails a test
instead of a render.

Free of the database and of I/O: the caller passes the config, the
narration's fps and word start frames, the pack's `extra` block and the
video's id.
"""
from __future__ import annotations

import math
import re

from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "EditorialCollage"
PROPS_KEY = "collage"
STYLE_ID = "editorial_collage"
TREATMENTS = ("print", "sticker")

W, H = 1080, 1920
HEADLINE_KINDS = ("clipping", "label", "black")
HERO_KINDS = ("print", "sticker", "index", "figure", "stack")
EVENTS = ("circle", "underline", "highlight", "stamp", "arrow", "strike")
ARROW_SIDES = ("left", "right")
NOTES = {"print": "Illustration", "recreation": "Recreation"}

ZONES = {"headTop": 236, "headBottom": 600, "heroTop": 640, "heroBottom": 1280, "left": 100, "right": 980,
         "heroCenterY": 960}
DESK = {"dx": 620, "dy": 1140, "tile": 1024}
HEADLINE = {
    "clipping": {"sizes": (96, 84, 72, 62), "charW": 0.56, "width": 780, "line": 1.04, "pad": 34, "maxLines": 3,
                 "zone": 364},
    "label": {"sizes": (72, 62, 52, 44), "charW": 0.66, "width": 800, "line": 1.1, "pad": 22, "maxLines": 2,
              "zone": 364},
    "black": {"sizes": (96, 84, 72, 62), "charW": 0.56, "width": 760, "line": 1.04, "pad": 40, "maxLines": 3,
              "zone": 364},
    "blackFull": {"sizes": (128, 112, 96, 84, 72), "charW": 0.56, "width": 760, "line": 1.04, "pad": 70,
                  "maxLines": 6, "zone": 1044},
}
KICKER_H = 64
LIMITS = {
    "maxStations": 20, "minStationSeconds": 1.5, "headlineChars": 60, "kickerChars": 28, "captionChars": 40,
    "labelChars": 24, "lineChars": 34, "minLines": 1, "maxLines": 4, "prefixChars": 3, "suffixChars": 10,
    "figureLabelChars": 24, "maxFigure": 999999999, "figureDecimals": 2, "minStack": 2, "maxStack": 3,
    "stackCaptionChars": 24, "stampChars": 12, "maxImages": 10, "maxStillSeconds": 3.5,
}
TIMING = {
    "snap": 2, "readFrames": 8, "glide": 36, "step": 2.5, "headLand": 8, "heroDelay": 4, "heroLand": 10,
    "labelDelay": 10, "labelLand": 8, "stackStagger": 4, "circle": 30, "underline": 15, "highlight": 10,
    "strike": 10, "stamp": 6, "kick": 4, "arrow": 8, "count": 30, "typeRate": 13, "sway": 1.5,
    "swayPeriod": 72, "tilt": 4,
}

MAX_ERRORS = 12

_IMAGE_SRC = re.compile(r"^/public/([A-Za-z0-9_-]+)/images/treated/([A-Za-z0-9-]+)\.(print|sticker)\.png$")
_STATION_KEYS = {"start", "headline", "hero", "events"}
_HEADLINE_KEYS = {"text", "kind", "kicker"}
_HERO_KEYS = {
    "print": {"kind", "image", "caption"},
    "sticker": {"kind", "image", "label"},
    "index": {"kind", "lines", "recreation"},
    "figure": {"kind", "value", "prefix", "suffix", "label", "countAt"},
    "stack": {"kind", "items"},
}
_EVENT_KEYS = {"circle": set(), "underline": {"word"}, "highlight": {"word"}, "stamp": {"text"},
               "arrow": {"from"}, "strike": {"word"}}
# Fields an agent might reach for to show a person or switch a note off.
_PERSON_WORDS = ("face", "portrait", "person", "people", "likeness", "headshot", "photo")
_NOTE_WORDS = ("note", "footnote", "illustration", "credit", "watermark")
# Fields an agent might reach for to place a piece: the code lays out the desk.
_PLACE_WORDS = ("x", "y", "pos", "position", "left", "top", "camera", "zoom", "scale", "rotate", "tilt")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _text(v, limit: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= limit and "\n" not in v


# ── the geometry (mirrors stage.ts) ──────────────────────────────────────────

def stepped(frame: float) -> float:
    """A frame count held on twelve steps a second (stage.ts::stepped)."""
    return math.floor(frame / TIMING["step"]) * TIMING["step"]


def station_center(i: int) -> tuple[int, int]:
    """The desk point the camera rests on for station i: a zig-zag down the desk."""
    return (DESK["dx"] if i % 2 == 1 else 0, i * DESK["dy"])


def _ease_in_out_sine(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return -(math.cos(math.pi * t) - 1) / 2


def camera_at(starts: list[int], frame: float) -> tuple[float, float]:
    """The desk point at the centre of the frame (stage.ts::cameraAt)."""
    k = 0
    for i, s in enumerate(starts):
        if frame >= s:
            k = i
    to = station_center(k)
    if k == 0:
        return (float(to[0]), float(to[1]))
    fr = station_center(k - 1)
    t = _ease_in_out_sine((frame - starts[k]) / TIMING["glide"])
    return (fr[0] + (to[0] - fr[0]) * t, fr[1] + (to[1] - fr[1]) * t)


def clean_word(w: str) -> str:
    """A headline word as the agent names it: lower case, letters, digits and hyphens only."""
    return "".join(c for c in w.lower() if c.isalnum() or c == "-")


def layout_kind(kind: str, has_hero: bool) -> str:
    return "blackFull" if kind == "black" and not has_hero else kind


def headline_layout(text: str, kind: str, kicker: bool) -> tuple[int, list[str], bool]:
    """The headline's font size, its lines and whether it fits (stage.ts::headlineLayout)."""
    spec = HEADLINE[kind]
    words = text.split()
    room = spec["zone"] - 2 * spec["pad"] - (KICKER_H if kicker else 0)
    lines: list[str] = []
    size = spec["sizes"][0]
    for s in spec["sizes"]:
        size = s

        def fits(t: str) -> bool:
            return len(t) * s * spec["charW"] <= spec["width"]

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
        if len(lines) <= spec["maxLines"] and all(fits(line) for line in lines) \
                and len(lines) * s * spec["line"] <= room:
            return size, lines, True
    return size, lines, False


def typed_chars(text: str, at: int, frame: int) -> int:
    """Characters of an index line typed at a frame: 13 a second, on twos."""
    if frame < at:
        return 0
    age = (frame - at) // 2 * 2
    return min(len(text), age * TIMING["typeRate"] // 30 + 1)


def type_frames(text: str) -> int:
    """The frames an index line takes to type out in full."""
    age = 0
    while age * TIMING["typeRate"] // 30 + 1 < len(text):
        age += 2
    return age


def decimals_of(value: float) -> int:
    for d in (0, 1):
        if abs(round(value * 10 ** d) / 10 ** d - value) < 1e-9:
            return d
    return 2


def figure_text(value: float, prefix: str = "", suffix: str = "", k: float = 1.0) -> str:
    """The figure's text when it has counted k (0 to 1) of the way up (stage.ts::figureText)."""
    d = decimals_of(value)
    shown = value if k >= 1 else math.floor(value * max(0.0, min(1.0, k)) * 10 ** d + 1e-9) / 10 ** d
    space = " " if len(suffix) >= 3 and suffix[:3].isalpha() else ""
    return f"{prefix}{shown:,.{d}f}{space}{suffix}"


# ── checks ───────────────────────────────────────────────────────────────────

def is_collage_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: an Editorial Collage video is exactly the one
    EditorialCollage scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_collage_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The EditorialCollage scene draws a whole Editorial Collage video and is used only when the "
                    "video's visual_style is editorial_collage (chosen at the topic). Build this video's scenes "
                    "from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("An Editorial Collage video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"EditorialCollage\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"collage\": {...}}}. Put every station in its stations.")
    return ""


def _unknown(keys, allowed, where, err, what) -> None:
    bad = sorted(set(keys) - allowed)
    if not bad:
        return
    low = [k.lower() for k in bad]
    if any(any(w in k for w in _PERSON_WORDS) for k in low):
        err(f"{where}: {bad} cannot be given. A real person is never shown with a face, generated or drawn: name "
            "them in a headline or a sticker's label, and show their work, a place or an object instead.")
    elif any(any(w in k for w in _NOTE_WORDS) for k in low):
        err(f"{where}: unknown field(s) {bad}. The note \"Illustration\" on every print and \"Recreation\" on a "
            "recreation index card are painted by the renderer and cannot be changed or hidden.")
    elif any(k in _PLACE_WORDS for k in low):
        err(f"{where}: unknown field(s) {bad}. The code lays every station out on the desk and moves the camera; "
            "a station takes no position, size or angle.")
    else:
        err(f"{where}: unknown field(s) {bad}; {what} takes {sorted(allowed)}.")


def _timed(v, start, end, on_word) -> str:
    """Why a frame of a station's part is off, or ""."""
    if not _int(v) or not start <= v <= end - TIMING["readFrames"]:
        return f"must be a frame inside its station, at least {TIMING['readFrames']} frames before the station ends"
    if v != start and not on_word(v):
        return f"is frame {v}, which is not on a word"
    return ""


def _image_error(src, video_id, treatments=TREATMENTS) -> str:
    m = _IMAGE_SRC.match(src) if isinstance(src, str) else None
    vid = video_id or "<video_id>"
    if not m or (video_id and m.group(1) != video_id) or m.group(3) not in treatments:
        looks = " or ".join(f"<name>.{t}.png" for t in treatments)
        calls = " or ".join(f"treat_image(video_id, name, \"{t}\")" for t in treatments)
        return (f"must be a treated still of this video, the public_path treat_image returned "
                f"(/public/{vid}/images/treated/{looks}). Make the still with generate_image, then {calls}.")
    return ""


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "", quiet=()) -> list[str]:
    """Every problem with an Editorial Collage config, one sentence each (at
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the stations."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    _unknown(data, {"stations"}, PROPS_KEY, err, PROPS_KEY)

    stations = data.get("stations")
    if not isinstance(stations, list) or not 1 <= len(stations) <= LIMITS["maxStations"] \
            or not all(isinstance(s, dict) for s in stations):
        return errors + [f"stations must list 1 to {LIMITS['maxStations']} stations."]
    starts = [s.get("start") for s in stations]
    if not all(_int(v) for v in starts):
        return errors + ["Every station needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first station must start at frame 0: the video opens on its desk.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Station starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    images: set[str] = set()
    change_frames: list[list[int]] = []
    for i, st in enumerate(stations):
        where = f"Station {i + 1}"
        start, end = starts[i], ends[i]
        _unknown(st, _STATION_KEYS, where, err, "a station")
        if i and not on_word(start):
            err(f"{where} starts at frame {start}, which is not on a word: start a station within "
                f"{TIMING['snap']} frames of a word's start.")
        if (end - start) < LIMITS["minStationSeconds"] * fps:
            err(f"{where} lasts {(end - start) / fps:.1f} s; a station needs at least "
                f"{LIMITS['minStationSeconds']} s (the camera's glide alone takes {TIMING['glide']} frames). "
                "Merge it with the station before or after.")
        changes = [start]

        hero = st.get("hero")
        hkind = hero.get("kind") if isinstance(hero, dict) else None

        # the headline
        headline = st.get("headline")
        words: list[str] = []
        hl_kind = None
        if headline is not None:
            if not isinstance(headline, dict):
                err(f"{where}: headline must be an object {{\"text\", \"kind\", \"kicker\"}}.")
            else:
                _unknown(headline, _HEADLINE_KEYS, f"{where}, headline", err, "a headline")
                hl_kind = headline.get("kind")
                if hl_kind not in HEADLINE_KINDS:
                    err(f"{where}: headline.kind must be one of {list(HEADLINE_KINDS)}.")
                    hl_kind = None
                if "kicker" in headline and not _text(headline.get("kicker"), LIMITS["kickerChars"]):
                    err(f"{where}: headline.kicker must be 1 to {LIMITS['kickerChars']} characters, such as "
                        "\"TECH · FEB 28, 2017\".")
                text = headline.get("text")
                if not _text(text, LIMITS["headlineChars"]):
                    err(f"{where}: headline.text must be 1 to {LIMITS['headlineChars']} characters on one line.")
                elif hl_kind:
                    words = [clean_word(w) for w in text.split()]
                    lk = layout_kind(hl_kind, hero is not None)
                    _, _, fits = headline_layout(text, lk, "kicker" in headline)
                    if not fits:
                        err(f"{where}: the headline {text!r} does not fit its {hl_kind} even at the smallest size; "
                            "use fewer or shorter words" + (" or drop the kicker." if "kicker" in headline else "."))

        # the hero
        if hero is None:
            if hl_kind != "black":
                err(f"{where}: give it a hero (a print, sticker, index card, figure or stack); only a black "
                    "headline card may stand alone.")
        elif hkind not in HERO_KINDS:
            err(f"{where}: hero must be an object whose kind is one of {list(HERO_KINDS)}.")
            hkind = None
        elif hkind in ("print", "sticker"):
            _unknown(hero, _HERO_KEYS[hkind], f"{where}, hero", err, f"a {hkind} hero")
            why = _image_error(hero.get("image"), video_id, (hkind,))
            if why:
                err(f"{where}: image {why}")
            else:
                images.add(hero["image"])
            if hkind == "print" and "caption" in hero and not _text(hero.get("caption"), LIMITS["captionChars"]):
                err(f"{where}: caption must be 1 to {LIMITS['captionChars']} characters (typed under the print).")
            if hkind == "sticker" and "label" in hero and not _text(hero.get("label"), LIMITS["labelChars"]):
                err(f"{where}: label must be 1 to {LIMITS['labelChars']} characters (the black label bar).")
        elif hkind == "index":
            _unknown(hero, _HERO_KEYS["index"], f"{where}, hero", err, "an index hero")
            if "recreation" in hero and not isinstance(hero["recreation"], bool):
                err(f"{where}: recreation must be true (the card recreates a real document) or false.")
            lines = hero.get("lines")
            if not (isinstance(lines, list) and LIMITS["minLines"] <= len(lines) <= LIMITS["maxLines"]
                    and all(isinstance(ln, dict) for ln in lines)):
                err(f"{where}: lines must list {LIMITS['minLines']} to {LIMITS['maxLines']} lines, each "
                    "{\"text\", \"at\"}.")
            else:
                last = start - 1
                for n, ln in enumerate(lines):
                    at = f"{where}, line {n + 1}"
                    _unknown(ln, {"text", "at"}, at, err, "a line")
                    ok_text = _text(ln.get("text"), LIMITS["lineChars"])
                    if not ok_text:
                        err(f"{at}: text must be 1 to {LIMITS['lineChars']} characters.")
                    why = _timed(ln.get("at"), start, end, on_word)
                    if why:
                        err(f"{at}: at {why}.")
                    elif ln["at"] <= last:
                        err(f"{at}: lines type on in order, each on a later word than the one before.")
                    else:
                        last = ln["at"]
                        changes.append(ln["at"])
                        if ok_text and ln["at"] + type_frames(ln["text"]) > end:
                            err(f"{at}: it types {TIMING['typeRate']} characters a second and is still typing "
                                f"when the station ends at frame {end}; start it sooner or shorten it.")
        elif hkind == "figure":
            _unknown(hero, _HERO_KEYS["figure"], f"{where}, hero", err, "a figure hero")
            value = hero.get("value")
            if not (_num(value) and 0 <= value <= LIMITS["maxFigure"]
                    and abs(round(value, LIMITS["figureDecimals"]) - value) < 1e-9):
                err(f"{where}: value must be a number from 0 to {LIMITS['maxFigure']} with at most "
                    f"{LIMITS['figureDecimals']} decimals (it counts up from 0).")
            if "prefix" in hero and not _text(hero.get("prefix"), LIMITS["prefixChars"]):
                err(f"{where}: prefix must be 1 to {LIMITS['prefixChars']} characters, such as \"$\".")
            if "suffix" in hero and not _text(hero.get("suffix"), LIMITS["suffixChars"]):
                err(f"{where}: suffix must be 1 to {LIMITS['suffixChars']} characters, such as \"%\" or \"hours\".")
            if not _text(hero.get("label"), LIMITS["figureLabelChars"]):
                err(f"{where}: label must be 1 to {LIMITS['figureLabelChars']} characters (the bar under the figure).")
            why = _timed(hero.get("countAt"), start, end, on_word)
            if why:
                err(f"{where}: countAt {why}.")
            else:
                changes.append(hero["countAt"])
        elif hkind == "stack":
            _unknown(hero, _HERO_KEYS["stack"], f"{where}, hero", err, "a stack hero")
            items = hero.get("items")
            if not (isinstance(items, list) and LIMITS["minStack"] <= len(items) <= LIMITS["maxStack"]
                    and all(isinstance(it, dict) for it in items)):
                err(f"{where}: items must list {LIMITS['minStack']} to {LIMITS['maxStack']} prints or stickers, "
                    "each {\"image\", \"caption\"}.")
            else:
                for n, it in enumerate(items):
                    at = f"{where}, item {n + 1}"
                    _unknown(it, {"image", "caption"}, at, err, "a stack item")
                    why = _image_error(it.get("image"), video_id)
                    if why:
                        err(f"{at}: image {why}")
                    else:
                        images.add(it["image"])
                    if "caption" in it and not _text(it.get("caption"), LIMITS["stackCaptionChars"]):
                        err(f"{at}: caption must be 1 to {LIMITS['stackCaptionChars']} characters.")

        # the events
        events = st.get("events", [])
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            err(f"{where}: events must be a list of objects.")
            events = []
        counts: dict[str, int] = {}
        marked: set[tuple[str, str]] = set()
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
            if do in ("underline", "highlight", "strike"):
                w = e.get("word")
                if headline is None:
                    err(f"{at}: {do} marks a word of the headline; this station has no headline.")
                elif not words:
                    pass  # the headline itself is refused above
                elif not isinstance(w, str) or len(w.split()) != 1 or clean_word(w) not in words:
                    err(f"{at}: word must be one word of this station's headline.")
                elif (do, clean_word(w)) in marked:
                    err(f"{at}: {w!r} already has a {do} in this station.")
                else:
                    marked.add((do, clean_word(w)))
                if do == "highlight" and words and hl_kind != "clipping":
                    err(f"{at}: highlight puts a yellow bar behind a word of a clipping; on a {hl_kind} the "
                        "white letters would not read. Use underline instead.")
            elif do in ("circle", "stamp", "arrow"):
                if hero is None:
                    err(f"{at}: {do} lands on the hero; this station has none.")
                if do == "stamp":
                    t = e.get("text")
                    if not _text(t, LIMITS["stampChars"]) or t != t.upper():
                        err(f"{at}: text must be 1 to {LIMITS['stampChars']} capital letters, such as \"OFFLINE\".")
                if do == "arrow" and e.get("from") not in ARROW_SIDES:
                    err(f"{at}: from must be \"left\" or \"right\", the side the arrow comes from.")
        for do in ("circle", "stamp", "arrow", "strike"):
            if counts.get(do, 0) > 1:
                err(f"{where}: at most one {do} event per station.")
        change_frames.append(sorted(set(changes)))

    if len(images) > LIMITS["maxImages"]:
        err(f"The stations use {len(images)} different stills; a video may use at most {LIMITS['maxImages']}. "
            "Show one again on another station.")

    for i, frames in enumerate(change_frames):
        s = starts[i]
        if i:
            hit = next(((a, b) for a, b in quiet if a < s + TIMING["glide"] and b > s), None)
            if hit:
                err(f"Station {i + 1}: the camera glides from frame {s} to {s + TIMING['glide'] - 1}, which runs "
                    f"into an insert ({window_text(hit)}), where the desk is hidden. Start the station on a word at "
                    f"least {TIMING['glide']} frames before the insert, or after it.")
                continue
        for f in frames:
            if f == 0 or f == s:
                continue
            w = window_at(f, quiet)
            if w:
                err(f"Station {i + 1} has an event, a line or a count at frame {f}, inside an insert "
                    f"({window_text(w)}), where the desk is hidden. Move it to a word before or after the insert.")

    if not errors:
        still = round(LIMITS["maxStillSeconds"] * fps)
        for i, frames in enumerate(change_frames):
            marks = frames + [ends[i]]
            for a, c in (g for x, y in zip(marks, marks[1:]) for g in uncovered(x, y, quiet)):
                if c - a > still:
                    err(f"Station {i + 1}: nothing new happens from frame {a} to {c} ({(c - a) / fps:.1f} s); the "
                        f"longest stretch allowed is {LIMITS['maxStillSeconds']} s. Add an event on a word in "
                        "between (a circle, a highlight, a stamp, an arrow), or start the next station sooner.")
    return errors


def beat_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every station of an Editorial Collage config, for the
    text-layout audit to sample each like a scene: from the frame the glide,
    the landings and its last event, line or count have played out. [] when the
    config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_collage_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    stations = [s for s in data.get("stations") or [] if isinstance(s, dict) and _int(s.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    longest = max(TIMING["circle"], TIMING["underline"], TIMING["highlight"], TIMING["strike"],
                  TIMING["stamp"] + TIMING["kick"], TIMING["arrow"])
    windows = []
    for i, (st, end) in enumerate(zip(stations, [n["start"] for n in stations[1:]] + [total])):
        settled = st["start"] + (max(TIMING["glide"], TIMING["heroDelay"] + TIMING["labelDelay"]
                                     + TIMING["labelLand"]) if i else 0)
        for e in st.get("events") or []:
            if isinstance(e, dict) and _int(e.get("at")):
                settled = max(settled, e["at"] + longest)
        hero = st.get("hero") if isinstance(st.get("hero"), dict) else {}
        for ln in hero.get("lines") or []:
            if isinstance(ln, dict) and _int(ln.get("at")) and isinstance(ln.get("text"), str):
                settled = max(settled, ln["at"] + type_frames(ln["text"]))
        if _int(hero.get("countAt")):
            settled = max(settled, hero["countAt"] + TIMING["count"])
        if end > st["start"]:
            windows.append((min(settled + 2, end - 1), end))
    return windows
