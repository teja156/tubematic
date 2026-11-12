"""Insert scenes (TMDEV-224): the checks a config's `inserts` must pass before
it is written, and what write_scene_config fills into each insert.

A video has one main style, drawn by its scene(s) across the whole video, and
may carry a few short inserts from an insert style (System Flow, Terminal Doc),
drawn over it and under the captions. An insert covers a window inside one
script segment that the script marked with that style. The limits are the
user's (TMDEV-223) and live in tubematic_core/inserts.py; the insert style's
own data is checked by its module (system_flow.check_insert,
terminal_doc.check_insert), which the caller passes in as `style_checks`.

Free of the database and of I/O: the caller passes the video's settings, the
script's marks and the voiced timeline.
"""
from __future__ import annotations

from tubematic_core import inserts as tinserts
from tubematic_core import visual_styles as tvs

H = 1920
# Where each insert style draws on the frame, top to bottom, at shift 0: the
# headline and diagram band of SystemFlow (systemFlow/camera.ts BAND, the
# header 0.115 of the height above it) and the stage slots of TerminalDoc
# (terminalDoc/contract.ts SLOTS, context top to note bottom). The shift moves
# this block clear of the main style's captions.
BLOCKS = {"system_flow": (221, 1325), "terminal_doc": (230, 1344)}
# Room kept between the captions and an insert, and at the frame's edges.
CAPTION_GAP = 24
EDGE = 60
MAX_ERRORS = 12
ENTRY_KEYS = {"style", "startFrame", "durationInFrames", "props", "src", "palette", "shift"}


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def windows(config: dict) -> list[tuple[int, int]]:
    """(start, end) of every well-formed insert in a config, in time order. The
    main style's validator treats these as quiet spans: nothing of the main
    starts inside one, and its stillness rule skips them."""
    out = []
    for e in config.get("inserts") or []:
        if isinstance(e, dict) and _int(e.get("startFrame")) and _int(e.get("durationInFrames")) \
                and e["durationInFrames"] > 0:
            out.append((e["startFrame"], e["startFrame"] + e["durationInFrames"]))
    return sorted(out)


def caption_box(subtitles) -> tuple[int, int] | None:
    """The band the captions may take, top to bottom in pixels, or None when
    the video has none. Captions are centred on `position` and hold one or two
    lines of the font size; this is their largest extent."""
    subs = subtitles if isinstance(subtitles, dict) else {}
    if subs.get("enabled") is False:
        return None
    pos = subs.get("position", 0.78)
    size = subs.get("fontSize", 62)
    if not isinstance(pos, (int, float)) or not isinstance(size, (int, float)):
        pos, size = 0.78, 62
    centre = pos * H
    half = 1.3 * size + 12
    return round(centre - half), round(centre + half)


def shift_for(style: str, subtitles) -> int:
    """Pixels an insert's layout moves down (or up, when negative) to stay
    clear of the main style's captions. Captions in the upper half push it
    down; captions in the lower half that reach into it lift it a little."""
    top, bottom = BLOCKS.get(style, (221, 1325))
    box = caption_box(subtitles)
    if box is None:
        return 0
    cap_top, cap_bottom = box
    if (cap_top + cap_bottom) / 2 < H / 2:
        shift = max(0, cap_bottom + CAPTION_GAP - top)
        return min(shift, H - EDGE - bottom)
    overlap = bottom - (cap_top - CAPTION_GAP)
    return -min(max(0, overlap), top - 120)


