---
name: tubematic-operator
description: Operate the Tubematic video pipeline — advance videos through each stage using MCP tools, halt at human checkpoints
---

# Tubematic Pipeline Operator Skill

**Invoke this skill when:** starting any Tubematic pipeline session — topic research, scripting, voicing, rendering, review, or publishing.

All operations use the `tubematic` MCP server. Tool signatures and return shapes are in the MCP docstrings — read them if you need parameter details.

---

## Pipeline Status Overview

| Status | Actionable | Notes |
|---|---|---|
| `TOPIC_PROPOSED` | **Human** | approve → TOPIC_APPROVED, reject → TOPIC_REJECTED, or request revision → REVISION_REQUESTED |
| `TOPIC_APPROVED` | AI | write script → SCRIPT_READY (stays here with a comment if scripting fails) |
| `SCRIPT_READY` | **Human** | approve script → VOICING, or request revision → REVISION_REQUESTED |
| `VOICING` | AI | generate_voice → VOICE_READY |
| `VOICE_READY` | AI | write scene config, validate_job, submit_render → RENDER_QUEUED |
| `RENDER_QUEUED` | **AUTO** | render worker claims the job and starts rendering; advances to RENDERING automatically |
| `RENDERING` | **AUTO** | render worker renders + AI review; advances to VIDEO_READY, REVISION_REQUESTED, or FAILED automatically |
| `REVISION_REQUESTED` | AI | read comment, infer stage, fix → matching checkpoint (or FAILED if unfixable) |
| `VIDEO_READY` | **Human** | approve → VIDEO_APPROVED, or request revision → REVISION_REQUESTED |
| `TOPIC_REJECTED` | — | terminal — human flat-rejected the topic, no further action |
| `VIDEO_APPROVED` | **Human** | publish or schedule from the dashboard, or leave it — never agent-actionable |
| `SCHEDULED` | **AUTO** | a post is waiting at postforme for its scheduled time; the render worker moves it to PUBLISHING when it falls due. A human may cancel it back to VIDEO_APPROVED |
| `FAILED` | — | terminal — unrecoverable render/pipeline failure, no further action |

---

## Setup Check — Run Before Anything Else

Before touching the pipeline, verify the following. If **any item fails**, stop immediately, list every failing item clearly, and ask the user to fix them before continuing. Do not proceed until all are confirmed.

