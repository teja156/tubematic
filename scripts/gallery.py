#!/usr/bin/env python3
"""The Tubematic style gallery's tools (TMDEV-255).

The gallery is a repository the maintainer curates (its skeleton is
scripts/gallery/repo/). Each submission is a package folder `styles/<id>/` or a
pointer `styles/<id>.json` naming the author's repository at a pinned commit:
{"repo": "https://github.com/someone/style", "commit": "<40 hex>"}. The
gallery's CI checks out Tubematic and runs:

    python3 scripts/gallery.py scan <gallery>/styles [--only ext_a,ext_b]
        Check and scan each package the way an install does. Prints a Markdown
        report; exits 1 when a package fails its check or the scan refuses it.

    python3 scripts/gallery.py build <gallery>/styles <site dir> --base-url https://…/ [--repo-url https://…]
        Write the site: archives/<id>-<version>.zip (a deterministic zip of the
        package), previews/<id>.mp4 and .webp, index.json, which Tubematic's
        Gallery tab reads and every gallery install checks against, and
        index.html, a page people browse (it links the repo's submission guide
        when --repo-url is given).

    python3 scripts/gallery.py render <package> <out.mp4> --image <tubematic backend image>
        Render a scene style's example config (silent) in the backend image, for
        the review. A 3D world style's example needs generated source, so it is
        rendered by hand: exit code 3. Any other failure exits 1.

    python3 scripts/gallery.py stage <gallery>/styles <out dir> [--only ext_a,ext_b]
        Copy each submission's package to <out dir>/<id>/ as plain files (a
        pointer is fetched at its pinned commit; symlinks are left out; a dot-file,
        CLAUDE.md or AGENTS.md is renamed *.submitted so no agent loads it), for
        the Claude review to read. Exits 1 when a submission cannot be fetched or
        is submitted twice.
"""
import argparse
import base64
import hashlib
import html
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import external_styles as ext  # noqa: E402
from tubematic_core import style_install  # noqa: E402
from tubematic_core import style_scan  # noqa: E402

INDEX_VERSION = 1
# render's exit code for a style CI cannot render (a 3D world): a notice, never a pass for a failed render
NOT_RENDERABLE = 3
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
# the version names the published archive (archives/<id>-<version>.zip): a safe file name and URL part
VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,39}")
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class GalleryError(Exception):
    pass


def submissions(styles_dir: pathlib.Path, only: set[str] | None = None) -> list[tuple[str, pathlib.Path]]:
    """(id, path) of every submission: a folder, or a `.json` pointer."""
    out = []
    for entry in sorted(pathlib.Path(styles_dir).iterdir()):
        sid = entry.stem if entry.suffix == ".json" else entry.name
        if entry.name.startswith(".") or (only and sid not in only):
            continue
        # every visible entry is listed, so materialise refuses a symlink or a stray file by name
        out.append((sid, entry))
    return out


