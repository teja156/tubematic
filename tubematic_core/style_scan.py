"""The mechanical scan of an external style package before a person installs it (TMDEV-253).

A package is trusted once installed: its TSX runs in the renderer's Chromium
and its guide is read by the agent. The scan is what the install screen shows
that person before they say yes, so it reports, and refuses only what can never
work or never belongs in a style:

- refusals: an import the renderer does not ship (a package reaches the rest of
  the renderer through `@tubematic/scene-api`), a file type a style has no use
  for (a script, a binary).
- flags: code that reaches the network, evaluates strings, imports at run time
  or touches browser storage; guide lines that read as shell commands, tool
  calls outside the authoring skill or instructions to the agent; large files;
  fonts whose licence needs a look.

Flags never block an install; they are the questions the person should be able
to answer before approving. A clean scan is not a review.
"""
import pathlib
import re

from . import external_styles as ext

# What a package may import by name: what the renderer image ships for scenes.
# @remotion/google-fonts is left out (it fetches fonts over the network; a
# package ships its fonts in fonts/), and so are the build tools.
ALLOWED_IMPORTS = frozenset({
    "react", "react/jsx-runtime", "remotion", "@tubematic/scene-api",
    "@remotion/noise", "@remotion/paths", "@remotion/shapes", "@remotion/three", "@remotion/transitions",
    "three", "@react-three/fiber", "postprocessing", "d3-geo", "topojson-client", "@dagrejs/dagre", "zod",
})
# three's examples are part of the three package (loaders, controls, shaders)
_ALLOWED_PREFIXES = ("three/examples/jsm/", "three/addons/")

ALLOWED_SUFFIXES = frozenset({
    ".ts", ".tsx", ".json", ".md", ".txt", ".css",
    ".mp4", ".webm", ".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".woff", ".woff2", ".ttf", ".otf", ".glb", ".gltf", ".wav", ".mp3", ".ogg",
})
_TEXT_SUFFIXES = frozenset({".ts", ".tsx", ".json", ".md", ".txt", ".css", ".svg", ".gltf"})
_BARE_NAMES = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS|OFL)", re.I)

CODE_FILE_FLAG_BYTES = 200_000
FILE_FLAG_BYTES = 5_000_000
GUIDE_SHOWN_CHARS = 20_000

# The tools tubematic-external-style names (scripts/tests/test_external_style_skill.py
# pins this set to the skill). A guide that asks for any other tool is flagged.
AUTHORING_TOOLS = frozenset({
    "get_video", "get_style_guide", "get_timeline", "write_scene_config", "validate_job", "preview_frames",
    "submit_render", "add_comment", "write_scene_file", "list_scene_files", "read_scene_file",
    "cartoon_kit_list", "cartoon_kit_read", "cartoon_still", "cartoon_read_still", "cartoon_beat_gate",
    "cartoon_beat_gate_record", "cartoon_soundtrack", "render_style_parts", "render_style_props",
})

_CODE_PATTERNS = [
    (re.compile(r"\bfetch\s*\("), "reaches the network (fetch)"),
    (re.compile(r"\bXMLHttpRequest\b"), "reaches the network (XMLHttpRequest)"),
    (re.compile(r"\bWebSocket\b"), "reaches the network (WebSocket)"),
    (re.compile(r"\bEventSource\b"), "reaches the network (EventSource)"),
    (re.compile(r"\bsendBeacon\b"), "reaches the network (sendBeacon)"),
    (re.compile(r"\beval\s*\("), "evaluates a string as code (eval)"),
    (re.compile(r"\bnew\s+Function\b|\bFunction\s*\("), "evaluates a string as code (Function)"),
    (re.compile(r"\bimport\s*\("), "imports at run time (dynamic import)"),
    (re.compile(r"\brequire\s*\("), "loads a module with require"),
    (re.compile(r"document\.cookie|\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b"), "touches browser storage"),
    (re.compile(r"\bwindow\.open\b|\blocation\.(href|assign|replace)\b"), "navigates the page"),
    (re.compile(r"\bWorker\s*\(|\bimportScripts\b"), "starts a worker"),
    (re.compile(r"\bprocess\.env\b"), "reads environment variables"),
]
_SHELL_LINE = re.compile(
    r"^\s*(\$\s|sudo\b|curl\b|wget\b|bash\b|sh\s|zsh\b|rm\s|chmod\b|chown\b|pip3?\b|npm\b|npx\b|git\b|docker\b|"
    r"python3?\b|node\b|ssh\b|scp\b|nc\b|eval\b|export\s+\w+=)")
