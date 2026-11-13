"""What the code-drawn character styles share on the Python side (Mid-century
How-To, Process Cast, Comic Panels, Puppet History): the custom-prop checks,
and small number helpers. character_styles holds the registry the MCP
server, the picture checks and the text-layout audit loop over.

Each style module (midcentury_howto, ...) exposes the same names:
STYLE_ID, SCENE_SRC, PROPS_KEY, LIBRARY_KEY, TIMING, is_scene(scene),
check_scene_use(visual_style, scenes),
custom_prop_errors(custom, video_id, library, sources), check(config, fps, word_starts, words,
extra, video_id, sources, quiet), audit_windows(config),
change_frames(data), first_frame_problem(data), sample_text(data, prop_id)
and CHANGE_FIX. A new style of
this kind is one more module in STYLES.

Free of the database and of I/O.
"""
from __future__ import annotations

import re

from bean_explainer import FORBIDDEN_SOURCE, _IMPORT

_CUSTOM_ACT = re.compile(r"^[a-z0-9]{2,16}$")
_CUSTOM_FILE = re.compile(r"^prop-[a-z0-9-]{1,40}$")
ID = re.compile(r"^[a-z0-9_]{1,24}$")
# A character style's drawing is rasterised into a cached bitmap outside the
# render's React tree, so a hook (useCurrentFrame, useState...) has no frame or
# state to read there: the drawing gets everything it needs as props.
HOOK = (re.compile(r"\buse[A-Z]\w*\b"),
        "a React or Remotion hook (useCurrentFrame, useState...): the drawing gets its phase, act and text as props")
# The source rules read the raw text, so each looks for the bare word: a comment, a bracket or a
# comma between the name and its call (`import/**/(...)`, `(0, eval)(...)`, `React["useState"]`)
# must not slip a dynamic import, an eval or a hook past them.
STRICT_SOURCE = (
    (re.compile(r"\brequire\b"), "require: a prop imports with `import` only"),
    (re.compile(r"\beval\b"), "eval"),
    (re.compile(r"\bFunction\b"), "the Function constructor"),
    (re.compile(r"\.constructor\b|\bconstructor\s*\]|[\"']constructor[\"']"), "a constructor lookup, which can build a function from text"),
    (re.compile(r"\bReact\s*\["), "React[...] lookups (a hook by another name)"),
)
# A static import at the top of the file; once these are taken out, any other `import` is dynamic or import.meta.
# Between `import` and `from` a static import holds only names, braces, commas, `*` and spaces: no
# comment, string or parenthesis, so a dynamic `import (...)` cannot hide behind a `from "..."` written
# in a comment. An import may follow another on the same line after a `;`.
_STATIC_IMPORT = re.compile(r"""(?:^|(?<=;))\s*import\s+(?=[\w{*$])[\w\s{},*$]*?\bfrom\s*["'][^"']+["']\s*;?"""
                            r"""|(?:^|(?<=;))\s*import\s*["'][^"']+["']\s*;?""", re.M)
_OTHER_IMPORT = re.compile(r"\bimport\b")


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def overlap(a, b, tol: float) -> bool:
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


def echo_runs(words: list[str], n: int) -> set[tuple]:
    """Every run of n narration words, normalised, to spot a label that repeats the narration."""
    narration = [norm(w) for w in words]
    return {tuple(narration[i:i + n]) for i in range(max(0, len(narration) - n + 1))}


