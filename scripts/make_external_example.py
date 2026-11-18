#!/usr/bin/env python3
"""Build an external style package from a built-in style (TMDEV-252).

    python3 scripts/make_external_example.py night_signal <out>
    python3 scripts/make_external_example.py low_poly_skit <out> [--gpu]

Writes `<out>/ext_<style>[_gpu]/`, a package `tubematic_core.external_styles`
accepts: the built-in style's drawing code with its imports from the rest of
the renderer rewritten to `@tubematic/scene-api`, its pack turned into an
external pack, its skill and reference as the guide, its previews, and the
manifest. Night Signal is a scene style (components/); Low-Poly Skit a world
style (runner/), and `--gpu` makes the variant whose pack needs a GPU.

These packages prove the platform: each renders through the external path
beside its built-in twin. They are not shipped. Copy one into
~/.tubematic-data/styles/ on a test install to use it.
"""
import argparse
import json
import pathlib
import re
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tubematic_core import external_styles as ext  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

SRC = REPO / "renderer" / "remotion" / "src"
SKILLS = REPO / "agent_files" / "skills"
PREVIEWS = REPO / "dashboard" / "public" / "style-previews"
SKIP = re.compile(r"(\.test\.tsx?|Sheet\.tsx|PartsSheet\.tsx)$")
# Imports a package may not reach by a relative path: the renderer outside the
# style, which the package reaches through the scene API alias instead.
OUTSIDE = re.compile(r'(from |import\()"(\.\./)+(camera|kit/set|video)"')


def _schema_from_example(props: dict) -> dict:
    """A schema the example's props match: every top-level key required, each
    with the JSON type it holds. The style's full rules stay in its guide."""
    kinds = {dict: "object", list: "array", str: "string", bool: "boolean", int: "number", float: "number"}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
            "required": sorted(props),
            "properties": {k: {"type": kinds.get(type(v), "object")} for k, v in props.items()}}


def _pack(style: str, sid: str, props_key: str, gpu: bool) -> dict:
    p = json.loads((tvs.PACKS_DIR / f"{style}.json").read_text(encoding="utf-8"))
    p.update(id=sid, label=f"{p['label']} (external)", order=9000 + p["order"], preview=sid,
             inserts={"host": False}, mascot=False, authoring_skill=ext.AUTHORING_SKILL)
    p["messages"] = dict(p.get("messages", {}))
    p["messages"].setdefault("inserts", "This external style takes no insert scenes.")
    p["messages"].setdefault("mascot", "External styles take no mascot. Choose another visual style, or no mascot.")
    if gpu:
        p["needs"] = dict(p["needs"], gpu=True)
        p["messages"].update(
            gpu=f"{p['label']} renders on a GPU only, and no renderer's GPU is working. Set one up "
                "(python3 onboard.py --step gpu), or choose another style.",
            gpu_unknown=f"{p['label']} renders on a GPU only, and the GPU has not been tested yet.")
    p["external"] = {"version": "1.0.0", "author": "Tubematic", "source": f"built-in style {style}",
                     "licence": "the Tubematic licence", "scene_api": ext.SCENE_API, "props_key": props_key}
    return p


def _copy_code(src_dir: pathlib.Path, dest: pathlib.Path, files: list[pathlib.Path]) -> None:
    for f in files:
        rel = f.relative_to(src_dir)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(OUTSIDE.sub(lambda m: m.group(1) + '"@tubematic/scene-api"', f.read_text(encoding="utf-8")),
                       encoding="utf-8")


