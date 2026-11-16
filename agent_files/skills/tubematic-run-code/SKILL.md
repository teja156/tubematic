---
name: tubematic-run-code
description: Run a short Python, JavaScript or TypeScript program in the code sandbox with the run_code tool, to get real numbers, positions, timings or a cropped picture instead of guessing them. Use it when you are authoring a video's scenes and a value has to be computed or a picture measured; no style needs it.
---

# Running code with `run_code`

**Invoke this skill when:** while authoring a video you need a result you would otherwise estimate: positions
or sizes computed from real numbers, values for a chart, a crop or a measurement of a picture you generated,
a check of timings in `timeline.json`, or what a snippet really prints. If the value is easy and certain, do
not run code.

You have no shell and no file writes, and you never will. `run_code` is the one way to run a program, and it
runs in a separate container that has **no network, no keys, no database and none of the other videos**. It
sees only the files you list in `inputs`.

## The call

```
run_code(video_id, language, code, inputs=[...], timeout_s=20)
```

- `language`: `python` (3, with Pillow and numpy), `javascript` or `typescript` (Node 20).
- `code`: the whole program (up to 64 KB). It starts in an empty folder. Read inputs from `./in/<name>`,
  write results to `./out/<name>`, print to stdout.
- `inputs`: up to 8 of this video's files by job-relative name: `timeline.json`, `scene-config.json`,
  `images/<file>`, `images/treated/<file>`, or `runs/<run_id>/<file>` (a file an earlier run wrote). Each
  appears in `./in/` under its base name; two inputs cannot share one.
- Output files: at most 8, each up to 8 MB, names of letters, digits and `. _ -`, ending `png jpg jpeg webp json
  txt csv svg`. They are kept under `runs/<run_id>/` and listed in the result; up to four pictures come back
  in the result for you to look at.

The result has `exit_code`, `stdout`, `stderr`, `timed_out`, `files` and `run_id`. Long output is cut in the
middle (`output_truncated`). A run that is killed (time, memory, output size) has `exit_code: null`.

## Limits you will meet

One run at a time (`sandbox_busy` means wait a minute), 1 to 60 seconds, about 1.5 GB of memory for Python,
no processes left behind, no way to reach the internet (a `requests.get` fails; do not try to download a
font or a picture). Nothing a run writes enters the video by itself: the numbers you read go into your
scene yourself, and a picture a run wrote under `runs/` is not an image of the video.

## When it says `sandbox_unavailable`

The sandbox container is not answering. Carry on without the run: estimate the value, or leave out what you
wanted to check. Never retry in a loop, and never work around it.

## Do not

- Do not paste secrets, keys or other people's data into code. The sandbox holds none of them, so there is
  nothing to read; keep it that way.
- Do not run code to download, scrape or call an API. It cannot, and the attempt wastes a run.
- Do not use a run's output as an authority over the video's script facts: it computes what you asked, not
  whether the claim is true.

## Code Scenes

You do not need to run a Code Scenes snippet yourself: `write_scene_config` runs the code behind every output
pane of a Python, JavaScript or TypeScript insert and tells you what it printed when your pane differs. See
`tubematic-code-scenes`.
