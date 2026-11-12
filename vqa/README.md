# VQA: the video quality assessment environment

This folder builds a [Kasm Workspaces](https://kasmweb.com/) image for judging the videos
Tubematic renders. A session has no dashboard, no cron and no install wizard. You open Claude Code,
run `/vqa-new-video "<topic>"`, approve the topic, the script and the video in chat, and get an
mp4. You ask for an AI review when you want one.

You need a Kasm Workspaces server. To test the installer, the dashboard or the poller, use
[`kasm_workspace_testing/`](../kasm_workspace_testing/README.md). The design of this image is in
[Development: `vqa/`](../docs/developer/17-development.md#vqa-video-quality-assessment).

## What is in this folder

| Path | Contents |
|---|---|
| `build.sh`, `dockerfile_tubematic_vqa` | Build the image `tubematic/tubematic-vqa-env` |
| `kasm_post_run_user.sh` | The launch hook. It prepares the session and starts the containers |
| `custom_startup.sh`, `watch_bootstrap.sh` | Open a terminal that shows the launch hook's log |
| `make_seed_db.py` | Writes the database a new session starts with |
| `edit_settings.py`, `stage_script.py`, `review_video.py`, `reset_db.py` | The [utilities](#utilities) |
| `agent/commands/` | The `/vqa-*` slash commands |
| `statusline.py` | Claude Code's status line |
| `vqa_test_topics.md` | Topics to try |
| `tests/` | The utilities' tests ([`vqa/tests`](../docs/developer/test-suites/vqa.md)) |

## Build the image

```bash
cd vqa
./build.sh                         # builds tubematic/tubematic-vqa-env:latest
./build.sh 1.0.0                   # another tag
./build.sh --no-cache              # clean rebuild
./build.sh --worktree <path|branch|dirname>   # name the source tree, no prompt
```

`build.sh` builds from one git worktree and asks which. The list marks a worktree that has
uncommitted work, which goes into the image too. An unattended caller must pass `--worktree`. See
[Both build scripts offer worktrees only](../docs/developer/17-development.md#both-build-scripts-offer-worktrees-only).

## Register the image in Kasm

Register the image as a workspace by hand in the Kasm admin UI. `build.sh` does not do it.

- Set a Persistent Profile Path. Without one, each session loses its videos, its database, its
  API keys and the Claude Code login when it ends.
- Set the Docker Run Config Override to `{"privileged": true}`. The session runs Docker inside
  the container, which needs it.
- Give it at least 4 cores and 8 GB of memory.
- Add no File Mapping. The API keys are stored in the session's database.

The containers' images are not kept between sessions. Each launch builds them again, which is the
slowest part of a launch.

## Where things live in a session

| Location | Contents | Changes when |
|---|---|---|
| `/opt/tubematic` | The source, its Python environment and the seed database, from the image | You rebuild the image |
| `~/tubematic` | The working tree, where Claude Code and `docker compose` run | A launch finds a new image and copies `/opt/tubematic` over it |
| `~/.tubematic-data` | The database, job files, generated scenes, rendered videos, API keys and service tokens | The pipeline writes to it. The launch hook creates what is missing and replaces nothing |
| `~/.claude`, `~/.claude.json` | Claude Code's login, settings, skills and commands | Each launch replaces the skills and commands |

The persistent profile keeps the home directory, so it keeps the last three.

- An edit under `~/tubematic` survives a relaunch of the same image. The next image replaces it.
- A skill or command you add to `~/.claude` by hand is deleted at the next launch.
- To keep a change, make it in the repository and rebuild the image.
- Do not run `onboard.py` in a session. Its settings step overwrites the seeded settings.

## Use a session

1. Launch a session and wait for the launch hook. A terminal opens and follows
   `~/tubematic/vqa/logs/bootstrap.log`. The session is ready when the log ends with
   `=== VQA environment ready ===`. If no terminal opens, open one and run
   `tail -f ~/tubematic/vqa/logs/bootstrap.log`.
2. On the first launch, [set the API keys](#api-keys).
3. Start Claude Code from the working tree. Log in the first time.

   ```bash
   cd ~/tubematic
   claude
   ```

4. Create a video:

   ```
   /vqa-new-video "how binary search works"
   ```

   The agent stops three times and waits for your answer in chat:
   - At the topic, it shows the topic and its score and asks which visual style to use. The style
     cannot change after you approve.
   - At the script, it writes the [staged script files](#stage_scriptpy), then shows the script,
     both file paths and the estimated ElevenLabs cost. Voicing is the one spend you cannot get
     back, so read the script here.
   - At the video, it tells you where the file is.

   Scripting, voicing, scene writing and rendering run between those stops without you.
5. Watch the video. `mpv` is installed.

   ```bash
   mpv ~/.tubematic-data/output_videos/proj_vqa/<video_id>.mp4
   ```

6. Ask for an AI review, before or after you approve the video, as often as you like:

   ```
   /vqa-review <video_id>
   ```

7. Check on the pipeline with `/tubematic-status` (pipeline status and the video list) and
   `/tubematic-dashboard-status` (whether the containers are running).
8. Repeat from step 4 for the next video. Each video is filed in the one domain, `proj_vqa`.
9. Close the session when you are done. The containers stop with it.

## API keys

The launch hook's log warns about each missing key, and the session still starts. Set the keys
once from a terminal:

```bash
cd ~/tubematic
/opt/tubematic/.venv/bin/python3 vqa/edit_settings.py \
    --set openai_api_key=... \
    --set elevenlabs_api_key=... \
    --set gemini_api_key=...
```

| Key | Used for |
|---|---|
| `openai_api_key` | Scene images, and the characters of the `illustrated` visual style. Without it `/vqa-new-video` lists that style as unavailable, with the reason |
| `elevenlabs_api_key` | Voicing |
| `gemini_api_key` | `/vqa-review` |

## What a new session starts with

`make_seed_db.py` seeds one domain (`proj_vqa`) and these settings. Each other setting has the
pipeline's default.

| Setting | Seeded value |
|---|---|
| `elevenlabs_voices`, `elevenlabs_voice_id` | One voice: ElevenLabs' premade "Rachel" (`21m00Tcm4TlvDq8ikWAM`) on `eleven_multilingual_v2` |
| `gemini_review_enabled` | `false` |
| `image_model` | `gpt-image-2.5-flare` |
| `render_timeout_secs` | `2700` |
| `max_render_retries` | `1` |

Check that your ElevenLabs account can use the seeded voice before the first video. The pipeline
checks the roster and does not ask ElevenLabs, so an unavailable voice fails at voicing with an
ElevenLabs API error. Replace it with `/vqa-settings`.

AI review is seeded off, because the automatic review sends a video with any finding back to
`REVISION_REQUESTED`.

## Utilities

Each utility has a slash command. To run one yourself, use the image's Python environment from
the working tree:

```bash
cd ~/tubematic
/opt/tubematic/.venv/bin/python3 vqa/<script> [arguments]
```

| Script | Slash command | Purpose |
|---|---|---|
| `edit_settings.py` | `/vqa-settings` | Shows and changes pipeline settings |
| `stage_script.py <video_id>` | Part of `/vqa-new-video` | Writes the script as two text files for review before voicing |
| `review_video.py <video_id>` | `/vqa-review <video_id>` | Runs the AI review on a rendered video |
| `reset_db.py --yes [--db-only]` | `/vqa-reset-db` | Returns the session to its first-launch state |

### `edit_settings.py`

```
edit_settings.py                                  # print every setting in effect
edit_settings.py --list image_model               # print the named settings
edit_settings.py --set render_timeout_secs=2700   # change one; repeat --set for more
edit_settings.py --set elevenlabs_voices='[{"name":"Rachel","voice_id":"21m00Tcm4TlvDq8ikWAM","model_id":"eleven_multilingual_v2"}]'
edit_settings.py --help                           # every key with its allowed values
edit_settings.py --restart renderer               # restart a stuck container
```

- A change applies at once. No setting needs a restart, because each process reads the database
  when it needs a value.
- A list-valued key is replaced whole. Read the current value first and pass the full new list.
- Read each `WARNING` line. It means the API accepted the write and the pipeline will use a
  different value. The usual case is a default voice (`elevenlabs_voice_id`) that is not in
  `elevenlabs_voices`: the API reads it as blank and voicing fails with "No default voice set".
  Replacing the roster can cause this too.
- Each voice in `elevenlabs_voices` carries its own `model_id`. There is no install-wide model key.
- The research settings do nothing here, because a session runs no cron and no topic research.
- `--restart` takes `renderer`, `worker`, `api` or `mcp`. `--restart mcp` also needs `--yes`,
  because it disconnects Claude Code from the Tubematic tools.
- Do not edit the database with SQL. The script writes through `POST /settings`, and some checks
  exist only there.

### `stage_script.py`

`/vqa-new-video` runs it at `SCRIPT_READY`, before it asks you to approve voicing. It writes two
files to `~/.tubematic-data/jobs/<video_id>/`:

- `script_with_broll.txt` has each segment's spoken text beside its visual direction.
- `tts_text.txt` has the text that voicing would send to ElevenLabs, with the pronunciation
  lexicon and the `<respell>`, `<ipa>` and phoneme tags applied
  (`mcp/server.py::_build_tts_text`).

`tts_text.txt` is a preview under the current settings. If you change the pronunciation lexicon,
the video's voice or that voice's model after staging, run the script again. The script refuses
`<ipa>` or phoneme tags that the voice's model cannot speak, as voicing would.

### `review_video.py`

It runs the function the pipeline's automatic review runs
(`renderer/api/ai_review.py::run_ai_review`), with the
`ai_review_model` and `ai_review_fps` settings (defaults `gemini-2.5-flash` and `10`). To compare
two reviews, keep both settings the same.

- It prints the feedback and writes it to `~/.tubematic-data/jobs/<video_id>/ai_review.txt`. Each
  run overwrites that file.
- It writes nothing to the database and does not change the video's status, so you can repeat it.
- It can take up to about seven minutes.
- It gives the reviewer the script as written and the text sent to ElevenLabs, so a respelled
  word is not reported as a mispronunciation.

### `reset_db.py`

```
reset_db.py                    # print what it would delete, change nothing
reset_db.py --yes              # reset the database and delete each video's files
reset_db.py --yes --db-only    # reset the database, keep the files
```

A reset cannot be undone. It replaces the database with a new seed: one domain, no videos and the
seeded settings. The API keys are settings, so set them again afterwards. Without `--db-only` it
also empties `jobs/`, `output_videos/` and `scenes/generated/` under `~/.tubematic-data`.
`/vqa-reset-db` asks you to confirm before it runs.

## Troubleshooting

Start with `~/tubematic/vqa/logs/bootstrap.log`. The launch hook logs each step and the reason
for a stop.

| Symptom | What to do |
|---|---|
| No terminal opens at launch | Open one and follow the log. The terminal is a viewer and the session starts without it |
| The log file never appears | Kasm did not run the hook. Check that it exists with `ls -la /dockerstartup/kasm_post_run_user.sh`, then run it with `bash /dockerstartup/kasm_post_run_user.sh` |
| `dockerd did not become ready within 120s` | The workspace is not privileged. See [Register the image in Kasm](#register-the-image-in-kasm) |
| `WARNING: no API key configured for: ...` | [Set the keys](#api-keys) |
| A container `did not become healthy within 300s` | Run `docker compose logs <service>` from `~/tubematic` |
| `no skills found ... but the working tree is marked current` | Run `rm -f ~/tubematic/.vqa-image-id` and launch again. The hook then copies the working tree again |
| `tubematic.db existed before this working-tree refresh and is gone after it` | Stop. The hook refused to seed a new database over a missing one. Find out what removed `~/.tubematic-data/data/tubematic.db` first |
| A utility fails with a permission error under `~/.tubematic-data` | Run `sudo chown -R kasm-user:kasm-user ~/.tubematic-data`. The containers run as root and can leave root-owned files there |
| Claude Code has no Tubematic tools | Look for `claude mcp add-json failed or timed out` in the log. Run the hook again with `bash /dockerstartup/kasm_post_run_user.sh`, then restart Claude Code |
