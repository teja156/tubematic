# Development

How to work on Tubematic: run the tests, understand the conventions, and know which environment a
given kind of verification actually belongs in.

---

## Tests

Full per-suite documentation lives in **[docs/developer/test-suites/](test-suites/README.md)** — what every test file
guards, how to run each suite, and the traps each one encodes. The commands below are the short
version.

```bash
python -m pytest tubematic_core/tests
python -m pytest mcp/tests
python -m pytest renderer/api/tests
python -m pytest onboard/tests
python -m pytest scripts/tests
python -m pytest vqa/tests
```

> **Run `scripts/tests` and `renderer/api/tests` separately.** Neither parent directory has an
> `__init__.py`, so pytest's default import mode treats each `tests/` subdirectory as a top-level
> package literally named `tests`. Whichever is collected first wins the name, and the second fails
> to import. Other combinations are fine — `onboard/` has an `__init__.py` and `mcp/tests` has none,
> so neither collides. `tubematic_core/tests` deliberately has no `__init__.py` for the same reason.

Host-side suites cannot import `tubematic_core` on their own: in the containers it arrives on
`PYTHONPATH` (`/app/lib`), and nothing puts the repo root on `sys.path` here. `renderer/api/tests`
and `mcp/tests` each carry a `conftest.py` that does it per-suite. A repo-root `conftest.py` would be
the obvious-looking alternative and is the wrong one — it invites collecting the colliding suites
together.

`pytest` is not installed by `scripts/requirements.txt` or by the wizard's bootstrap. Install it
yourself.

**No test may read or write your real service tokens.** `tubematic_core/auth.py` resolves them to
`~/.tubematic-data/secrets/` unless `TUBEMATIC_SECRETS_DIR` says otherwise, and starting the stack
creates any that are missing — so `onboard/tests` and `scripts/tests` each have an autouse fixture in
their `conftest.py` that points the variable at a temporary directory (the scripts one also puts a
token there, because `poll.main()` refuses to run without one). A new suite that reaches either
code path needs the same fixture.

JavaScript:

```bash
cd dashboard
npm test                 # vitest
npx tsc --noEmit
npm run test:e2e         # Playwright — builds the Docker test stack first

cd renderer/remotion
npx tsc --noEmit         # exactly what validate_job runs
```

