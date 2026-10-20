# VQA — Video Quality Assessment environment (TMDEV-68)

A purpose-built Kasm Workspaces session for assessing Tubematic video quality without standing up
the whole product: no dashboard, no cron, no `onboard.py` wizard. Open the session, run
`/vqa-new-video "<topic>"`, watch the pipeline advance in chat, get a rendered mp4, ask for an
on-demand AI review whenever you want one.

Base image: `kasmweb/ubuntu-noble-dind:1.19.0-rolling-daily` (root-mode Docker-in-Docker) — same
base as [`kasm_workspace_testing/`](../kasm_workspace_testing/README.md), the existing full-onboarding testing
environment. This is a sibling image with a different purpose, not a replacement for it.

## Building the image

```bash
cd vqa
./build.sh            # builds tubematic/tubematic-vqa-env:latest
./build.sh 1.0.0       # custom tag
./build.sh --no-cache  # force a clean rebuild
./build.sh --worktree worktree-vqa-9  # skip the prompt, name the source tree
```

`build.sh` first asks **which git worktree to build into the image**, listing each one with its
branch, HEAD, path, and an `*uncommitted` marker (uncommitted work is baked in and can't be
recovered from the tag afterwards). Enter accepts the default — the worktree the script itself
lives in. Everything comes from the chosen tree: the source, `dockerfile_tubematic_vqa`, and the
startup hooks it copies in, so the image is genuinely that branch rather than a mix of two.

`--worktree <path|branch|dirname>` picks non-interactively, and errors rather than guessing if the
value matches nothing or more than one worktree. With no TTY the prompt is skipped and the
script's own worktree is used, so existing scripted `./build.sh <tag>` calls are unaffected. A
wrapper run from a terminal *does* inherit a TTY and will stop at the prompt, so pass
`--worktree <path>` from any wrapper that must run unattended.

Branches without a worktree are deliberately **not** offered — they could only be staged from
their committed tip, silently dropping uncommitted work. `git worktree add` one first.

Same git-filtered staging as `kasm_workspace_testing/build.sh`: `git ls-files --cached --others
--exclude-standard` decides what enters the build context, so `.env`, `mounted/`, `.venv`,
`vqa/logs/`, and `vqa/seed/` never reach the image regardless of what's sitting in your working
tree when you build.

## What's baked in vs. generated at session start

Everything a human normally answers during `onboard.py` is either baked into the image at build
time or generated automatically by `vqa/kasm_post_run_user.sh` the moment a session launches —
there is no wizard to run and **`onboard.py` must never be run inside this environment** (it would
re-prompt for everything already handled here, and its `install_config` step would overwrite the
settings this bootstrap seeds).

| Baked into the image (`vqa/dockerfile_tubematic_vqa`) | Generated at session start (`vqa/kasm_post_run_user.sh`) |
|---|---|
| Source, Node 22, Claude Code CLI | Working tree refreshed from the image |
| `.venv` (for the `vqa/*.py` utilities) | Claude Code skills/commands/MCP registration |
| Seed DB (`vqa/make_seed_db.py`, at build time) | `mounted/` directories created |
| `remotion-dev/skills` pre-fetched | DB seeded (only if not already present) |
| — | `tubematic-api` + `tubematic-mcp` + `tubematic-renderer` built and started |

## The code/state split — why two directories

Everything a human cares about losing — rendered mp4s, the pipeline DB, job files, generated
scenes, and Claude Code's own login — must survive session teardown. Kasm's persistent-profile
mechanism only covers `$HOME` (`/home/kasm-user`), so all of that has to live there. But a
persistent profile also **shadows** Kasm's normal profile-seeding: once something exists in a
persisted `$HOME`, rebuilding the image never refreshes it. Staging the whole repo into `$HOME`
would freeze the code at whichever version happened to be there on first launch, forever.

So the two concerns are split, and `vqa/kasm_post_run_user.sh` reconciles them on every launch:

| | Lives at | Owned by | Refreshed |
|---|---|---|---|
| Source, `.venv`, seed DB, remotion skills | `/opt/tubematic` | the image | every image rebuild |
| Working tree (where `docker compose` runs) | `~/tubematic` | the persistent profile | rsync'd from `/opt` when the image changes |
| `mounted/` — DB, jobs, scenes, **rendered mp4s** | `~/tubematic/mounted` | the persistent profile | **never touched by bootstrap** |
| Claude Code config + skills | `~/.claude*` | the persistent profile | `skills/`+`commands/` wiped and re-copied every launch |

`docker compose` is invoked from `~/tubematic`, so every bind mount (`${PWD}/mounted/...`) lands
inside the persisted tree with no compose-file changes needed. API keys live in the settings
table inside that same `mounted/` tree, so they persist too. Rendered
videos end up at `~/tubematic/mounted/output_videos/proj_vqa/<video_id>.mp4` and stay there across
relaunches.

**A hand-edit under `~/tubematic` survives a relaunch of the same image, but is overwritten by the
next image rebuild.** If you need a change to persist, make it in the repo and rebuild — don't
patch the working tree directly.

### Deleted and renamed skills/commands

The working-tree rsync runs without `--delete` — that is deliberate, and it is what keeps
`mounted/` safe. The side effect is that a file *removed* from the repo would never be removed
from an already-persisted working tree, so a deleted skill would linger forever and a renamed one
would leave both copies live and visible to the agent.

Three directories are therefore treated as wholly image-owned and cleared before being
repopulated, so they track the image exactly rather than accumulating:

- `~/tubematic/agent_files/skills`, `~/tubematic/agent_files/claude/commands`, and
  `~/tubematic/vqa/agent/commands` — deleted immediately before the rsync, on the refresh path
  only (i.e. only when the image stamp changed).
- `~/.claude/skills` and `~/.claude/commands` — deleted at the start of the Claude Code config
  step, on **every** launch, then repopulated from the working tree and from
  `/opt/tubematic/vqa/skills-cache`.

In both cases the removal happens *before* the copy that repopulates them, in the same single
pass of `kasm_post_run_user.sh` — a launch never ends with them missing. The two have different
triggers, though (every launch vs. only on an image change), so the `~/.claude` wipe is guarded:
if the working tree's skills are missing while its stamp claims to be current, bootstrap stops
with instructions rather than clearing `~/.claude/skills` and leaving the session with none. Consequence worth
knowing: a skill or command hand-installed into `~/.claude` inside a session will **not** survive
a relaunch. Put it in the repo and rebuild.

## How this actually starts — two Kasm hooks, not supervisord

`kasm_post_run_user.sh` (the reconciliation script above) runs because it overwrites
`/dockerstartup/kasm_post_run_user.sh` — one of the base image's own stub hooks, invoked
automatically by the Kasm platform as `kasm-user` after session start, independent of anything
else in the container's boot chain. It's what actually does everything in the table above: refresh
the working tree, refresh Claude Code's skills/commands/MCP registration, create `mounted/`, create
any missing service token (`python3 -m tubematic_core.auth ensure`), seed the DB, and bring up
`tubematic-api`/`tubematic-mcp`/`tubematic-renderer`. The MCP registration is redone on every launch
rather than skipped when present: the server needs its token, which Claude Code fetches through
`scripts/mcp_auth_header.py`, and a registration persisted from an older image has no such helper.
The VQA stack runs no dashboard, so it needs no dashboard password.