def materialise(sid: str, entry: pathlib.Path, work: pathlib.Path) -> tuple[pathlib.Path, dict]:
    """The package folder of a submission, and where it came from. A pointer is
    fetched at its pinned commit with the installer's own git fetch."""
    if entry.is_symlink():
        # git checks out symlinks: one could point the scan, or the review's artifact, at the runner
        raise GalleryError(f"styles/{entry.name} is a symlink; submit the folder or pointer itself")
    if entry.is_dir():
        return entry, {"kind": "folder"}
    if entry.suffix != ".json":
        raise GalleryError(f"styles/{entry.name} is neither a package folder nor a .json pointer")
    try:
        pointer = json.loads(entry.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise GalleryError(f"{entry.name} is not valid JSON") from exc
    repo, commit = pointer.get("repo"), pointer.get("commit")
    if not isinstance(repo, str) or not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise GalleryError(f"{entry.name} must be {{\"repo\": <https url>, \"commit\": <40-hex commit>}}")
    style_install._check_git_source(repo, commit)
    dest = work / f"{sid}-src"
    got = style_install._git(repo, commit, dest)
    return style_install._package_root(dest), {"kind": "repo", "repo": repo, "commit": got}


def check_one(sid: str, pkg: pathlib.Path) -> dict:
    pack, reason = ext.check_folder(sid, pkg)
    if pack is not None and pack.get("id") != sid:
        pack, reason = None, f"the submission is named {sid} but style.json's id is {pack.get('id')!r}"
    version = str(((pack or {}).get("external") or {}).get("version", ""))
    if pack is not None and not VERSION_RE.fullmatch(version):
        pack, reason = None, (f"external.version {version!r} must be letters, digits, '.', '+', '_' or '-' "
                              "(it names the published archive)")
    return {"id": sid, "pack": pack, "reason": reason, "scan": style_scan.scan(pkg)}


def scan(args) -> int:
    only = set(filter(None, (args.only or "").split(","))) or None
    failed = False
    lines = ["# Style gallery scan", ""]
    with tempfile.TemporaryDirectory() as tmp:
        for sid, entry in submissions(pathlib.Path(args.styles), only):
            try:
                pkg, origin = materialise(sid, entry, pathlib.Path(tmp))
                result = check_one(sid, pkg)
            except (GalleryError, style_install.InstallError) as exc:
                failed = True
                lines += [f"## {sid}: FAILED", "", f"- {exc}", ""]
                continue
            ok = result["pack"] is not None and not result["scan"]["refusals"]
            failed |= not ok
            lines += [f"## {sid}: {'passes' if ok else 'FAILED'}", ""]
            if origin["kind"] == "repo":
                lines.append(f"- Source: {origin['repo']} at {origin['commit']}")
            if result["pack"] is None:
                lines.append(f"- Check: {result['reason']}")
            else:
                block = result["pack"]["external"]
                lines.append(f"- {result['pack']['label']} {block['version']} by {block['author']}, "
                             f"licence {block['licence']}, renderer {result['pack']['renderer']}"
                             + (", needs a GPU" if result["pack"]["needs"]["gpu"] else ""))
            lines += [f"- Refused: {r}" for r in result["scan"]["refusals"]]
            lines += [f"- Flag: `{f['file']}{':' + str(f['line']) if f['line'] else ''}` {f['what']}"
                      for f in result["scan"]["flags"]]
            files = result["scan"]["files"]
            lines += [f"- {len(files)} files, {sum(f.get('lines', 0) for f in files)} lines of text, imports: "
                      + (", ".join(result["scan"]["imports"]) or "none"), ""]
    print("\n".join(lines))
    return 1 if failed else 0


def deterministic_zip(pkg: pathlib.Path, sid: str) -> bytes:
    """The package as a zip whose bytes depend only on its files: fixed times and order."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in sorted(ext._files(pkg).items()):
            info = zipfile.ZipInfo(f"{sid}/{name}", date_time=_ZIP_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    return buf.getvalue()


# The dashboard's look (dashboard/app/globals.css: its CRT tokens, Space Mono and Inter, square
# corners, amber section marks). Copied, since the page ships without the dashboard; the tokens are
# pinned to globals.css by scripts/tests/test_gallery.py.
_PAGE_CSS = """
:root {
  --bg: #08090d; --panel: #0c1018; --panel-2: #11151f; --border: #1c2330; --border-2: #2a3344;
  --ink: #e6e8ec; --ink-2: #b6bdca; --dim: #939cae; --mute: #7d869a; --amber: #f5a623;
  --amber-soft: rgba(245, 166, 35, 0.16);
  --mono: "Space Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans: "Inter", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  color-scheme: dark;
}
* { box-sizing: border-box; }
::selection { background: var(--amber); color: #000; }
body {
  margin: 0; color: var(--ink); font: 15px/1.6 var(--sans); -webkit-font-smoothing: antialiased;
  background:
    radial-gradient(1400px 800px at 80% -10%, rgba(245, 166, 35, 0.04), transparent 60%),
    radial-gradient(1100px 700px at -10% 110%, rgba(95, 163, 255, 0.03), transparent 55%),
    var(--bg);
  background-attachment: fixed;
}
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 9999; opacity: 0.6;
  background: repeating-linear-gradient(to bottom, rgba(255, 255, 255, 0.012) 0, rgba(255, 255, 255, 0.012) 1px, transparent 1px, transparent 3px);
}
a { color: var(--amber); }
a:focus-visible { outline: 1px solid var(--amber); outline-offset: 2px; }
header {
  display: flex; align-items: center; gap: 14px; height: 56px; border-bottom: 1px solid var(--border);
  padding: 0 max(16px, env(safe-area-inset-left)); background: rgba(8, 9, 13, 0.85);
}
.brand { display: flex; align-items: center; gap: 12px; font: 700 17px var(--mono); letter-spacing: 0.02em; }
.brand img { width: 36px; height: 36px; display: block; }
.divider { width: 1px; height: 18px; background: var(--border-2); }
.crumb { font: 12px var(--mono); letter-spacing: 0.14em; text-transform: uppercase; color: var(--amber); }
main { max-width: 1240px; margin: 0 auto; padding: 32px max(16px, env(safe-area-inset-left)) 64px; }
h1 { font: 400 18px var(--mono); margin: 0 0 10px; letter-spacing: 0.02em; }
.lede { max-width: 78ch; color: var(--dim); margin: 0 0 10px; }
.how { max-width: 78ch; color: var(--ink-2); margin: 0; padding: 12px 14px; border: 1px solid var(--border); background: var(--panel); }
.how b { color: var(--ink); font-weight: 600; }
.label { display: flex; align-items: center; gap: 14px; margin: 32px 0 16px; font: 10.5px var(--mono);
  letter-spacing: 0.22em; text-transform: uppercase; color: var(--mute); }
.label .mark { color: var(--amber); margin-right: -8px; }
.label .rule { flex: 1; height: 1px; background: linear-gradient(to right, var(--border) 0, var(--border) 60%, transparent); }
.label .count { color: var(--ink-2); letter-spacing: 0.18em; padding: 2px 8px; border: 1px solid var(--border-2); background: var(--panel); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.card { background: var(--panel); border: 1px solid var(--border); display: grid; align-content: start; min-width: 0; }
.card:hover { border-color: var(--border-2); }
.card video { width: 100%; aspect-ratio: 9 / 16; object-fit: cover; background: #000; display: block; border-bottom: 1px solid var(--border); }
.body { padding: 12px 12px 14px; display: grid; gap: 6px; min-width: 0; }
.body h2 { font: 600 15px var(--sans); margin: 0; }
.meta, .sum { font: 11.5px/1.55 var(--mono); color: var(--dim); overflow-wrap: anywhere; }
.sum { color: var(--mute); }
.body p { margin: 0; font-size: 14px; color: var(--ink-2); }
.btn { justify-self: start; margin-top: 4px; font: 11px var(--mono); letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--amber); border: 1px solid var(--amber); padding: 6px 12px; text-decoration: none; }
.btn:hover { background: var(--amber-soft); }
.empty { color: var(--dim); font-family: var(--mono); }
footer { margin-top: 40px; color: var(--mute); font: 12px var(--mono); }
"""


def _logo_uri() -> str:
    """The dashboard's logo mark, as an image (its own SVG ids stay inside it). Empty when this
    checkout has no dashboard."""
    path = REPO_ROOT / "dashboard" / "public" / "logo-mark.svg"
    return ("data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()) if path.is_file() else ""


def render_page(entries: list[dict], repo_url: str = "") -> str:
    """The gallery's browsable page (index.html), from the same entries as index.json, in the
    dashboard's look. Static and script-free. Every package field is a submitter's text, so all of
    it is escaped, and a homepage is linked only when it is an https address. Paths are relative,
    so the page works at any address."""
    e = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    cards = []
    for s in entries:
        archive = s["archive_url"].rsplit("/", 1)[-1]
        homepage = s.get("homepage") or ""
        home = (f' · <a href="{e(homepage)}" rel="noopener">homepage</a>'
                if re.fullmatch(r"https://[^\s\"'<>]+", homepage) else "")
        needs = "needs a GPU" if s.get("needs_gpu") else "renders on a CPU"
        cards.append(
            f'<article class="card" id="{e(s["id"])}">'
            f'<video src="previews/{e(s["id"])}.mp4" poster="previews/{e(s["id"])}.webp" '
            f'muted loop autoplay playsinline preload="none" aria-label="Preview of {e(s["name"])}"></video>'
            f'<div class="body"><h2>{e(s["name"])}</h2>'
            f'<div class="meta">{e(s["id"])} · {e(s["version"])} · {e(s["author"])} · {e(s["licence"])}</div>'
            f'<p>{e(s["tagline"])}</p>'
            f'<div class="meta">{e(needs)}{home}</div>'
            f'<a class="btn" href="archives/{e(archive)}" download>Download zip</a>'
            f'<div class="sum">sha256 {e(s["sha256"])}</div></div></article>')
    listing = (f'<div class="grid">{"".join(cards)}</div>' if cards
               else '<p class="empty">No styles yet.</p>')
    submit = (f' To add a style, read <a href="{e(repo_url.rstrip("/"))}/blob/main/SUBMITTING.md">the submission guide</a>.'
              if re.fullmatch(r"https://[^\s\"'<>]+", repo_url or "") else "")
    logo = _logo_uri()
    mark = f'<img src="{logo}" alt="">' if logo else ""
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Tubematic style gallery</title>"
        + (f'<link rel="icon" href="{logo}">' if logo else "")
        + "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700"
        "&amp;family=Inter:wght@400;500;600&amp;display=swap\">"
        f"<style>{_PAGE_CSS}</style></head><body>"
        f'<header><div class="brand">{mark}<span>TUBEMATIC</span></div><div class="divider"></div>'
        '<div class="crumb">Style gallery</div></header><main>'
        "<h1>External styles</h1>"
        "<p class=\"lede\">Visual styles for Tubematic, each reviewed by a maintainer before it was published. "
        "A style is code that runs in Tubematic's renderer: a review lowers the risk of installing one, "
        "it does not remove it.</p>"
        "<p class=\"how\">To install one, open your Tubematic dashboard and go to <b>Profiles</b> → <b>Styles</b> "
        "→ <b>Gallery</b>. Or download its zip and use <b>Install from file</b> there. Either way, Tubematic "
        f"checks the download against its sha256 and shows you the package before it installs.{submit}</p>"
        f'<div class="label"><span class="mark">▌</span><span>Styles</span><div class="rule"></div>'
        f'<span class="count">{len(entries)}</span></div>'
        f"{listing}"
        "<footer>The machine-readable list is <a href=\"index.json\">index.json</a>.</footer>"
        "</main></body></html>\n")


def build(args) -> int:
    site = pathlib.Path(args.site)
    base = args.base_url.rstrip("/") + "/"
    for sub in ("archives", "previews"):
        (site / sub).mkdir(parents=True, exist_ok=True)
    entries = []
    with tempfile.TemporaryDirectory() as tmp:
        for sid, entry in submissions(pathlib.Path(args.styles)):
            pkg, origin = materialise(sid, entry, pathlib.Path(tmp))
            result = check_one(sid, pkg)
            if result["pack"] is None or result["scan"]["refusals"]:
                print(f"{sid}: left out of the index: {result['reason'] or result['scan']['refusals'][0]}",
                      file=sys.stderr)
                return 1
            pack, block = result["pack"], result["pack"]["external"]
            data = deterministic_zip(pkg, sid)
            archive = f"archives/{sid}-{block['version']}.zip"
            (site / archive).write_bytes(data)
            shutil.copyfile(pkg / "preview.mp4", site / "previews" / f"{sid}.mp4")
            shutil.copyfile(pkg / "preview.webp", site / "previews" / f"{sid}.webp")
            entries.append({
                "id": sid, "name": pack["label"], "author": block["author"], "tagline": pack["tagline"],
                "version": block["version"], "licence": block["licence"], "homepage": block["source"],
                "renderer": pack["renderer"], "needs_gpu": bool(pack["needs"]["gpu"]),
                "scene_api": block["scene_api"], "commit": origin.get("commit", args.commit or ""),
                "archive_url": base + archive, "sha256": hashlib.sha256(data).hexdigest(),
                "preview_url": f"{base}previews/{sid}.mp4", "poster_url": f"{base}previews/{sid}.webp",
            })
    index = {"version": INDEX_VERSION, "styles": entries}
    (site / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (site / "index.html").write_text(render_page(entries, args.repo_url or ""), encoding="utf-8")
    print(f"index.json and index.html list {len(entries)} style(s)")
    return 0


def render(args) -> int:
    """Render a scene style's example in the backend image, with silent audio."""
    pkg = pathlib.Path(args.package).resolve()
    sid = json.loads((pkg / "style.json").read_text(encoding="utf-8"))["id"]
    pack, reason = ext.check_folder(sid, pkg)
    if pack is None:
        sys.exit(f"{sid}: {reason}")
    if pack["renderer"] != "dom":
        print(f"{sid} is a 3D world style: its example needs generated source, so render it by hand",
              file=sys.stderr)
        return NOT_RENDERABLE
    config = json.loads((pkg / "guide" / "example-config.json").read_text(encoding="utf-8"))
    timeline_file = pkg / "guide" / "example-timeline.json"
    timeline = (json.loads(timeline_file.read_text(encoding="utf-8")) if timeline_file.is_file()
                else {"fps": config.get("fps", 30), "words": []})
    seconds = config["totalFrames"] / config.get("fps", 30)
    out = pathlib.Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    vid = "gallery_example"
    with tempfile.TemporaryDirectory() as tmp:
        job = pathlib.Path(tmp) / vid
        job.mkdir()
        (job / "scene-config.json").write_text(json.dumps(config), encoding="utf-8")
        (job / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        os.chmod(tmp, 0o755)
        props = json.dumps({"sceneConfigPath": f"/public/{vid}/scene-config.json",
                            "timelinePath": f"/public/{vid}/timeline.json",
                            "audioPath": f"/public/{vid}/audio.mp3", "watermark": True})
        script = (f"ffmpeg -v error -y -f lavfi -i anullsrc=r=44100:cl=mono -t {seconds:.2f} -q:a 9 "
                  f"/app/remotion/public/{vid}/audio.mp3 && cd /app/remotion && "
                  f"npx remotion render Composition /out/{out.name} --props '{props}' "
                  f"--browser-executable /usr/bin/chromium")
        cmd = ["docker", "run", "--rm",
               "-e", f"TUBEMATIC_EXTERNAL_STYLE={sid}", "-e", f"TUBEMATIC_RENDER_VIDEO={vid}",
               "-v", f"{pkg}:/app/remotion/src/scenes/external/{sid}:ro",
               "-v", f"{job}:/app/remotion/public/{vid}",
               "-v", f"{out.parent}:/out",
               "--entrypoint", "bash", args.image, "-c", script]
        proc = subprocess.run(cmd)
    if proc.returncode or not out.is_file():
        sys.exit(f"the render failed (exit {proc.returncode})")
    print(out)
    return 0


# Names Claude Code loads as instructions from a folder it reads (CLAUDE.md, CLAUDE.local.md, rules
# and settings under .claude/, .mcp.json), plus AGENTS.md: staged under another name so the review
# reads them as data. A package has no use for a dot-file or these names.
AGENT_FILES = {"claude.md", "claude.local.md", "agents.md"}


def _staged_name(part: str) -> str:
    return part + ".submitted" if part.startswith(".") or part.lower() in AGENT_FILES else part


def stage(args) -> int:
    """Each submission's package as plain files under <out>/<id>/: what the Claude review reads.
    Symlinks are left out (the review uploads the folder as an artifact), and files an agent would
    load as instructions are renamed."""
    only = set(filter(None, (args.only or "").split(","))) or None
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    found = submissions(pathlib.Path(args.styles), only)
    ids = [sid for sid, _ in found]
    failed = False
    for sid in sorted(only - set(ids)) if only else []:
        print(f"{sid}: not in the pull request's styles/ (removed)")
    with tempfile.TemporaryDirectory() as tmp:
        for sid, entry in found:
            if ids.count(sid) > 1:
                failed = True
                print(f"{sid}: submitted both as a folder and as a pointer", file=sys.stderr)
                continue
            try:
                pkg, _ = materialise(sid, entry, pathlib.Path(tmp))
            except (GalleryError, style_install.InstallError) as exc:
                failed = True
                print(f"{sid}: {exc}", file=sys.stderr)
                continue
            plan: dict[str, list[pathlib.Path]] = {}
            for src in pkg.rglob("*"):
                rel = src.relative_to(pkg)
                if src.is_symlink() or not src.is_file() or ".git" in rel.parts:
                    continue
                staged = pathlib.Path(*(_staged_name(part) for part in rel.parts)).as_posix()
                plan.setdefault(staged, []).append(rel)
            # a rename must never let one submitted file hide another from the review: two files on
            # one name, or a file on the name another needs as its folder
            clashes = [f"{' and '.join(sorted(r.as_posix() for r in rels))} would both be staged as {dest}"
                       for dest, rels in sorted(plan.items()) if len(rels) > 1]
            clashes += [f"{plan[folder][0].as_posix()} and {rel.as_posix()} would both be staged under {folder}"
                        for dest, (rel, *_) in sorted(plan.items())
                        for folder in (p.as_posix() for p in pathlib.PurePosixPath(dest).parents)
                        if folder in plan]
            if clashes:
                failed = True
                for clash in clashes:
                    print(f"{sid}: {clash}", file=sys.stderr)
                continue
            for dest, (rel,) in sorted(plan.items()):
                if dest != rel.as_posix():
                    print(f"{sid}: {rel.as_posix()} staged as {dest}")
                target = out / sid / dest
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pkg / rel, target)
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("styles")
    p.add_argument("--only", default="")
    p = sub.add_parser("build")
    p.add_argument("styles")
    p.add_argument("site")
    p.add_argument("--base-url", required=True)
    p.add_argument("--commit", default="", help="the gallery repository's commit, for folder submissions")
    p.add_argument("--repo-url", default="", help="the gallery repository, linked from index.html")
    p = sub.add_parser("render")
    p.add_argument("package")
    p.add_argument("out")
    p.add_argument("--image", required=True)
    p = sub.add_parser("stage")
    p.add_argument("styles")
    p.add_argument("out")
    p.add_argument("--only", default="")
    args = ap.parse_args(argv)
    try:
        return {"scan": scan, "build": build, "render": render, "stage": stage}[args.cmd](args)
    except (GalleryError, style_install.InstallError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