The Playwright suite's global setup runs `docker compose -f docker-compose.test.yml up -d --build
--wait` from the repo root. That is a multi-gigabyte build — check free disk first.

**Do not put test counts in documentation.** They are stale on the next commit. Run the suite.

**When you change a test, update its page in [docs/developer/test-suites/](test-suites/README.md) in the same commit.**

---

## Where verification belongs

This distinction matters more than it looks, and getting it wrong produces confident, wrong results.

| Kind of check | Where | Why |
|---|---|---|
| Unit tests, `tsc`, `vitest`, reading code | Your machine | Platform-independent |
| Anything measuring **text geometry** | **A container** | `system-ui` resolves to a different font face outside the container. Host-measured pixel numbers are fiction |
| A real render | **A container** | Same font problem, plus `--ignore-scripts` means no local headless Chromium |
| Onboarding, or bringing up the stack | **A disposable environment** | Fixed container names and ports collide with an existing stack, and Docker leaves root-owned bind sources behind |

A clean typecheck on your machine proves the *tree* typechecks. `validate_job` runs `tsc` against the
container's own `node_modules`; the Dockerfile installs from the same lockfile, so the two agree
today — but if that install line changes, the local result stops transferring.

---

## Test environments

Two Kasm Workspaces images, both built by a script that stages the repository through
`git ls-files`, so `.gitignore`d content — `.env`, `node_modules`, pipeline data — can never enter an
image without maintaining a second exclude list.

### `kasm_workspace_testing/` — full-install testing

A disposable browser-accessible desktop running Docker-in-Docker, where you run
`python3 onboard.py` by hand and answer every prompt exactly as a first-time installer would, then
bring up all four containers. This is how the *installation experience* gets tested.

```bash
kasm_workspace_testing/build.sh [tag] [--no-cache] [--worktree <path|branch|dirname>]
```

Its launch form offers to delete the data directory and the agent workspace, defaulting to no and
deliberately non-savable — a remembered "yes" would wipe data on every future launch. It does not
recreate what it deletes, because Docker would then auto-create those directories as root.

The image patches one line into the base image's `custom_startup.sh`, making `/tmp` a mountpoint
before `supervisord` starts. Without it the nested Docker daemon's `dind` wrapper mounts an empty
tmpfs over `/tmp`, which hides the X socket and the session bus and kills the desktop a few seconds
after it appears — a session that connects normally and shows a blank screen. `kasm_workspace_testing/README.md`
has the mechanism and the reason the patch is a guarded `sed` rather than a forked copy of the script.

### `vqa/` — video quality assessment

A sibling image aimed at judging rendered output with minimal friction. No dashboard, no cron, no
wizard: everything onboarding would ask is baked into the image or done at session start. A session
boots straight into `/vqa-new-video "<topic>"` → approve the script → render → optionally
`/vqa-review`.

Its persistence design is the interesting part: code is baked at `/opt` and replaced on every
rebuild, while the session hook rsyncs it to a home directory that persists — gated on a build stamp,
so in-session edits survive relaunches of the *same* image. Pipeline data lives outside that tree
entirely, and an explicit post-rsync check fails loudly if the database existed before the sync and
is gone after.

AI review is seeded **off** there, deliberately: the worker bounces any video with a non-empty
suggestions list back to `REVISION_REQUESTED`, so leaving it on means few videos ever reach
`VIDEO_READY` while you are iterating on visual quality.

Its utilities are usable on their own:

| Script | Purpose |
|---|---|
| `vqa/edit_settings.py` | `--list`, `--set KEY=VALUE`, `--restart {renderer,api}` |
| `vqa/review_video.py <video_id>` | Runs AI review with **no database writes** — repeatable, no side effects |
| `vqa/stage_script.py <video_id>` | Writes out the script with visual briefs, and the exact text that would go to ElevenLabs |
| `vqa/reset_db.py --yes [--db-only]` | Rebuilds a seed database and optionally clears job, output and scene files |

> **`edit_settings.py` writes over `POST /settings`, never direct SQL.** Do not "simplify" it. Some
> checks live only in that endpoint — the live webhook probe, and keeping a re-sent masked secret
> from overwriting the real key — so a direct-SQL script would skip them.

### Both build scripts offer worktrees only

Never bare branches. This looks like an obvious gap and is the thing not to add: a worktree is a real
checkout, so staging includes untracked and uncommitted work (marked as such in the picker), whereas
a branch with no worktree could only be staged from its committed tip, silently dropping exactly
that. The chosen tree also supplies the Dockerfile, so an image is never a mix of two trees.

`--worktree` resolution is strict — it fails on both no match and an ambiguous match, because a
silent fallback bakes the wrong branch into an image unnoticed. A wrapper started from a terminal
inherits its TTY and **will** stop at the interactive picker; unattended callers must pass
`--worktree`.

> An image holds whichever tree it was built from — by default the checkout `build.sh` itself lives
> in — and recreating a session does not rebuild it. Testing a feature branch needs an explicit
> `--worktree` build, then a new session.

---

## `kasm_workspace/` — the published workspace

The Kasm Workspace users install Tubematic from — see
[Installing in Kasm Workspaces](../user-guide/02-installing.md#installing-in-kasm-workspaces) for what
they see. Unlike the two test environments it bakes **no** Tubematic source: the launch form picks a
version and an install method, and the session downloads that version. The image is therefore
version-agnostic, and **is rebuilt only when its base image or tooling changes, never per release**
— `scripts/tests/test_kasm_workspaces.py` fails if a `COPY` of the repository appears in its
Dockerfile. It shares the testing image's base, tooling and `dind` `/tmp` patch, comments included.

**Everything is baked, nothing is mapped.** A workspace registry entry carries a launch form but no
File Mappings, so the launch hook, the bootstrap and the desktop launcher are all in the image; the
testing workspace's mapped hook is a route that cannot be published.

**The launch hook is the root one, dropping to the session user.** `kasm_post_run_root.sh` is the
post-run hook observed to fire automatically with no Docker Exec Config; the user-context sibling
would need no privilege drop, but has never been seen to fire. The hook runs when Kasm's agent
chooses, so it backgrounds itself and returns at once, waits a bounded time for the desktop (the
base image's own `desktop_ready` is unbounded and returns mid-startup), retries the window a few
times, and opens `xfce4-terminal` with `runuser -u kasm-user`. The install must run as that user:
everything it creates — the extracted tree, `~/.tubematic-data`, the onboarding state, the compose
bind sources — has to be user-owned, and a root-owned leftover in a persisted profile is the
failure that breaks host-side scripts later.

**The bootstrap** (`kasm_workspace/image/tubematic_bootstrap.py`, standard library only, since the
image has no virtualenv) does the work, so all of it is unit-tested and every message lands in the
window the user is watching:

- It reads the launch-form answers from `/dockerstartup/tubematic_launch_selections.json` — not
  `/tmp`, so nothing depends on the `/tmp` patch winning its race. An unreadable answer, a missing
  key or a version that is not a plain `X.Y.Z` is refused; a version is never guessed.
- A persistent profile is relaunched, so an existing install is the normal case. It records what it
  installed in `~/.tubematic-workspace.json`. The same version is reported and left alone; a
  **different** version is refused with a pointer to [Upgrading](../user-guide/07-upgrading.md),
  because installing a second copy beside an install, or replacing one, is not something to do
  silently. Tubematic data with no record of this launcher installing it is refused the same way.
- **Release:** it downloads the tarball and the release's `CHECKSUMS.txt` and checks the sha256
  **before** extracting anything — a downloaded archive is untrusted until it matches — and refuses
  an archive with any path outside its own `tubematic-v<version>/` directory.
- **Source:** it clones the version's **tag**, never the default branch.
- It then runs `python3 onboard.py` interactively in the same terminal. The terminal always ends
  in a shell, so a failure leaves the error on screen rather than a vanished window.

The repository name is duplicated from `tubematic_core.version.GITHUB_REPO`, because the image has
nothing to import it from; a test pins the two together.

**The registry entry** is `kasm_workspace/registry/Tubematic/workspace.json` (registry schema 1.1).
Each release writes it into the workspace registry with every published release on the form — see
[Publishing the Kasm registry entry](#publishing-the-kasm-registry-entry). The version list there
has no free-text fallback, newest first and the default; a version missing from it cannot be
installed from the form. The list in this repository is only a seed: the release job replaces it,
and copies every other key verbatim. The entry asks for no GPU on
purpose: a GPU attached to this desktop crash-loops XFCE on an NVIDIA EGL failure.

---

## Schema changes

The full model — where migrations live, why `0001` is Python, the write lock, backups — is in
[Database — Migrations](03-database.md#migrations). This is the checklist for actually making one.

- **A schema change is a new migration file, never an edit to an existing one.** Add
  `tubematic_core/migrations/NNNN_<name>.sql` (plain SQL — see the one-statement-per-line rule
  below) with the next number after whatever is already in the directory.
- **Never edit a migration that has shipped.** A database that already applied it has that behaviour
  stamped into `schema_migrations` and will not see the edit; a database that has not will apply the
  edited version. The two silently diverge. If a shipped migration was wrong, write a new one that
  corrects it.
- **One statement per line group in a `.sql` migration.** Migrations run inside one transaction for
  the whole batch, which rules out `executescript()` (it issues its own `COMMIT` and would drop the
  lock that makes concurrent `migrate()` calls safe), so files are split with
  `sqlite3.complete_statement` instead. Two statements written on the same line arrive at `execute()`
  as one string and raise "you can only execute one statement at a time" — at authoring time, not as
  a silent runtime surprise. **The same rule applies inside a `.py` migration's `up(con)` — never call
  `con.executescript()` there either.** `0001_baseline.py` shipped doing exactly that; it drops the
  lock the same way a `.sql` migration would, just without the loud authoring-time error to catch it.
- **Update `tubematic_core/tests` in the same change.** A new column needs an `EXPECTED_*_COLUMNS`
  entry in `test_baseline.py` (only for `0001` itself) or its own assertion in a new migration's
  test; a change that an old database needs to converge through should get a fixture-backed test, not
  just a fresh-database one. See [Tests — `tubematic_core`](test-suites/tubematic-core.md).
- **Run the migration tests before finishing schema work**: `python -m pytest tubematic_core/tests`.
- **If the change is externally visible, update every consumer, not just the column:**
  - An MCP tool or HTTP field change needs `mcp/server.py` and/or `renderer/api/pipeline.py`, and
    `dashboard/lib/types.ts`.
  - A new setting needs its `SETTINGS_SPEC` entry and coercion branch, the dashboard `Settings` type
    and a tab in `dashboard/app/settings/page.tsx`, and — if it should be asked at install time — an
    `onboard/config.py` `Field`. See [Settings — Adding a setting](04-settings.md#adding-a-setting)
    for the full sequence.
  - A new video status needs `VALID_VIDEO_STATUSES`/`WORKABLE_STATUSES` in **both**
    `renderer/api/pipeline.py` and `mcp/server.py`, the `dashboard/lib/types.ts` copy, the state
    diagram in [The Pipeline](02-pipeline.md#the-states), and every place that branches on status —
    the worker's transition table, the poller's workable-video query, and any skill or slash command
    that names statuses.
- **Prefer additive.** A rename is a one-way door — see `videos.animatability_score →
  producibility_score` in [Database](03-database.md#migrations) for what that costs to reverse.

---

## Release tooling

Maintainer-only host CLIs for cutting a release. None of them run inside a container or during a
normal install — they exist for whoever builds a release tarball and publishes it. This is a
reference for what each one does. How a release fits together — its artifacts, release branches,
image tags and what it expects of migrations — is [Releases](18-releases.md); the versioning and
rollback policies are in [Upgrading](../user-guide/07-upgrading.md#versioning).

Every one of them reads the version through `tubematic_core.version.version()` — backed by the
`VERSION` file at the repo root — rather than a literal, so a release script can never disagree with
what the running services report.

| Script | What it does |
|---|---|
| `scripts/print_version.py` | Prints the current version |
| `scripts/migrate_db.py` | Runs `tubematic_core.db.migrate()` against a database from the host, outside any container. `--allow-no-backup` skips the pre-migration snapshot and prints a visible warning — the database's `settings` table is the credential store, so disabling its backup must never be silent |
| `scripts/backup_db.py` | Takes an unconditional snapshot with `tubematic_core.db.backup_db()`, independent of any pending migration — a manual "back this up right now" |
| `scripts/gen_release_compose.py` | Turns `docker-compose.yml` into the form a release install runs. Exactly two mechanical transformations: every `build:` section (and every service that reuses that locally-built image without a `build:` key of its own) becomes a pinned `ghcr.io/<owner>/tubematic-<role>:<version>` image, and every published port is forced onto a `127.0.0.1:` binding. Everything else — volumes, environment, healthchecks, `depends_on`, `restart`, `container_name`, the top-level `name:` — passes through untouched, which is the entire point: it is what stops the release compose becoming a second, silently-drifting copy of the development one. Owns the single definition of "a valid release version" (`check_version_is_tag_safe`): the version is interpolated straight into the image tag with no escaping, so a legal-SemVer `+build metadata` suffix — illegal in a Docker tag — is refused outright rather than emitted into a compose file every service then fails to pull. It also accepts the development branch's `develop` marker, which is tag-safe; refusing to *release* that is `check_release.py`'s job |
| `scripts/build_release_tarball.py` | Builds `dist/tubematic-v<version>.tar.gz`, the artifact a release install downloads — see [Installing — Two ways to install](../user-guide/02-installing.md#two-ways-to-install). Built from an explicit allowlist, never a copy of the repo: the checkout also holds `renderer/`, `dashboard/`, `mcp/`, `vqa/`, `.env`, and other things a public download must never carry. Reproducible — the same commit built twice is byte-identical — so the archive's own `CHECKSUMS.txt` means something |
| `scripts/check_release.py <version>` | Maintainer pre-flight. Reports every failing check in one pass instead of stopping at the first, accepts either `1.2.3` or `v1.2.3`, checks the version is tag-safe (reusing `gen_release_compose`'s definition, not restating it), mechanically enforces that no migration file git already has committed history for has since been modified, and — reusing the real builder against a scratch directory rather than restating its rules — that the tarball's exclusions actually hold, not just that its allowlist is satisfiable |
| `scripts/release.py <version>` | Thin orchestrator: runs `check_release`'s checks, builds the tarball, and prints a release-notes skeleton plus — never runs — the `git tag`/push commands. It does **not** bump `VERSION`: that is a separate, reviewed commit a maintainer makes first, since bumping it here and then checking it would make `check_release`'s "VERSION matches" check vacuous. It does **not** create a tag or push, either — pushing the tag is what actually triggers the release ([Continuous Integration](#continuous-integration), below), and a script that tags on its own can ship a release nobody approved |

Full behavioral detail and the edge cases each one guards are pinned by tests, not repeated here —
see [Tests — `scripts`](test-suites/scripts.md).

`gen_release_compose.py`, `build_release_tarball.py`, `check_release.py` and `release.py` need
`pip install pyyaml`, a maintainer-only dependency deliberately left out of
`scripts/requirements.txt` since nothing at runtime needs it. `print_version.py`, `migrate_db.py`
and `backup_db.py` need nothing beyond what already runs the pipeline.

---

## Continuous Integration

Three GitHub Actions workflows: `.github/workflows/ci.yml`, `.github/workflows/release.yml` and
`.github/workflows/docs-site.yml`.

> **Status: written and structurally checked, never executed.** GitHub Actions only runs on GitHub,
> and this repository has never had a `.github/` directory before now, so neither workflow has ever
> actually run. `actionlint` is not installed on the machine that wrote them either. The one
> automated check either file gets before its first real run is
> `scripts/tests/test_workflows.py` — see [Tests — `scripts`](test-suites/scripts.md) — which parses the
> YAML and asserts structure (every `needs:` resolves, every action is version-pinned, the Python
> matrix matches the suite directories actually on disk, the e2e job never triggers on a pull
> request) rather than behavior. Do not read "written" as "working."

### `ci.yml` — pull requests and pushes

Triggers: `pull_request`, `push`, `workflow_call` (so `release.yml` can run these same jobs as its
own pre-flight instead of keeping a second, driftable copy), and `workflow_dispatch` (so the e2e job
can be run on demand without cutting a tag).

| Job | What it runs |
|---|---|
| `python-tests` | A matrix over the six suite directories — `tubematic_core/tests`, `mcp/tests`, `renderer/api/tests`, `onboard/tests`, `scripts/tests`, `vqa/tests` — one per matrix entry. They cannot run combined; see the `conftest.py`/`sys.path` collision noted under [Tests](#tests) above. The matrix is the fix for that, not a stylistic choice |
| `dashboard` | `npm ci`, `npx vitest run`, `npm run build`. No Playwright — the e2e suite needs the Docker test stack and is handled separately below |
| `remotion` | `npm ci --ignore-scripts`, `npx tsc --noEmit`. Deliberately not `npm run lint` — that script also runs eslint, which has two pre-existing errors unrelated to type safety, and `validate_job` (the pipeline's own per-render gate) runs `tsc`, not eslint |
| `compose-check` | `docker compose config` against `docker-compose.yml`, then again against a release compose generated on the fly by `scripts/gen_release_compose.py`. The release compose is a distinct document — pinned images, loopback-bound ports — so validating only the development file would miss a syntax error the generator itself introduces |
| `e2e` | Playwright against `docker-compose.test.yml`. **Conditional: a tag push or a manual dispatch only, never a pull request or an ordinary push** |

**Why `e2e` is not on every pull request.** It needs no secrets — the test stack passes literal
`test` strings for every API key — so the objection isn't credentials, it's cost: `global-setup.ts`
builds both the backend and dashboard images cold, 12–20 minutes before the first assertion runs.
That's unaffordable against a limited Actions budget on every push, and effectively free once, at tag
time.

**Its current status is non-blocking** (`continue-on-error: true`), set from an observed run rather
than a guess: when the job was added, its first real run failed only on tests whose fix had not yet
reached the branch it ran against. That's a strong inference, not a verified one. The comment
directly above the `e2e` job in `ci.yml` records that run, the commit that fixes it, and the exact
promotion criterion — rerun on a branch that has the fix, and flip to blocking only on a fully green
result.

### `release.yml` — version tags

Triggers only on a `v*.*.*` tag push. Permissions are exactly `contents: write` (to create the
Release) and `packages: write` (to push images) — nothing broader, since a workflow that publishes
packages and releases is a standing risk if it can do anything else.

The job order is load-bearing:

1. **Preflight** — assert the tag matches `VERSION` and run `scripts/check_release.py`.
2. **Reuse `ci.yml`** via `workflow_call`, with the `e2e` job enabled. This is one definition of the
   test matrix, not a second copy that can silently drift from the pull-request one.
3. **Build and push** `tubematic-backend` (from `renderer/Dockerfile`) and `tubematic-dashboard` to
   GHCR, each under the single bare tag `X.Y.Z` — what the generated release compose pulls. See
   [Releases — Image tags](18-releases.md#image-tags) for the two tags that
   were dropped and why. The packages are public, so a release install pulls them without logging in.
4. **Build the release tarball** with `scripts/build_release_tarball.py` and write a `CHECKSUMS.txt`
   for the archive itself.
5. **Smoke-test the published artifact** — extract the tarball into a fresh temporary directory
   (never the checkout), create the data directories and service tokens onboarding would have made
   (Compose refuses to start a service whose token file is missing), bring up its own
   `docker-compose.yml` against the images just pushed, assert
   every service reaches healthy and the API answers, then tear down.
6. **Create the GitHub Release** and attach the tarball and its checksum.
7. **Publish the docs** (`publish-docs`) — sync this tag's `docs/` into the documentation site as its
   release line, then build and push it. See [Publishing the docs](#docs-siteyml--publishing-the-docs).
8. **Publish the Kasm registry entry** (`publish-kasm-registry`) — put this release on the Kasm
   workspace's launch form. Skipped for a prerelease. See
   [Publishing the Kasm registry entry](#publishing-the-kasm-registry-entry).

**Why the smoke test sits between the image push and the Release.** It has to pull the images, so
they must already be pushed — but a broken artifact must never become a published Release. A failure
here leaves images on GHCR under a tag with no Release attached, which is recoverable: a package
version can be deleted. An already-downloaded Release cannot be un-published.

`--owner` is always passed explicitly as `${{ github.repository_owner }}` rather than left to a
script default, so a fork publishes to its own namespace instead of someone else's.

### `docs-site.yml` — publishing the docs

The documentation site, docs.tubematic.ai, is a Docusaurus project in its own repository
(`tubematic-docs`). This repository's `docs/` is the only source: the site holds a synced copy of it
per release line plus one of `develop`, and Vercel deploys the site on every push to it.

Two places sync it, both through the composite action `.github/actions/sync-docs-site`, which checks
out the site, runs its `scripts/sync-docs.mjs` against a tubematic checkout, builds the site, and
commits and pushes only if something changed:

- **`release.yml`'s `publish-docs` job**, after `release`, for the tag being released. It runs only
  once the Release exists and nothing depends on it, so a docs failure never blocks or undoes a
  release; re-run the job, or run `docs-site.yml` by hand with the version.
- **`docs-site.yml`**, on a push to `develop` that touches `docs/` (the site's "develop
  (unreleased)" version), and by hand (`workflow_dispatch`) with `develop` or any released version.
  A manual run checks out its own commit for the action and the requested ref separately, because an
  older release tag predates the action.

**The build runs before the push.** The site's build fails on any broken link or anchor, so a page
that would publish a dead link stops in CI and never reaches the site.

**The token is an environment secret.** The site repo is reached with `TUBEMATIC_DOCS_TOKEN`, a
fine-grained token with Contents read/write on that repository only, stored in the `TubeMatic`
environment. Only a job that names the environment can read it, so both jobs declare it, and the
shared logic is a composite action rather than a reusable workflow: a reusable workflow sees an
environment secret only if its caller passes it through too, and a missing one silently becomes an
empty string. The action refuses an empty token up front. Both jobs share one concurrency group, so
a release sync and a `develop` sync queue rather than race on the site repo. This repository is
only read (`contents: read`).

### Publishing the Kasm registry entry

`release.yml`'s `publish-kasm-registry` job, after `release`, runs the composite action
`.github/actions/sync-kasm-registry`. It writes the Tubematic entry into the workspace registry
repository (the one the [install guide](../user-guide/02-installing.md#installing-in-kasm-workspaces)
tells people to add, on its schema branch `1.1`) with `kasm_workspace/sync_registry.py`, and pushes
only if something changed. The registry's own build then republishes its `list.json`.

- **The version list is every published Release**, newest first, drafts and prereleases excluded —
  not every tag, because a release-method install downloads the Release's assets. A prerelease tag
  skips the job entirely.
- **The entry comes from the newest release's tree**, not the tag being released, so a patch on an
  older line adds its version without rolling back a newer entry's description or image.
- **The workspace image is checked first.** Nothing in CI builds it — it carries no Tubematic
  version, so it is built and pushed by hand with `kasm_workspace/build.sh --push` only when its
  base image or tooling changes. The job therefore runs `docker manifest inspect` on the entry's
  image without logging in, exactly as Kasm pulls it, and writes nothing if that fails.
- **It gates nothing**, like `publish-docs`: a failure leaves the release intact and is recovered
  by re-running the job.

The registry is reached with `TUBEMATIC_KASM_REGISTRY_TOKEN`, a fine-grained token with Contents
read/write on that repository only, in the same `TubeMatic` environment and for the same reason as
the docs token. Its push is also what triggers the registry's build: a push made with a workflow's
own `GITHUB_TOKEN` starts no workflow.

---

## Conventions

**Documentation is part of the change.** `docs/` is public and must never carry stale information.
See [Keeping the docs true](#keeping-the-docs-true).

**MCP docstrings own technical contracts; skills own workflow.** A skill must not restate a tool's
parameter signature.

**Agent-visible text carries no ticket identifiers.** Skills, slash commands and `@mcp.tool`
docstrings are read by a model that cannot look them up. Internal comments may reference whatever
they like.

**No `CLAUDE.md` for agent instructions.** Behaviour belongs in skills, documentation in `docs/`.

**Diagrams are inline ```mermaid fences.** GitHub renders them natively; there is no build step and
no binary asset to fall out of date.

