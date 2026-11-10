# Development

How to work on Tubematic: set up a checkout, run the tests, choose where to verify a change, and
follow the conventions. Release tooling and the CI workflows are in [Releases](18-releases.md).

---

## Setting up a checkout

You need Python 3 with the `venv` module, Node.js 22 and git. CI runs Python 3.12 and Node 22.

```bash
git clone https://github.com/teja156/tubematic.git
cd tubematic
git checkout develop

python3 -m venv .venv
source .venv/bin/activate
pip install pytest pyyaml
pip install -r scripts/requirements.txt
pip install -r mcp/requirements.txt
pip install -r renderer/api/requirements.txt

(cd dashboard && npm ci)
(cd renderer/remotion && npm ci --ignore-scripts)
```

- `pytest` and `pyyaml` are in no requirements file, because nothing needs them at runtime.
  `onboard/tests` and `scripts/tests` import `pyyaml`.
- Install all three requirements files. Several suites import across them: `vqa/tests` needs
  Flask, `httpx` and `fastmcp`, and `mcp/tests` needs `pillow`.
- `--ignore-scripts` keeps the Remotion install from downloading a headless Chromium, which the
  typecheck and the unit tests do not need.

This checkout runs the tests and the typechecks. To run the pipeline itself, see
[Where verification belongs](#where-verification-belongs).

---

## Tests

[The test suite pages](test-suites/README.md) say what each test file guards and which traps it
encodes. The commands:

```bash
python -m pytest tubematic_core/tests
python -m pytest mcp/tests
python -m pytest renderer/api/tests
python -m pytest onboard/tests
python -m pytest scripts/tests
python -m pytest vqa/tests
python -m pytest renderer/remotion/cartoon-tools/audio/tests   # skips without numpy and scipy
```

Run each suite in its own `pytest` invocation. Several suite directories import as a top-level
package named `tests` (`scripts/tests` and `renderer/api/tests` both do), and others share test
file names, so pytest cannot collect two suites in one run. CI runs one suite per job for the
same reason (see [Releases: `ci.yml`](18-releases.md#ciyml-pull-requests-and-pushes)).

Host-side suites cannot import `tubematic_core` on their own. In the containers it is on
`PYTHONPATH` (`/app/lib`), and on the host nothing puts the repository root on `sys.path`.
`renderer/api/tests` and `mcp/tests` each carry a `conftest.py` that adds it. Do not add a
`conftest.py` at the repository root, because it would invite collecting the colliding suites
together.

No test may read or write your real service tokens. `tubematic_core/auth.py` resolves them to
`~/.tubematic-data/secrets/` unless `TUBEMATIC_SECRETS_DIR` is set, and starting the stack creates
any that are missing. `onboard/tests` and `scripts/tests` each have an autouse fixture in their
`conftest.py` that points the variable at a temporary directory. The `scripts/tests` fixture also
puts a token there, because `poll.main()` refuses to run without one. A new suite that reaches
either code path needs the same fixture.

JavaScript, under Node 22:

```bash
cd dashboard
npm test                 # vitest
npx tsc --noEmit
npm run test:e2e         # Playwright, builds the Docker test stack first

cd renderer/remotion
npm test                 # vitest
npx tsc --noEmit         # the whole tree (validate_job checks one video's scenes)
```

The Playwright suite's global setup runs
`docker compose -f docker-compose.test.yml up -d --build --wait` from the repository root. That
build takes several gigabytes, so check free disk first. [The test stack](16-infrastructure.md#the-test-stack)
describes what it starts.

When you change a test, update its page under [test-suites](test-suites/README.md) in the same
commit. Do not put test counts in documentation.

---

## Where verification belongs

| Kind of check | Where | Why |
|---|---|---|
| Unit tests, `tsc`, `vitest`, reading code | Your machine | The result does not depend on the platform |
| Anything that measures text geometry | A container | `system-ui` resolves to a different font outside the container, so pixel numbers measured on the host are wrong |
| A real render | A container | The same font difference, and `--ignore-scripts` leaves no local headless Chromium |
| Onboarding, or bringing up the stack | A disposable environment | Fixed container names and ports collide with an existing stack, and Docker can leave root-owned bind sources behind |

A disposable environment is a virtual machine or a spare machine with Docker, on which you follow
the source install in [Installing](../user-guide/02-installing.md). The two images under
[Test environments](#test-environments) package that for Kasm Workspaces.

A clean typecheck on your machine shows that the tree typechecks. `validate_job` runs `tsc`
against the container's own `node_modules`. The Dockerfile installs from the same lockfile, so the
two agree as long as that install line stays as it is.

---

## Test environments

The repository holds two images for Kasm Workspaces, a platform that streams containerised desktop
sessions to a browser. You need a Kasm Workspaces server to use them. Both build scripts stage the
repository through `git ls-files`, so content that `.gitignore` excludes (`.env`, `node_modules`,
pipeline data) cannot enter an image.

### `kasm_workspace_testing/`: full-install testing

A disposable desktop with Docker-in-Docker. You run `python3 onboard.py` by hand, answer each
prompt as a first-time installer would, and bring up all five containers. Use it to test the
installation itself.

```bash
kasm_workspace_testing/build.sh [tag] [--no-cache] [--worktree <path|branch|dirname>]
```

- Its launch form offers to delete the data directory and the agent workspace. The answer
  defaults to no and cannot be saved, because a remembered "yes" would wipe the data on each
  later launch.
- It does not recreate what it deletes, because Docker would then create those directories as
  root.
- The image makes `/tmp` a mountpoint before `supervisord` starts. Without that, the nested
  Docker daemon mounts an empty tmpfs over `/tmp`, which hides the X socket and the session bus
  and leaves a blank desktop. `kasm_workspace_testing/README.md` describes the patch.

### `vqa/`: video quality assessment

An image for judging rendered output. It has no dashboard, no cron and no wizard: everything
onboarding would ask is in the image or done when the session starts. A session goes from
`/vqa-new-video "<topic>"` to approving the script, to the render, and optionally to
`/vqa-review`.

- Code is built into the image at `/opt` and replaced on each rebuild. The session hook copies it
  with `rsync` to a home directory that persists. The copy is gated on a build stamp, so edits
  made in a session survive a relaunch of the same image.
- Pipeline data lives outside that tree. A check after the `rsync` fails the launch if the
  database existed before the copy and is gone after it.
- AI review is seeded off. The review sends any video with a non-empty suggestions list back to
  `REVISION_REQUESTED`, so with it on, few videos reach `VIDEO_READY` while you iterate on visual
  quality.

Its utilities also work on their own:

| Script | Purpose |
|---|---|
| `vqa/edit_settings.py` | `--list`, `--set KEY=VALUE`, `--restart {renderer,worker,api,mcp}` |
| `vqa/review_video.py <video_id>` | Runs the AI review and writes nothing to the database, so you can repeat it |
| `vqa/stage_script.py <video_id>` | Writes out the script with its visual briefs, and the text that would go to ElevenLabs |
| `vqa/reset_db.py --yes [--db-only]` | Rebuilds a seed database and optionally clears job, output and scene files |

`edit_settings.py` writes through `POST /settings` and uses no direct SQL. Some checks exist only
in that endpoint: the live webhook probe, and the rule that keeps a re-sent masked secret from
overwriting the real key.

### Both build scripts offer worktrees only

`kasm_workspace_testing/build.sh` and `vqa/build.sh` build from a git worktree and do not accept
a bare branch. A worktree is a real checkout, so staging includes untracked and uncommitted work,
which the picker marks. A branch with no worktree could be staged only from its committed tip,
which would drop that work. The chosen tree also supplies the Dockerfile, so an image does not
mix two trees.

- `--worktree` fails on no match and on an ambiguous match, because a fallback would build the
  wrong branch into an image unnoticed.
- A wrapper started from a terminal inherits its TTY and stops at the interactive picker. An
  unattended caller must pass `--worktree`.
- An image holds the tree it was built from, by default the checkout `build.sh` lives in.
  Recreating a session does not rebuild it. To test a feature branch, build with `--worktree`,
  then start a new session.

---

## `kasm_workspace/`: the published workspace

The Kasm workspace that users install Tubematic from. What they see is in
[Installing in Kasm Workspaces](../user-guide/02-installing.md#installing-in-kasm-workspaces).

The image holds no Tubematic source. The launch form picks a version and an install method, and
the session downloads that version. The image is rebuilt only when its base image or tooling
changes, by hand with `kasm_workspace/build.sh --push`. `scripts/tests/test_kasm_workspaces.py`
fails if a `COPY` of the repository appears in its Dockerfile. It shares the testing image's
base, tooling and `/tmp` patch.

A workspace registry entry carries a launch form and no File Mappings, so the launch hook, the
bootstrap and the desktop launcher are all in the image.

The launch hook is `kasm_post_run_root.sh`, which runs as root. It puts itself in the background
and returns at once, waits a bounded time for the desktop, and opens `xfce4-terminal` with
`runuser -u kasm-user`, retrying a few times. The install runs as the session user because
everything it creates (the extracted tree, `~/.tubematic-data`, the onboarding state, the Compose
bind sources) must be owned by that user.

The bootstrap, `kasm_workspace/image/tubematic_bootstrap.py`, uses the standard library only,
because the image has no virtualenv. It prints each message in the terminal the user watches.

- It reads the launch-form answers from `/dockerstartup/tubematic_launch_selections.json`. It
  refuses an unreadable answer, a missing key, or a version that is not a plain `X.Y.Z`.
- It records what it installed in `~/.tubematic-workspace.json`, because a persistent profile is
  relaunched. It reports the same version and leaves it alone. It refuses a different version and
  points to [Upgrading](../user-guide/07-upgrading.md). It refuses Tubematic data that has no
  record of this launcher installing it.
- For a release install, it downloads the tarball and the release's `CHECKSUMS.txt` and checks the
  sha256 before it extracts anything. It refuses an archive with a path outside its own
  `tubematic-v<version>/` directory.
- For a source install, it clones the version's tag.
- It then runs `python3 onboard.py` in the same terminal. The terminal ends in a shell, so an
  error stays on screen.

The bootstrap duplicates the repository name from `tubematic_core.version.GITHUB_REPO`, because
the image has nothing to import it from. A test compares the two.

The registry entry is `kasm_workspace/registry/Tubematic/workspace.json` (registry schema 1.1).

- Each release writes it into the workspace registry with every published release on the form.
  See [Publishing the Kasm registry entry](18-releases.md#publishing-the-kasm-registry-entry).
- The form's version list has no free-text field. It is newest first, and the newest is the
  default. A version missing from the list cannot be installed from the form.
- The list in this repository is a seed. The release job replaces it and copies every other key
  unchanged.
- The entry asks for no GPU (`gpu_count` is 0), because a GPU attached to this desktop makes XFCE
  fail in a loop on an NVIDIA EGL error.

---

## Schema changes

[Database: Rules for a migration](03-database.md#rules-for-a-migration) has the rules a migration
must follow, and [Adding a column](03-database.md#adding-a-column) has the steps for a column.
The checklist for any schema change:

1. Add a new file, `tubematic_core/migrations/NNNN_<name>.sql`, with the next number after those
   in the directory. Do not edit a migration that has shipped. If a shipped migration was wrong,
   write a new one that corrects it.
2. Prefer an additive change. A rename cannot be undone by reverting the code.
3. Update `tubematic_core/tests` in the same change. A column that `0001` creates needs an
   `EXPECTED_*_COLUMNS` entry in `test_baseline.py`. A new migration gets its own assertion, and a
   fixture-backed test when an older database must converge through it. See
   [Tests: `tubematic_core`](test-suites/tubematic-core.md).
4. Run `python -m pytest tubematic_core/tests`.
5. Update every consumer of an externally visible change, listed below.

| Change | Also update |
|---|---|
| An MCP tool or an HTTP field | `mcp/server.py` or `renderer/api/pipeline.py`, and `dashboard/lib/types.ts` |
| A new setting | Its `SETTINGS_SPEC` entry and coercion branch, the dashboard's `Settings` type and a tab in `dashboard/app/settings/page.tsx`, and an `onboard/config.py` `Field` if onboarding should ask. See [Adding a setting](04-settings.md#adding-a-setting) |
| A new video status | The list below |

A new video status needs:

- `VALID_VIDEO_STATUSES` and `WORKABLE_STATUSES` in both `renderer/api/pipeline.py` and
  `mcp/server.py`, and the copy in `dashboard/lib/types.ts`,
- the state diagram in [The Pipeline](02-pipeline.md#the-states),
- every place that branches on status: the worker's and the render gateway's transitions
  (`render_results.py`), the poller's workable-video query, and any skill or slash command that
  names statuses.

---

## Conventions

- Documentation is part of the change. See [Keeping the docs true](#keeping-the-docs-true).
- MCP docstrings own technical contracts, and skills own workflow. A skill does not restate a
  tool's parameter signature.
- Agent-visible text carries no ticket identifiers. A model reads skills, slash commands and
  `@mcp.tool` docstrings and cannot look an identifier up. Internal comments may carry them.
- Agent behaviour belongs in skills, and documentation in `docs/`.
- Duplication across processes is intended. See
  [Architecture: Duplication](01-architecture.md#duplication-is-intentional). Before you change a
  constant, `grep` for its value as well as its name, because several settings defaults are
  repeated without a keep-in-sync comment.
- A schema change is a new migration file. See [Schema changes](#schema-changes).
- Send credentials as headers. Client libraries put the request URL in exception strings, and
  the pipeline stores error text in a table the dashboard shows.

---

## Working on a branch

Use a git worktree so that parallel work does not interfere:

```bash
git worktree add .worktrees/my-feature -b my-feature develop
```

`.worktrees/` is gitignored, and both Kasm build scripts can build an image from any worktree.

Give each agent session its own worktree. Two sessions that commit in one checkout can rewrite
each other's history: one session's `git commit --amend` can absorb the other's commit while
`git status` reads clean. If two sessions must share a checkout, commit with explicit pathspecs
and compare against `HEAD` afterwards.

`node_modules` is gitignored in `dashboard/` and `renderer/remotion/`, so a new worktree has
none. Symlink them from the main checkout to run the JavaScript suites without a second install.

---

## Keeping the docs true

`docs/` is public. Its readers have not seen the code or the project's history. A change that
touches behaviour is finished when the docs describe the new behaviour, on every page that mentions
it.

### What to update

When you add, change or remove one of these, search `docs/` for its name and fix every page that
mentions it:

- an MCP tool or its parameters,
- an HTTP route, its request body, its response or its status codes,
- a settings key, its type or its default,
- a status or a transition,
- a database table, column or migration,
- an installed component or the shape of `scene-config.json`,
- a skill, a slash command, or an onboarding step or question,
- a Compose service, volume, port or image.

A change often makes a sentence on a neighbouring page false. The tool count in
[MCP Server](06-mcp-server.md) is one example: a test compares it with the code.

### Facts

- Cite code by symbol, such as `pipeline.py::patch_video`. Do not cite line numbers.
- Give no test counts, suite totals or dates.
- Every path, route, tool name and settings key in the docs must exist in the code. Check with
  `grep`.
- Use no ticket identifiers, host paths, user names or credentials, including in examples.
- Link only to pages under `docs/`. The release tarball ships `docs/README.md`,
  `docs/quickstart.md`, `docs/release-notes.md`, `docs/user-guide/`, `docs/developer/` and
  `docs/images/`, and its build fails on a link from one of those to anything else.
- Draw diagrams as `mermaid` code fences. Put screenshots in `docs/images/` and link them with a
  relative path.

### Where things go

- `docs/user-guide/` says what a person running Tubematic does and sees. It uses the labels on the
  dashboard.
- `docs/developer/` says how Tubematic works and how to change it. It uses the names in the code.
- Each explanation has one page that owns it. Other pages give one sentence and a link.
- Pages are numbered inside their folder. A new page takes the next number and needs a row in
  `docs/README.md`.
- Version history belongs in the [release notes](../release-notes.md). Other pages describe
  Tubematic as it is now.

### Writing

- Address the reader as "you", in the active voice. Software can be the subject of what software
  does: "the wizard asks", "the API returns `409`".
- Give one instruction per sentence, with its condition first.
- State what something is. Avoid defining it by what it is not.
- Use "never", "always" and "every" only where the code enforces the claim.
- When a design looks wrong, give its reason in one sentence beside it. Leave out the story of how
  the reason was found.
- Use bold for the names of on-screen controls. Do not open a paragraph with a bold sentence.
- Use full stops, commas and colons. Do not use em dashes.
- Leave out words that add emphasis and no meaning: "simply", "actually", "exactly", "silently",
  "deliberately", "on purpose", "by design".
- Keep a table cell to a phrase or a sentence or two. Put anything longer under a heading.
- Write host commands with `python3`, run from the install directory.

---

## Contributing

The project is licensed under Apache-2.0 (`LICENSE`). Open pull requests against `develop`.
Report a bug through the repository's issue form, with the redacted report that
`scripts/collect_diagnostics.py` writes (see
[Reporting a bug](../user-guide/08-troubleshooting.md#reporting-a-bug)).

Two small first contributions:

- Register a JSON error handler, so that an unhandled exception stops returning HTML. See
  [HTTP API: Known quirks](05-http-api.md#known-quirks), which lists other candidates.
- Fix the two eslint errors in the Remotion project, which keep `npm run lint` out of CI.

Before you open a pull request:

1. The relevant Python suites pass, one directory at a time.
2. `npx tsc --noEmit` passes in both `dashboard/` and `renderer/remotion/`.
3. `npm test` passes in `dashboard/` and `renderer/remotion/`.
4. `docs/` reflects the change, and nothing it says has become false.

CI runs the Python suites, the dashboard's unit tests and build, and the Remotion typecheck on
the pull request. See [Releases: Continuous Integration](18-releases.md#continuous-integration).