def check(config: dict, *, fps: int, word_starts: list[int], segments: list[dict], marks: dict,
          insert_mode: str, allowed, host: dict, host_message: str, style_checks: dict,
          subtitles=None) -> list[str]:
    """Every problem with a config's `inserts`, one sentence each (at most
    MAX_ERRORS), or [] when they may be written.

    segments: the voiced timeline's segments in order, [{id, startFrame,
        endFrame, role}] (role "payoff" on the payoff's first segment).
    marks: segment id -> the insert style the script marked it with.
    insert_mode, allowed: the video's Inserts setting and its chosen insert
        styles (None while undecided).
    host: the main style's `inserts` block; host_message: why it takes none.
    style_checks: insert style id -> a function(entry) -> list of problems.
    subtitles: the config's captions, which an insert must stay clear of.
    """
    entries = config.get("inserts")
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    marked = [s for s in segments if marks.get(s.get("id"))]
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        return ["config.inserts must be a list of insert scenes, or left out."]
    if entries and not host.get("host"):
        return [host_message or "This video's style takes no insert scenes: remove config.inserts."]
    if entries and insert_mode == "none":
        return ["This video's Inserts setting is None: remove config.inserts."]
    total = config.get("totalFrames")
    if not _int(total) or total < 1:
        return errors
    max_frames = round(tinserts.MAX_SECONDS * fps)
    min_frames = round(2 * fps)
    gap = round(tinserts.MIN_MAIN_GAP_SECONDS * fps)
    snaps = sorted(set(word_starts))
    by_id = {s.get("id"): i for i, s in enumerate(segments)}
    covered: set = set()
    spans: list[tuple[int, int, int]] = []

    for k, e in enumerate(entries):
        where = f"Insert {k + 1}"
        if not isinstance(e, dict):
            err(f"{where} must be an object {{style, startFrame, durationInFrames, props}}.")
            continue
        extra = set(e) - ENTRY_KEYS
        if extra:
            err(f"{where} has unknown keys {sorted(extra)}; an insert is {{style, startFrame, "
                "durationInFrames, props}.")
        if not isinstance(e.get("props"), dict):
            err(f"{where}: props must be an object holding the insert style's data under its props key.")
            continue
        style = e.get("style")
        if style not in tvs.INSERT_STYLES:
            err(f"{where}: style {style!r} is not an insert style (insert styles: "
                f"{', '.join(tvs.INSERT_STYLES)}).")
            continue
        if allowed is not None and style not in allowed:
            chosen = ", ".join(allowed) if allowed else "none"
            err(f"{where}: {style} is not one of this video's insert styles ({chosen}).")
            continue
        start, dur = e.get("startFrame"), e.get("durationInFrames")
        if not (_int(start) and _int(dur)) or dur <= 0 or start < 0 or start + dur > total:
            err(f"{where}: startFrame and durationInFrames must be whole numbers placing it inside the "
                f"video (0-{total}).")
            continue
        end = start + dur
        label = tvs.PACKS[style]["label"]
        where = f"Insert {k + 1} ({label}, frames {start}-{end - 1})"
        if dur > max_frames:
            err(f"{where} lasts {dur / fps:.1f} s; an insert lasts at most {tinserts.MAX_SECONDS:.0f} s "
                f"(aim for {tinserts.TARGET_SECONDS:.0f}). Cover only the part of the segment it shows best.")
        if dur < min_frames:
            err(f"{where} lasts {dur / fps:.1f} s; an insert needs at least 2 s to be read.")
        if snaps and min(abs(start - w) for w in snaps) > tinserts.WORD_SNAP_FRAMES:
            nearest = min(snaps, key=lambda w: abs(start - w))
            err(f"{where} starts at frame {start}, which is not on a word; start it on a word (the nearest "
                f"word starts at {nearest}).")
        # The segment the insert starts in: the last one whose first word is at
        # or before the insert's start. A segment's endFrame can equal the next
        # one's startFrame when the narration has no pause, so the end cannot
        # decide it.
        starting = [i for i, s in enumerate(segments)
                    if _int(s.get("startFrame")) and s["startFrame"] - tinserts.WORD_SNAP_FRAMES <= start]
        seg_i = starting[-1] if starting else None
        if seg_i is None or marks.get(segments[seg_i].get("id")) != style:
            err(f"{where} does not start inside a segment the script marked as a {style} insert. An insert "
                "covers part of a segment marked \"insert\": \"" + style + "\".")
        else:
            seg = segments[seg_i]
            covered.add(seg.get("id"))
            limit = segments[seg_i + 1]["startFrame"] if seg_i + 1 < len(segments) else total
            if end > limit + tinserts.WORD_SNAP_FRAMES:
                err(f"{where} runs past its segment, into the next one's words (from frame {limit}); end it "
                    "by then, so the main style takes the next segment.")
            if seg_i == 0 or seg_i == len(segments) - 1:
                err(f"{where} is in the {'first' if seg_i == 0 else 'last'} segment; the main style carries "
                    "the opening and the ending.")
            if seg.get("role") == "payoff":
                err(f"{where} is in the segment that opens the payoff; the payoff belongs to the main style. "
                    "Mark another segment as the insert.")
        for s in segments:
            if s.get("role") == "payoff" and start <= s.get("startFrame", -1) < end:
                err(f"{where} covers the first word of the payoff (frame {s['startFrame']}); the payoff "
                    "belongs to the main style. End the insert before it.")
        spans.append((start, end, k))
        clash = caption_clash(style, subtitles)
        if clash:
            err(f"{where}: {clash}")
        check_one = style_checks.get(style)
        if check_one:
            for p in check_one(e):
                err(f"{where}: {p}")

    spans.sort()
    if spans:
        if spans[0][0] < gap:
            err(f"Insert {spans[0][2] + 1} starts at frame {spans[0][0]}; the video opens in its main style for "
                f"at least {tinserts.MIN_MAIN_GAP_SECONDS} s.")
        if total - spans[-1][1] < gap:
            err(f"Insert {spans[-1][2] + 1} ends at frame {spans[-1][1]}; the video ends in its main style, "
                f"with at least {tinserts.MIN_MAIN_GAP_SECONDS} s of it after the last insert.")
    for (a0, a1, ak), (b0, b1, bk) in zip(spans, spans[1:]):
        if b0 < a1:
            err(f"Inserts {ak + 1} and {bk + 1} overlap.")
        elif b0 - a1 < gap:
            err(f"Inserts {ak + 1} and {bk + 1} come back to back ({(b0 - a1) / fps:.1f} s apart); keep at "
                f"least {tinserts.MIN_MAIN_GAP_SECONDS} s of the main style between them.")
    # The main layer is hidden under an insert, so a main scene that starts
    # inside one is never seen starting: start it where the insert ends.
    for i, sc in enumerate(config.get("scenes") or []):
        sf = sc.get("startFrame") if isinstance(sc, dict) else None
        for a, b, k in spans:
            if _int(sf) and sf > 0 and a <= sf < b:
                err(f"Scene {i + 1} starts at frame {sf}, inside insert {k + 1} ({a}-{b - 1}), where the main "
                    f"style is hidden; start it at frame {b}, when the insert ends.")
    share = sum(b - a for a, b, _ in spans)
    if share > tinserts.MAX_SHARE * total:
        err(f"Inserts take {share / total:.0%} of the video; together they take at most a third. Drop one "
            "or shorten them.")
    for s in marked:
        if s.get("id") not in covered:
            err(f"Segment {s.get('id')!r} is marked as a {marks[s['id']]} insert but no insert covers it: "
                "add one, starting on one of its words.")
    return errors