def night_signal(out: pathlib.Path) -> pathlib.Path:
    sid = "ext_night_signal"
    d = out / sid
    installed = SRC / "scenes" / "installed"
    code = [installed / "NightSignal.tsx"] + [f for f in sorted((installed / "nightSignal").iterdir())
                                               if f.suffix in (".ts", ".tsx") and not SKIP.search(f.name)]
    _copy_code(installed, d / "components", code)
    ref = SKILLS / "tubematic-night-signal" / "reference"
    config = json.loads((ref / "example-config.json").read_text(encoding="utf-8"))
    for scene in config["scenes"]:
        if scene.get("source") == "installed" and scene.get("src") == "NightSignal":
            scene.update(source="external", src=f"{sid}/components/NightSignal")
            props = scene["props"]["nightSignal"]
    _finish(d, _pack("night_signal", sid, "nightSignal", gpu=False), config, _schema_from_example(props),
            [SKILLS / "tubematic-night-signal" / "SKILL.md", ref / "contract.md"], "night_signal",
            timeline=ref / "example-timeline.json")
    return d


def low_poly_skit(out: pathlib.Path, gpu: bool) -> pathlib.Path:
    sid = "ext_low_poly_skit_gpu" if gpu else "ext_low_poly_skit"
    d = out / sid
    lowpoly = SRC / "cartoon3d" / "lowpoly"
    code = [f for f in sorted(lowpoly.iterdir()) if f.suffix in (".ts", ".tsx") and not SKIP.search(f.name)]
    _copy_code(lowpoly, d / "runner", code)
    config = {"totalFrames": 0, "fps": 30, "canvas": "dark", "scenes": [{
        "type": "generated", "src": "<video_id>/CartoonShort", "startFrame": 0, "durationInFrames": 0,
        "props": {"cartoon3d": {"beats": [{"start": 0, "end": 0, "shot": "what the first shot shows"}]}}}],
        "sfx": []}
    guide = [SKILLS / "tubematic-lowpoly-skit" / "SKILL.md", SKILLS / "tubematic-lowpoly-skit" / "reference" / "kit.md"]
    _finish(d, _pack("low_poly_skit", sid, "lowPolySkit", gpu=gpu), config, {"type": "object"}, guide, "low_poly_skit",
            note=(f"In this package the kit is the runner: import it from a file at the top of your video's "
                  f"directory as \"../../external/{sid}/runner/<file>\" (LowPolyShort, def, figure, poses, ...), "
                  "and the camera helpers and types from \"@tubematic/scene-api\". Wherever the text below says "
                  "\"../../../cartoon3d/lowpoly/<file>\" or \"../../../cartoon3d/camera\", use those instead."))
    return d


def _finish(d: pathlib.Path, pack: dict, config: dict, schema: dict, guide_files: list, preview: str,
            timeline: pathlib.Path | None = None, note: str = "") -> None:
    (d / "guide").mkdir(parents=True, exist_ok=True)
    (d / "style.json").write_text(json.dumps(pack, indent=1) + "\n", encoding="utf-8")
    (d / "schema.json").write_text(json.dumps(schema, indent=1) + "\n", encoding="utf-8")
    (d / "guide" / "example-config.json").write_text(json.dumps(config, indent=1) + "\n", encoding="utf-8")
    if timeline is not None:
        shutil.copy(timeline, d / "guide" / "example-timeline.json")
    parts = [note] if note else []
    parts += [p.read_text(encoding="utf-8") for p in guide_files]
    (d / "guide" / "guide.md").write_text("\n\n---\n\n".join(parts), encoding="utf-8")
    shutil.copy(PREVIEWS / f"{preview}.mp4", d / "preview.mp4")
    shutil.copy(PREVIEWS / f"{preview}.webp", d / "preview.webp")
    ext.write_manifest(d)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("style", choices=("night_signal", "low_poly_skit"))
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--gpu", action="store_true", help="Low-Poly Skit only: the variant whose pack needs a GPU")
    args = ap.parse_args(argv)
    if args.gpu and args.style != "low_poly_skit":
        ap.error("--gpu applies to low_poly_skit only")
    d = night_signal(args.out) if args.style == "night_signal" else low_poly_skit(args.out, args.gpu)
    found = ext.load(args.out)[d.name]
    if not found.ok:
        print(f"{d}: the package does not load: {found.reason}", file=sys.stderr)
        return 1
    print(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