_SHELL_FENCE = re.compile(r"^\s*```\s*(bash|sh|shell|zsh|console|powershell|cmd)\b", re.I)
_INJECTION = re.compile(
    r"ignore (all |any |the )?(previous|prior|above|earlier|other) (instructions|rules|steps)|system prompt|"
    r"do not (tell|inform|show) the (user|human|person)|don'?t (tell|inform|show) the (user|human|person)|"
    r"without (asking|telling)|api[_ ]?key|access token|password|secret", re.I)
_TOOL_CALL = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s*\(")
_SPECIFIER_RE = ext._SPECIFIER_RE


def _allowed_import(spec: str) -> bool:
    return spec in ALLOWED_IMPORTS or spec.startswith(_ALLOWED_PREFIXES)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def scan(d: pathlib.Path) -> dict:
    """Scan a package folder. Raises nothing for a bad package; an unreadable
    folder is one refusal."""
    d = pathlib.Path(d)
    out = {"refusals": [], "flags": [], "files": [], "imports": {}, "guide": "", "fonts": []}
    try:
        files = ext._files(d)
    except (ext._Bad, OSError) as exc:
        out["refusals"].append(str(exc))
        return out

    def flag(name, line, what):
        out["flags"].append({"file": name, "line": line, "what": what})

    for name, path in sorted(files.items()):
        size = path.stat().st_size
        suffix = pathlib.PurePosixPath(name).suffix.lower()
        row = {"path": name, "bytes": size}
        if suffix in _TEXT_SUFFIXES:
            row["lines"] = _text(path).count("\n") + 1
        out["files"].append(row)
        base = pathlib.PurePosixPath(name).name
        if suffix not in ALLOWED_SUFFIXES and not (suffix in ("", ".txt") and _BARE_NAMES.match(base)):
            out["refusals"].append(f"{name}: a style package has no use for a {suffix or 'extensionless'} file")
            continue
        if size > FILE_FLAG_BYTES:
            flag(name, 0, f"a large file ({size // 1_000_000} MB)")
        if suffix in (".ts", ".tsx"):
            if size > CODE_FILE_FLAG_BYTES:
                flag(name, 0, f"a large code file ({size // 1000} KB): generated or minified code is hard to review")
            _scan_code(name, _text(path), out, flag)
        if suffix == ".svg" and re.search(r"<script|on\w+\s*=", _text(path), re.I):
            flag(name, 0, "an SVG with a script or an event handler")
        if name.startswith("fonts/"):
            out["fonts"].append(name)

    guide = files.get("guide/guide.md")
    if guide is not None:
        text = _text(guide)
        out["guide"] = text[:GUIDE_SHOWN_CHARS]
        _scan_guide("guide/guide.md", text, flag)
    for name in sorted(n for n in files if n.startswith("guide/") and n.endswith(".md") and n != "guide/guide.md"):
        _scan_guide(name, _text(files[name]), flag)

    if out["fonts"]:
        licences = [n for n in out["fonts"] if _BARE_NAMES.match(pathlib.PurePosixPath(n).name)]
        known = any(re.search(r"SIL Open Font License|Apache License|MIT License|Ubuntu Font Licence",
                              _text(files[n]), re.I) for n in licences)
        if not known:
            flag(licences[0] if licences else "fonts/", 0,
                 "the fonts' licence is not one this scan recognises (OFL, Apache, MIT, Ubuntu): read it")
    out["imports"] = dict(sorted(out["imports"].items()))
    return out


def _scan_code(name, text, out, flag):
    for spec in _SPECIFIER_RE.findall(text):
        if spec.startswith("."):
            continue
        out["imports"][spec] = out["imports"].get(spec, 0) + 1
        if not _allowed_import(spec) and f"{name}: imports {spec!r}" not in " ".join(out["refusals"]):
            out["refusals"].append(f"{name}: imports {spec!r}, which the renderer does not ship to styles "
                                   f"(allowed: {', '.join(sorted(ALLOWED_IMPORTS))})")
    for no, line in enumerate(text.splitlines(), 1):
        for pattern, what in _CODE_PATTERNS:
            if pattern.search(line):
                flag(name, no, what)


def _scan_guide(name, text, flag):
    for no, line in enumerate(text.splitlines(), 1):
        if _SHELL_FENCE.match(line) or _SHELL_LINE.match(line):
            flag(name, no, "reads as a shell command for the agent")
        if _INJECTION.search(line):
            flag(name, no, "reads as an instruction to the agent about secrets or about hiding something")
        for tool in _TOOL_CALL.findall(line):
            if tool not in AUTHORING_TOOLS:
                flag(name, no, f"asks for {tool}(), a tool the external-style skill does not use")
