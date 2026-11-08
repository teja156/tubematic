#!/usr/bin/env python3
"""Final-frame QA of a rendered Short: every frame checked for black, white, frozen spans and pop frames, plus the
soundtrack's loudness, and a contact sheet per beat. The shape of mromidev/claude-animated-shorts' short_qa.py,
rewritten for this pipeline (PIL only; frames and audio come out through Remotion's ffmpeg).

    python frameqa.py <video.mp4> <outdir> [--beats beats.json] [--ffmpeg "npx remotion ffmpeg"] [--lufs-tool <dsp dir>]

Exit 0 when nothing fails, 2 otherwise. Writes <outdir>/report.json and <outdir>/report.md.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys

from PIL import Image, ImageChops, ImageStat

FROZEN_MIN = 12          # frames: a span this long with no change is a freeze (the reference never holds still)
FROZEN_DIFF = 0.25       # mean abs luma diff (0-255) under which two frames count as identical
POP_DIFF = 40.0          # a single frame that differs this much from BOTH neighbours, which agree, is a pop
BLACK = 6.0              # mean luma
WHITE = 249.0


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"command failed: {cmd}\n{r.stderr[-800:]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--beats", default=None)
    ap.add_argument("--ffmpeg", default="npx remotion ffmpeg")
    ap.add_argument("--cwd", default=None, help="where to run ffmpeg (the Remotion project)")
    ap.add_argument("--lufs-tool", default=None, help="directory holding dsp.py (the audio engine) for a loudness read")
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    out = os.path.abspath(a.outdir)
    frames = os.path.join(out, "frames")
    os.makedirs(frames, exist_ok=True)
    cwd = a.cwd or os.getcwd()
    ff = f"cd {shlex.quote(cwd)} && {a.ffmpeg}"
    run(f"{ff} -v error -y -i {shlex.quote(a.video)} -vf scale=180:320 {shlex.quote(frames)}/f%05d.png")
    names = sorted(n for n in os.listdir(frames) if n.endswith(".png"))
    lum = []
    diffs = []
    prev = None
    for n in names:
        im = Image.open(os.path.join(frames, n)).convert("L")
        lum.append(ImageStat.Stat(im).mean[0])
        if prev is not None:
            diffs.append(ImageStat.Stat(ImageChops.difference(im, prev)).mean[0])
        prev = im
    N = len(names)
    black = [i for i, v in enumerate(lum) if v < BLACK]
    white = [i for i, v in enumerate(lum) if v > WHITE]
    frozen = []
    run_start = None
    for i, d in enumerate(diffs):
        if d < FROZEN_DIFF:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start + 1 >= FROZEN_MIN:
                frozen.append((run_start, i))
            run_start = None
    if run_start is not None and len(diffs) - run_start + 1 >= FROZEN_MIN:
        frozen.append((run_start, len(diffs)))
    pops = []
    for i in range(1, N - 1):
        d0, d1 = diffs[i - 1], diffs[i]
        both = ImageStat.Stat(ImageChops.difference(Image.open(os.path.join(frames, names[i - 1])).convert("L"),
                                                    Image.open(os.path.join(frames, names[i + 1])).convert("L"))).mean[0]
        if d0 > POP_DIFF and d1 > POP_DIFF and both < POP_DIFF / 3:
            pops.append(i)
    # a hard cut (big diff, neighbours differ) is reported, not failed: the author decides if it was meant
    cuts = [i + 1 for i, d in enumerate(diffs) if d > POP_DIFF and (i + 1) not in pops]

    loud = None
    if a.lufs_tool:
        wav = os.path.join(out, "audio.wav")
        run(f"{ff} -v error -y -i {shlex.quote(a.video)} -ar 48000 -ac 2 {shlex.quote(wav)}")
        code = ("import sys; sys.path.insert(0, %r); from dsp import read_wav, integrated, true_peak, lra; import json\n"
                "x, sr = read_wav(%r); print(json.dumps(dict(I=float(integrated(x)), TP=float(true_peak(x)), LRA=float(lra(x)), s=x.shape[1]/sr)))") % (a.lufs_tool, wav)
        r = subprocess.run([a.python, "-c", code], capture_output=True, text=True)
        if r.returncode == 0:
            loud = json.loads(r.stdout.strip().splitlines()[-1])
        else:
            loud = {"error": r.stderr[-400:]}

    # contact sheets: one per beat (or one per 2 s)
    sheets = []
    if a.beats:
        beats = json.load(open(a.beats))
        spans = [(b["start"], b["end"]) for b in beats]
    else:
        spans = [(s, min(N - 1, s + 59)) for s in range(0, N, 60)]
    for k, (s, e) in enumerate(spans):
        idx = list(range(s, min(e, N - 1) + 1, max(1, (e - s) // 11 or 1)))[:12]
        if not idx:
            continue
        tiles = [Image.open(os.path.join(frames, names[i])).convert("RGB") for i in idx]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * len(tiles), h), (20, 20, 20))
        for j, t in enumerate(tiles):
            sheet.paste(t, (j * w, 0))
        p = os.path.join(out, f"sheet{k:02d}.jpg")
        sheet.save(p, quality=85)
        sheets.append(p)

    fails = []
    if black: fails.append(f"{len(black)} black frames (first {black[:5]})")
    if white: fails.append(f"{len(white)} white frames (first {white[:5]})")
    if frozen: fails.append(f"{len(frozen)} frozen spans >= {FROZEN_MIN} f: {frozen[:5]}")
    if pops: fails.append(f"{len(pops)} pop frames: {pops[:8]}")
    if loud and "I" in loud:
        if not (-15.0 <= loud["I"] <= -13.0): fails.append(f"integrated loudness {loud['I']:.1f} LUFS, want -14 +-1")
        if loud["TP"] > -1.0: fails.append(f"true peak {loud['TP']:.2f} dBTP, want <= -1")
    report = dict(video=a.video, frames=N, black=black, white=white, frozen=frozen, pops=pops, cuts=cuts, loudness=loud,
                  mean_luma=sum(lum) / max(1, N), mean_diff=sum(diffs) / max(1, len(diffs)), sheets=sheets, fails=fails)
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
    md = [f"# Frame QA: {os.path.basename(a.video)}", "", f"- {N} frames; mean luma {report['mean_luma']:.1f}; mean frame-to-frame change {report['mean_diff']:.2f}",
          f"- black {len(black)}, white {len(white)}, frozen spans {len(frozen)}, pops {len(pops)}, hard cuts {len(cuts)} {cuts[:12]}",
          f"- loudness: {json.dumps(loud) if loud else 'not measured'}", "", ("FAIL: " + "; ".join(fails)) if fails else "PASS", "", "sheets: " + ", ".join(sheets)]
    open(os.path.join(out, "report.md"), "w").write("\n".join(md))
    print("\n".join(md))
    sys.exit(2 if fails else 0)


if __name__ == "__main__":
    main()
