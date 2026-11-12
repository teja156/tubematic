#!/usr/bin/env python3
"""Make a visual style's preview for the dashboard's style picker (TMDEV-226).

Cuts a short silent loop and a poster out of any finished 9:16 video of the
style, and writes them where the dashboard serves them and the style pack's
`preview` field names them:

    dashboard/public/style-previews/<stem>.mp4    (540x960, 30 fps, H.264, no audio)
    dashboard/public/style-previews/<stem>.webp   (the loop's first frame)

    python3 scripts/make_style_preview.py <source.mp4> <stem> --start 12.5
    python3 scripts/make_style_preview.py clip.mp4 whiteboard --start 1 --docker-image tubematic-renderer-image

The previews ship inside the dashboard image, so each one has a size cap
(the loop 400 KB, the poster 40 KB; tubematic_core/tests/test_style_packs.py
pins both and the folder total). A loop that comes out over is encoded again at
a lower quality until it fits; a poster the same way.

It needs ffmpeg: one on PATH, one named with --ffmpeg, or a Docker image that
has it (--docker-image; every Tubematic backend image does). With an image it
runs `docker run --rm --network none` with the source and the output folder
mounted, as your own user. It renders nothing and calls no paid service.
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "dashboard" / "public" / "style-previews"

WIDTH, HEIGHT, FPS = 540, 960, 30
DEFAULT_DURATION = 6.0
LOOP_MAX_BYTES = 400 * 1024
POSTER_MAX_BYTES = 40 * 1024
LOOP_CRFS = (30, 32, 34, 36, 38)
POSTER_QUALITIES = (72, 64, 56, 48, 40, 32)


def _runner(args):
    """A function that runs ffmpeg in a work folder, written as /out/ in its
    arguments, and the source's path as that ffmpeg sees it."""
    src = pathlib.Path(args.source).resolve()
    if args.docker_image:
        def run(work: pathlib.Path, ff_args: list[str]):
            cmd = ["docker", "run", "--rm", "--network", "none", "-u", f"{os.getuid()}:{os.getgid()}",
                   "-v", f"{src.parent}:/src:ro", "-v", f"{work}:/out", "--entrypoint", "ffmpeg",
                   args.docker_image, *ff_args]
            subprocess.run(cmd, check=True)
        return run, f"/src/{src.name}"
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg is not on PATH: pass --ffmpeg <path> or --docker-image <image with ffmpeg>")

    def run(work: pathlib.Path, ff_args: list[str]):
        ff_args = [a.replace("/out/", f"{work}/") for a in ff_args]
        subprocess.run([ffmpeg, *ff_args], check=True)
    return run, str(src)


def make(args) -> tuple[pathlib.Path, pathlib.Path]:
    out_dir = pathlib.Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run, src = _runner(args)
    scale = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos," \
            f"crop={WIDTH}:{HEIGHT},fps={FPS}"
    with tempfile.TemporaryDirectory(prefix="style-preview-") as tmp:
        work = pathlib.Path(tmp)
        loop = work / "loop.mp4"
        for crf in LOOP_CRFS:
            run(work, ["-v", "error", "-y", "-ss", str(args.start), "-t", str(args.duration), "-i", src,
                       "-an", "-vf", scale, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
                       "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
                       "/out/loop.mp4"])
            if loop.stat().st_size <= LOOP_MAX_BYTES:
                break
        else:
            sys.exit(f"the loop is still {loop.stat().st_size} bytes at crf {LOOP_CRFS[-1]}: "
                     "pick a calmer stretch or a shorter --duration")
        poster = work / "poster.webp"
        for q in POSTER_QUALITIES:
            run(work, ["-v", "error", "-y", "-i", "/out/loop.mp4", "-frames:v", "1",
                       "-c:v", "libwebp", "-quality", str(q), "/out/poster.webp"])
            if poster.stat().st_size <= POSTER_MAX_BYTES:
                break
        else:
            sys.exit(f"the poster is still {poster.stat().st_size} bytes at quality {POSTER_QUALITIES[-1]}")
        clip_out, poster_out = out_dir / f"{args.stem}.mp4", out_dir / f"{args.stem}.webp"
        shutil.copyfile(loop, clip_out)
        shutil.copyfile(poster, poster_out)
    return clip_out, poster_out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="a finished 9:16 video of the style")
    ap.add_argument("stem", help="the style pack's `preview` value (normally the style id)")
    ap.add_argument("--start", type=float, default=0.0, help="second of the source the loop starts at")
    ap.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="loop length in seconds")
    ap.add_argument("--ffmpeg", help="path to an ffmpeg binary")
    ap.add_argument("--docker-image", help="run ffmpeg from this Docker image instead")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="where the two files go")
    args = ap.parse_args(argv)
    if not args.stem.replace("_", "").isalnum() or args.stem != args.stem.lower():
        ap.error("stem must be lowercase letters, digits and underscores")
    if not 1 <= args.duration <= 10:
        ap.error("--duration must be between 1 and 10 seconds")
    clip, poster = make(args)
    print(f"{clip.relative_to(REPO_ROOT) if clip.is_relative_to(REPO_ROOT) else clip}  {clip.stat().st_size} bytes")
    print(f"{poster.relative_to(REPO_ROOT) if poster.is_relative_to(REPO_ROOT) else poster}  {poster.stat().st_size} bytes")


if __name__ == "__main__":
    main()
