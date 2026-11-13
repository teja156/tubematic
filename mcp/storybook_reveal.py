"""Storybook Reveal (TMDEV-231): the checks a Storybook Reveal scene-config
must pass before it is written, so an unattended agent cannot ship a foreign
or untreated picture, the hero sheet as a page, a pencil plate that does not
match its picture, a reveal off the narration, a colour that arrives too late
to be seen, or a still page.

A Storybook Reveal video is one installed `StorybookReveal` scene spanning
every frame. The agent writes no code for it: `props.reveal` holds the pages
timed to the narration's word frames: a short title, one generated still and
its pencil plate (treat_image "pencil"), the frame the pencil plate wipes in,
the frame the colour floods over it, an optional focus for the slow push and
an optional page turn. The renderer's side of this contract is
renderer/remotion/src/scenes/installed/storybookReveal/contract.ts.

Keep in sync: ZONES, LIMITS, TIMING, the title sizes and the turns mirror
contract.ts, and title_size, picture_box, push_scale, pushed_box and
land_frame mirror stage.ts. mcp/tests/test_storybook_reveal.py reads the
TypeScript constants and the style pack, and both sides run the shared cases
in tests/fixtures/storybook_reveal_contract.json, so a drift fails a test
instead of a render.

Free of the database and of I/O: the caller passes the config, the
narration's fps and word start frames, the pack's `extra` block and the
video's id.
"""
from __future__ import annotations

import math
import re

from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "StorybookReveal"
PROPS_KEY = "reveal"
STYLE_ID = "storybook_reveal"
TREATMENT = "pencil"
SHEET = "hero"

W, H = 1080, 1920
TURNS = ("cut", "curl")

ZONES = {
    "titleTop": 230, "titleBottom": 390, "titleWidth": 880, "swashY": 362, "panelLeft": 90, "panelTop": 410,
    "panelWidth": 900, "panelHeight": 870, "panelRadius": 44, "feather": 44, "captionTop": 1300,
    "captionBottom": 1500, "pageNoY": 1640,
}
TITLE_SIZES = (92, 56)
TITLE_CHAR_W = 0.6
LIMITS = {
    "maxPages": 24, "maxImages": 12, "titleChars": 24, "titleWords": 3, "minPageSeconds": 2.5, "maxCurls": 2,
    "maxHoldSeconds": 6,
}
TIMING = {
    "snap": 2, "title": 10, "pencilAfter": 6, "pencil": 12, "colourWithin": 30, "colour": 18, "read": 8, "curl": 14,
    "push": 0.06,
}

MAX_ERRORS = 12

_IMAGE_SRC = re.compile(r"^/public/([A-Za-z0-9_-]+)/images/([A-Za-z0-9-]+)\.png$")
_PENCIL_SRC = re.compile(r"^/public/([A-Za-z0-9_-]+)/images/treated/([A-Za-z0-9-]+)\.pencil\.png$")
_PAGE_KEYS = {"start", "title", "image", "pencil", "focus", "pencilAt", "colourAt", "turn"}


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _uv(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_num(x) and 0 <= x <= 1 for x in v)


# ── the geometry (mirrors stage.ts) ──────────────────────────────────────────

def title_size(text: str) -> int:
    """The title's font size (stage.ts::titleSize)."""
    n = max(1, len(text.strip()))
    return max(TITLE_SIZES[1], min(TITLE_SIZES[0], math.floor(ZONES["titleWidth"] / (n * TITLE_CHAR_W))))


def picture_box(img_w: float, img_h: float) -> tuple[float, float, float, float]:
    """A still contain-fitted in the panel, in panel pixels (stage.ts::pictureBox)."""
    s = min(ZONES["panelWidth"] / img_w, ZONES["panelHeight"] / img_h)
    w, h = img_w * s, img_h * s
    return ((ZONES["panelWidth"] - w) / 2, (ZONES["panelHeight"] - h) / 2, w, h)


def land_frame(colour_at: int) -> int:
    """The frame a page's colour has finished flooding."""
    return colour_at + TIMING["colour"]


def _ease_in_out(t: float) -> float:
    x = max(0.0, min(1.0, t))
    return 2 * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 2 / 2


def push_scale(frame: int, land: int, end: int) -> float:
    return 1 + TIMING["push"] * _ease_in_out((frame - land) / max(1, end - land))


def pushed_box(box, scale: float, focus=(0.5, 0.5)) -> tuple[float, float, float, float]:
    x, y, w, h = box
    ax, ay = x + focus[0] * w, y + focus[1] * h
    return (ax - focus[0] * w * scale, ay - focus[1] * h * scale, w * scale, h * scale)


