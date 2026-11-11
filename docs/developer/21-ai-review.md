# AI Review

AI review uploads a finished render to Gemini and asks a model to watch it.
`renderer/api/ai_review.py` makes the call, and `render_results.py::finish_render` decides what the
answer does to the video. Any finding sends the video back for a revision, so much of the prompt
exists to stop the reviewer reporting things the pipeline does on every video.

AI review is experimental and off by default. It runs only when `gemini_review_enabled` is on and a
Gemini key is stored. The default is off because the review fails open: with review on and something
wrong (a quota gap, a broken upload), a video still reaches `VIDEO_READY`. An existing install keeps
the value it has stored.

How a render gets uploaded is on [Rendering and Review](11-rendering-and-review.md).

---

## When a review runs

A video is reviewable once its render has been uploaded: it is still `RENDERING`, with
`render_uploaded_at` set. The review runs in the worker on its own thread
(`worker.py::_start_review_thread`), which takes the oldest upload first and reviews one video at a
time (`_review_once`).

- One at a time, because a review is a paid Gemini call that takes minutes and several would compete
  for the same quota.
- A thread, so that a slow review does not hold up a publish or an Auto Pilot approval.
- In the worker, so that the renderer needs no database and no Gemini key and is free as soon as its
  upload lands.
- A worker restart during a review reviews the video again, because the row is still `RENDERING`
  and uploaded.

`finish_render` moves the video on in every case:

