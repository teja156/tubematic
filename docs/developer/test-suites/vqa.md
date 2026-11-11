# `vqa/tests`

Covers the helper scripts under `vqa/`. They ship in the video quality assessment image, a desktop
session for judging rendered videos
([Test environments](../17-development.md#vqa-video-quality-assessment)), and run on the host side
of that session. The suite needs the packages of all three requirements files, because the helpers
import `renderer/api/pipeline.py` and `mcp/server.py`.

```bash
python -m pytest vqa/tests
```

## Settings and status

### `test_edit_settings.py`

Covers `vqa/edit_settings.py`, the settings read and write utility.

- It parses `key=value` assignments, sends them to `POST /settings` unchanged and prints the
  effective values. A rejection shows the endpoint's own error.
- It warns when the stored value differs from the requested one. The case that matters is a
  default voice left off the roster, which the API stores and then reads as blank
  ([the default-voice invariant](../04-settings.md#the-default-voice-invariant-is-enforced-on-read)).
- Every API call carries the API token from the secrets directory, and a missing token stops with
  the command that creates it.
- `--restart mcp` needs `--yes`, because it drops a live agent session's tools. `--restart api`
  and `--restart renderer` need none.
- `--help` lists every settable key and reads the model catalogs from `pipeline.py`.

Trap: the script writes through `POST /settings` and uses no SQL. The live webhook probe and the
rule that keeps a re-sent masked secret from overwriting the real key exist only in that endpoint,
so a direct database write would skip them. No key needs a restart to apply
([Storage and reads](../04-settings.md#storage-and-reads)), so `--restart` is for a container
that has stopped responding.

### `test_statusline.py`

Covers `vqa/statusline.py`, the status line of the image's Claude Code session.

- The usage bar clamps to 0 and 100 percent and changes colour at its thresholds.
- A session with no rate-limit data, or no API call yet, shows the bars it has.
- The script reads JSON on stdin and prints one line, checked through a subprocess.

## The seed database and reset

### `test_make_seed_db.py`

Covers `vqa/make_seed_db.py`, which builds the database the image starts from.

- The schema comes from the real migrations and carries their newest columns.
- The seeded default voice is on the roster, and the seeded image model is in the OpenAI catalog.
- AI review is seeded off (`gemini_review_enabled`), and the image's own domain exists and is
  active.
- Running the generator twice gives the same database.

Trap: the seed rows are written after the migrations run, so no migration rewrites them. The
seeded voice must already carry its own model, and the seeded `image_model` must already be an
OpenAI model with no `image_provider` row. The generator also checkpoints the WAL before it
closes, because the session hook copies the `.db` file alone.

### `test_reset_db.py`

Covers `vqa/reset_db.py`, which replaces the database with a new seed and clears the job, output
and scene directories.

- Without `--yes` it prints what it would do and touches nothing.
- `--db-only` leaves the directories alone.
- A copy of the script in another tree resets that tree, whatever the working directory is.

## Review and staging

### `test_review_video.py`

Covers `vqa/review_video.py`, which runs the AI review on one rendered video.

- It passes the reviewer the script, the spoken text, and the review model and sampling rate from
  the settings table, with the pipeline defaults when they are unset.
- It writes the feedback to a file in the job directory and makes no database write, so a run can
  be repeated.
- An unknown video, an unrendered one and a missing file each stop with a plain message.

Trap: the script finds the mp4 and `scene-config.json` from the video's id and domain
(`tubematic_core/jobfiles.py`), honours the `OUTPUT_VIDEOS_PATH` override, and does not read the
stored path columns. A row that names another host file in `video_path` therefore cannot make the
script upload that file.

### `test_stage_script.py`

Covers `vqa/stage_script.py`, which writes a video's script with its visual briefs, and the text
that would go to ElevenLabs, as files a person can review before voicing.

- The staged text comes from `mcp/server.py::_build_tts_text`, the function `generate_voice`
  uses, with the model of the video's own voice. One test runs the real `mcp/server.py` to prove
  it.
- A script that `generate_voice` would refuse for that model is not staged, and neither is a
  video with no voice on the roster.
- The job directory is derived through `tubematic_core/jobfiles.py`. An id that is not one path
  component writes nothing, and a symlinked job directory or output file is refused
  ([Video ids in paths](../06-mcp-server.md#video-ids-in-paths)).

Trap: `tts_text.txt` in the job directory is a preview of what would be sent. The record of what
was sent is the column `videos.tts_text`
([What is sent](../08-scripting-and-voice.md#what-is-sent)), and nothing writes that record to
this file.

Needs: the isolated tree in the real-server test must copy every `mcp/*.py` and `tubematic_core`,
because `server.py` imports its sibling modules when it loads.

## Imports

A script with a second voice is staged run by run, through `mcp/server.py::_plan_voice_runs`, the
planning `generate_voice` uses.

### `test_host_side_imports.py`

Covers the import fallback at the top of `renderer/api/pipeline.py` and `mcp/server.py`.

- Each module imports with only its own directory on `sys.path` and no `PYTHONPATH`, which is how
  the helpers load them on the host.
- `make_seed_db.py` runs from start to finish that way.

Trap: the fallback that adds the repository root must stay off when `tubematic_core` already
resolves. The root also holds an `mcp` directory, and on the path it would shadow the MCP SDK
package of the same name. The containers set `PYTHONPATH`, so only this file sees a broken host
import.
