"""External visual styles (TMDEV-252): style packages installed from outside the release.

A package is one folder, `<STYLES_DIR>/<id>/`, holding the style's pack
(`style.json`, the built-in pack schema plus an `external` block), the drawing
code the renderer compiles (`components/` for a scene style, `runner/` for a
whole-video world), the JSON Schema its scene props must match, the guide the
agent reads, previews, optional fonts, and a manifest of every file's sha256.

Packages come from other people, so nothing here raises on a bad one: it is
listed unavailable with the reason, and every other style keeps working. A
built-in pack that fails its check still stops the process (visual_styles.py);
that file ships with the release, a package does not.

The registry is read again whenever the folder changes (a package added,
removed or rewritten), so installing a style needs no restart.
"""
import dataclasses
import hashlib
import json
import os
import pathlib
import posixpath
import re
import stat

from . import jobfiles

SCENE_API = 1
ID_RE = re.compile(r"ext_[a-z0-9_]{1,40}")
PROPS_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,40}")
AUTHORING_SKILL = "tubematic-external-style"
STYLES_DIR = pathlib.Path(os.environ.get("TUBEMATIC_STYLES_DIR", "/app/remotion/src/scenes/external"))
MANIFEST = "MANIFEST.json"
# The approval record (TMDEV-253): {id: {"fingerprint", "version", "source", "reviewed", "installed_at"}}.
# A person approves every package on the dashboard's install screen; a package
# with no record, or whose files changed after it was approved, is listed
# unavailable, so a changed package goes through that screen again. A file
# beside the packages, not a table: the renderer and upgrade.py read packages
# without the database.
INSTALLED = ".installed.json"
NOT_APPROVED = "it has not been approved: review it on the dashboard's Styles page"
CHANGED = "its files changed after it was approved: review it again on the dashboard's Styles page"
# The built-in previews' caps (tubematic_core/tests/test_style_packs.py), so an
# external style costs the picker no more than a built-in one.
PREVIEW_CAPS = {"preview.mp4": 400_000, "preview.webp": 40_000}
_EXTERNAL_KEYS = {"version": str, "author": str, "source": str, "licence": str,
                  "scene_api": int, "props_key": str}
_REQUIRED = ("schema.json", "guide/guide.md", "guide/example-config.json", "preview.mp4", "preview.webp")
_CODE_DIR = {"dom": "components", "cartoon_3d": "runner"}
# The module specifiers of a TypeScript file: `from "x"`, `import "x"`, `import("x")`, `require("x")`.
_SPECIFIER_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"'\n]+)["']""")


@dataclasses.dataclass(frozen=True)
class ExternalStyle:
    id: str
    path: pathlib.Path
    pack: dict | None
    ok: bool
    reason: str
    # a valid package that only waits for a person's approval (a Review button, not a broken package)
    needs_review: bool = False


class _Bad(Exception):
    pass


def _files(d: pathlib.Path) -> dict[str, pathlib.Path]:
    """Every plain file under d by its relative path; a symlink or any other
    entry is refused, since its target can change without the package changing."""
    out = {}

    def walk(cur, rel):
        for entry in sorted(os.scandir(cur), key=lambda e: e.name):
            name = f"{rel}/{entry.name}" if rel else entry.name
            mode = os.lstat(entry.path).st_mode
            if stat.S_ISLNK(mode):
                raise _Bad(f"{name} is a symlink; a style package holds plain files only")
            if stat.S_ISDIR(mode):
                walk(entry.path, name)
            elif stat.S_ISREG(mode):
                out[name] = pathlib.Path(entry.path)
            else:
                raise _Bad(f"{name} is not a regular file")

    walk(d, "")
    return out


def _check_manifest(files: dict[str, pathlib.Path]) -> None:
    if MANIFEST not in files:
        raise _Bad(f"{MANIFEST} is missing")
    try:
        listed = json.loads(files[MANIFEST].read_text(encoding="utf-8"))["files"]
    except (ValueError, KeyError, TypeError) as exc:
        raise _Bad(f"{MANIFEST} is not valid ({exc})") from exc
    if not isinstance(listed, dict):
        raise _Bad(f"{MANIFEST} files must be an object of path: sha256")
    present = set(files) - {MANIFEST}
    for name in sorted(present - set(listed)):
        raise _Bad(f"{name} is not in {MANIFEST}")
    for name in sorted(set(listed) - present):
        raise _Bad(f"{name} is in {MANIFEST} but missing")
    for name in sorted(present):
        if hashlib.sha256(files[name].read_bytes()).hexdigest() != listed[name]:
            raise _Bad(f"{name} does not match its {MANIFEST} checksum")