The one other file this image overwrites is `$STARTUPDIR/custom_startup.sh` — the script that
launches `supervisord` (and thus `dockerd`) in the first place. **`kasm_workspace_testing/`, this repo's
other Kasm image, deliberately never touches this file**, after an earlier attempt in this repo's
history (`00099ff`/`a69cd1c`/`7abf2d0`) edited it, hit a race, and was reverted — that incident came
from inserting logic *inside* the process-supervision while-loop the file runs (auto-launching
`onboard.py`, re-entering on every loop iteration until `supervisord` became visible to `pgrep`).
This image's own addition (auto-opening a terminal that tails the bootstrap log, via
`vqa/watch_bootstrap.sh`) is deliberately kept *outside* that loop and backgrounded, so it can only
ever run once and never interacts with the loop's own `supervisord`-launch retry logic — see
`vqa/custom_startup.sh`'s header comment for the exact, verified diff against the base image's
original. If you ever need to touch this file again, diff it against a fresh pull of
`kasmweb/ubuntu-noble-dind:1.19.0-rolling-daily` first; getting it wrong disables Docker-in-Docker
entirely.

## Registering the image as a Kasm workspace (manual — not automated by `build.sh`)

- **Persistent Profile Path — mandatory.** This is what makes the whole design above work.
  Without it, every session starts from scratch: rendered videos, the pipeline DB, and Claude
  Code's own credentials are all lost at teardown, and you'll be asked to log in to Claude Code on
  every single launch.
- **Docker Run Config Override `{"privileged": true}` — mandatory.** This base image is root-mode
  DinD; the rootless variant was abandoned after a kernel-level `newuidmap: write to uid_map
  failed: Operation not permitted` on this host's Ubuntu 24.04 + AppArmor combination — see
  `kasm_workspace_testing/README.md` for the full story, which applies identically here.
- **No File Mapping is needed.** API keys used to arrive as a mapped `.env`; they now live in the
  settings table, which sits in the persistent profile — so you enter them once, in the session,
  and they survive every relaunch.
- **Sizing:** at least 4 cores / 8 GB. The renderer needs `shm_size: 2gb` for Chromium on top of
  the Node/Python/ffmpeg footprint of two containers.
- **Nested container images are not persisted.** Every session rebuild rebuilds
  `tubematic-renderer-image` from scratch (Remotion + Chromium — the slowest layer). If launches
  feel slow, a Kasm Volume Mapping for `/var/lib/docker` is a later upgrade path that would let
  images survive teardown too; it's deliberately not part of this design (see the design decisions
  in `docs/infrastructure.md`'s VQA section for why).

## Using the environment, step by step

Once the workspace is registered (above) and you launch a session:

1. **Wait for bootstrap to finish.** A terminal window opens automatically on session start
   (`vqa/watch_bootstrap.sh`, launched from `vqa/custom_startup.sh` — see "How this actually
   starts" above) once `~/tubematic/vqa/logs/bootstrap.log` exists, and tails it live — no need to
   go find a terminal or the log yourself. It just tails (`Ctrl+C` to stop, or close the window);
   it doesn't detect completion or hand off to a shell on its own. If that window doesn't appear
   for any reason, open one manually (right-click the desktop → Open Terminal, or the
   Files/Applications menu) and tail the same file:

   ```bash
   tail -f ~/tubematic/vqa/logs/bootstrap.log   # ends with "=== VQA environment ready ==="
   ```

   First launch of a given image build is the slowest — `tubematic-renderer-image` builds from
   scratch (Remotion + Chromium). Later relaunches of the *same* image are much faster since
   `kasm_post_run_user.sh` skips the working-tree refresh (see the code/state split above), though
   the nested container image itself is never persisted (see Registering, above), so every launch
   still rebuilds it.

2. **Open Claude Code from `~/tubematic`.** This is the working tree `kasm_post_run_user.sh` set
   up — it's where the MCP server is registered against and where `mounted/` lives.

   ```bash
   cd ~/tubematic
   claude
   ```

3. **Create and drive a video with `/vqa-new-video`:**

   ```
   /vqa-new-video "how binary search works"
   ```

   This runs the tubematic-operator skill with VQA's chat-based checkpoints (no dashboard exists
   here — see "Human checkpoints, without a dashboard" below). Expect to be asked to approve three
   times in the conversation:
   - **Topic approval** — right after the video is created.
   - **Script approval** — before asking, the agent stages the script as two plain-text files
     under `~/tubematic/mounted/jobs/<video_id>/` (see "Staged script + b-roll, as plain text"
     below) and shows you both paths, alongside the script itself and the estimated ElevenLabs
     character cost. This is the one non-refundable spend in the flow, and the only point where
     you're looking at the script/b-roll plan *before* money is spent voicing it.
   - **Video approval** — after rendering completes, once you've seen where the file landed.

   Everything in between (scripting, voicing, scene authoring, rendering) happens automatically;
   you only need to respond at those three points.

