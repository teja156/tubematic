# `mcp/tests`

Covers `mcp/server.py`, the MCP server the agent calls, and the modules beside it:
`mcp/text_audit.py`, `mcp/cartoon.py` and `mcp/mascot_sheets.py`. The suite needs `fastmcp`,
`httpx` and `pillow` from `mcp/requirements.txt`, and a missing package fails at collection. Run it
in its own `pytest` invocation
([Run each Python suite on its own](README.md#run-each-python-suite-on-its-own)).

```bash
python -m pytest mcp/tests
```

`sample_angle.py` holds an angle a research proposal can be filed with, and `mined()`, one mining
candidate as Gemini returns it. A test that files a `curriculum`, `trending` or `mining` topic for
another reason passes it, because `create_video` refuses such a topic with no angle.

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

### `test_domain_agent.py`

Covers a domain's agent, model and effort in `upsert_project`, `create_video` and
`mine_youtube_topics` ([Assignment](../07-agent-layer.md#assignment)).

- `create_video` copies the three values onto a video of every `strategy`, and its result carries
  what was stored. A mined topic gets them too.
- A domain with no agent is dealt one. A domain agent uninstalled since falls back to the deal
  without its model, and a model the agent dropped seeds `""`.
- `upsert_project` keeps an omitted field and clears on `""`. It refuses an agent that is not
  live, a model outside the agent's list, a model with no agent and an unknown effort, and writes
  nothing when it refuses.
- A stored agent and model that became invalid do not block another edit of the domain, and the
  model can be cleared while its agent is uninstalled.

Trap: changing the agent without naming a model clears the stored model. Keeping it would refuse
the call, because the stored model belongs to the previous agent's list.

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

### `test_topic_angle.py`

Covers the [topic's angle](../02-pipeline.md#topic-angle) in `create_video`, `get_video`,
`update_video` and `mine_youtube_topics`.

- `create_video` stores a research proposal's angle, refuses one with no angle or with an angle
  scoring under 5, and files nothing in either case. A left-out score is refused with a request for
  it. A `manual` topic is accepted with no angle, however the agent says none (nulls through the
  real MCP client, empty strings, `none` spelled out, or a score for an angle it did not find).
  `none` spelled out on a research topic is still refused, and its message does not suggest leaving
  the angle out. A real sentence with `none` as its kind is refused for the kind, not dropped. A `manual` topic keeps an angle of
  any score. A malformed angle is refused on every strategy, and a kind is matched whatever its
  spelling.
- `get_video` returns the angle and `angle_formula`, the formula the kind points to. A video with
  no angle reads as empty, and a topic filed before angles existed still approves.
- `update_video` writes the angle at `TOPIC_PROPOSED` and `REVISION_REQUESTED`, and at
  `TOPIC_APPROVED` only while the video has none. It refuses the write at every later status. A
  rewrite sent with no score stores 0. A call with the score alone, or with one of the sentence and
  the kind, is refused and leaves the angle as it was. The approved angle sent again with other
  fields is not a write and does not stop them. An angle written with a profile, a style and an
  effort in one call stores all four.
- A mined candidate with no angle, an unknown kind or an angle scoring under 5 comes back in
  `not_filed` with the reason. The prompt carries the kinds and the score from
  `tubematic_core.angles`. The cap goes to the candidates with the highest two scores together. A
  kind written as its label, or with a hyphen, files under its id. A fractional or quoted score is
  brought to a whole number, and a `NaN`, `Infinity` or huge integer score costs that candidate only.

Trap: the write at `TOPIC_APPROVED` fills a missing angle when the agent picks a video up. Without
`angle = ''` in the `UPDATE`'s `WHERE`, it could replace an angle a person read and approved. A test
commits a change between the read and the `UPDATE` for that clause and for the status clause, and
each was confirmed to fail with its clause removed.

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

### `test_script_record.py`

Covers what `update_video` records with a script: `formula_id`, `hooks` and the returned `warnings`
([What a script records](../08-scripting-and-voice.md#what-a-script-records)).

- A script is stored with its formula, the kept opening's type and the three openings, which are
  saved as spoken text. `get_video` returns the openings and the warnings as lists.
- A malformed record is refused and nothing is written: one argument without the other, an unknown
  formula, a hook type the formula does not offer, not three openings, two of one type, none or two
  marked `kept`, a record with no `script_segments`.
- A flagged script is still written, and the stored warnings equal the returned ones. A script with
  no record is accepted and gets `no_formula`.
- A pronunciation fix that resends the script with no record keeps it, checks nothing and returns
  no warnings, on a script with a record, on one without, and on a stored flat script that holds
  markup and line breaks. A rewrite that sends none clears it.
  A rewrite with a new record replaces it.
- A fault inside the checks does not stop the write.
- The closing sentence is compared with the 30 newest other scripts of the same domain, and with
  none when the video has no domain. The opening is compared with the same scripts, and the kept
  opening's type with the domain's previous two videos.
- On a video with a `formula_pick`, a script recorded under another formula is refused and nothing
  is written. With no pick a person's choice binds the same way, and a choice of a formula this
  version lacks does not. With neither, any formula id is taken. New words with no record are
  refused beside a pick or a choice and accepted with neither, and a pronunciation fix is not
  checked against the pick.
- A `beat` label on a segment must be a short non-empty string.

Trap: a warning must never refuse a write, and a script with no record must be accepted. An agent
on an older skill sends no record during an upgrade.

Trap: a pronunciation fix goes straight to a paid re-voice with no approval in between. A warning
returned there would invite the agent to change words a person approved.

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

### `test_voice_segments.py`

Covers a voice per segment and a voice's speed in `generate_voice` and `update_video`
([A voice per segment](../08-scripting-and-voice.md#a-voice-per-segment)).

- A one-voice script is one request with the payload it had before speeds and segment voices: no
  `speed` at 1.0 and no context fields. A voice with a speed sends it.
- A script with a second voice is voiced in runs, in play order, each with its voice's id and model,
  and `credits` is their sum. Each run's ledger row carries its voice, and `tts_text` holds every
  run.
- A run carries its neighbours' words as `previous_text` and `next_text`, except on `eleven_v3`,
  which refuses them.
- Words after a join are offset by the length of the runs before, and the segments' frame spans
  stay in play order.
- A markup problem in a later run, a segment voice that left the roster, or no `ffmpeg` spends
  nothing. A failed later run keeps the credits already spent, writes no file and leaves the video
  at `VOICING`.
- `update_video` keeps a segment's voice, drops one equal to the video's, refuses one off the roster,
  and checks each segment's markup against its own voice. The roster reader keeps a valid speed.
- A pronunciation fix that resends the same words without any `voice_id` keeps the stored voices,
  and a rewrite with new words and no `voice_id` gives every line to the video's voice.
- The real join, when an `ffmpeg` is found on the host, measures each run and keeps the total
  length. It is skipped otherwise; the MCP image has `ffmpeg`.

Trap: the offset is each run's decoded length and never its last alignment time, which on
`eleven_v4` can run past the audio. The fake ElevenLabs reply encodes its length in the audio bytes
so the fake join can return it.

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
- A new and an overwritten file both get `0o666` less the umask. The temporary file is `0600`,
  and the MCP container runs as root, so without this the host user cannot read the scene and
  `upgrade.py` refuses.
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
- A path inside an installed scene's folder (`beanExplainer/props/lifeProps`, with or without
  `.ts`/`.tsx`) reads as a reference. A path that climbs out, starts at the root, runs past three
  parts or looks like a video's composed name is refused.

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
- Each segment carries its beat and its role. A beat split over two segments owes its change once,
  where it starts, and the formula's `first_frame` comes back with the segments. A video whose
  formula is not known keeps its beat labels and has no role past the opening.
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

### `test_bean_explainer.py`

Covers `mcp/bean_explainer.py`, the checks `write_scene_config` runs on a Bean Explainer config, the
`subtitles.emphasis` check, and the text audit's per-shot sampling
([Bean Explainer](../10-scene-authoring.md#bean-explainer)).

- The limits, timings, geometry, event types and cast ids equal the ones in the renderer's
  `contract.ts`, read from the TypeScript source. The style pack's catalogues (poses, faces, looks,
  marks, accessories, tints, entrances, fields, section colours, and every prop with its text limit
  and acts) equal the renderer's, and every prop has one drawing and no drawing lacks a prop. Both sides answer the
  shared cases in `fixtures/bean_explainer_contract.json` (label wrapping, prop, label and bean
  boxes).
- The skill's worked example (`reference/example-config.json`, timed against
  `reference/example-timeline.json`) passes.
- Each refusal names its shot or event and cause: an unknown field, accessory, pose, prop or act, two
  beans with one tint, a header too long, a badge that is not a prop, a section with no shot at its
  start, a cut or a pose off the words, a missing first `x`, a text slot over its limit, a scale out
  of range, an act before its prop lands, a label that repeats the narration, a label over a prop or
  the bean, a prop over the bean or off the stage, an event during the carousel or too close to a
  cut, a strike on nothing, too many elements, poses too close together, and a still stretch over
  3 seconds. Props may overlap each other, which the gags in the example rely on.
- A prop the agent drew (the skill's `example-prop-rocket.tsx`) passes, serves as a badge, and is
  placed by its declared box. A bad `customProps` entry (a library id, another video's file, a box out
  of range, a text slot too long, a bad act name) is refused, and so is a prop file that is missing,
  uses a filter, a gradient (SVG or CSS), randomness, a timer, a dynamic import, `performance`, a
  fetch, Remotion's media parts, the page or a `Function` constructor, imports another package
  (`from"fs"` with no space included) or has no default export. Terminal Doc and its moves share this
  list.
- `validate_job`'s re-check finds a prop file redrawn with a gradient, or deleted, after the config was
  written. A value of the wrong type (a list where an id belongs, scene props that are not an object)
  gets a sentence back and raises nothing. `.filter(Boolean)` is ordinary code while an SVG filter is
  refused, a variable named `filter` is not, every import form is checked (a bare `import`,
  `export ... from`), and `require` is refused in any form, `require("")` included. A config
  that sets only `subtitles.emphasis` keeps the style's caption look.
- `write_scene_config` reads the prop files a config names. `render_bean_props` refuses another
  style, a video with no config and a config with no `customProps`; it returns the picture (the
  renderer stubbed) and gives way to a heavy check that holds the lock.
- `write_scene_config` writes a sound config with the style's captions, keeps an `emphasis` it was
  given, refuses a bad one before writing anything, refuses `BeanExplainer` on another style and
  other scenes on a Bean Explainer video. `emphasis` beyond the narration's last word, on more than
  one word in 5, repeated, or not a list of numbers is refused, on any style.

### `test_storybook_atlas.py`

Covers `mcp/storybook_atlas.py`, the checks `write_scene_config` and `validate_job` run on a Storybook
Atlas config, the `label` caption background, `render_storybook_props`, and the text audit's
per-stretch sampling ([Storybook Atlas](../10-scene-authoring.md#storybook-atlas)).

- The limits, timings, stage, acts and other lists equal the renderer's, and titles wrap and walks are
  timed as in `fixtures/storybook_atlas_contract.json`, whose cases the renderer's own `stage.ts`
  produced (a walk in from the edge, a walk cut short by the next move, an exit). After a change to
  `stage.ts`, a limit or the library, `node storybook-tools/sync-contract.mjs` (from `renderer/remotion`)
  rewrites the fixture and the pack's `extra`; never edit them by hand.
- The pack carries the prop catalogue, and the caption band `mascots.caption_band` gives for the
  pack's captions holds a two-line label, so a mascot stays out of it.
- The skill's worked example passes. Each refusal names its chapter or event and cause: a bad coat,
  knob or name, too many people, too few chapters, a chapter off the words or too short, a title or
  byline too long, an unknown backdrop, entrance, prop, pose or act, an event off the words or in the
  chapter's last frames, a prop off the stage, a wall prop at a bad height, an act before its prop
  lands, a tag on nothing, the guide standing inside a prop or on a person, a plate too short,
  overlapping another or with something else happening under it, constellation words that cannot be
  lettered, gauge values out of range, a morph that is both or neither, a push with no portal, a still
  stretch, three people on stage, and two name tags that touch. A person walking past the guide is
  fine: only where people stand is checked.
- A bad `customProps` entry and a prop file that breaks a rule (no default export, another import,
  a filter, SVG text, a gradient, randomness) are refused; the example moth passes.
- `write_scene_config` writes a sound config with the style's captions, refuses a missing prop file, a
  broken config before writing anything, and `StorybookAtlas` on another style. `background: "label"`
  is accepted on any style and an unknown background is refused. `validate_job`'s re-check finds a
  prop redrawn with a filter. `render_storybook_props` refuses another style, a video with no config
  and a config with no `customProps`, and returns the picture with the Storybook script (the renderer
  stubbed).

### `test_terminal_doc.py`

Covers `mcp/terminal_doc.py`, the checks `write_scene_config` runs on a Terminal Doc config,
`preview_terminal_moves`, `validate_job`'s re-check of the agent's own moves, and the text audit's
per-beat sampling ([Terminal Doc](../10-scene-authoring.md#terminal-doc)).

- The limits, timings, geometry, sizes, slots, custom-move limits and catalogues equal the ones in the
  renderer's `contract.ts`, read from the TypeScript source, and the pack's `extra` lists the same
  moves, slots, sizes, tones, reveals, cuts and skins. Both sides answer the shared cases in
  `fixtures/terminal_doc_contract.json` (characters per size, number cells, note wrapping, every
  move's length).
- The `log` caption look and its `accent` are values `_validate_subtitles` accepts, read from
  `Subtitles.tsx`'s type: without that, the server would refuse the style's own captions in either
  skin.
- The skill's worked example passes. Each refusal names its beat, event and cause: an unknown skin,
  move, slot, size or tone, a cut off the words, a string too wide for its size, an encode not from
  `a` to `c` or with `b` taken, a move on an element that is still playing or not on stage, two
  elements in one slot, a reused id, more than 4 elements on screen, a bracket reaching into a taken
  slot, stage text that repeats the narration, a move too close to its cut, and a still stretch over
  3 seconds. A cleared slot can be used again.
- A move the agent wrote (the skill's `example-move-caesar.tsx`) passes. A bad `customMoves` entry, a
  text longer than the move takes, and a move file that is missing, uses a filter, randomness or
  `useCurrentFrame`, imports anything but the kit, or has no default export are refused, at write time
  and again by `validate_job` after a rewrite. A video id that is a UUID works for the files and the
  preview script.
- `write_scene_config` writes the pack's `log` captions, in amber for the `crt` skin, under the keys
  the config sets, refuses a broken config before writing anything, and refuses `TerminalDoc` on
  another style and other scenes on a Terminal Doc video. `preview_terminal_moves` refuses another
  style, a video with no config and a config with no moves, returns the picture (the renderer stubbed)
  with each move's slot and text, and gives way to a heavy check that holds the lock.

### `test_under_the_hood.py`

Covers `mcp/under_the_hood.py`, the checks `write_scene_config` runs on an Under the Hood config, the
`subtitles.look` check, the text audit's per-plate sampling, and the cap on photographs in
`generate_image` ([Under the Hood](../10-scene-authoring.md#under-the-hood)).

- The limits, timings, geometry, camera, event types, poses, tones, shapes, entrances and stat slots
  equal the ones in the renderer's `contract.ts`, read from the TypeScript source, and the pack's
  poses, events, tones and photograph cap equal them too. Both sides answer the shared cases in
  `fixtures/under_the_hood_contract.json` (the projection, the photograph's box, the push, chip and
  stat boxes, the stat's text with JavaScript's rounding, the leader's start, overlap).
- The skill's worked example (`reference/example-config.json`, timed against
  `reference/example-timeline.json`) passes.
- Each refusal names its plate or event and cause: a plate or a pose off the words, a plate too
  short, another video's or a container image path, a photograph that does not cover the band, a
  zoom out of range, photograph fields on a plain plate, a zoom entrance with no photograph before it
  or no `through`, a callout too long, a pinned point that leaves the band before its plate ends, a
  chip outside the band or on its point or over another, a bad region, arc count, counter values,
  stat affix, label, slot or width, a bad chart, a chart on a photograph or a callout on a plain
  plate, a second footnote, text too late to read, events out of order, too many elements, poses too
  close together or repeating the current pose, and a still stretch over 3 seconds. More than 12
  different photographs is
  refused and a reused one is free. A zoom-through counts the plate's text as leaving 6 frames early.
  A value of the wrong type gets a sentence back and raises nothing.
- The text audit samples each plate and stops before a zoom-through.
- `write_scene_config` writes a sound config with the style's captions, fills each plate's `aspect`
  from its file, keeps an `emphasis` it was given, refuses a photograph too wide to cover the band
  before writing anything, refuses `UnderTheHood` on another style and other scenes on an Under the
  Hood video. `subtitles.look` accepts `plain` and `selection` only.
- `generate_image` refuses a 13th new photograph on an Under the Hood video before any request goes
  out, and allows regenerating an existing one; other styles are not capped. A name being generated
  holds its slot, so a second new name cannot take the last one meanwhile, and a call that fails gives
  the slot back.

Trap: a plate whose own fields are bad is skipped for every check that projects through its camera,
including the next plate's zoom-through, or a malformed `focus` raised instead of being reported.

### `test_case_file_story.py`

Covers `mcp/case_file_story.py`, the checks `write_scene_config` runs on a Case File Story config,
the `subtitles.look` check, the text audit's per-beat sampling, and what `generate_image` does for
the style: the reference picture, the text added to the prompt and the cap on pictures
([Case File Story](../10-scene-authoring.md#case-file-story)).

- The limits, timings, geometry, camera, accents and their colours, beat kinds, meter kinds and
  icons equal the ones in the renderer's `contract.ts`, read from the TypeScript source, and the
  pack lists the same values. The pack's picture count is the stills limit plus the lead sheet. Both
  sides answer the shared cases in `fixtures/case_file_story_contract.json` (the number format, the
  meter cells, the camera's scale and view, the term's font size, the bars' layout, the frames of a
  beat's parts and the quiet stretches).
- The skill's worked example (`reference/example-config.json`, timed against
  `reference/example-timeline.json`) passes.
- Each refusal names its meter or beat and cause: a bad accent, meter count, id, kind, label or
  value; a first beat that is late or is a card; a beat off the words or out of order; a missing,
  early or second choice; no term card before the choice; a field the beat's type does not take;
  another video's or a container image path; the lead sheet used as a picture; a bad focus or
  punch-in; a `set` or `panel` naming the wrong meter; card text over its limit; an unknown icon or
  kind; a bar, result, payoff line, stamp or button timed off a word or out of order; a card whose
  last part comes too late to read. A shot or a finished card that sits unchanged for over 4
  seconds is refused, and a punch-in fixes the shot. More than 16 different stills is refused and a
  reused one is free. A value of the wrong type gets a sentence back and raises nothing, and so does
  a broken beat whose own problem falls past the 12 that are reported.
- The text audit samples each beat, a card from the frame its last part has appeared.
- `write_scene_config` writes a sound config with the style's captions, writes nothing for a broken
  one, refuses `CaseFileStory` on another style and other scenes on a Case File Story video.
  `subtitles.look` accepts `plain`, `selection` and `fill` only.
- The house lead's sheet ships beside the server. The lead sheet is made from it through the edits
  endpoint, at 16:9, with the outfit between the pack's lead description and sheet style. A still
  with `reference="lead"` sends the video's own sheet and the pack's lead description and painting
  style around the scene. A still with no reference goes to the generations endpoint with the
  painting style added. A still is sent at 9:16 whatever `aspect_ratio` asks for. A prompt with no
  final full stop gets one before the pack's text.
- `generate_image` refuses, before any request goes out, a lead sheet without `reference="house"`,
  the house sheet used for another picture, a picture named `house`, a reference that is not yet an image of the video, a
  reference with a path in it, and a reference on a video of another style, whose prompt is sent
  unchanged. A 17th new still is refused and a regeneration is allowed. The lead sheet has a slot
  of its own: a video that already holds 16 stills can still make it, and it never takes a still's
  place. Under the Hood keeps its own cap and wording.

- An edit from a reference waits up to 600 seconds for a response and a picture from text 180, and
  a reserved slot lasts longer than both waits.

Trap: the refusals for a wrong reference run before the scene-work claim and the cap, so a refused
call reserves no picture slot and reaches no paid endpoint.

Trap: a reservation that lapses sooner than the slowest call gives that call's slot to a parallel
one, and both are billed.
### `test_choose_script_formula.py`

Covers `choose_script_formula`, `get_video`'s `formula_routing`, the domain's default formula in
`create_video` and `upsert_project`, and the write that gives a pick back
([How a formula is picked](../08-scripting-and-voice.md#how-a-formula-is-picked)).

- A pick is recorded with its runner-up and its reason on one line. A bad formula, runner-up or
  reason is refused and nothing is written.
- The style is decided first at `TOPIC_APPROVED`: a video still on `auto` with no style pick is
  refused there, and a video Auto gave mixed scenes is accepted. In a revision a video scripted
  before picks existed gets a formula whatever its style.
- The pick is made once at `TOPIC_APPROVED` and is refused at every status but `TOPIC_APPROVED` and
  `REVISION_REQUESTED`. In a revision the agent may pick again on a video with no person's choice.
- A status change between the row read and the `UPDATE` leaves the video untouched. While the tool
  reads the setting and the domain's history, another writer is locked out.
- An experimental formula or runner-up is refused while the setting is off and accepted once it is
  on. The candidates carry `available`, `suits_style` and `recent`, and only a video at
  `TOPIC_APPROVED` with no pick or at `REVISION_REQUESTED` gets them. A revision whose pick is a
  person's choice gets none.
- `recent` is the domain's previous two videos, newest first, counting a video by its recorded
  formula or else its pick, and rows filed in the same second by insertion order. A formula among
  them is refused without `repeat_reason` and accepted with it, and the reason is stored. Another domain's videos and a video with no domain have no
  history.
- A person's choice becomes the pick, with the agent's formula as the runner-up and "Auto would
  have picked" in the reason. It holds for an experimental formula with the setting off, is exempt
  from rotation (also when the agent names the same recent formula), is written as the pick in a
  revision of a video that had none, and is not replaced in a revision. A choice of a formula that the installed
  version does not have reads as Auto.
- A move back to `TOPIC_PROPOSED`, guarded or not, empties the pick and keeps the person's choice.
  A script revision keeps the pick.
- A move to `SCRIPT_READY`, guarded or not, is refused while the stored script's formula is not
  the pick, including a pick with no record. A move to `VOICING` or `VOICE_READY` after a re-pick
  in a revision is refused the same way, with a refusal that sends the new script to a person.
- A pick of a formula the installed version lacks counts as none: the video is offered the
  candidates and picked for again, and a script write is not bound to it. A rewritten script and a script from before picks pass.
- Only a formula marked recent stores the repeat note. Recent counts the pick ahead of a switched
  script's record, and leaves out a topic sent back or rejected.
- The domain's default formula seeds every new video whatever its strategy. A default that is no
  formula seeds nothing, a new default must be a formula, an omitted one is left alone, and a
  stored one that was dropped does not block another edit.

Trap: the `formula` argument is the agent's own best formula on every call. A tool that took the
person's choice as the argument would lose what Auto would have picked, which the dashboard offers
as the switch.

Trap: rotation is enforced by the tool. Left to the skill's prose, a model that skipped the step
would give a domain the same structure every time, with nothing recording that it did.

### `test_learned_routing.py`

Covers [Learned routing](../08-scripting-and-voice.md#learned-routing) through the MCP surface:
`get_video`'s `formula_routing.learned`, each candidate's `learned` points, and the
`formula_evidence` record `choose_script_formula` stores.

- With evidence, a better formula has 2 points, a worse one -1 and an untried one 0, every formula
  is a candidate, and the opening types come ranked. `learned` carries no per-formula table.
- The setting `learned_routing` off, `publishing_enabled` off, or a domain with no evidence gives 0
  points everywhere and stores `''`. At a status where nothing is picked or written, the figures are
  not read.
- A pick with `learned_stamp` stores what the figures said about its formula, also when it was not
  favoured. A pick without it stores `''`. On a video with a person's choice nothing is checked,
  `''` is stored and no trial slot is used.
- A stamp that differs from the one worked out under the lock is refused and nothing is written:
  a pick recorded in between, new figures, and learning switched off each change it.
- Every fourth pick in a domain is a trial pick, which gives the points to formulas with too few
  videos and empties the openings list. A trial pick's openings stay empty after later picks in
  the domain move the count, and a pick with no record keeps its openings when the count sits on a
  trial position. A return to `TOPIC_PROPOSED` clears the record with the pick.

Trap: the record is worked out by the server under the pick's write lock, and only for a pick the
agent scored with the same stamp. Without that check, a session that read two videos before
picking either would score the second with learned points while its record called it a trial pick.

### `test_choose_visual_style.py`

Covers `choose_visual_style`, `get_video`'s `style_routing`, and the two writes that give a pick back
([How Auto picks a style](../10-scene-authoring.md#how-auto-picks-a-style)).

- A pack pick becomes the video's `visual_style`, so `get_video`'s `style` names its authoring skill
  and script guidance. `scenes` keeps `auto` and still counts as decided.
- The choice is made once, only at `TOPIC_APPROVED`, never over a style a person chose, and never
  for an archived video. A bad style, runner-up or reason is refused.
- An unavailable style or runner-up is refused with the reason, and a mascot rules out a 3D world
  and Under the Hood.
- A status, style, pick or archive change between the row read and the `UPDATE` leaves the video
  untouched, and so does a mascot landing before a 3D pick. While the tool reads what the install
  can make, another writer is locked out.
- `style_routing` lists every candidate and the video's domain.
- A pick clears the renderer and canvas recorded for earlier scenes, including a `cartoon_3d`
  renderer on a video with a mascot, and so does a return to the topic of an `auto` video or an Auto
  pick, or a person changing the style. A style a person chose keeps its canvas through a return to
  the topic.
- A video Auto routed to mixed scenes cannot record the `cartoon_3d` renderer or take a Cartoon 3D
  scene through `write_scene_config`, while a video from before Auto picked styles still can.
- `visual_style` and a `resolved_*` field are refused in one call, and a style change with a mascot
  is not refused for the Cartoon 3D renderer the same write clears.
- A move back to `TOPIC_PROPOSED`, guarded or not, returns an Auto pick to `auto`. A person's style
  survives it, and other moves keep the pick. A changed `visual_style` clears the pick and the same
  value keeps it.

Trap: the race and lock tests are mutation-checked. Each clause of the `UPDATE`'s `WHERE` is there
because a check made on an earlier read can be out of date by the write, and the write lock is what
keeps a removed key or a failed GPU from landing between the availability check and the write.

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
- An event that cannot be drawn and read before its board fades out is refused, a node's label
  typing included (the last board has no fade-out and ends on its final frame). Two chips or two
  focuses too close together, and a second fault on one node, are refused. The
  stillness rule counts seconds at the timeline's frame rate, whatever `fps` the config claims.
- The text audit samples each board.

Trap: the rows are the validator's promise to the renderer. `layout.ts` pins dagre to them through
each edge's `minlen`; a change to `compute_rows` on one side only lets a frame show more nodes in a
row than the check counted.

### `test_whiteboard.py`

Covers `mcp/whiteboard.py`, the checks `write_scene_config` runs on a Whiteboard config, and the
text audit's per-region sampling ([Whiteboard](../10-scene-authoring.md#whiteboard)).

- The board sizes, limits, timings, slots, inks, marks and glyph widths equal the renderer's, read
  from the TypeScript source, and both sides answer the shared cases in
  `fixtures/whiteboard_contract.json`. The pack's doodle list equals the doodles `doodles.ts` draws.
  Rounding follows JavaScript's `Math.round`.
- The skill's worked example passes. It opens on a doodle at frame 0, which may sit before the first
  word and is scheduled from `TIMING.openLead` frames before frame 0 (shared case `schedule_open`).
- Each refusal names its region, item and cause: a region count outside 2 to 6, an unknown layout,
  slot or doodle, a used slot, text that does not fit or uses a character the font lacks, an item
  off a word, out of order or before the camera arrives, a mark or arrow on a missing or later item,
  an arrow across another item, a second highlight, a marker that cannot keep up, an item drawn as
  the camera leaves, a still stretch over 3.5 seconds at the narration's frame rate, and a recap
  too short for every region's number or longer than 8 seconds.
- A wrong type (a list where a name belongs, props that are not an object, a `big` that is not a
  boolean) is refused with a message, never raised.
- `write_scene_config` writes a sound config with the style's captions on the light canvas, refuses
  a bad one before writing anything, refuses `Whiteboard` on another style, other scenes on a
  Whiteboard video and a dark canvas, and skips the word check when there is no timeline.
- The text audit samples each region and the recap.
- The doodle expander answers the shared cases (every primitive, and a digest of the whole shipped
  library) as `doodles.ts` does, and every shipped doodle passes the rules a video's own doodle
  must, since the agent copies from them. A video's own doodle is accepted, and refused when it
  reuses a shipped name, is defined but never drawn, leaves the box, uses an unknown primitive or a
  wrong number of values, asks for a huge arc or star, has a single-point stroke, too many strokes,
  or is one of more than 8; an item naming a doodle that is neither shipped nor defined is refused.
- `preview_doodles` returns the names and a picture with a cell for each doodle and the two shipped
  references, and refuses a doodle `write_scene_config` would refuse for its own sake. An extreme
  number (one that overflows the trigonometry or a float) is refused, never raised, and a doodle of a
  million segments is refused from its point count without being expanded.

Trap: the validator's placement and timing must equal the renderer's to the frame. The tests that
read `contract.ts` and the shared fixture are what catch a change made on one side only.

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

### `test_validate_job_typecheck.py`

Covers `validate_job`'s typecheck ([`validate_job`](../06-mcp-server.md#validate_job)), with a fake
`npx` that records the config it was given and can hang with a child of its own.

- The temporary config extends `tsconfig.json`, sits beside it, and includes only this video's
  directory and the scene files its config names. It is removed after a pass, a failure and a
  timeout. A video with no generated scenes runs no typecheck, and neither does one whose directory
  was emptied (`tsc` fails on an include that matches nothing).
- On a timeout the child the fake started is dead afterwards, and the error asks for another call.
- Two videos validated at once never overlap their typecheck, and a call that cannot get the checker
  in time returns an error without running one.

Trap: `npx` runs `tsc` as a child of its own, so killing `npx` alone leaves `tsc` running. Agents
call `validate_job` again after a timeout, and those leftover processes once filled a host's memory.
The timeout test fails if the kill reaches `npx` only.

### `test_picture_checks.py`

Covers `mcp/picture_checks.py` and its place in `validate_job`
([Picture warnings](../10-scene-authoring.md#picture-warnings)).

- Each data-driven style's worked example is read as its style and opens on a subject, and the
  same example with its opening pushed late, its subject removed or its words first is warned once.
- A segment owes its beat's role once, where the beat starts, and a beat label matches whatever its
  case and spacing. Segments with no beat, or a video with no formula, owe nothing past the opening
  and get no beat warnings. A Cartoon 3D config gets none either.
- A System Flow node entering by `TIMING.openWithin` opens the video; one frame later is warned.
- A mixed-scenes video that cuts on every beat is quiet. A turn or payoff inside a running scene is
  warned with its time, segment, beat and first words. A cut `CHANGE_LEAD` frames before the word
  or `CHANGE_WINDOW` after it counts, one frame further does not.
- Every style reports its cuts as changes; a System Flow chip alone does not count, and a
  Whiteboard doodle counts when the marker starts it. Malformed data is skipped, never raised.
- `validate_job` adds these warnings after the text audit's.

Trap: the quiet cases matter as much as the warnings. Each skill's example is what the agent copies,
and a warning on a sound video teaches the agent to ignore the list.

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
- The frame-0 pass is added for a mixed-scenes video only, outside the pinned sampling plan. It warns
  when frame 0 shows only text or a backdrop (a full-frame fill or SVG rect, a faint or tiny
  picture) and when nothing moves by frame 6. A picture already moving, something arriving or
  fading, and a canvas are quiet. The shapes of one SVG count as one picture, so a stick figure is a
  subject, and a filled card holding only text is a title card. A line drawing on counts as moving,
  and the warning names the scene on frame 0. Its frames skip the text checks.

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

- A new video gets the default mascot only while a GPU works, and none on a Cartoon 3D or Under the
  Hood video.
- The pick is frozen after the topic stage, needs a working GPU when it changes, is refused on an
  Under the Hood video, and is cleared by a switch to `cartoon_3d` or `under_the_hood` in the same
  write.
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