def _check_external_rules(sid: str, pack: dict) -> None:
    if pack.get("role") != "main":
        raise _Bad("role must be \"main\": an external style carries a whole video")
    if pack.get("inserts") != {"host": False}:
        raise _Bad("inserts must be {\"host\": false}: external styles host no inserts yet")
    if pack.get("mascot") is not False:
        raise _Bad("mascot must be false: external styles take no mascot")
    if pack.get("authoring_skill") != AUTHORING_SKILL:
        raise _Bad(f"authoring_skill must be {AUTHORING_SKILL!r}")
    block = pack.get("external")
    if not isinstance(block, dict):
        raise _Bad("the pack needs an \"external\" block")
    for key, kind in _EXTERNAL_KEYS.items():
        value = block.get(key)
        if not isinstance(value, kind) or isinstance(value, bool) or (kind is str and not value.strip()):
            raise _Bad(f"external.{key} must be a non-empty {kind.__name__}")
    if block["scene_api"] != SCENE_API:
        raise _Bad(f"external.scene_api is {block['scene_api']}, and this Tubematic draws scene_api {SCENE_API}")
    if not PROPS_KEY_RE.fullmatch(block["props_key"]):
        raise _Bad("external.props_key must be a plain identifier")


def _check_files(pack: dict, files: dict[str, pathlib.Path]) -> None:
    for name in _REQUIRED:
        if name not in files:
            raise _Bad(f"{name} is missing")
    for name, cap in PREVIEW_CAPS.items():
        if files[name].stat().st_size > cap:
            raise _Bad(f"{name} is larger than {cap} bytes")
    try:
        schema = json.loads(files["schema.json"].read_text(encoding="utf-8"))
    except ValueError as exc:
        raise _Bad(f"schema.json is not valid JSON ({exc})") from exc
    if not isinstance(schema, dict):
        raise _Bad("schema.json must be a JSON Schema object")
    code = _CODE_DIR[pack["renderer"]]
    if not any(n.startswith(f"{code}/") and n.endswith(".tsx") for n in files):
        raise _Bad(f"a {pack['renderer']} style needs its code in {code}/ (at least one .tsx file)")
    for name in sorted(n for n in files if n.endswith((".ts", ".tsx"))):
        for spec in _SPECIFIER_RE.findall(files[name].read_text(encoding="utf-8", errors="replace")):
            if spec.startswith("/"):
                raise _Bad(f"{name} imports {spec!r}, a path outside the package")
            if spec.startswith("."):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), spec))
                if target == ".." or target.startswith("../"):
                    raise _Bad(f"{name} imports {spec!r}, outside the package: a package reaches the rest "
                               "of the renderer through @tubematic/scene-api")
    fonts = [n for n in files if n.startswith("fonts/")]
    if fonts and not any(re.match(r"fonts/(OFL|LICEN[CS]E)", n, re.I) for n in fonts):
        raise _Bad("fonts/ needs a licence file (fonts/OFL.txt or fonts/LICENSE)")


def _check(sid: str, d: pathlib.Path) -> dict:
    from . import visual_styles as tvs  # visual_styles reads this registry; import late

    if not ID_RE.fullmatch(sid):
        raise _Bad("the folder name is the style id, which must look like ext_<lowercase letters, digits, _>")
    if os.path.islink(d):
        raise _Bad("the package folder is a symlink")
    files = _files(d)
    _check_manifest(files)
    if "style.json" not in files:
        raise _Bad("style.json is missing")
    try:
        pack = json.loads(files["style.json"].read_text(encoding="utf-8"))
    except ValueError as exc:
        raise _Bad(f"style.json is not valid JSON ({exc})") from exc
    try:
        tvs._check_pack(pathlib.Path(f"{sid}.json"), pack)
    except tvs.PackError as exc:
        raise _Bad(str(exc)) from exc
    _check_external_rules(sid, pack)
    _check_files(pack, files)
    return pack