| Check | How to verify |
|---|---|
| MCP server connected | Attempt to call any `tubematic:` tool. If it fails with a connection or tool-not-found error, the MCP server is not running — tell the user to re-register it with `python onboard.py --install-agent <agent>` and restart their agent session. |
| API container healthy | `curl -s http://localhost:4000/health` — must return `{"status":"ok"}`. If not, tell the user: `docker compose up -d tubematic-api` |
| MCP container healthy | `curl -s http://localhost:4100/health` — must return `{"status":"ok"}`. Flask and the MCP server are separate containers, so a healthy API says nothing about this one. If not: `docker compose up -d tubematic-mcp` |
| Render worker container running | `docker compose ps tubematic-renderer` — state must be `running`. This is the separate process that actually renders videos; if it's down, videos will pile up in `RENDER_QUEUED` forever. If not: `docker compose up -d tubematic-renderer` |
| Remotion render ready | `curl -s http://localhost:4000/render/health` — must return `{"status":"ok"}` (a Chromium smoke test served by the API container, which shares the render worker's image). If not, rebuild: `docker compose build tubematic-api && docker compose up -d tubematic-api tubematic-mcp tubematic-renderer` |
| Dashboard container running | `docker compose ps tubematic-dashboard` — state must be `running`. If not: `docker compose up -d tubematic-dashboard` |
| ElevenLabs API key set | `GET /settings` → `elevenlabs_api_key` must be non-empty. It comes back masked, never as the real key — a mask means it is set. If empty, tell the user to add it on the Settings dashboard (voicing will fail without it). |
| OpenAI API key set | `GET /settings` → `openai_api_key` must be non-empty (masked, like the others). If empty, tell the user to add it on the Settings dashboard — every scene image comes from OpenAI, so `generate_image` fails without it. |
| Gemini API key (optional) | `gemini_api_key` is optional. If empty, the mining strategy is off and AI review inside the render worker is skipped, so the video advances directly to `VIDEO_READY`. This is expected. |

If all checks pass, continue. If one or more fail, output a clear list like:

```
⚠ Setup incomplete — fix the following before I can continue:

  ✘ Render worker container is not running
      → docker compose up -d tubematic-renderer

  ✘ No ElevenLabs API key configured
      → Add it on the Settings dashboard (or re-run onboard.py)
```

Do not proceed until the user confirms the issues are resolved.

---

## How to Start Every Run

**A scheduled run scoped to one video** — its prompt names one video and the status at which to
stop — skips steps 1, 3 and 4 below. The poller has already checked the pause, and it sends the
user preferences in the prompt. Call `get_video` for that video only, do its one stage per the
**Per-Status Workflow**, and end the session when the video reaches the status the prompt names,
or a human checkpoint. Never list, read or act on any other video: other sessions are working on
them at the same time. That scope is about other videos, not about settings: when a skill needs an
install setting from `get_pipeline_status` (the pronunciation lexicon, the voice roster), call it.
Interactive runs follow the steps below.

1. Call `get_pipeline_status` — check `paused`, `workable_count`, and `video_counts` (a per-status breakdown showing which workable statuses are non-empty). Read `user_preferences` too and apply the parts that fit the stage you are working on — including inside any skill you invoke from here (a scheduled run also carries them as the USER PREFERENCES block in its prompt)
2. If paused: stop immediately, tell the user
3. If `workable_count` > 0: `get_pipeline_status` only returns a count, not the videos themselves — call `list_videos(status=<status>)` for each workable status with a non-zero count (`TOPIC_APPROVED`, `VOICING`, `VOICE_READY`, `REVISION_REQUESTED`) to get the actual video IDs to act on. (`RENDER_QUEUED`, `RENDERING`, `SCHEDULED` and `PUBLISHING` are worker-owned, and `VIDEO_APPROVED` is human-owned — none of them are agent-workable, and they never appear in this list.)
4. For each workable video: call `get_video` before acting — verify current status and read any human comments

---

## Pipeline State Machine

```
TOPIC_PROPOSED  →  TOPIC_APPROVED  →  SCRIPT_READY
                                            ↓  [human approves]
                                         VOICING
                                            ↓
                                       VOICE_READY
                                            ↓
                                      RENDER_QUEUED  (AUTO)
                                            ↓
                                        RENDERING  (AUTO)
                                            ↓
                                        VIDEO_READY
                                            ↓  [human approves]
                                       VIDEO_APPROVED
                                            ↓  [human publishes, or schedules, from the dashboard]
                                       (SCHEDULED)  (AUTO — waits for its time)
                                            ↓
                                        PUBLISHING  (AUTO)
                                            ↓
                                         PUBLISHED

Side exits:
  TOPIC_PROPOSED      → TOPIC_REJECTED       (human flat-rejects; terminal)
  any checkpoint       → REVISION_REQUESTED   (human requests a revision, mandatory comment)
  RENDERING           → REVISION_REQUESTED   (render worker: render crash or AI-review findings)
  RENDERING           → FAILED               (render worker: render-crash retry cap exceeded)
  SCHEDULED           → VIDEO_APPROVED       (human cancels the scheduled post)
  PUBLISHING          → PUBLISHED | FAILED   (render worker: polls the publish results; PUBLISHED if any target succeeded)
  REVISION_REQUESTED  → FAILED               (agent judges the failure unfixable)
  REVISION_REQUESTED  → TOPIC_PROPOSED | SCRIPT_READY | VOICE_READY   (after agent fixes, back to the rejected checkpoint)
```

---

## Human Checkpoints — NEVER Move a Video Out Of One Without Approval

A checkpoint is a **status** that only a human moves a video out of. That move *is* the approval:
once a human has advanced a video past a checkpoint, the work the next status calls for is
authorized. Do not stop and ask for it again.

On an install with **Auto Pilot** switched on, the approval at a checkpoint can be made by
Tubematic itself, for the projects the operator selected. That changes nothing for you. You still
never move a video out of a checkpoint yourself, and a video you find past a checkpoint is
authorized exactly as if a human had moved it — its comment thread says which it was.

- **`SCRIPT_READY`** — do NOT move a `SCRIPT_READY` video into `VOICING` yourself. ElevenLabs
  charges per character, non-refundable, so the human's move to `VOICING` is what authorizes that
  spend — and once they have made it, `VOICING` is ordinary agent work (see its row below).
  If a human explicitly asks you to approve a `SCRIPT_READY` video, first pick the voice: call
  `get_pipeline_status` and read `elevenlabs_voices` (the named roster, each voice with its own
  ElevenLabs `model_id`) and `elevenlabs_voice_id` (the default), and `get_video` for the voice the
  video already has. If the roster has 2 or more entries, list the names with their models (marking
  the video's current voice) and ask which to use; with 0 or 1 entries there's no real choice, so
  skip the question. If a voice was chosen, call `update_video(video_id, voice_id=<chosen_voice_id>)`
  before advancing status. The script's pronunciation and pause markup was written for its voice's
  model, so a voice on a model that cannot speak it is refused with the reason — tell the human and
  offer to keep the current voice or request a revision (handled under **A revision that asks for a
  different voice** below); never rewrite the script at `SCRIPT_READY` yourself. In an unattended cron run there is no human to ask this of — leave `voice_id` alone:
  the video already carries the voice its script was written for (its domain's default voice, or
  the install default, recorded when the script was written).
- **`VIDEO_READY`** — do NOT publish. Wait for explicit human approval.
- **A different agent for the next step.** Only when a human explicitly asks for it: at any of the
  three checkpoints, call `update_video(video_id, agent_id=<id>)` with a live agent's id from
  `get_pipeline_status`'s `agents` — **before** the status change that hands the video on (approving
  or requesting a revision). It resets `agent_model` to that agent's default unless you pass one in
  the same call. It is refused once the video has left the checkpoint.

At every checkpoint: call `add_comment` explaining what was done and what decision is needed.

**Never advance Human-actionable statuses** (`TOPIC_PROPOSED`, `SCRIPT_READY`, `VIDEO_READY`) without an explicit user request — even though the MCP allows it.

---

## Per-Status Workflow

| Status | What to do |
|---|---|
| `TOPIC_APPROVED` | Invoke **tubematic-script-writing-skill** to write the script. It is always installed and owns the whole scripting contract, including the case where the video has no script profile selected. It returns a segments list (`[{id, voice, visual}, ...]`), a publish title and description, and, in `pronunciation_mode == "respell"` (the default) or `"ipa"`, a possibly-empty list of new lexicon entries for recurring terms (one-off terms are already inline as `<respell as="...">word</respell>` or `<ipa ph="...">word</ipa>` tags in `voice`; in `pronunciation_mode == "phoneme"`, pronunciation fixes are inline `<phoneme>` tags instead and no lexicon-entry list is produced). On success: (1) call `update_video(video_id, script_segments=[...], publish_title=..., publish_description=...)` with the segments list exactly as produced — do not reformat or flatten it, `update_video` derives the flat `script` itself — and the publish title and description the skill wrote (`update_video` refuses a script without both); (2) in `pronunciation_mode == "respell"` or `"ipa"` only, and only if the skill returned one or more new lexicon entries, call `upsert_pronunciation_lexicon(entries=[...])` — if the list is empty, **skip this call entirely**, never call it with `entries=[]`, since it hard-errors on an empty list; in `pronunciation_mode == "phoneme"`, skip this call entirely; (3) `add_comment` with a one-line summary; (4) `set_video_status` → `SCRIPT_READY`. On failure (the script genuinely can't be written, or a downstream call errors): stay at `TOPIC_APPROVED` and `add_comment` explaining why — do not advance. |
| `TOPIC_REJECTED` | Terminal — the human flat-rejected the topic. Do nothing; stop processing this video. |
| `VOICING` | **Already authorized — voice it now.** A video only reaches `VOICING` because a human approved its script at `SCRIPT_READY` (or, on a re-voice, approved it there earlier — see the pronunciation row under **Handling REVISION_REQUESTED**). That move is the approval, both for the ElevenLabs spend and for sending the script to ElevenLabs. Do not ask for approval again, and do not stop to confirm the cost or the third-party disclosure: in a cron run nobody is present to answer, and a refusal wedges the video — it stays in `VOICING`, and every scheduled session picks it up and refuses it again. Call `generate_voice(video_id, script)` — same call shape as always. Internally, if the video has `script_segments`, the text actually sent to ElevenLabs is derived from the segments (joined `voice` text), not the flat `script` argument, which is otherwise ignored in that case; legacy videos with only a flat `script` are unaffected. Voice is resolved from the video's own `voice_id` (set at job creation, or by a human at the `TOPIC_PROPOSED` or `SCRIPT_READY` checkpoint) if present, else the install default — nothing to do here, `generate_voice` handles the fallback. It automatically saves paths and advances to `VOICE_READY`. |
| `VOICE_READY` | Invoke **tubematic-scene-config skill** — it discovers reusable scenes in `installed/` and `generated/`, classifies every segment's visual treatment (photographic, hybrid, diagrammatic — see **Visual Treatment** below), generates images for the photographic and hybrid ones via `generate_image`, looks at each one via `read_image` before building the scene around it, authors any new scene TSX into `generated/{video_id}/`, then calls `write_scene_config(video_id, config)` to write `scene-config.json` and save `scene_config_path` in one call. **Image generation and scene authoring are co-equal productions — neither is subordinate to the other.** When it returns: (1) read the canvas and the per-segment treatment list it reports. That is the video's `visual_style` plus the canvas — and for `auto`, which canvas the skill chose and why — if it did not say, send it back, because nothing downstream can explain what the video is otherwise. Then, **on a dark canvas only**, if it named any segment photographic or hybrid but no scene entry carries an image path, send it back to generate those images before anything else — a video about named characters, creatures, real places or one specific historical event with zero generated images is a defect, not a style choice, and `validate_job` cannot detect it (it only checks that image paths which *are* referenced resolve), so this check is yours. On a light canvas that floor does not apply, but its reason still does: a **named, specific** person, creature or place reported as a stick figure rather than a panel-framed image is the same defect, and is also yours to catch; (2) call `list_scene_files(source="generated", video_id=video_id)` to confirm all newly-authored scenes are present; (3) call `validate_job` and fix any errors it reports, then read its `warnings` — the text-layout audit measures real text rects in a browser, so an overlap or safe-zone warning is a measurement, not a guess, and is far cheaper to fix now than after a render; (4) call `submit_render`. `submit_render` is a pure DB write — it just queues the video (`VOICE_READY → RENDER_QUEUED`) and returns immediately. The render worker (a separate always-on process) picks it up from there — **do not poll**. |
| `RENDER_QUEUED` | AUTO — do not take any action. The render worker will claim it (advancing to `RENDERING`) as soon as it's free; a single worker renders one video at a time, so this may sit for a while if another render is in progress. Fire and forget. |
| `RENDERING` | AUTO — do not take any action. The render worker renders the video and automatically advances to `VIDEO_READY`, `REVISION_REQUESTED`, or `FAILED` (its own render-crash retry cap exceeded). Fire and forget. |
| `REVISION_REQUESTED` | Read the comment(s), classify the revision, and route to the matching checkpoint — see **Handling REVISION_REQUESTED** below. If the failure is unfixable, escalate to `FAILED`. |
| `VIDEO_APPROVED` | **Human-owned — take no action.** Publishing to real social accounts is decided on the dashboard — by a human, or by Auto Pilot for the projects the operator put on it — and there is no tool here that can do it. Never advance this video yourself, and in particular never `set_video_status` it to `SCHEDULED`, `PUBLISHING` or `PUBLISHED` — that would mark a video as scheduled or published when nothing was ever posted. |
| `SCHEDULED` | AUTO — do not take any action. A human or Auto Pilot scheduled the post and postforme is holding it; the render worker moves the video to `PUBLISHING` when its time comes. |
| `FAILED` | Terminal — unrecoverable failure. Do nothing; stop processing this video. |

---

## Visual Treatment — what a `visual` brief must say

Every segment's `visual` brief commits that beat's treatment, and the treatment follows the beat's
**subject**, not the writer's habit:

- **Subject the viewer wants to *see*** — a named character or real person, a creature or animal, a
  real place or structure, one specific dramatic or historical moment, or a mood/establishing beat →
  write a **photographic/illustrative** brief: name the subject, the moment, the framing, the light.
  `"Aemond on Vhagar breaking through low cloud over the burning field, low angle, hard backlight"`,
  not `"dragon icon on an overhead map"`.
- **Subject the viewer wants to *track*** — a process with discrete stages, a before/after
  comparison, a mechanism or dataflow, counts, timing, cause and effect, code or terminal output →
  write a **diagrammatic** brief. `"cut to terminal showing whoami output"`,
  `"memory-allocation diagram, 4 boxes filled of 8"`.
- **Both** — the exception, not the usual case. Only when the viewer must follow structure the
  narration doesn't give them: *which* way, *what order*, *how many*. Say both in one brief:
  `"photographic wide of the castle and coastline, animated march-route arrow drawn over it"`. A
  battle, ambush, siege, duel, expedition or assassination is **never a bare diagram** — but it is
  photographic by default, and only earns drawn-on structure when the beat turns on *where* or *in
  what order*. If the brief would only be adding an arrow to make the beat feel busy, or to repeat
  in a picture what the `voice` line already says, write it photographic and leave it alone.

A brief that reduces a named character, creature or real place to an icon, silhouette or marker on a
diagram is a defect: it tells `tubematic-scene-config` to draw a shape where the viewer expects the
thing itself. That skill may reclassify a brief by subject, but never make it guess.

**Where figures are permitted** — `visual_style` is `"stick"` or `"auto"`, the two options that
do not exclude them — there is a fourth treatment: a beat about a **generic role** ("the user",
"an attacker", anyone in a hypothetical or a walkthrough) is drawn as a posed stick figure, and its
brief names the action and the emotion rather than the photography:
`"scientist at a console, shocked, red alert pops in"`. That is a carve-out for generic roles only;
the rule directly above is unchanged, and a named, specific subject is still a real generated
image.

`visual_style` is a **permission set, not a look**. `motion_graphics` and `stick` are restrictions
— on the canvas, and on whether figures may appear at all. `auto` is the absence of one: the agent
picks the canvas and *may* use any vocabulary.

**A permission is not an instruction, and this is yours to enforce.** A video that uses every
vocabulary because `auto` allowed it is a defect — it reads as three half-finished videos spliced
together, not as a rich one. When the scene-config skill hands back a mixed treatment list, make it
justify each vocabulary in one sentence. If a treatment appears in a single beat with no reason you
would accept, send it back to build that beat in the vocabulary the rest of the video already uses.

---

## Handling REVISION_REQUESTED

`REVISION_REQUESTED` is a single status covering several distinct kinds of revision. Read `get_video`'s comment thread and which fields are already populated to classify which stage is being revised, then route back to that stage's checkpoint — never skip ahead of a human checkpoint on the way back:

Check the **Pronunciation revision** row before the two below it — `video_path` and
`voice_file_path` are populated in that case too, but the fix and target status are different from
a generic render/script rewrite.

| Signal | Classification | What to do |
|---|---|---|
| No `script` yet, or the human comment is about the topic itself | **Topic revision** | Revise the proposal, `update_video`, then `set_video_status` → `TOPIC_PROPOSED` |
| `script` populated, no `voice_file_path` yet, or the comment is about the script content (not specifically a mispronunciation — see the row below) | **Script revision** | Rewrite the script via the script-writing skill, regenerating **both** the segments and (in `respell` or `ipa` mode, if applicable) any lexicon entries coherently — never patch just the `voice` text of one segment while leaving its `visual` note stale, or vice versa; treat each segment as a single unit to re-derive together, re-deriving each segment's `visual` per **Visual Treatment** below. Pause markup is part of that unit: re-derive it with the rewritten `voice` rather than carrying old break tags across a rewrite, since their placement was tied to the old phrasing. Rewrite the publish title and description from the new script too. Then `update_video(script_segments=[...], publish_title=..., publish_description=...)`, and in `respell` or `ipa` mode only, if the regenerated lexicon-entry list has one or more entries, `upsert_pronunciation_lexicon(entries=[...])` (skip entirely if empty, per the `TOPIC_APPROVED` rule above), then `set_video_status` → `SCRIPT_READY` |
| `voice_file_path` populated and either a human comment reports a mispronunciation (a name, term, or acronym audibly wrong) **or** the AI review returned a `mispronunciation` must-fix | **Pronunciation revision** | The script text itself is not wrong, so don't rewrite it. Call `upsert_pronunciation_lexicon(entries=[{"term": ..., "respell": "..."}])` with a corrected respelling — this is an upsert, so it overwrites any existing entry for that term — or, for a one-off term not worth a global lexicon entry, edit the segment's `voice` via `update_video(script_segments=[...])` to add/fix an inline `<respell as="...">word</respell>` tag — passing the current `publish_title` and `publish_description` from `get_video` unchanged, since `update_video` refuses a script without them. If they are blank there (a video scripted before these existed), write both from the script per the script-writing skill instead — `update_video` refuses blanks too. Compare the audio's reported defect against the video's `tts_text` (what was actually sent) before choosing the new respelling — if the old one was already correct and simply wasn't honored, a different spelling of the same sound is the fix, not the same one again. **If the old respelling was hyphenated (`Day-mon`), that is almost certainly why it wasn't honored — ElevenLabs does not speak hyphenated respellings correctly. Rewrite it as one plain word spelling the same sound (`Daymon`).** When the video's `pronunciation_mode` (from `get_video`) is `ipa` (its voice's model is `eleven_v3`), the better retry for a one-off term is an inline `<ipa ph="...">word</ipa>` tag per the script-writing skill; if the term already had one, correct the transcription (stress marks, a vowel) instead of re-sending the same one — v3's IPA is not 100% consistent, so one failure does not prove the transcription wrong, but an identical retry is a paid re-voice spent on the same odds. Then `set_video_status` → `VOICING`. **In a scheduled run scoped to one video and one stage, end the session here** — do not call `generate_voice`: the voicing and the scene work each run in a session of their own, and doing them here would record their cost as this revision's. In any other run, call `generate_voice` again. This re-voice is already authorized — by the script approval the human gave at `SCRIPT_READY`, whose text you have not changed — so do not ask for approval again. Re-voicing re-charges ElevenLabs and produces a **new `timeline.json`**, so the old frame spans no longer apply: continue through the normal `VOICE_READY` flow afterwards (re-derive the scene config against the new timeline, `validate_job`, `submit_render`) rather than re-submitting the existing config. If the same review also returned non-pronunciation must-fix items, apply those scene fixes in that same `VOICE_READY` pass. Note in `add_comment` that the video keeps its old audio and rendered video until the re-voice and re-render complete. |
| `scene_config_path`/`video_path` populated, or the comment is a render failure or AI-review feedback with no `mispronunciation` must-fix | **Animation/render revision** | Invoke the `tubematic-scene-config` skill and take its **Revising an Existing Video** branch — this is an edit to the scenes that exist, not a new video on the same topic. It reads the current config with `get_scene_config` and the faulted scenes with `read_scene_file`, rewrites **only** those via `write_scene_file`, and writes the config back with every other entry carried through unchanged. Do not let it re-run the 1–8 authoring workflow here: that discards every frame span, `src`, image and prop the previous round got right, and re-charges for images that were never the problem. Then `set_video_status` → `VOICE_READY`, re-validate with `validate_job`, then `submit_render`. The scene-work claim taken by the first of these calls (while still `REVISION_REQUESTED`) spans this whole re-entry — the `→ VOICE_READY` transition deliberately does not release it, so `submit_render` at the end still succeeds for the same session. |

**A revision that asks for a different voice.** The human names a voice in the comment. Take it
from `get_pipeline_status`'s `elevenlabs_voices` — each entry carries its `model_id` and
`pronunciation_mode`. If no roster voice matches, do not guess: `add_comment` listing the roster
voices, change nothing, and `set_video_status` → `SCRIPT_READY` so the human can pick there. If one
matches, first try `update_video(video_id, voice_id=<new>)` on its own: it succeeds when the new
voice's model can speak the stored script, and that alone is the fix — `add_comment`, then
`set_video_status` → `SCRIPT_READY`. If it is refused, the script's markup belongs to the old model
and must be rewritten for the new one: treat it as a **Script revision**, telling the script-writing
skill to write for the new voice, then pass `voice_id=<new>` **and** the rewritten
`script_segments` — with `publish_title` and `publish_description`, as every script write carries —
in the **same** `update_video` call. The voice alone stays refused while the old
script is stored, and the script alone is checked against the old voice, so neither order of two
separate calls works. Then `set_video_status` → `SCRIPT_READY`: a new voice is a new voicing spend,
which only the human approves, even when the video had been voiced before.

For an AI-review revision, `get_video`'s `gemini_feedback` field (not just the comment) carries the
full review: an **overall** critique, **must-fix** errors (blocking — each names the offending
**scene**, a **timestamp**, and a **suggested fix**), and **suggestions** (non-blocking improvement
ideas, which may be empty). Fix every must-fix item first — that scene, not the
pipeline in general — then apply the suggestions in the same revision pass rather than deferring
them; a review with zero must-fix but non-empty suggestions still arrives as `REVISION_REQUESTED`
and still deserves a real revision, not a pass-through re-submit. The comment also states which
review number this is out of the cap (e.g. "AI review 1 of 1") — past the cap, the render worker
runs one final review, writes its feedback, and accepts the render as `VIDEO_READY` regardless of
what it found, so there is no further automatic round to lean on.

One must-fix type does **not** belong to the animation/render path: `mispronunciation`. The review
is given both the authored script and the exact text sent to ElevenLabs, so a finding under this
type means the *audio* is wrong, never the scene — take the **Pronunciation revision** row above
(fix the lexicon or the inline `<respell>` / `<ipa>`, re-voice, then re-derive the scene config against the
new timeline). Editing scene TSX in response to it changes nothing about what is heard. A
deliberate respelling is not itself a defect — the review is told the two script forms may
legitimately differ — so treat such a finding as a genuine pronunciation error rather than
reverting the respelling that caused the difference.

If a render-failure comment describes something you cannot fix by editing scenes (e.g. a renderer/infrastructure error rather than a scene bug), do not keep retrying — call `set_video_status` → `FAILED` with an `add_comment` explaining why it's unfixable. In every case, `add_comment` explaining what was fixed (or why it couldn't be) before moving on.

