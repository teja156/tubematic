Read or change a pipeline setting in this VQA environment.

User's input: $ARGUMENTS (e.g. "show me the current settings", "set the image model to
gpt-image-2.5-sunburst", "bump the render timeout to 45 minutes")

This environment has no dashboard and no `onboard.py` wizard, so this is how settings get
changed here. Never hand-write SQL against `~/.tubematic-data/data/tubematic.db` to do it — some
checks live only in the API's `POST /settings`, so a direct write can store a value the pipeline
will then fail on.

**To show the current settings** (also the right first step whenever the user's request is
vague, or when you need to know the current roster before editing it):

  `/opt/tubematic/.venv/bin/python "$(ls -d ~/tubematic 2>/dev/null || echo /opt/tubematic)"/vqa/edit_settings.py`

**To change settings** — repeat `--set` for each key, and quote JSON values:

  `/opt/tubematic/.venv/bin/python "$(ls -d ~/tubematic 2>/dev/null || echo /opt/tubematic)"/vqa/edit_settings.py --set render_timeout_secs=2700`

Common keys: `image_model`, `render_timeout_secs` (seconds, minimum 60),
`max_render_retries`, `gemini_review_enabled`, `pipeline_paused`,
`elevenlabs_voices` (JSON list of `{"name": ..., "voice_id": ..., "model_id": ...}` — each voice
carries its own ElevenLabs model; there is no install-wide model setting), `elevenlabs_voice_id` (the
default voice — must be a `voice_id` already in `elevenlabs_voices`), `pronunciation_lexicon`
(JSON list of `{"term": ..., "respell": ...}`).

**If you are unsure a key exists or what values it accepts, run `--help`** — it prints every
settable key with its allowed values (real model catalogs, not examples), read live from the
pipeline's own spec. Prefer that over guessing a key name and relaying a 400.

Editing a list-valued key **replaces the whole list**, so read the current value first and pass
the full new list, not just the entry being added.

**Changes take effect immediately — never restart anything to apply a setting.** Every reader
queries the database live at use time.

If the command prints a `WARNING` line, **relay it and stop for the user** rather than reporting
the change as done: it means the write returned success but the value is not what the pipeline will
actually use. The usual cause is a default voice that names no entry in the roster — including the
case where replacing `elevenlabs_voices` orphaned the *existing* default without the request ever
mentioning it. The fix is to set `elevenlabs_voice_id` to a `voice_id` that is in the new roster;
until then voicing will fail with "No default voice set".

If the command exits with an error, relay it as-is — the API's own message already names the
specific problem (unknown key, invalid value, mismatched provider/model pair).

`--restart renderer` exists for a genuinely wedged render worker and nothing else. Do not offer it
as part of a settings change. `--restart api` additionally restarts the MCP server this session is
connected to and needs `--yes`; only run it if the user explicitly asks, and tell them their
Tubematic tools will drop until the connection re-establishes.