# ── checks ───────────────────────────────────────────────────────────────────

def is_reveal_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Storybook Reveal video is exactly the one
    StorybookReveal scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_reveal_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The StorybookReveal scene draws a whole Storybook Reveal video and is used only when the "
                    "video's visual_style is storybook_reveal (chosen at the topic). Build this video's scenes "
                    "from the other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Storybook Reveal video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"StorybookReveal\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"reveal\": {\"pages\": [...]}}}. Put every page in its pages.")
    return ""


def check(config: dict, fps: int, word_starts: list[int], extra: dict, video_id: str = "", quiet=()) -> list[str]:
    """Every problem with a Storybook Reveal config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `extra` is the style pack's
    catalogue block. `quiet` holds the config's insert windows
    (mcp/quiet_windows.py)."""
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    del extra  # the turns are this module's own constants; the pack only lists them
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
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: {{\"pages\": [...]}}."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    bad = sorted(set(data) - {"pages"})
    if bad:
        err(f"{PROPS_KEY}: unknown field(s) {bad}; it takes only pages.")

    pages = data.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= LIMITS["maxPages"] \
            or not all(isinstance(p, dict) for p in pages):
        return errors + [f"pages must list 1 to {LIMITS['maxPages']} pages."]
    starts = [p.get("start") for p in pages]
    if not all(_int(v) for v in starts):
        return errors + ["Every page needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first page must start at frame 0: the video opens on its page.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Page starts must increase and stay inside the video."]
    ends = starts[1:] + [total]

    snaps = sorted(set(word_starts))

    def on_word(frame) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    images: set[str] = set()
    curls = 0
    marks_of: list[list[int]] = []
    hold = round(LIMITS["maxHoldSeconds"] * fps)
    for i, p in enumerate(pages):
        where = f"Page {i + 1}"
        start, end = starts[i], ends[i]
        first = i == 0
        bad = sorted(set(p) - _PAGE_KEYS)
        if bad:
            err(f"{where}: unknown field(s) {bad}; a page takes {sorted(_PAGE_KEYS)}.")
        if not first and not on_word(start):
            err(f"{where} starts at frame {start}, which is not on a word: start a page within {TIMING['snap']} "
                "frames of a word's start.")
        if (end - start) < LIMITS["minPageSeconds"] * fps:
            err(f"{where} lasts {(end - start) / fps:.1f} s; a page needs at least {LIMITS['minPageSeconds']} s "
                "for its pencil and its colour to be seen. Merge it with the page before or after.")

        title = p.get("title")
        if not (isinstance(title, str) and 0 < len(title.strip()) <= LIMITS["titleChars"] and "\n" not in title
                and len(title.split()) <= LIMITS["titleWords"]):
            err(f"{where}: title must be 1 to {LIMITS['titleWords']} words and at most {LIMITS['titleChars']} "
                "characters on one line (it is hand-lettered in capitals above the picture).")

        # the pictures
        src, pencil = p.get("image"), p.get("pencil")
        m = _IMAGE_SRC.match(src) if isinstance(src, str) else None
        name = m.group(2) if m else None
        if not m or (video_id and m.group(1) != video_id):
            err(f"{where}: image must be a still of this video, the public_path generate_image returned "
                f"(/public/{video_id or '<video_id>'}/images/<name>.png).")
            name = None
        elif name == SHEET:
            err(f"{where}: {SHEET!r} is this video's hero sheet, the reference the pages are painted from, and is "
                "never a page. Make a page with generate_image(video_id, \"<name>\", \"<the scene>\", "
                f"reference=\"{SHEET}\").")
            name = None
        else:
            images.add(name)
        pm = _PENCIL_SRC.match(pencil) if isinstance(pencil, str) else None
        if not pm or (video_id and pm.group(1) != video_id) or (name and pm.group(2) != name):
            want = name or "<name>"
            err(f"{where}: pencil must be the pencil plate of this page's own image, the public_path "
                f"treat_image(video_id, \"{want}\", \"pencil\") returned "
                f"(/public/{video_id or '<video_id>'}/images/treated/{want}.pencil.png).")
        if "focus" in p and not _uv(p["focus"]):
            err(f"{where}: focus must be [u, v], each from 0 to 1 (fractions of the still from its top left).")
        turn = p.get("turn", "cut")
        if turn not in TURNS:
            err(f"{where}: turn must be one of {list(TURNS)}.")
        elif turn == "curl":
            if first:
                err(f"{where}: the first page cannot turn in with a curl: there is no page before it.")
            curls += 1

        # the reveal
        pa, ca = p.get("pencilAt"), p.get("colourAt")
        marks = [start]
        if not _int(pa) or not start <= pa < end:
            err(f"{where}: pencilAt must be a frame inside the page.")
            pa = None
        elif first and pa == start:
            pass  # the first page may open on its pencil plate, drawn whole from frame 0
        elif pa < start + TIMING["pencilAfter"]:
            err(f"{where}: pencilAt is frame {pa}; the pencil plate wipes in at least {TIMING['pencilAfter']} "
                "frames after its page starts, after the title (the first page may instead give its start, 0).")
            pa = None
        elif not on_word(pa):
            err(f"{where}: pencilAt is frame {pa}, which is not on a word.")
            pa = None
        if pa is not None:
            marks.append(pa)
        if not _int(ca) or not start <= ca < end:
            err(f"{where}: colourAt must be a frame inside the page.")
            ca = None
        elif pa is not None and not pa + TIMING["pencil"] <= ca <= pa + TIMING["colourWithin"]:
            err(f"{where}: colourAt is frame {ca}, {ca - pa} frames after pencilAt ({pa}); the colour follows the "
                f"pencil on a word {TIMING['pencil']} to {TIMING['colourWithin']} frames after it (within a "
                "second), once the pencil plate has wiped in. Move the colour, or the pencil, to a nearer word.")
            ca = None
        elif not on_word(ca):
            err(f"{where}: colourAt is frame {ca}, which is not on a word.")
            ca = None
        elif land_frame(ca) + TIMING["read"] > end:
            err(f"{where}: the colour finishes flooding at frame {land_frame(ca)}, too close to the page's end "
                f"({end}) to be seen; flood it on an earlier word.")
            ca = None
        if ca is not None:
            marks += [ca, land_frame(ca)]
        marks_of.append(marks)

        # nothing starts or is still moving inside an insert window, where the page is hidden
        turn_in = max(TIMING["title"], TIMING["curl"] if turn == "curl" else 0)
        for f, n, what in ((start, turn_in, "turns in"), (pa, TIMING["pencil"], "wipes its pencil in"),
                           (ca, TIMING["colour"], "floods its colour")):
            if f is None or f == 0:
                continue
            w = window_at(f, quiet) or next(((a, b) for a, b in quiet if a < f + n and b > f), None)
            if w:
                err(f"{where} {what} from frame {f} to {f + n - 1}, which runs into an insert ({window_text(w)}), "
                    f"where the page is hidden. Move it to a word at least {n} frames before the insert, or after it.")

    if curls > LIMITS["maxCurls"]:
        err(f"{curls} pages turn in with a curl; a video may have at most {LIMITS['maxCurls']}. Make the others "
            "\"cut\" (the default).")
    if len(images) > LIMITS["maxImages"]:
        err(f"The pages show {len(images)} different stills; a video may show at most {LIMITS['maxImages']}. "
            "Show one again on another page.")

    if not errors:
        for i, (start, pa, ca, land) in enumerate(marks_of):
            # the stretches with nothing new: page start to pencil, pencil to colour, colour landed to page end
            for a, c in ((start, pa), (pa, ca), (land, ends[i])):
                for x, y in uncovered(a, c, quiet):
                    if y - x > hold:
                        err(f"Page {i + 1}: nothing new happens from frame {x} to {y} ({(y - x) / fps:.1f} s); the "
                            f"longest stretch allowed is {LIMITS['maxHoldSeconds']} s (the slow push does not "
                            "count). Start the next page sooner, or move the pencil or the colour to a word in "
                            "between.")
    return errors


def page_windows(config: dict) -> list[tuple[int, int]]:
    """(settled, end) of every page of a Storybook Reveal config, for the
    text-layout audit to sample each like a scene: from the frame its title has
    wiped in and its colour has landed. [] when the config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_reveal_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    pages = [p for p in data.get("pages") or [] if isinstance(p, dict) and _int(p.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    windows = []
    for p, end in zip(pages, [n["start"] for n in pages[1:]] + [total]):
        settled = p["start"] + max(TIMING["title"], TIMING["curl"] if p.get("turn") == "curl" else 0)
        if _int(p.get("colourAt")):
            settled = max(settled, land_frame(p["colourAt"]))
        if end > p["start"]:
            windows.append((min(settled + 2, end - 1), end))
    return windows


def change_frames(config: dict) -> list[int]:
    """Every frame something visible starts changing on a page: the page
    itself, its pencil wipe and its colour flood. For the picture checks."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_reveal_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    out = []
    for p in data.get("pages") or []:
        if isinstance(p, dict):
            out += [p.get(k) for k in ("start", "pencilAt", "colourAt")]
    return [f for f in out if _int(f)]