---

## Error Handling

- **Render failure** — the render worker sets the video to `REVISION_REQUESTED` with an error comment (or `FAILED` directly if its own render-crash retry cap was already exceeded). Read the comment; if fixable, fix the scene TSX before re-submitting — otherwise escalate to `FAILED` (see **Handling REVISION_REQUESTED**). A worker crash/restart mid-render is handled separately and automatically (the worker requeues it to `RENDER_QUEUED` on its own startup reconcile) — no agent action needed for that case.
- **AI-review feedback** — the render worker sets the video to `REVISION_REQUESTED` whenever the review has any must-fix errors or suggestions, with a comment summarizing both (full detail in `gemini_feedback`). Fix the must-fix items first, then apply the suggestions, before re-submitting — see **Handling REVISION_REQUESTED**. A `mispronunciation` must-fix routes to the pronunciation path there, not a scene edit.
- **`generate_voice` error** — call `add_comment` with the error and leave the video at `VOICING`; it is already there, so do not call `set_video_status`. Re-writing the same status changes only `updated_at`, which is the clock the render worker uses to flag a video stuck in `VOICING` to the human.
- **`validate_job` errors** — fix all reported issues (missing scene files, TypeScript errors) before calling `submit_render`.
- **`validate_job` warnings** — advisory, and they never block `submit_render`, but do not ignore them. They come from the text-layout audit, which renders settled frames in a real browser and measures real text rects, so "overlaps by 73% of the smaller box" or "crosses bottom (y=1900 > 1750)" is measured fact. Each names the scene, the frame, and the text, which is enough to find the element in your own TSX. Fix them and re-run `validate_job` before submitting; a render plus an AI-review round costs far more than the edit. If a warning looks wrong, say so in `add_comment` rather than silently submitting — a false positive is a bug worth reporting. One warning is expected and not a defect: `audit skipped: an audit for <id> is already running`.
- **`set_video_status` returns `status_mismatch`** — the video already moved on (human action or concurrent agent). Stop processing it — treat as success.
- **`generate_image`/`write_scene_file`/`write_scene_config`/`submit_render` return `scene_work_claimed`** — another agent session is already doing scene work on this video right now. Stop processing it immediately — do not retry — and move on to another workable video, or end the session if the run is scoped to one video; the claim expires on its own if that session stalls.
- **Any unrecoverable error** — call `add_comment` explaining the failure and stop. Never silently swallow errors.