def caption_clash(style: str, subtitles) -> str:
    """Why the captions still cover the insert once it has moved by
    shift_for, or "". The shift is bounded so the insert stays in the frame,
    so captions placed near the middle can leave no room."""
    if style not in BLOCKS:
        return ""
    box = caption_box(subtitles)
    if box is None:
        return ""
    top, bottom = BLOCKS[style]
    shift = shift_for(style, subtitles)
    if top + shift < box[1] and bottom + shift > box[0]:
        return ("the captions (subtitles.position) sit where this insert draws, and moving the insert "
                "cannot clear them. Put the captions in the lower or the upper part of the frame.")
    return ""


def cue_errors(cues, spans: list[tuple[int, int]]) -> list[str]:
    """The mascot is hidden during inserts, so a cue may not land inside one."""
    out = []
    for c in cues if isinstance(cues, list) else []:
        f = c.get("frame") if isinstance(c, dict) else None
        if _int(f) and any(a <= f < b for a, b in spans):
            out.append(f"the mascot cue at frame {f} falls inside an insert, where the mascot is hidden; move "
                       "it before or after the insert")
    return out


def fill(config: dict, *, canvas: str, transition: str) -> dict:
    """The config with each insert's src, palette and shift, and the main
    style's transition, filled in. The agent writes none of these."""
    entries = config.get("inserts") or []
    if not entries:
        config.pop("inserts", None)
        config.pop("insertTransition", None)
        return config
    out = []
    for e in entries:
        style = e["style"]
        block = tvs.PACKS[style]["insert"]
        palette = canvas if canvas in block["palettes"] else block["palettes"][0]
        out.append({**e, "src": block["component"], "palette": palette,
                    "shift": shift_for(style, config.get("subtitles"))})
    config["inserts"] = out
    config["insertTransition"] = transition
    return config
