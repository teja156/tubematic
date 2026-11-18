#!/usr/bin/env python3
"""Make a style package's preview.mp4 and preview.webp with ffmpeg.

    python3 make_preview.py <package folder> --from <sample.mp4> [--start 2] [--duration 6]
    python3 make_preview.py <package folder> --placeholder "#101418"

--from cuts a loop out of a rendered sample video of the style (540x960,
30 fps, H.264, no audio, at most 400,000 bytes) and takes its first frame as
the poster (WebP, at most 40,000 bytes): the sizes Tubematic's loader allows.
--placeholder makes a 2-second loop of one colour, for a package that has no
rendered sample yet; replace it once one exists.

Needs ffmpeg on PATH. Standard library only; it installs nothing.
"""
import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

W, H, FPS = 540, 960, 30
LOOP_MAX, POSTER_MAX = 400_000, 40_000
CRFS = (30, 32, 34, 36, 38, 40)
QUALITIES = (72, 64, 56, 48, 40, 32, 24)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from", dest="source")
    src.add_argument("--placeholder", metavar="HEX")
    ap.add_argument("--start", type=float, default=2.0)
    ap.add_argument("--duration", type=float, default=6.0)
    args = ap.parse_args(argv)
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on PATH; install it yourself (this script installs nothing)")
    pkg = pathlib.Path(args.package)
    with tempfile.TemporaryDirectory() as tmp:
        loop, poster = pathlib.Path(tmp) / "loop.mp4", pathlib.Path(tmp) / "poster.webp"
        if args.placeholder:
            color = args.placeholder.lstrip("#")
            inputs = ["-f", "lavfi", "-i", f"color=c=0x{color}:s={W}x{H}:r={FPS}:d=2"]
            vf = "null"
        else:
            inputs = ["-ss", str(args.start), "-t", str(args.duration), "-i", args.source]
            vf = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS}"
        for crf in CRFS:
            ffmpeg(*inputs, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(loop))
            if loop.stat().st_size <= LOOP_MAX:
                break
        else:
            sys.exit(f"the loop is still {loop.stat().st_size} bytes: pick a calmer stretch or a shorter --duration")
        for q in QUALITIES:
            ffmpeg("-i", str(loop), "-frames:v", "1", "-c:v", "libwebp", "-quality", str(q), str(poster))
            if poster.stat().st_size <= POSTER_MAX:
                break
        else:
            sys.exit(f"the poster is still {poster.stat().st_size} bytes")
        shutil.copyfile(loop, pkg / "preview.mp4")
        shutil.copyfile(poster, pkg / "preview.webp")
    print(f"preview.mp4 {(pkg / 'preview.mp4').stat().st_size} bytes, preview.webp {(pkg / 'preview.webp').stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