| Case | Result |
|---|---|
| `gemini_review_enabled` is off, or no Gemini key is stored | `VIDEO_READY`, with no comment |
| The job's `scene-config.json` is missing | `VIDEO_READY`, with a comment that the review was skipped |
| The review ran | See [Routing](#routing) |
| `finish_render` raised | `REVISION_REQUESTED`, with the comment "Unexpected error in render tail: …" |

A blank settings row falls back to the environment variable of the same name in upper case
(`GEMINI_API_KEY`), so a key supplied through the container's environment counts.

`ai_review.py` does not read the database. It takes its model, sampling rate, key and style flags as
arguments and returns its token usage, which is why `vqa/review_video.py` can call `run_ai_review()`
from a host script.

## The call

`run_ai_review` makes three requests. The key travels in the `x-goog-api-key` header, and `_redact`
removes it from any error string before the string is stored.

1. A resumable upload: `POST /upload/v1beta/files` with `X-Goog-Upload-Protocol: resumable` and
   `X-Goog-Upload-Command: start`. The upload URL comes back in the `x-goog-upload-url` response
   header. The bytes go to that URL with `X-Goog-Upload-Command: "upload, finalize"`. The whole mp4
   is read into memory first.
2. A poll until the file is `ACTIVE`: up to 60 attempts, 5 seconds apart. A `FAILED` state, or no
   `ACTIVE` after 60 attempts, returns an error result.
3. `generateContent` with `temperature: 0.0` and `response_mime_type: "application/json"`.

```jsonc
{
  "file_data":      { "mime_type": "video/mp4", "file_uri": "…" },
  "video_metadata": { "fps": 10 }        // sibling of file_data
}
```

`video_metadata` is a sibling of `file_data` on the part. Google's documentation has shown it nested
inside `file_data`, where Gemini ignores it and samples at its default of 1 fps without an error.

The upload requests time out after 300 seconds and the review request after 120. `GEMINI_BASE` and
`GEMINI_UPLOAD_BASE` override the base URLs. With no model passed, `AI_REVIEW_MODEL`, then
`GEMINI_MODEL`, then `gemini-2.5-flash` apply.

## What it is given

- The rendered video, sampled at the rate under [Sampling rate](#sampling-rate). The prompt states
  the rate.
- The full `scene-config.json`: the job's copy, which the bundle was built from.
- Both forms of the script: the authored `videos.script`, which the captions show, and the spoken
  `videos.tts_text`, the text sent to ElevenLabs.
- The video's intended style as four flags: `canvas` (`dark` or `light`), `figures`, `line_art` and
  `cartoon_3d`.

`tts_text` is stored at voicing and is not derived again. The review asks whether ElevenLabs
honoured the respelling it was sent, and the lexicon is install-wide and can change, so a later
derivation could produce an instruction that was not sent.

The style flags come from `pipeline.py::effective_canvas`, `figures_allowed` and
`line_art_allowed`. They are separate because they vary independently:

- An `auto` video can be dark and full of held, discretely posed figures.
- The illustrated style has figures, but they are generated character artwork, and hand-drawn line
  art is what that style excludes.
- `cartoon_3d` (the chosen style, or `videos.resolved_renderer`) replaces the other three.

A [style pack](10-scene-authoring.md#style-packs) may carry its own `review` text, which
`render_results.py` passes as `style_block`. When it is present it replaces the canvas and figure
blocks, which describe the scene system's styles. System Flow, Bean Explainer and Terminal Doc carry one.

## The prompt's guard clauses

The prompt is `ai_review.py::_REVIEW_PROMPT`, with the style contract (`_register_block`) and the
script reference (`_reference_text_block`) inserted. Under the [routing](#routing) rule one
systematic false positive puts every affected video into a revision round, and a round can cost a
paid re-voice. Each clause below prevents one. Keep them.

| Clause | What it tells the reviewer | Without it |
|---|---|---|
| Captions | Burned-in captions of the narration are correct. Judge their legibility, safe zone and sync only. A config with `"subtitles": {"enabled": false}` has none, which is also correct | Every video is captioned, so every review reports duplicated on-screen text |
| Watermark | The "Made with tubematic.ai" mark is intended: its presence, position, size, and content visible through or beneath it. A video without it is also fine | The mark is on every video, so every review returns a finding |
| Mascot | A small watercolour character over the picture is intended. It does not speak, so a mouth that does not move with the words is correct | Every mascot video is reported for stray artwork or missing lip sync |
| Light canvas | A plain white canvas with flat black line art is the approved look. A white frame is the canvas, and `blank_frames` means black frames. Photographs sit inside drawn panels | A light video is reported as unfinished, blank or badly cropped |
| Dark canvas | The canvas is dark with full-bleed imagery. A scene static for more than about a third of a second is worth reporting | A dark video has no stated look to be judged against |
| Discrete motion | Figures hold a pose and change state in a single frame, roughly 2 to 5 times per 10 seconds | A held pose reads as broken animation on every video with figures |
| Line art | Simple line-art stick figures are the intended style | Flat, unshaded figures are reported as placeholder art |
| Cartoon 3D | Ink outlines, depth-of-field blur, colour grading, film grain, the vignette, flat cut-out characters and a continuously moving camera are the style. Report only a frozen, black or white frame | Each of those reads as a rendering fault |
| System Flow (from its pack) | Dimmed parts, dotted connectors with travelling lights, a glow on the active box, a moving camera and no people or images are the style. It still lists what to report | The dimming and missing imagery read as defects against the dark-canvas contract |
| Bean Explainer (from its pack) | A flat colour field, a thick-outlined bean that snaps between poses and holds still, props that build up until each cut, and no photographs are the style. It still lists what to report | The held poses and missing imagery read as broken animation and an unfinished video |
| Terminal Doc (from its pack) | Sparse monospace text, typing, glyph noise, a ciphertext wall, an empty dark frame, the amber CRT skin and the typed log captions are the style. It still lists what to report, including stage text that repeats the sentence being spoken | On-screen text reads as duplicated narration and the empty frame as an unfinished video |
| Two scripts | Where the written and spoken forms differ, audio matching the spoken form is correct. An IPA transcription between slashes is spoken as the sounds it spells | Every working respelling or IPA term is reported as a mispronunciation |
| Decorative suggestions | A suggestion must critique something in the video. Adding a glow, an icon or a flourish does not count, and an empty list is acceptable | The model pads `suggestions`, and any suggestion costs a revision round |

### Scope of the clauses

- The mascot is reported in two cases: it covers something the viewer needs (on-screen text, or the
  subject being narrated), as an `animation_defect`, or its reaction contradicts the narration, as a
  suggestion.
- The discrete-motion clause goes to every style that may contain figures. The line-art clause goes
  only to a style that draws line art. An illustrated video gets the first and not the second,
  because the second would accept the one thing that style forbids. The errors are unequal: the
  line-art clause sent too widely costs a missed defect, and the discrete-motion clause withheld
  costs a false positive on every video in that style.
- An unknown canvas produces no style contract, because a wrong contract tells the reviewer to
  accept defects.
- The two-script exemption covers only the words that differ. The prompt still asks for a
  mispronunciation when the audio does not match the spoken form, or when the respelling itself
  sounds wrong. Identical forms are stated as identical, so the model does not look for a
  difference. A video with one form, or neither, gets a block that says which is missing.
- One clause asks for a finding: a scene that writes out what the narration says (a headline, a
  title card, a lower third) repeats the captions and is reported as the suggestion
  `redundant_text`. Text with its own information (a number, a label on a diagram, a defined term,
  code, a chart axis) is exempt.

### The mispronunciation bar

`mispronunciation` covers proper nouns and technical terms pronounced objectively wrong: wrong
phonemes, spelled out letter by letter, or stressed into a different word. Non-English,
transliterated and mythological names are in scope. Accent, cadence, prosody, emphasis and regional
variants are at most a suggestion. Every mispronounced word of the video goes in one finding. A
lower bar would report narration style, and each such finding costs a paid re-voice. A test pins the
wording (`test_ai_review.py::test_mispronunciation_bar_is_not_lowered`).

## The response

```jsonc
{
  "overall": "a few sentences, always present",
  "mustFix": [ { "type", "timestamp", "scene", "description", "suggestedFix" } ],
  "suggestions": [ { "area", "timestamp", "scene", "description", "suggestedFix" } ]
}
```

- `mustFix` holds what makes the video unshippable. The defined types are `text_offscreen`,
  `sync_drift`, `blank_frames`, `audio_drop`, `safe_zone_violation`, `animation_defect` and
  `mispronunciation`, and the model may add its own `snake_case` types. The list has no cap.
- `suggestions` holds everything else worth changing, each with an `area` of `video` or `audio`.
  The prompt caps the list at 5.

`run_ai_review` returns `overall`, `must_fix`, `suggestions`, `feedback` (the review as markdown)
and `usage`. Findings are normalised without raising. A bare must-fix string becomes its `type`, and
a bare suggestion string becomes its `description`, because free-form critique is not an area label.
A missing `type` reads as `unknown` and a missing `area` as `video`.

## Routing

`finish_render` adds one to `videos.ai_review_count` before each review. The count is not reset.

| Outcome | Status | Comment |
|---|---|---|
| The review returned an error | `VIDEO_READY` | "AI review failed", then the error |
| The count is above `ai_review_max_loops` | `VIDEO_READY` | "Max AI reviews (N) reached", then the review |
| `mustFix` or `suggestions` is non-empty | `REVISION_REQUESTED` | "AI review N of M found X must-fix, Y suggestions", then the review |
| Both are empty | `VIDEO_READY` | "AI review N of M", marked clean, then the review |

Any finding sends the video to `REVISION_REQUESTED`, including a review with no must-fix items and
one suggestion. An agent may not act on suggestions at `VIDEO_READY`, which is a human checkpoint,
and passing suggestions through would ship videos the reviewer wanted changed.

`ai_review_max_loops` (default 1, at most 2) caps the rounds the reviewer can force. The test is
`ai_review_count > ai_review_max_loops`, so with the default the first review can send the video
back and the second is accepted whatever it finds. It is separate from `max_render_retries`, which
counts failed renders.

The review past the cap still runs, and only its routing changes. Do not add an early return that
skips it, or the video ships with the feedback of the round before.

Every status write is guarded on `RENDERING`, so a human who moved the video first wins.

## Fail-open

A review that errors moves the video to `VIDEO_READY`, so a broken reviewer does not stop the
pipeline. Every error path in `run_ai_review` returns the same shape (`_error_result`): empty
findings, an `error`, and a `feedback` of `AI review did not run: <reason>`.

A failing reviewer therefore looks like a passing one. To make it visible, `finish_render` writes
`videos.gemini_feedback` and posts a comment on every outcome. Search `gemini_feedback` for
`AI review did not run:`, or the comments for "AI review failed", if you suspect the reviewer is not
running.

## What is stored

| Where | What |
|---|---|
| `videos.gemini_feedback` | The formatted review, whole, replaced each round. The agent reads it to fix the video, so it has no cap |
| The video's comments | The same text after the outcome line, cut to 2,000 characters with a note naming `gemini_feedback` as the full copy |
| `videos.ai_review_count` | How many reviews the video has had |
| `usage_events` | One row per review Gemini answered with `200` |

`ai_review.py::_format_feedback` orders the text overall, must-fix, suggestions, so a truncated
comment loses suggestions first.

## Cost

Every review Gemini answers is recorded against the video with the token counts from
`usageMetadata` (`tubematic_core/usage.py::record_usage`, service `gemini`, operation `ai_review`).
A video reviewed twice shows two calls. A reply that failed to parse is recorded too, because it was
billed. The Files API upload is free and is not recorded. See
[Settings](../user-guide/05-settings.md#costs) for how tokens become dollars.

### Sampling rate

Video tokens scale with the frames sampled, so `ai_review_fps` (default 10, range 1 to 24) sets the
cost.

| | `gemini-2.5-flash` | `gemini-3.5-flash`, `gemini-3.6-flash` |
|---|---|---|
| Tokens per frame | 263 | 71 |

Audio costs 32 tokens per second on each model whatever the rate. A model with no figure here is
assumed to cost 263 tokens per frame.

`ai_review.py::_effective_fps` lowers the requested rate until video and audio tokens fit a budget of
800,000 (`_VIDEO_TOKEN_BUDGET`), which leaves about 200,000 of the 1M context window for the prompt,
the scene-config and the answer. It takes the duration from the scene-config (`totalFrames / fps`)
and does not go below 1. Without the clamp a long video would overrun the window, the request would
fail with `400`, and the video would pass unreviewed. A rate of 0 sends no `video_metadata`.

A 250-second video on `gemini-2.5-flash` is about 1.32M tokens at 20 fps, over the window, and about
665,000 at 10 fps, which is why 10 is the default. Per second of reviewed video the 3.x models cost
about 1.4 times the 2.5 model, well under the 5 times their list price suggests, because they use
fewer tokens per frame.

The default of 10 fps has not been shown to find more defects than 1 fps. The reviewer's weak point
is precision: it sometimes reports a defect that is not in the video, and a false finding costs a
revision round.

## Related pages

- [Rendering and Review](11-rendering-and-review.md): how a render is uploaded, and the text-layout
  audit that checks a video before it is queued.
- [The Worker](12-the-worker.md): the review thread beside the worker's loop.
- [The Pipeline](02-pipeline.md): `VIDEO_READY`, `REVISION_REQUESTED` and the revision loop.
- [Settings internals](04-settings.md): the `ai_review_*` keys and their bounds.
