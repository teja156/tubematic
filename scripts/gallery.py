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

    python3 scripts/gallery.py build <gallery>/styles <site dir> --base-url https://…/
        Write the site: archives/<id>-<version>.zip (a deterministic zip of the
        package), previews/<id>.mp4 and .webp, and index.json, which Tubematic's
        Gallery tab reads and every gallery install checks against.

    python3 scripts/gallery.py render <package> <out.mp4> --image <tubematic backend image>
        Render a scene style's example config (silent) in the backend image, for
        the review. A 3D world style's example needs generated source, so it is
        rendered by hand.
"""
import argparse
import hashlib
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
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
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
        if entry.is_dir() or entry.suffix == ".json":
            out.append((sid, entry))
    return out


def materialise(sid: str, entry: pathlib.Path, work: pathlib.Path) -> tuple[pathlib.Path, dict]:
    """The package folder of a submission, and where it came from. A pointer is
    fetched at its pinned commit with the installer's own git fetch."""
    if entry.is_dir():
        return entry, {"kind": "folder"}
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
    print(f"index.json lists {len(entries)} style(s)")
    return 0


def render(args) -> int:
    """Render a scene style's example in the backend image, with silent audio."""
    pkg = pathlib.Path(args.package).resolve()
    sid = json.loads((pkg / "style.json").read_text(encoding="utf-8"))["id"]
    pack, reason = ext.check_folder(sid, pkg)
    if pack is None:
        sys.exit(f"{sid}: {reason}")
    if pack["renderer"] != "dom":
        sys.exit(f"{sid} is a 3D world style: its example needs generated source, so render it by hand")
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
                  f"--browser-executable-path /usr/bin/chromium")
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
    p = sub.add_parser("render")
    p.add_argument("package")
    p.add_argument("out")
    p.add_argument("--image", required=True)
    args = ap.parse_args(argv)
    try:
        return {"scan": scan, "build": build, "render": render}[args.cmd](args)
    except (GalleryError, style_install.InstallError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