def approvals(root: pathlib.Path) -> dict:
    """The approval record of the packages under root; {} when there is none or it is unreadable."""
    try:
        data = json.loads((pathlib.Path(root) / INSTALLED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _write_approvals(root: pathlib.Path, data: dict) -> None:
    path = pathlib.Path(root) / INSTALLED
    tmp = path.with_name(f"{INSTALLED}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def approve(root: pathlib.Path, sid: str, **meta) -> str:
    """Record the package under root/sid as approved as it is now; returns its fingerprint."""
    fp = jobfiles.source_fingerprint(pathlib.Path(root) / sid)
    data = approvals(root)
    data[sid] = {**meta, "fingerprint": fp}
    _write_approvals(root, data)
    return fp


def drop_approval(root: pathlib.Path, sid: str) -> None:
    data = approvals(root)
    if data.pop(sid, None) is not None:
        _write_approvals(root, data)


def _checked(sid: str, d: pathlib.Path, record: dict | None) -> ExternalStyle:
    try:
        pack = _check(sid, d)
        fp = jobfiles.source_fingerprint(d)
    except (_Bad, OSError, jobfiles.UnsafePath) as exc:
        return ExternalStyle(sid, d, None, False, str(exc))
    if not record:
        return ExternalStyle(sid, d, pack, False, NOT_APPROVED, needs_review=True)
    if record.get("fingerprint") != fp:
        return ExternalStyle(sid, d, pack, False, CHANGED, needs_review=True)
    return ExternalStyle(sid, d, pack, True, "")


def load(root: pathlib.Path) -> dict[str, ExternalStyle]:
    """Every package folder under root, valid or not, by id."""
    root = pathlib.Path(root)
    if not root.is_dir():
        return {}
    records = approvals(root)
    out = {}
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        if entry.name.startswith(".") or not (entry.is_dir() or entry.is_symlink()):
            continue
        out[entry.name] = _checked(entry.name, pathlib.Path(entry.path), records.get(entry.name))
    return out


_cache: tuple = (None, None, {})


def _stamp(root: pathlib.Path):
    if not root.is_dir():
        return ()
    # Every file's mtime and size, so a file edited in place reloads the
    # registry too: packages are a few dozen files, so the walk is cheap.
    rows = []
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        # a folder can vanish between the listing and the stat (a package being removed)
        try:
            d = os.lstat(entry.path).st_mtime_ns
        except OSError:
            continue
        files = []
        for top, dirs, names in os.walk(entry.path):
            dirs.sort()
            for name in sorted(names):
                try:
                    st = os.lstat(os.path.join(top, name))
                except OSError:
                    continue
                files.append((os.path.relpath(os.path.join(top, name), entry.path), st.st_mtime_ns, st.st_size))
        rows.append((entry.name, d, tuple(files)))
    return tuple(rows)


def registry() -> dict[str, ExternalStyle]:
    """The installed packages, read again when any file of the folder changes."""
    global _cache
    root, stamp = STYLES_DIR, _stamp(STYLES_DIR)
    if _cache[0] != root or _cache[1] != stamp:
        _cache = (root, stamp, load(root))
    return _cache[2]


def get(sid: str) -> ExternalStyle | None:
    return registry().get((sid or "").strip())


def check_now(sid: str) -> ExternalStyle | None:
    """One installed package checked from disk, past the registry's cache. The
    cache reloads on any file's mtime or size; an edit that keeps both (a
    copy with preserved times) still reaches this. The gates that queue a
    render use it."""
    sid = (sid or "").strip()
    d = STYLES_DIR / sid
    if not ID_RE.fullmatch(sid) or not (d.is_dir() or d.is_symlink()):
        return None
    return _checked(sid, d, approvals(STYLES_DIR).get(sid))


def check_folder(sid: str, d: pathlib.Path) -> tuple[dict | None, str]:
    """A package folder that is not installed (a staged install): its pack, or
    None and the reason it would be listed unavailable."""
    try:
        return _check(sid, pathlib.Path(d)), ""
    except (_Bad, OSError) as exc:
        return None, str(exc)


def config_style(config) -> str:
    """The external style a scene-config draws (the first `source: "external"`
    scene's style id), or "" when it draws none. The bundlers compile that one
    package (renderer/remotion/webpack-override.mjs)."""
    scenes = config.get("scenes") if isinstance(config, dict) else None
    for scene in scenes if isinstance(scenes, list) else []:
        if isinstance(scene, dict) and scene.get("source") == "external" and isinstance(scene.get("src"), str):
            sid = scene["src"].split("/", 1)[0]
            return sid if ID_RE.fullmatch(sid) else ""
    return ""


def write_manifest(d: pathlib.Path) -> None:
    """Write `MANIFEST.json` for a package folder: every other file's sha256."""
    d = pathlib.Path(d)
    files = {name: hashlib.sha256(path.read_bytes()).hexdigest()
             for name, path in _files(d).items() if name != MANIFEST}
    (d / MANIFEST).write_text(json.dumps({"files": files}, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8")


def fingerprint(sid: str) -> str:
    """A short hash of one installed package's files, as the render compares them."""
    return jobfiles.source_fingerprint(STYLES_DIR / sid)
