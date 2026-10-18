# `vqa/tests`

Covers the utilities shipped inside the VQA Kasm image — the environment used to assess the quality
of videos Tubematic has produced.

```bash
python -m pytest vqa/tests
```

Most of these files use `class Test…` grouping rather than flat `test_` functions, unlike the other
Python suites; `test_host_side_imports.py` and `test_make_seed_db.py` are flat.

---

| File | Guards |
|---|---|
| `test_edit_settings.py` | `edit_settings.py` — the settings read/write utility, including assignment parsing (`key=value`, split on the first `=` only, empty values allowed) Every API call carries the API token from the secrets directory, and a missing token stops with the command that creates it. |
| `test_host_side_imports.py` | That `pipeline.py` and `mcp/server.py` still import with only their own directory on `sys.path` and no `PYTHONPATH`, which is how the host-side VQA helpers load them. When the two modules gained a `tubematic_core` import, every helper died with `ModuleNotFoundError`, and nothing else could catch it: the container sets `PYTHONPATH` to the package, and the isolated-tree tests set it explicitly. `make_seed_db.py` is run end to end as the cheapest proof a real helper works. The fallback that adds the repo root must **not** fire when the package already resolves, because the repo root also carries an `mcp` directory whose name collides with the MCP SDK |
| `test_make_seed_db.py` | `make_seed_db.py` — the build-time seed database baked into the VQA image. The seed is written *after* migrating, so migration `0006` never stamps it: its voice must already carry its own model, or every reader sees an empty roster. The same goes for `0016`: the seeded `image_model` must already be an OpenAI model, with no `image_provider` row |
| `test_reset_db.py` | `reset_db.py` — the destructive DB and artifact reset |
| `test_review_video.py` | `review_video.py` — the on-demand AI review script. It finds the mp4 and `scene-config.json` from the video's id and project, never from the stored path columns: a planted `video_path` is not what gets reviewed, and the `OUTPUT_VIDEOS_PATH` override is honoured |
| `test_stage_script.py` | `stage_script.py` — staging the script, broll and the ElevenLabs-bound text as plain files for human review. The one test that runs the real `mcp/server.py` also proves the staged text goes through `_build_tts_text`, the same function `generate_voice` uses, so an `<ipa>` tag for a voice on `eleven_v3` is staged in its `"/…/"` form. The model comes from the video's voice, resolved exactly as `generate_voice` resolves it. A script `generate_voice` would refuse for that model — an `<ipa>` or `<phoneme>` tag the voice's model cannot speak — is not staged at all, and neither is a video with no voice in the roster, so the review file never shows text that would not be sent. The job directory comes from `tubematic_core.jobfiles`: an existing row whose id is `../outside`, an absolute path, `.`, `..` or `a/b` is found in the database yet writes nothing anywhere, and a job directory or staged file that is a symlink is refused, while a legacy `a.b` still stages |
| `test_statusline.py` | `statusline.py` — the Claude Code statusline showing context usage and rate-limit windows |

---

## What these encode

**`edit_settings.py` writes over `POST /settings`, never direct SQL.** Some checks live *only* in
`post_settings` — the live webhook probe, and keeping a re-sent masked secret from overwriting the
real key — so a direct-SQL script reusing `_coerce_setting` would skip them. Do not "simplify" this
into a DB write.

**No settings key needs a restart.** `worker.py`, `mcp/server.py` and `pipeline.py` all read the
database per use with no in-process cache, so a write applies to the next read. `--restart` is
opt-in, for a wedged container only.

**The seed database sets `gemini_review_enabled=false` deliberately.** The worker bounces any video
with a non-empty suggestions list to `REVISION_REQUESTED`, so leaving review on would mean almost no
video ever reaches `VIDEO_READY` in the VQA environment.

**`review_video.py` derives paths rather than translating them.** It used to map the stored
container paths (`/jobs/…`, `/output_videos/…`) onto the host tree by prefix. The stored columns were
once writable by any caller, so a row could name any host file to be uploaded for review; deriving
the location from the ids, exactly as the worker does, makes such a row harmless. The isolated-tree
test therefore copies `tubematic_core` along with the script.

**`stage_script.py` owns `mounted/jobs/<vid>/tts_text.txt` with preview semantics.** That is why
`videos.tts_text` — the record of what was actually sent to ElevenLabs — is stored in the database
instead, and deliberately not written to that path.