4. **Watch the rendered video.** Once the video reaches `VIDEO_READY`, the file is at:

   ```
   ~/tubematic/mounted/output_videos/proj_vqa/<video_id>.mp4
   ```

   Open it with `mpv <path>` from a terminal, or double-click it in a file manager.

5. **Ask for an AI review whenever you want one** — before or after approving the video, any
   number of times:

   ```
   /vqa-review <video_id>
   ```

   This can take a few minutes (see "AI review: on-demand, not automatic" below). It only prints a
   critique in the conversation — it never changes the video's status or blocks you from doing
   anything else while you wait.

6. **Check on things without starting a new video:**

   ```
   /tubematic-status             # pipeline status + video counts + total spend
   /tubematic-dashboard-status   # container health (docker compose ps, /health)
   ```

7. **Repeat from step 3 for the next video.** Every video files into the same `proj_vqa` project;
   there's no domain-matching step to think about.

8. **When you're done, just close the session.** Nothing to shut down manually —
   `tubematic-api`/`tubematic-mcp`/`tubematic-renderer` stop with the container. Anything under `~/tubematic`
   (rendered videos, the DB, Claude Code's login) is there again on your next launch, as long as
   the workspace has a Persistent Profile Path configured (see Registering, above).

## Required API keys (first launch)

Keys are stored in the settings table, not a file. The bootstrap log warns if any is missing
and the session still comes up — a keyless box is still useful for staging scripts and DB
inspection. Set them once from a terminal in the session:

```bash
cd ~/tubematic
python3 vqa/edit_settings.py \\
    --set gemini_api_key=... \\
    --set elevenlabs_api_key=... \\
    --set openai_api_key=...
```

They live under `~/tubematic/mounted/`, so the persistent profile keeps them across relaunches.
`openai_api_key` draws every scene image and the `illustrated` style's characters — without it
`generate_image` fails and `/vqa-new-video` does not offer that style. `gemini_api_key` is for
on-demand review here.

The output-video path is left at its default (`${PWD}/mounted/output_videos`, inside the
persisted tree) — pointing it outside `$HOME` would defeat persistence: videos would render
successfully and disappear at teardown.

## Seeded voice

The seed DB's default voice roster is ElevenLabs' standard premade "Rachel" voice
(`21m00Tcm4TlvDq8ikWAM`, on `eleven_multilingual_v2`) — a real, publicly documented preset ID, not a placeholder that needs
editing before `generate_voice` will work. **Confirm it's actually available on the account tied
to `ELEVENLABS_API_KEY`** before the first `/vqa-new-video` run: `generate_voice`'s pre-spend guard
only checks that the chosen `voice_id` is present in `settings.elevenlabs_voices` (the roster
itself), not that ElevenLabs' API will actually accept it — an unavailable premade voice on a
given plan surfaces as an opaque ElevenLabs API error on the first voicing attempt, not a clear
config message. Swap it with `/vqa-settings` (see [Changing settings](#changing-settings)) if
needed.

## AI review: on-demand, not automatic

The seed DB sets `gemini_review_enabled=false`, so a render lands straight at `VIDEO_READY`
instead of looping through the worker's automatic post-render review. This is deliberate, not a
gap: that automatic path bounces a video to `REVISION_REQUESTED` on *any* non-empty `suggestions`
list. VQA-7 removed the prompt's "expect at least one suggestion on nearly every review" quota,
which makes that far less likely than it was — but the routing rule itself is unchanged, so leaving
the automatic review on here would still risk unwanted revision loops.

Instead, review is a script you run when you want one: `/vqa-review <video_id>` (which runs
`vqa/review_video.py` — see its docstring). It calls the exact same `run_ai_review()` the worker
uses, but writes nothing to the DB — no `gemini_feedback`, no `ai_review_count`, no status change
— so re-reviewing the same video any number of times is free of side effects. A review can take up
to ~7 minutes worst case (Gemini's upload-processing poll is bounded at 60 × 5s, plus up to 120s
for the review call itself).

The review is handed the video's script in both forms — the authored wording (`videos.script`,
what the captions show) and the exact text sent to ElevenLabs (`videos.tts_text`, with `<respell>`
tags and lexicon terms substituted in, and any `<ipa>` tag written as its `"/IPA/"` form) — so its `mispronunciation` check has ground truth for what
was meant to be said, and a deliberate respelling isn't reported as a defect. A video voiced before
that column existed has no `tts_text` and falls back to the authored script alone.

`review_video.py` also reads `ai_review_model` and `ai_review_fps` from the settings table and
passes them through, so `/vqa-review` reviews on exactly the configuration the pipeline would use.
This matters more here than anywhere else: this script is the only way to evaluate a change to the
review prompt at all, and it can only do that if the sampling rate and model are held fixed across
a before/after pair. Change either with `/vqa-settings` (e.g.
`edit_settings.py --set ai_review_fps=1`) and note that **the default is 10** — comparing a run
made before a prompt change against one made after it, without pinning the rate, moves two
variables at once. Keys absent from the seed DB fall back to the same defaults the worker uses
(`gemini-2.5-flash`, 10 fps).

The feedback is shown in chat and also written to
`~/tubematic/mounted/jobs/<video_id>/ai_review.txt` by default (overwritten on each re-run, same
convention as the staged script files below) — the agent reports that path once the review lands,
so you can reopen it later without re-running anything.

## Staged script + b-roll, as plain text

`/vqa-new-video` stages the script at the `SCRIPT_READY` checkpoint — **before** asking you to
approve voicing, not after — by running `vqa/stage_script.py <video_id>`, which writes two files
to `~/tubematic/mounted/jobs/<video_id>/`. Open either directly, no MCP tool call or DB query
needed:

- **`script_with_broll.txt`** — every segment's spoken text next to its visual/b-roll direction,
  straight from `videos.script_segments`. This is the plan; the rendered video is what it actually
  produced.
- **`tts_text.txt`** — the text that would actually be sent to ElevenLabs: segments joined, then
  the same phoneme-tag/`<respell>`/`<ipa>`/pronunciation-lexicon processing `generate_voice()`
  applies — calling its `_build_tts_text` directly from `mcp/server.py` rather than a second,
  drift-prone copy of that logic. A script with `<ipa>` tags on a model other than `eleven_v3` is
  refused here, exactly as `generate_voice` would refuse it.

Staging only needs `videos.script_segments` to exist, not an actual ElevenLabs call — which is
exactly why this can happen at `SCRIPT_READY`, ahead of the spend, rather than after voicing.
**`tts_text.txt` is therefore a preview of what generate_voice() would send under the *current*
settings, not a captured copy of literal bytes already sent.** It can only go stale if
`settings.pronunciation_lexicon`, the video's voice, or that voice's model change between staging and
the actual voicing call — if you edit the lexicon mid-review, re-run the staging command (part of the
`SCRIPT_READY` checkpoint in `vqa/agent/commands/vqa-new-video.md`) before trusting the file again.

If a revision loop rewrites the script later, `/vqa-new-video`'s own checkpoint instructions call
for re-staging after the fix — there's no separate command for this, it's folded into the normal
script-approval flow.

## Changing settings

This environment has no dashboard and no `onboard.py` wizard, so `/vqa-settings` (or directly:
`/opt/tubematic/.venv/bin/python ~/tubematic/vqa/edit_settings.py`) is how a pipeline setting gets
changed here. With no arguments it prints every effective setting; `--set key=value` (repeatable)
changes them:

```
edit_settings.py                                  # print every effective setting
edit_settings.py --list image_model               # print selected settings
edit_settings.py --set render_timeout_secs=2700
edit_settings.py --set image_model=gpt-image-2.5-sunburst
edit_settings.py --set elevenlabs_voices='[{"name":"Rachel","voice_id":"21m00Tcm4TlvDq8ikWAM","model_id":"eleven_multilingual_v2"}]'
```

Values pass through as raw strings — the API's `_coerce_setting` already accepts `"true"`/`"1800"`
and JSON text for the list-valued keys, so the script owns no type table of its own to drift out of
sync with `SETTINGS_SPEC`. Editing a list-valued key **replaces the whole list**; read the current
value first and pass the full new one.

`--help` prints every settable key with its allowed values — the real model catalogs, roster cap
and timeout floor, read off `renderer/api/pipeline.py` at display time rather than written out in
the script, so the help can't drift from what `POST /settings` will accept. It also flags the six
research/cron settings that exist in `SETTINGS_SPEC` but do nothing here, and notes that the
defaults it shows are the pipeline's shipped ones, which `vqa/make_seed_db.py` seeds over in
places — run with no arguments for the values actually in effect.

**Writes go over HTTP to `POST /settings`, never straight to SQLite.** That endpoint is the
canonical write path: some checks live *only* there — the live webhook probe, and keeping a re-sent
masked secret from overwriting the real key — so a direct-SQL edit reusing `_coerce_setting` would
skip them.

**No setting needs a restart to take effect.** Every reader queries the database live at use time —
`renderer/api/worker.py::_setting`, `mcp/server.py::_get_setting` and
`renderer/api/pipeline.py::_read_all_settings` are each called per-use, with no module-level reads
and no in-process cache — so a write applies to the very next read. `--restart renderer` exists for
a genuinely wedged render worker and nothing else. `--restart mcp` bounces the MCP server on port
4100, dropping the Claude Code session's connection and every Tubematic tool with it, so it
requires an explicit `--yes`; `--restart api` bounces Flask alone and needs no confirmation, since
the two are separate containers.

**Watch for `WARNING` lines.** A `200` from `POST /settings` does not mean every value took.
`post_settings` responds with the *effective* settings (`_read_all_settings`), and the script diffs
that against both what was asked for and what was in place beforehand. The case this exists for:
the default-voice invariant is enforced on read, not by rejecting the write — an
`elevenlabs_voice_id` naming no entry in `elevenlabs_voices` is stored happily and then blanked, so
the write looks successful and the next `generate_voice` dies with "No default voice set".

That invariant breaks from either side, which is why the diff covers unrequested keys too:
**replacing the roster orphans the current default voice** even though the request never mentioned
`elevenlabs_voice_id` — and swapping a voice is the most likely roster edit there is. Growing the
roster while keeping the default, or changing a voice's model, are not warned about.

There is no install-wide ElevenLabs model: every entry in `elevenlabs_voices` carries its own
`model_id`, and a video's pronunciation mode (`"ipa"` for `eleven_v3`, `"phoneme"` for the
phoneme-compatible models, else `"respell"`) follows its voice's model. `elevenlabs_model_id` and
`pronunciation_mode` are unknown keys to `POST /settings`.

## Resetting the environment

`/vqa-reset-db` (or directly: `/opt/tubematic/.venv/bin/python ~/tubematic/vqa/reset_db.py --yes`)
wipes the pipeline database and reseeds it from scratch — back to exactly the first-launch state:
one `proj_vqa` project, no videos, the default settings from `vqa/make_seed_db.py`. By default it
also clears every file a video could have left behind (`mounted/jobs/`, `mounted/output_videos/`,
`mounted/scenes/generated/`), since a DB-only reset would otherwise leave those as orphaned disk
usage with nothing left pointing at them. Pass `--db-only` to keep existing renders and reset just
the database.

**Destructive and irreversible — there is no undo.** Requires `--yes`; running it with no flags
prints what it would delete and changes nothing, which is also what running `/vqa-reset-db`
without confirming first should stop at — the command's own instructions require an explicit yes
from you before it ever passes `--yes`.

## Human checkpoints, without a dashboard

The pipeline's three human checkpoints (`TOPIC_PROPOSED`, `SCRIPT_READY`, `VIDEO_READY`) normally
need dashboard approval. Here, `/vqa-new-video` carries a fork of the operator skill's guidance
that stops in chat at each one instead — see `vqa/agent/commands/vqa-new-video.md`. The
`SCRIPT_READY` checkpoint stages the script/b-roll files (see above) and states the estimated
ElevenLabs cost before asking, since that spend is non-refundable.

## Troubleshooting

- Bootstrap log: `~/tubematic/vqa/logs/bootstrap.log` — every step it takes is logged there,
  including which failure caused it to stop.
- If bootstrap never seems to run at all (no log file ever appears, `/vqa-new-video` fails because
  nothing's registered), check whether `/dockerstartup/kasm_post_run_user.sh` actually exists and
  is executable inside the session (`ls -la /dockerstartup/kasm_post_run_user.sh`) — if the Kasm
  platform never invokes this hook for some deployment-specific reason, nothing here runs
  automatically, and the only diagnostic signal is its absence rather than a failure in it. Run it
  manually (`bash /dockerstartup/kasm_post_run_user.sh`) to confirm the script itself works when
  invoked directly.
- If bootstrap fails waiting for `dockerd`, that's almost certainly the workspace not being
  launched with `"privileged": true` (see above).
- If the bootstrap log warns that no API key is configured, set them with `vqa/edit_settings.py`
  as shown above. This is a warning, not a failure — the stack still comes up.
- If no terminal window auto-opens on launch, that's `vqa/watch_bootstrap.sh` (launched from
  `vqa/custom_startup.sh`) either never running or failing to reach the display — it has no effect
  on whether the environment actually comes up, just on whether you see it happen. Open a terminal
  manually and tail the log the same way either way.
- If bootstrap fails with `mounted/data/tubematic.db existed before this working-tree refresh and
  is gone after it` — stop and investigate before doing anything else with `mounted/` in this
  session. This is a deliberate, fail-loud guard (not a normal failure mode) that only fires if
  the working-tree refresh's protection for persisted data has somehow broken; see the code/state
  split section above for what that protection is supposed to guarantee.
- If `vqa/stage_script.py` or `vqa/review_video.py` fails with a plain permission error trying to
  create a file/directory under `mounted/`, that shouldn't happen — `kasm_post_run_user.sh`'s
  step 6 self-heals `mounted/`'s ownership to `kasm-user` on every launch specifically because
  `tubematic-api`/`tubematic-renderer` run as root inside their containers, and either the
  container or dockerd's own bind-mount auto-create can leave content under `mounted/` root-owned
  on the host (invisible to the containers themselves, since root bypasses permission checks, but
  not to these host-side scripts). If you hit this anyway, it likely means that self-heal step
  didn't run or failed silently on this launch — check the bootstrap log around `mounted/
  directories ready`, and as an immediate workaround: `sudo chown -R kasm-user:kasm-user
  ~/tubematic/mounted`.

## Local (non-Kasm) alternative

None — this environment's whole point is a disposable, pre-configured Kasm session. For local
development against a real checkout, use the normal `onboard.py` flow at the repo root, or
`kasm_workspace_testing/` for a Kasm session with the full onboarding wizard still in the loop.