def echoes(text: str, runs: set[tuple], n: int) -> bool:
    words = [norm(w) for w in text.split()]
    return any(tuple(words[k:k + n]) in runs for k in range(max(0, len(words) - n + 1)))


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None, custom_limits: dict,
                       allowed_import: re.Pattern, allowed_text: str) -> tuple[list[str], dict, dict]:
    """Problems with a config's customProps, and the catalogue and boxes with
    them added: (errors, {id: {text, acts}}, {id: (w, h)}). `library` is the
    pack's catalogue ({id: {text, acts}}); `sources` maps each src to its
    file's text, or is None to skip the source checks. The source rules are
    Bean Explainer's (bean_explainer.FORBIDDEN_SOURCE) plus no hooks."""
    errs: list[str] = []
    catalog: dict = dict(library)
    boxes: dict = {}
    if custom is None:
        return errs, catalog, boxes
    lim = custom_limits
    if not isinstance(custom, list) or len(custom) > lim["maxProps"]:
        return [f"customProps must be a list of at most {lim['maxProps']} props."], catalog, boxes
    for i, c in enumerate(custom):
        where = f"customProps {i + 1}"
        if not isinstance(c, dict):
            errs.append(f"{where} must be an object.")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not ID.match(cid) or cid in catalog:
            errs.append(f"{where}: id {cid!r} must be lowercase letters, digits or _, and not a library "
                        "name or another custom prop's id.")
            continue
        src = c.get("src")
        stem = src.split("/", 1)[1] if isinstance(src, str) and "/" in src else ""
        if (not isinstance(src, str) or not _CUSTOM_FILE.match(stem)
                or (video_id and src.split("/", 1)[0] != video_id)):
            errs.append(f"{where} ({cid}): src must be the src write_scene_file returned for this video's "
                        "prop-<name> file (\"<video_id>/prop-<name>\").")
            continue
        w, h = c.get("w"), c.get("h")
        if not (is_int(w) and is_int(h) and lim["minSide"] <= w <= lim["maxSide"] and lim["minSide"] <= h <= lim["maxSide"]):
            errs.append(f"{where} ({cid}): w and h are its box at scale 1, whole pixels from {lim['minSide']} "
                        f"to {lim['maxSide']}.")
            continue
        text = c.get("text", 0)
        if not is_int(text) or not 0 <= text <= lim["maxText"]:
            errs.append(f"{where} ({cid}): text is the most characters its text slot takes, 0 to {lim['maxText']}.")
            continue
        acts = c.get("acts", [])
        if (not isinstance(acts, list) or len(acts) > lim["maxActs"]
                or not all(isinstance(a, str) and _CUSTOM_ACT.match(a) for a in acts)):
            errs.append(f"{where} ({cid}): acts is a list of at most {lim['maxActs']} lowercase names.")
            continue
        if sources is not None:
            body = sources.get(src)
            if body is None:
                errs.append(f"{where} ({cid}): there is no {src}.tsx; write it with write_scene_file first.")
                continue
            for pattern, why in (*FORBIDDEN_SOURCE, HOOK):
                if pattern.search(body):
                    errs.append(f"{where} ({cid}): the drawing uses {why}.")
            for pattern, why in STRICT_SOURCE:
                if pattern.search(body):
                    errs.append(f"{where} ({cid}): the drawing uses {why} (the check reads comments and strings too, "
                                "so leave the word out of them).")
            if _OTHER_IMPORT.search(_STATIC_IMPORT.sub("", body)):
                errs.append(f"{where} ({cid}): the drawing uses an import other than a static `import ... from` at the "
                            "top of the file (a dynamic import or import.meta; the check reads comments too, so the "
                            "word import may appear only in the import lines, and those hold no comment).")
            named = [next((g for g in groups if g), "") for groups in _IMPORT.findall(body)]
            bad = [m or '""' for m in named if not allowed_import.match(m)]
            if bad:
                errs.append(f"{where} ({cid}): it imports {', '.join(sorted(set(bad)))}; a prop imports only "
                            f"{allowed_text}.")
            if not re.search(r"export\s+default\b", body):
                errs.append(f"{where} ({cid}): the file must default-export the drawing component.")
        catalog[cid] = {"text": text, "acts": acts}
        boxes[cid] = (w, h)
    return errs, catalog, boxes


def sample_windows(windows: list[tuple[int, int]], first_after: int, end_margin: int) -> list[tuple[int, int]]:
    """Text-audit windows for a style's shots: from `first_after` frames into
    each shot (its pops have settled) to `end_margin` frames before its cut."""
    out = []
    for a, b in windows:
        first = min(a + first_after, b - 1)
        last = max(first, b - 1 - end_margin)
        out.append((first, last + 1))
    return out