---

## User-Invocable Commands

| Command | What to do |
|---|---|
| `/tubematic` | List all available Tubematic commands |
| `/tubematic-status` | Call `get_pipeline_status` + `list_videos`, format a readable summary |
| `/tubematic-submit-new-job` | Score topic (rubric below), match-or-create a domain, `create_video(strategy="manual")` + `add_comment` |
| `/tubematic-add-topic` | Call `upsert_project` with `is_curriculum_seed=True` to add a curriculum seed domain |
| `/tubematic-pause-domain` | Call `set_project_status(project_id, "paused")` |
| `/tubematic-resume-domain` | Call `set_project_status(project_id, "active")` |
| `/tubematic-list-strategies` | Call `get_research_strategies`; also call `list_projects` and show seed domains |
| `/tubematic-set-strategy` | Call `set_research_strategies` with the parsed list |
| `/tubematic-dashboard-status` | Run `docker compose ps` + `curl http://localhost:4000/health` |
| `/tubematic-pause` | Call `pause_pipeline` |
| `/tubematic-resume` | Call `resume_pipeline` |

---

## Producibility Scoring (for `/tubematic-submit-new-job`)

Minimum score of 5 required. Do not create a video below this threshold. Sum the signals below and
clamp to 0–10; a topic scores on whichever track fits, and scoring on both simply means the topic is
rich on both tracks — it is not a treatment decision. How any given beat is *shown* is decided
per-beat downstream by `tubematic-scene-config`, and for a topic with real subjects in it that is
usually photographic. A topic that scores on the PHOTO track should be written up photographically
(name the subject, the moment, the framing), not as an abstract diagram — see **Visual Treatment**
above.

**DIAGRAM track**

| Signal | Points |
|---|---|
| Step-by-step process with discrete stages | +2 |
| Before/after comparison | +2 |
| Countable elements (≤ 12) | +2 |
| Flow diagram or state machine | +2 |
| Terminal / scriptable output | +1 |

**PHOTO track**

| Signal | Points |
|---|---|
| Named character, real person, creature or animal | +2 |
| Specific real place, structure, or distinctive physical object | +2 |
| One specific dramatic or historical moment | +2 |

**Penalties**

| Signal | Points |
|---|---|
| Live / unpredictable output | −3 |
| Scores zero on both tracks | −3 |
| Requires real footage that can't be generated as a still | −2 |