**Duplication across processes is intentional.** See
[Architecture — Duplication](01-architecture.md#duplication-is-intentional). Grep before changing a
constant, and grep for the *value* as well as the name — several settings defaults are repeated in
several places without a keep-in-sync comment.

**A schema change is a new migration file, never an edit to a shipped one.** See
[Schema changes](#schema-changes).

**Send credentials as headers, never as URL parameters.** Client libraries embed the request URL in
exception strings, and this pipeline persists error text into a dashboard-visible table.

---

## Working on a branch

Use a git worktree so parallel work does not interfere:

```bash
git worktree add .worktrees/my-feature -b my-feature develop
```

`.worktrees/` is gitignored, and both Kasm build scripts can build an image from any worktree.

> **Two agent sessions on one checkout will corrupt each other's git history.** A concurrent
> `git commit --amend` has silently absorbed another change's commit, and `git status` read clean
> immediately afterwards — the rewrite happened between commands. If two sessions must share a
> checkout, commit with explicit pathspecs and re-verify against `HEAD`, not the working tree.

`node_modules` is gitignored in both `dashboard/` and `renderer/remotion/`, so a fresh worktree has
none. Symlink them from the main checkout to run the JS suites without a second install.

---

## Keeping the docs true

Every change that touches behaviour touches `docs/`. The rules that keep it from rotting:

- **Cite symbols, never line numbers.** `pipeline.py::patch_video`, never a file path with a line number appended.
- **No test counts, suite totals, or "as of" dates.** They are wrong within a week.
- **Every path, route, tool name and settings key must exist.** Verify mechanically, not by reading.
- **No links into `plan/` or `code_review/`** — they are internal and gitignored.
- **No ticket identifiers.** Traceability lives in `git log`.
- **No host paths, usernames, or credentials**, including in examples.
- **Write for the page's audience, once.** `docs/user-guide/` says what a person running Tubematic
  does and sees; `docs/developer/` says how it works and how to change it. Each explanation lives on
  one page and the other links to it. Pages are numbered within their folder, and a new page needs a
  row in `docs/README.md`.
- **Shipped pages link only to shipped pages.** The release tarball carries `docs/README.md`,
  `docs/quickstart.md`, `docs/release-notes.md`, `docs/user-guide/` and `docs/developer/`, and the
  build fails on a link from one of them to anything else.

A change that adds an MCP tool, an HTTP route, a settings key, a status, a schema column, an
installed component, or a skill rule is **not finished** until the corresponding page reflects it —
and until the neighbouring claims that the change invalidated have been re-checked. The count of MCP
tools in `docs/developer/06-mcp-server.md` is the canonical example: it is wrong the moment a tool is added and
nothing but a person will notice.

---

## Contributing

Reasonable first contributions, all real and all small — see
[HTTP API — Known quirks](05-http-api.md#known-quirks) and
[Installing — Uninstalling](../user-guide/02-installing.md#uninstalling):

- Register a JSON error handler so unhandled exceptions stop returning HTML.
- Make an empty strategy list round-trip.
- Validate `project_id` before insert so a bad one is a `400`, not a `500`.
- Bring the uninstaller's skill and command lists up to date, and fix its step counter.
- Fix the two pre-existing eslint errors in the Remotion project.

Before opening a pull request:

1. The relevant Python suites pass, one directory at a time.
2. `npx tsc --noEmit` passes in **both** `dashboard/` and `renderer/remotion/`.
3. `npm test` passes in `dashboard/`.
4. `docs/` reflects the change, and nothing it says has become false.
