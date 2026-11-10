# `mcp/tests`

Covers `mcp/server.py`, the MCP server the agent calls, and the modules beside it:
`mcp/text_audit.py`, `mcp/cartoon.py` and `mcp/mascot_sheets.py`. The suite needs `fastmcp`,
`httpx` and `pillow` from `mcp/requirements.txt`, and a missing package fails at collection. Run it
in its own `pytest` invocation
([Run each Python suite on its own](README.md#run-each-python-suite-on-its-own)).

```bash
python -m pytest mcp/tests
```

`conftest.py` provides `through_mcp`, which calls a tool over a real in-memory FastMCP client. Use
it when a test is about what the middleware sees or logs, because only that path wraps the return
value as production does. [The MCP Server](../06-mcp-server.md) describes each tool.

## Videos and pipeline state

### `test_pipeline_status.py`

Covers `set_video_status`, `create_video`, `get_pipeline_status` and the research settings tools.

- The agent cannot set `TOPIC_REJECTED` or `SCHEDULED`, and the status lists of this server, the
  Flask API and the dashboard's `VideoStatus` agree, read as source text.
- `create_video` refuses an unknown domain or `strategy`, a score under the threshold and a voice
  that is not on the roster.
- `get_pipeline_status` returns `user_preferences` verbatim, and `illustrated_available` as a
  boolean that does not carry the key. `get_video` reports the flag too, and a test checks that
  the scene-config skill reads it there, where a scheduled session may look.
- Mining is left out of `active_strategies` while no Gemini key is stored. Each Gemini call is
  recorded in the usage ledger before its reply is parsed, and a run files at most its cap.

Trap: a save of the research modes made with no Gemini key keeps a stored `mining`. The agent sees
only the filtered list, so storing what it sends back would remove mining for good.

### `test_archived_videos.py`

Covers how the tools treat an archived video ([Archived videos](../03-database.md#archived-videos)).

- `list_videos` and the counts in `get_pipeline_status` leave archived videos out. One is still
  readable by id.
- `set_video_status` and `update_video` refuse one with `video_archived`. A live video stays
  writable, as the negative control.

Trap: a listing filter cannot cover a video that a person deletes after the poller handed its id
to the agent. Without the write refusal, a move to `VOICING` or `RENDER_QUEUED` would spend on
files that are gone.

### `test_video_title.py`

Covers `videos.title` and its length cap ([Video titles](../06-mcp-server.md#video-titles)).

- `create_video` clips a long title at a word boundary, returns a warning and leaves `topic` whole.
- `update_video` refuses a long title and writes nothing.
- The title stays writable after the topic checkpoint, and the cap equals the Flask API's copy.

### `test_publish_metadata.py`

Covers the publish title and description that `update_video` requires with every script write
([`update_video`](../06-mcp-server.md#update_video)).

- A script without both values is refused and nothing is written, for `script_segments` and for the
  flat `script=` form.
- The caps hold and equal the Flask API's copies. The pair alone can be rewritten with no script.

Trap: the pair is required because the Publish dialog only reads it. The refusal tells the agent
to resend the stored pair on a pronunciation fix, and to write one when the stored pair is blank.
A video scripted before the pair existed would otherwise resend blanks and be refused each time.

### `test_agents.py`

Covers installed agents as the MCP server sees them: the agent a new video is dealt, and
`update_video`'s `agent_id`, `agent_model` and `agent_effort`
([The agent group](../02-pipeline.md#the-agent-group)).

- A model must be on the list of the video's own agent. Changing the agent clears the model
  unless one is sent with it.
- The three fields are frozen between human checkpoints. The freeze is checked before membership,
  so a late edit is reported as frozen.
- `agent_effort` needs no installed agent, because the levels are the same for every agent.
- A write is refused when the video's status or agent changes between the check and the `UPDATE`.

Trap: `test_the_tool_count_matches_the_docs` counts `@mcp.tool` in the source and compares it with
the heading `## The N tools` in [The MCP Server](../06-mcp-server.md). Adding a tool fails the
suite until that heading is updated, and rewording the heading fails it too.

## Domains

### `test_project_pause.py`

Covers the domain pause in `create_video`, `upsert_project`, `set_project_status` and
`mine_youtube_topics` ([Domain pause](../02-pipeline.md#domain-pause)).

- `create_video` refuses a paused domain for every research mode except `manual`. The refusal
  tells the agent to skip the candidate and logs as a `warning`.
- Only a curriculum seed can be paused, and clearing the seed flag on a paused domain reactivates
  it.
- A pause that commits between the early check and the `INSERT` still refuses, because the
  `INSERT` repeats the check. Mining refuses a paused domain before any Gemini call.

Trap: the refusal does not mention that `manual` is exempt. The agent supplies `strategy`, so a
message naming the exemption would teach it to relabel a candidate past the pause.

### `test_topic_cap.py`

Covers `list_project_topics` and the topic cap ([Topic cap](../02-pipeline.md#topic-cap)).

- `list_project_topics` includes archived and rejected topics, for the named domain only.
- A domain at its cap refuses every research mode except `manual`, with the same wording rule as
  the pause. Raising the cap re-opens it.
- A topic committed between the early count and the `INSERT` is still refused, because the
  `INSERT` counts again.
- Mining asks Gemini only for the room left under the cap and ends the run at the first refusal.

Trap: research must deduplicate against `list_project_topics`. `list_videos` hides archived
videos, so a deleted topic would be proposed again and Auto Pilot would pay for it.

### `test_project_description.py`

Covers a domain's description through `upsert_project`
([`upsert_project`](../06-mcp-server.md#upsert_project)).

- A multi-line description is stored verbatim, and the limit counts code points.
- An over-limit description is refused on a new domain and as a change, with nothing stored.

Trap: the limit is checked only when the description changes. Re-sending a stored over-limit
description is accepted, so an old value cannot block an unrelated edit.

### `test_default_script_profile.py`

Covers a domain's default script profile in `upsert_project` and `create_video`.

- `create_video` puts the default on curriculum videos only, and on none when the profile is
  deleted or not `READY`, because the approving `PATCH` would refuse it.
- `upsert_project` keeps an omitted default, clears on `""`, and refuses a change to an unusable
  profile. Re-sending a stored default that was deleted since is accepted.

## Research

### `test_mining_urls.py`

Covers what `mine_youtube_topics` may hand Gemini, and `set_mining_sources`
([`mine_youtube_topics`](../06-mcp-server.md#mine_youtube_topics)).

- One URL that is not a YouTube video refuses the whole run with no Gemini call. Two spellings
  of one video are asked once.
- A run makes at most as many calls as the topics it may file, including when every call fails.
- A second run while one is in flight is refused, and the lock is released after a run that was
  refused or raised.
- `set_mining_sources` stores the canonical, deduplicated list and refuses a list with a bad
  entry, leaving the stored list as it was.

Trap: a mining URL becomes the `file_uri` of a paid Gemini call. The URL check, the call bound
and the lock each stand between a bad setting and repeated spend, so the fake client counts the
calls.

## Script and voice

### `test_script_segments.py`

Covers `videos.script_segments` in `update_video` and `get_video`, and the markup `update_video`
refuses when a script is written ([Script segments](../08-scripting-and-voice.md#script-segments)).

- The flat `script` is derived from the segments with every tag removed. It keeps the authored
  word of a `<respell>` or `<ipa>` tag, so no markup reaches the captions.
- Each segment needs a non-empty `voice`, a unique id, a `visual` key and one spoken word.
- A `<respell>` or `<ipa>` tag must be closed and wrap one word. Pause markup and `<ipa>` must
  suit the voice's model, and a stage direction in brackets is refused.

Trap: two values are refused that ElevenLabs accepts and gets wrong: a `<phoneme>` alphabet other
than `cmu-arpabet` or `ipa` (the word is dropped from the audio) and a `<break>` time outside 0 to
3 seconds. The attribute must be the real one, once: a prefixed name, a repeat, or the text inside
another attribute's value does not count.

### `test_generate_voice.py`

Covers `generate_voice`: the text it sends, the alignment it turns into `timeline.json`, and what
it records ([Voicing](../08-scripting-and-voice.md#voicing)).

- The spoken text applies the lexicon and `<respell>` tags, while captions and `timeline.words`
  keep the authored spelling. The text sent is stored as `videos.tts_text`.
- Markup is checked against the model of the video's voice before any request, on the segment
  path and the legacy flat-script path. A tag the model cannot speak is refused and is not
  stripped, because a stripped tag voices the word as spelled on a paid request.
- One call runs at a time per video, only while `VOICING`. A symlinked job file is refused
  before any request, and a reply whose alignment does not match the segments leaves no file and
  logs as a provider failure, since the `200` was billed.
- `enable_ssml_parsing` is set, and the normalised alignment read, only for a script with
  `<phoneme>` tags, because that alignment expands numbers and would break the word count.
- The model sets hold: `<phoneme>` tags go to `eleven_flash_v2` and `eleven_turbo_v2` alone
  ([Phoneme mode](../08-scripting-and-voice.md#phoneme-mode)), and `eleven_english_v1`, which
  ElevenLabs answers `model_not_found` for, stays out of the catalog.

Trap: spend is recorded as the plan credits in ElevenLabs' `character-cost` header, for every
`200` and before the body is used. A local character count misses markup ElevenLabs bills and the
half rate of some models, so it is only the fallback, marked estimated, for a reply with no
header.

### `test_voice_models.py`

Covers per-voice models at the MCP server
([The model follows the voice](../08-scripting-and-voice.md#the-model-follows-the-voice)).

- `get_video` reports the video's voice, its model and `pronunciation_mode`.
  `get_pipeline_status` carries no install-wide model.
- `update_video` checks a script against the video's own voice and writes the resolved voice onto
  a video that has none.
- A voice change that the stored script cannot be spoken by is refused. Setting the video's own
  voice again passes, as the negative control.
- A voice on another model is accepted only with the rewritten script in the same call. At
  `TOPIC_PROPOSED` an old script blocks no voice, and that write is bound to the status.
- `generate_voice` refuses before spend when the voice's model changed under the script.

Trap: an explicit `voice_id=""` beside a script means the install default, and the resolved voice
is still written on the video. Otherwise a later change of the default would swap the model under
a written script.

### `test_pronunciation_rules.py`

Covers `upsert_pronunciation_lexicon` and `remove_pronunciation_lexicon`, and the guidance an agent
reads about respellings
([Respelling and the lexicon](../08-scripting-and-voice.md#respelling-and-the-lexicon)).

- Entries are added, edited in place and removed with no HTTP call. One bad entry in a batch
  writes nothing.
- The two refusal messages, the tool's docstring and the script-writing skill's Pronunciation
  section teach the one-plain-word form with its reason, and keep the letter-by-letter form for
  an acronym. The skill shows no tag the server refuses.
- The skill's pointer to ElevenLabs' documentation stays limited to syntax, and the skill wins a
  conflict.

Trap: the guidance tests search for the phrase that recommended a hyphenated token, because the
correct wording has to name the hyphenated form to warn against it. The skill check covers `as`
values that spell a sound, and an acronym such as `S-Y-N` stays allowed.

### `test_script_profiles.py`

Covers the script-profile tools, the profile schema `mcp/server.py::_script_profile_problem`, and
`add_comment`'s author rule.
[The profile schema](../08-scripting-and-voice.md#the-profile-schema) lists the rules.

- Completing a profile stores the markdown and drops the transcripts. A `READY` or `FAILED`
  profile cannot be written again, and a video can point at a `READY` profile only.
- The schema refuses anything but the create skill's seven sections in order, a link in any form
  a reader could follow, a registered tool name in any spelling, and a code fence.
- Encoded forms are refused too: character references, raw HTML, backslash escapes, invisible and
  fullwidth characters, and a heading or fence hidden in a blockquote or list.
- Each refusal applies on write and on read. A stored profile that fails comes back with empty
  markdown and a warning that does not quote the withheld text.
- `add_comment` accepts the author `agent` only, so an agent cannot sign a comment as a person.

Trap: the negative controls decide whether the schema is usable. A realistic profile must save
and come back byte for byte, and ordinary style prose (dotted names, ratios, a `[topic]`
placeholder, `@handle`, `R&D`, a link shape inside inline code) must pass. A code span that holds
a `|` is refused although a reader sees code, and a test fixes that choice.

Needs: one test starts a fresh interpreter under a timeout. It proves the tool-name check does
not ask the running server for its tools, which can deadlock on the server's event loop and leave
a profile at `GENERATING`.

## Images

### `test_generate_image.py`

Covers `generate_image` ([`generate_image`](../06-mcp-server.md#generate_image)).

- The request carries the model from `image_model`, the aspect ratio as its mapped size, and the
  key in a header.
- A missing OpenAI key, an unsupported ratio, a stored model outside the catalog and a video
  another session has claimed are each refused before any request.
- Usage is recorded for every `200`, including one with no image. Each failure logs as one
  `error` record, and a `200` with a malformed body logs as HTTP `200`.
- Keys are removed from every returned error, and the returned `public_path` passes
  `validate_job`.

Trap: an image name must leave room for the longest extension (`.webp`), checked before the paid
call. The extension is known only from the reply, so a longer name would bill an image that
cannot be written. A `403` from a project without access to the model becomes an error naming the
project and the model, because OpenAI's model list shows models a project cannot call.

### `test_generate_character.py`

Covers `generate_character`, the transparent cut-out for the illustrated style
([Generated characters](../10-scene-authoring.md#generated-characters)).

- A model that cannot draw a transparent background and a missing OpenAI key are refused before
  any request. Only an `auto` or `illustrated` video may generate characters.
- A pose with a `reference` goes to the edits endpoint.
- The tool reports the stored file's pixel dimensions, and every call is one usage row.
- The four hand-kept copies of the OpenAI model catalog agree, the defaults match
  `SETTINGS_SPEC`, and every catalog model has a built-in price.

Trap: the request shape is what the provider was observed to accept. Every offered size is
divisible by 16, which is why the canvas width of 1080 is not offered, and `input_fidelity` is not
sent, because every catalog model answers `400` to it. A name reserves room for `.png` only, so
the limit here is one character longer than `generate_image`'s
([Scene and image names](../06-mcp-server.md#scene-and-image-names)).

### `test_read_image.py`

Covers `read_image` ([`read_image`](../06-mcp-server.md#read_image)).

- It finds an image by its stem whatever the extension, and reports the stored dimensions. A
  large image is scaled down and the reply says so.
- Reading is not blocked by another session's scene-work claim and takes none.
- The grid's font candidates are the fonts the renderer image installs, and the bitmap fallback
  works on a Pillow whose default font has no size.

Trap: the coordinate grid is drawn on a copy in memory. The file under the job directory is the
render input, so a grid written back to it would appear in the finished video.

## Scene files and scene config

### `test_scene_resolution.py`

Covers the `generated/` and `installed/` libraries in `list_scene_files`, `validate_job`,
`write_scene_file` and `delete_scene_file`.

- `list_scene_files` tags each scene with its source and filters by it.
- `validate_job` finds a scene in the library its `type` names and reports a missing one with a
  hint.
- Writes and deletes touch `generated/` only.

Needs: a `validate_job` fixture here, in `test_scene_subfolders.py` and in
`test_validate_job_segments.py` must copy each job file to `JOBS_DIR/<video_id>/` after inserting
the row. `validate_job` derives the files from the id and ignores the stored path columns.

### `test_scene_subfolders.py`

Covers per-video scene directories, `generated/<video_id>/<scene>.tsx`.

- Two videos that use one scene name do not overwrite each other.
- `write_scene_file` returns the composed `src`, which `write_scene_config` and `validate_job`
  accept unchanged.
- `list_scene_files` still lists legacy flat files, filters by video, and caps an unfiltered
  listing with a truncation flag.
- `validate_job` flags a flat `src` that a video-scoped file shadows.

### `test_scene_modules.py`

Covers a Cartoon 3D video's TypeScript modules through `write_scene_file`, `read_scene_file`,
`list_scene_files` and `delete_scene_file`
([`write_scene_file`](../06-mcp-server.md#write_scene_file),
[`read_scene_file`](../06-mcp-server.md#read_scene_file)).

- While a video is `RENDER_QUEUED` or `RENDERING`, a write, a delete, `write_scene_config` and
  `cartoon_soundtrack` are refused with `status_mismatch`.
- `submit_render` holds the per-video source lock from the readiness check to the queue and
  records the source fingerprint. A write that was waiting on the lock is then refused.
- A write that fails leaves the last good file and no temporary file.
- A name reads and deletes as `list_scene_files` lists it.

Trap: the module name parser reads its two arguments and does not look at the directories on
disk. A composed name must agree with an explicit `video_id`, and a module directory named after
its own video is refused, because that name already means the video's root module.

### `test_read_scene_file.py`

Covers `read_scene_file`.

- It accepts the composed `<video_id>/<scene>` name and the bare stem with a `video_id`. A
  composed name that disagrees with the `video_id` is an error.
- `generated/` and `installed/` are searched separately, with no fallback from one to the other.
- What `write_scene_file` wrote is what the read returns, so a scene can be copied from one video
  to another.
- The read is not blocked by a scene-work claim and takes none.

### `test_write_scene_config.py`

Covers `write_scene_config`'s write path.

- It writes `scene-config.json` where `tubematic_core/jobfiles.py` derives it, which is where
  every reader looks, and records the path on the video.
- It overwrites an existing file, and refuses an unknown video and a malformed config.

Trap: this file takes no scene-work claim. That shows the claim is taken on first use and an
unclaimed video works without one. Do not add a claim to its set-up.

### `test_get_scene_config.py`

Covers `get_scene_config`, the agent's read of a video's `scene-config.json`.

- Every scene entry comes back intact, and an unchanged round trip through `write_scene_config`
  leaves the file byte for byte the same.
- A missing config says it has not been authored yet. Malformed JSON is an error.
- The read is not blocked by a scene-work claim and takes none.

Trap: two tests fix the signal for an incremental revision. The config's `totalFrames` equals the
timeline's when the audio is unchanged and differs after a new voicing, which means every scene
must be derived again ([Revising an existing video](../10-scene-authoring.md#revising-an-existing-video)).

### `test_get_timeline.py`

Covers `get_timeline`, the agent's read of `timeline.json`.

- It returns segments, and words on request. A video from before segments returns an empty list.
- An unknown video, a missing file, malformed JSON and a `video_id` shaped like a path are errors.

### `test_subtitles.py`

Covers the `subtitles` block that `write_scene_config` accepts, and source guards on the caption
component ([`subtitles`](../09-remotion-project.md#subtitles)).

- An absent key means captions are on, and the tool does not write the defaults into the file.
  Opting out is an explicit `enabled: false`.
- `maxWords` outside 1 to 7 is refused and not clamped. An unknown key or `background` is refused,
  and a refused block writes nothing.
- Source guards: a caption's hold is capped so it does not stay through a long pause, and each
  webfont loads one weight and subset list, with Oswald at 700, its heaviest.

Trap: the absent-means-on rule is the only way the default reaches a video whose config was
written before captions existed. The default font must be a system font, because captions are on
for every render and a renderer with no network access would stall on a webfont fetch.

### `test_visual_style.py`

Covers `visual_style`, `resolved_visual_style` and `resolved_renderer` in `update_video`, the
domain default in `create_video` and `upsert_project`, and `write_scene_config`'s canvas and
renderer checks ([Visual styles](../10-scene-authoring.md#visual-styles),
[The topic group](../02-pipeline.md#the-topic-group)).

- `visual_style` is frozen after `TOPIC_PROPOSED`, and the freeze covers that field only. The two
  `resolved_*` fields are write-once under `auto`.
- `illustrated` needs a stored OpenAI key. `cartoon_3d` needs a working GPU. `_gpu_probe_status`
  reads `tubematic_core.renderers.gpu_status` over the `renderers` table, so a GPU on a remote
  renderer counts.
- A domain's default style reaches curriculum videos only. `upsert_project` is a partial update:
  an omitted field is kept and `""` clears.
- `write_scene_config` refuses a canvas that contradicts the style, fills in an absent one, and
  refuses a scene kind that disagrees with the video's renderer.
- The first config resolves an unresolved `auto` video's renderer as a compare-and-set, and a
  failed write or commit leaves the file and the row agreeing.
- The server's style names are the objects in `tubematic_core.visual_styles`, `get_video` returns the
  video's `style` with the skill that authors it, and `get_pipeline_status` lists every style.

Trap: write-once on `resolved_visual_style` is the only thing that keeps a revision round on the
canvas the video already uses, since no code on the revision path reads the field. A domain
default of `illustrated` or `cartoon_3d` is checked only when it changes: re-sending a stored
default after the key or the GPU is gone must pass, or every later edit of that domain would fail.

### `test_system_flow.py`

Covers `mcp/system_flow.py`, the checks `write_scene_config` runs on a System Flow config, and the
text audit's per-board sampling ([System Flow](../10-scene-authoring.md#system-flow)).

- The limits, timings, tones and event types equal the ones in the renderer's `contract.ts`, read
  from the TypeScript source, and both sides answer the shared cases in
  `fixtures/system_flow_contract.json` (label wrapping, row assignment). The pack's icon list equals
  the icons `icons.ts` draws.
- The skill's worked example (`reference/example-config.json`, timed against
  `reference/example-timeline.json`) passes.
- Each refusal names its board and cause: a fourth node in a row, a fourth row, a cycle, an unknown
  icon, a label too long, an edge before its source lands, a packet before its edge has drawn, an
  event outside its board, a board not on a word, a disconnected node, and a still stretch over
  3.5 seconds.
- `write_scene_config` writes a sound config with the style's captions, refuses a bad one before
  writing anything, refuses `SystemFlow` on another style, other scenes on a System Flow video, and a
  `SystemFlow` entry of any type but `generated`.
- A node or edge that cannot finish its entrance before the board cuts is refused, and the
  stillness rule counts seconds at the timeline's frame rate, whatever `fps` the config claims.
- The text audit samples each board.

Trap: the rows are the validator's promise to the renderer. `layout.ts` pins dagre to them through
each edge's `minlen`; a change to `compute_rows` on one side only lets a frame show more nodes in a
row than the check counted.

### `test_watermark.py`

Covers the watermark, as guards on the source text of `CompositionBuilder` and `Watermark.tsx`
([Watermark](../09-remotion-project.md#watermark)). No test runs the component.

- The composition draws the mark once, after the captions and outside the scene list, with no
  props. The only switch is the `watermark` render prop, tested as `!== false`.
- The mark carries the largest `z-index`, loads its image with `staticFile()`, and the baked file
  is byte for byte the plate-backed artwork in `logos/`.

Trap: these guards keep the agent from moving or removing the mark. A prop, a `scene-config.json`
key or a scene entry would each hand that control to whoever writes the scene config.

## Validation, paths and the render queue

### `test_validate_job_images.py`

Covers `validate_job`'s check of image references in scene props
([`validate_job`](../06-mcp-server.md#validate_job)).

- A reference must name a file under this video's `images/`. A container path, a bare relative
  path, another video's image and a missing file are each flagged.
- References are found by path shape, in any prop at any depth.

Trap: an image `src` that does not resolve fails the whole render, because Remotion's `<Img>`
retries and then cancels. The hint names `generate_image` only, since a hint that names a tool
the server does not have sends the agent looking for it.

### `test_validate_job_segments.py`

Covers `validate_job`'s checks on a segmented script.

- Stored `script_segments` must pass the same rules as `update_video`.
- `timeline.json`'s segments must be contiguous and cover the video. A normal pause between
  sentences passes and a long unexplained gap fails.
- A legacy video with no segments gets none of these checks and keeps the older ones.

### `test_text_audit.py`

Covers `mcp/text_audit.py`, the decision layer of the text-layout audit
([The text-layout audit](../11-rendering-and-review.md#the-text-layout-audit)).

- On the fixtures, real collisions and safe-zone breaches are reported once with the worst frame,
  and nested, rotated, faint and boundary cases are not.
- Sampling takes several frames per scene, inside a window that leaves out the entrance and both
  crossfades.
- The driver's result is read from a file, because Remotion writes browser console lines to its
  own stdout.
- Every failure of the subprocess returns a warning and does not raise. A timeout kills the
  process group, and staged files are removed.

Trap: every threshold lives in this module, because it is the only layer the tests reach. The
browser probe and its driver need a browser, so a threshold moved into the probe leaves the
tested code.

### `test_job_paths.py`

Covers ids that become paths, at every tool that builds one
([Video ids in paths](../06-mcp-server.md#video-ids-in-paths)).

- Each path tool refuses a `video_id` that is not one path component and accepts a legacy id that
  the creation rule would refuse today.
- With one video's job and scene directories symlinked to another's, every path tool is refused,
  makes no network call and leaves the tree unchanged.
- `update_video` does not declare the four path columns, and `validate_job` reports a planted
  path's file as missing.
- A scene name with no room for `.tsx` in a file name is refused with an error.

Trap: each tool checks the id's shape itself and does not rely on the video lookup.
`delete_scene_file` makes no lookup, so without its own check an absolute `video_id` would
replace the scenes directory.

### `test_scene_claim.py`

Covers the scene-work claim
([The scene-work claim](../06-mcp-server.md#the-scene-work-claim)).

- The first owner gets the claim, a second is refused and told who holds it, and an expired claim
  can be taken by anyone.
- A refused guarded tool makes no request and writes nothing. An unclaimed video passes every
  guard.
- `submit_render` and a status change out of the claim window release the claim. A change inside
  the window keeps it.

Trap: a caller with no session identity takes no claim and is not blocked by one. Every such
caller shares one identity, so a claim under it could not be released by its owner and would
block a real session until it expired.

### `test_submit_render.py`

Covers `submit_render` for an ordinary video ([`submit_render`](../06-mcp-server.md#submit_render)).

- It moves `VOICE_READY` to `RENDER_QUEUED` with one guarded `UPDATE` and makes no network call.
- A status change between the check and the `UPDATE` loses.

Trap: like `test_write_scene_config.py`, this file takes no scene-work claim. Keep it that way.

## Cartoon 3D

### `test_cartoon_tools.py`

Covers `mcp/cartoon.py` and the `cartoon_*` tools
([Cartoon 3D authoring](../06-mcp-server.md#cartoon-3d-authoring)). A stub `node` on `PATH` plays
back a plan, so nothing is bundled or rendered.

- The beat gate runs over the video's job directory and its generated source tree.
- One video's rendering tools do not overlap, while a verdict recorder waits for the running tool
  so that parallel judges all land.
- `cartoon_soundtrack` refuses a malformed spec before anything runs, publishes new files with
  `mix.wav` last, and leaves the previous mix when a run fails.
- `submit_render` refuses an ungated Cartoon 3D video with `cartoon_not_ready`. `validate_job`
  carries the same errors and skips the text-layout audit.

Trap: a still's name can only be a plain file name under the video's stills directory, checked
before any path is built. A judge passes names back, so a traversal there would read any file the
server can. A symlink under the job's `cartoon/` directory or in the source tree is refused too.

### `test_cartoon_scene.py`

Covers `_validate_cartoon_scene`, the shape of a Cartoon 3D scene config in `write_scene_config`
([Cartoon 3D](../10-scene-authoring.md#cartoon-3d)).

- A config with no Cartoon 3D scene is not looked at.
- A second scene, an installed scene, a `src` that is not this video's `CartoonShort`, a late
  start, a short span and beats that leave a gap are each refused with a reason.

## Mascots

### `test_mascot_tools.py`

Covers `get_mascot_job`, `render_mascot_sheets` and `submit_mascot`
([Mascot authoring](../06-mcp-server.md#mascot-authoring)). The sheet renderer is replaced by a
function that writes a real PNG.

- Rendering and submitting work only while the mascot is `BUILDING`.
- `get_mascot_job` hands over, as previous code, the version the person last reviewed.
- Submitting needs all three sheets for the current code, and a change request does not touch the
  approved version.
- A status change or an archive that commits after a tool's check wins: nothing is stored or
  rendered.

Trap: the render cap is checked before anything runs and counts a render that failed, or an agent
could loop on a broken script. Changed code deletes the sheets rendered from the old code, or a
person would review pictures of code that was not submitted.

### `test_mascot_video.py`

Covers a mascot on a video: `create_video`, `update_video`, `set_video_status`, `upsert_project`,
`write_scene_config`, `validate_job`, `submit_render` and the audit's mascot warning
([Mascots](../10-scene-authoring.md#mascots)).

- A new video gets the default mascot only while a GPU works, and none on a Cartoon 3D video.
- The pick is frozen after the topic stage, needs a working GPU when it changes, and is cleared by
  a switch to `cartoon_3d` in the same write.
- Topic approval is refused for a withdrawn mascot and for a Cartoon 3D video that holds one,
  including when the other write commits between the check and the `UPDATE`.
- Invalid cues are refused with their reasons and nothing written. The mascot version is fixed by
  the first config write and kept by a revision.
- `validate_job` and `submit_render` refuse a mascot video with no cues.

Trap: `update_video` does not let `auto` settle on `cartoon_3d` while a mascot is chosen. That
pair leaves no scene kind `write_scene_config` accepts, so the video could not move. A test also
compares `write_scene_config`'s description with the shared cue rules, so the agent does not learn
the allowed values from refusals.

### `test_mascot_sheets.py`

Covers `mcp/mascot_sheets.py::render_sheet`, the subprocess around the sheet renderer, with a fake
`node` on `PATH`.

- A non-zero exit carries the stderr tail, and exit 0 with no picture is a failure.
- A picture left by an earlier render does not pass for a new one.

Trap: a timeout kills the whole process group. A plain `subprocess.run(timeout=…)` would leave
Chromium running.

## The server

### `test_tool_call_logging.py`

Covers the FastMCP middleware that writes one record for each tool call
([Tool-call records](../16-infrastructure.md#tool-call-records)).

- Argument values are dropped. `video_id` and `profile_id` pass through by allowlist.
- The level follows the cause, which a call site reports through `_provider_failed`. There is one
  record per call, and a raised exception still reaches the agent.
- Credentials are removed in the record itself, before the text is cut to length, for a stored
  key and for one supplied through the environment.
- A provider failure's details go in the record's message, because the dashboard's Logs page shows
  the message alone.

Trap: a tool that returns `{"error": …}` must not log as a success. The reader of the returned
error is tested against real `ToolResult` objects from a throwaway FastMCP server, because FastMCP
wraps the tool's dict and a guessed shape would read every failure as a success.

### `test_log_retention.py`

Covers `server.py::_log_retention_days`, which reads `log_retention_days` before the server
starts.

- A missing database, a missing table or row, a value `int()` rejects and an out-of-range value
  each fall back to the default.
- The bounds and the default equal `pipeline.py`'s, read from that file's source.

Trap: this read runs before `mcp.run()`, so an exception here stops the server before it can
answer `/health`. A new install has no database when the container first starts.

### `test_mcp_auth.py`

Covers the bearer token on `/mcp`, on the ASGI app the entry point serves
([Authentication](../16-infrastructure.md#authentication)).

- A missing, wrong, non-Bearer or extended token gets `401`, and `/health` stays open for the
  Compose healthcheck.
- Importing the module needs no secret. The entry point reads the token before `mcp.run`, so a
  missing file stops the server.

Trap: a `401` must not advertise OAuth: a bare `WWW-Authenticate: Bearer` and no
`/.well-known/oauth-*` routes. A client that finds OAuth discovery starts a browser login, which
an unattended agent run cannot finish.

### `test_health_route.py`

Covers `GET /health`, the readiness probe of the `tubematic-mcp` container
([Readiness](../06-mcp-server.md#readiness)).

- The route answers at the server root with the Flask API's body, and `/mcp/health` does not
  exist.
- The handler does not touch the database.

Trap: the tests build the ASGI app with the entry point's `path="/mcp"`. A FastMCP change that
moved custom routes under that path would leave the container unhealthy and stop onboarding's
renderer step.

### `test_api_keys.py`

Covers how the server reads provider keys
([How credentials are stored](../04-settings.md#how-credentials-are-stored)).

- A key comes from the settings table on each call, and the settings row wins over the
  environment.
- The environment is the fallback when the row is missing or blank, which keeps the test stack
  working.

Trap: one test asserts that no key is held in a module-level constant. Such a constant would
bring back the restart after a key change, and no other test would fail.

### `test_removed_tools.py`

Covers the removal of the GIF tool
([No agent-authored Python](../06-mcp-server.md#no-agent-authored-python)).

- `write_gif_script` is absent from the tool list an agent sees.
- Nothing under `mcp/` imports the GIF toolkit, `numpy` or `imageio`. `requirements.txt` keeps
  `pillow`, and lists `numpy` for the Cartoon 3D soundtrack engine alone.
