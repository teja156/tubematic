# Upgrading

How to move an existing install to a newer version of Tubematic, and what happens to your data on
the way. Installing from scratch is
[Installing — Two ways to install](02-installing.md#two-ways-to-install). How a release is
built — release branches, image tags, migration mechanics — is
[Releases](../developer/18-releases.md), for contributors.

**What a release is, from your side.** Every release has a version number, `vX.Y.Z` (see
[Versioning](#versioning) for what a bump of each part means). It is published as a GitHub Release
carrying its release notes and a tarball. A release install downloads that tarball and pulls two
Docker images built for that exact version; a source install checks out the version's git tag and
builds the images from that checkout instead. Either way you upgrade with one command, `upgrade.py`, run
from the new version.

**Read the [Release Notes](../release-notes.md) for the version you are moving to before you
start** — above all their **Upgrade notes**, which list anything you must do by hand. When you skip
versions, read every version in between.

> `upgrade.py` is unit-tested, and the source route below has been run end to end in scratch
> environments against real published installs, with migrations applied on the way. The
> release-tarball route differs only in pulling images instead of building them,
> and that pull has not yet been exercised against published images.

---

## Upgrading — user instructions

Both routes end in the same command, `upgrade.py`, run from the install you are moving *to*. It
asks no questions, so it works over a non-interactive SSH session or from a deploy tool, and it runs
the steps in the order that keeps your data safe:

1. **Checks that nothing is in flight**: no video `RENDERING` or `VOICING`, no agent session running
   (it takes the same lock the poller holds for as long as it runs, and checks for sessions a poller
   that stopped left behind), and no publish still uploading. The poller can hold its lock for a
   while between sessions, so pause the pipeline first: it then stops as soon as its running
   sessions finish. Stopping
   the stack kills that work. A killed render counts as a render failure, and with the default retry
   budget of 1 that can mark the video `FAILED`. A killed voicing can lose audio ElevenLabs has
   already charged for, and leaves the video stuck at `VOICING` until someone moves it back by
   hand. If anything is in flight it names the video and stops before changing anything. Wait and
   re-run, or pass `--force`. It also refuses when the database is *newer* than the version you are
   running — that is a downgrade, which needs [Rollback policy](#rollback-policy), not an upgrade. It keeps holding the poller's lock until it finishes, so no agent run
   can start partway through.

   **It also refuses, before changing anything, when no dashboard password is set** — which is the
   case on every install older than 2.0.0, where the dashboard had no login. `upgrade.py` asks no
   questions, so set one first, from the same new directory you run `upgrade.py` from (the older
   version has no such command), then run the upgrade:
   ```bash
   python3 onboard.py --set-password
   ```
   This is safe while the older version is still serving: a version without the login ignores the
   stored password.

   **It also refuses, before changing anything, when no OpenAI API key is stored.** From 2.0.0 every
   scene image comes from OpenAI, so without a key the upgrade would succeed and then fail every
   image — on a video whose script was already approved and whose voicing was already paid for. Add
   the key on the dashboard first (Settings → API Keys), which works on the older version, then run
   the upgrade again.

   **It also refuses when a generated scene imports the removed `GifFX` component** — any `.tsx`
   under `~/.tubematic-data/scenes/generated/` with a module path (in an `import`, `export …
   from`, dynamic `import()` or `require()`, including `(require)(…)`, `require?.(…)`,
   `require.resolve(…)` and `require.resolveWeak(…)` and their bracket spellings
   (`require["resolve"](…)`), which webpack bundles the same way) that resolves to
   `installed/GifFX`. A method named `require` on another object (`loader.require(…)`) is not told
   apart from webpack's and refuses too, and neither is a call on any other bracket key of `require`
   (`require["cache"](…)`, `require[key](…)`): it refuses when its argument names `GifFX`. It reads the
   scene the way the bundler does, not as a substring search: a small lexer skips comments
   and strings, so an old import kept as a note in a comment or a string does not refuse. Comments between the keyword and the path are skipped, string escapes (`\u0047`,
   `\u{47}`, `\x47`, a line continuation) are decoded, a template string with no `${…}` counts as
   a string, and the path is normalised, so `installed/./GifFX`, `installed//GifFX` or
   `installed/GifFX.tsx` count too; the match is case-sensitive, like module resolution on the
   Linux renderer. An `import()` or `require()` whose argument is computed
   (`"../../installed/" + "GifFX"`, a template with a `${…}`) refuses when its string parts,
   joined, spell `GifFX`: webpack folds constant parts into one path, which then fails the
   bundle, and a computed path naming the component is refused rather than guessed at. That has
   one known cost: a computed path is not resolved, so `import("./" + "GifFX")` refuses even when
   it only names a sibling `./GifFX` of the scene's own (the static `import … from "./GifFX"`
   passes). It is a lexer rather than a TypeScript parser, so it can misread unusual code (code
   taken for JSX). It recognises a generic arrow function's type parameters (`<T,>`,
   `<T extends …>`, `<T = …>`, whatever letter the name starts with), which TSX does not read as
   JSX, and every other misreading errs towards refusing, never towards missing an import: JSX
   text is lexed as code too, in case it was code. Each piece of text runs to the next `<` or `{`,
   which in misread code may sit inside a comment or a bracket key, so a piece that cuts off an
   `import()`/`require()` call, or ends while `import` or `require` still awaits its path or call,
   cannot be judged and refuses. That has a known cost: JSX text whose last word before a tag or a
   `{…}` is `import` or `require` (`<p>The modules you require.</p>`) refuses too. `from` there is
   ordinary prose (`<p>Packets from {src}</p>`) and passes, unless a comment follows it. A comment, template or attribute value that never closes is not one, so what
   follows it is lexed as code; and a stray quote never hides the lines after it.
   You can see which file and why. The renderer compiles every generated scene
   together, so one such file would fail every render on the install, not just its own video. A
   generated scene it cannot read is refused for the same reason: the renderer could not compile it
   either. So is one whose module path holds an escape it cannot decode (an octal escape, or a
   malformed `\x`/`\u`), which TypeScript rejects too. It lists the files; delete them, fix the
   import or the file's permissions, then re-run. A video whose `scene-config.json` names `GifFX` is only warned about: if it is
   rendered again, the renderer skips the scene it cannot load and that overlay is simply left out.
2. Installs `scripts/requirements.txt` into this directory's `.venv`.
3. **Pulls (release) or builds (source) the new images.** The old stack keeps running meanwhile —
   containers keep the image they started from until they are recreated.
4. **Checks for in-flight work again, then stops the whole stack.** A long build is exactly when a
   queued render can start, so the check is repeated. If something is in flight now, it stops
   there with the new images in place, and a re-run is quick. The `GifFX` scene check is repeated
   here too, under the same lock and also with `--no-stop`: the old MCP server kept serving through
   the build and could have written such a scene since the first check. A refusal here likewise
   stops nothing.

   The full stop is the point. Without it, `docker compose up -d` recreates `tubematic-api` first,
   and the new code migrates the database while the *old* renderer, MCP server and dashboard are
   still running against it. An added column survives that; a rename or a drop does not — the
   same reason [Rollback policy](#rollback-policy) stops the containers before restoring.
5. Starts the stack: creates any missing data directories, re-points Docker volumes whose recorded
   device has moved, creates any missing service token in `~/.tubematic-data/secrets/` (an existing
   one is never replaced), runs `up -d`, and waits for the health checks. The containers apply pending
   migrations as they start, backing up first. `upgrade.py` never runs one itself.
6. Rewrites the cron entry to run this install.
7. Redeploys each installed agent's skills and commands from this install — the same files
   `onboard.py --install-agent` copies, without its questions and without re-checking the agent's
   login or models — removes any Tubematic skill an earlier version shipped and this one no longer
   does, and re-registers its MCP server with the token it now needs. **An agent left
   without a working registration fails the upgrade**: the rest of it completes, but it exits
   non-zero and names the agent, because the MCP server would refuse every call that agent makes
   and the pipeline would stall while looking healthy. Fix the cause it names, then
   `python3 onboard.py --install-agent <agent>`.
8. Reports the version, the database schema, the cron entry and each container's health.

| Flag | What it does |
|---|---|
| `--check` | Only the report in step 8, plus the password, the token files, a live check that the MCP server refuses a request without its token and accepts the install's, and each agent's registration. Changes nothing, and works on a half-configured install |
| `--dry-run` | Shows every step it would take, changes nothing |
| `--force` | Proceeds even though work is in flight — that work is killed |
| `--no-stop` | Skips the stop, so containers are recreated one at a time. Only for an upgrade whose migrations you know are additive. Refused while any service token is missing (an upgrade from before 2.0.0): old and new containers would refuse each other's calls. Also refused while migration `0016` is pending: old containers would keep reading the `image_provider` setting it deletes |
| `--install-mode dev\|release` | Overrides the detected install mode |

### If you installed from a release tarball

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/vX.Y.Z/tubematic-vX.Y.Z.tar.gz
curl -LO https://github.com/teja156/tubematic/releases/download/vX.Y.Z/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-vX.Y.Z.tar.gz
cd tubematic-vX.Y.Z
python3 upgrade.py
```

Extract into a fresh directory rather than over your existing one — see
[A worked upgrade example](#a-worked-upgrade-example) for why that's safe: both directories' compose
files address the same named volumes, so your database and files carry over with nothing to copy.
This works when upgrading *from* a version that did not have `upgrade.py`, because it is the new
directory's copy that runs.

**Do not remove the old directory until `upgrade.py` has finished.** Your cron entry points at it
until then — see [A worked upgrade example](#a-worked-upgrade-example) for why deleting it first
breaks the poller silently. When it finishes, `upgrade.py` names the old directory as safe to
remove.

If the release notes mention a changed MCP tool signature, restart any open agent session
afterwards; tool schemas are read once, at session start.

From 2.0.0 every request to the API (port 4000) and the MCP server (port 4100) needs a token, apart
from their `/health` probes. Any script or `curl` of your own that calls them must send it — see the
commands below — and an MCP server you registered with an agent yourself, rather than through
`onboard.py --install-agent`, needs re-registering through the installer.

### If you installed from source

```bash
cd tubematic   # your source checkout
git fetch --tags
git checkout vX.Y.Z
python3 upgrade.py
```

### After either route

The quickest confirmation that the upgrade landed is the **version badge in the dashboard top bar**
— it reads the version from the running API, so it shows what is actually serving rather than what
is on disk. If it shows nothing, the dashboard could not reach the API. For the same answer from a
shell:

```bash
python onboard.py --status                 # which steps completed
TOKEN="Authorization: Bearer $(cat ~/.tubematic-data/secrets/api_token)"
curl -s localhost:4000/health                          # Flask
curl -s localhost:4000/render/health                   # Chromium inside the container
curl -s -H "$TOKEN" localhost:4000/pipeline/status     # the full readout
curl -s -H "$TOKEN" localhost:4000/agents              # the installed agents and their models
python3 scripts/service.py status          # version, schema, cron entry, all four containers
python scripts/status.py                   # videos, costs, disk usage
```

[Installing — Verifying an install](02-installing.md#verifying-an-install) explains each of
these. If anything looks wrong before you've made any new changes of your own, the fastest way back
is [Rollback policy](#rollback-policy) below.

---

## A worked upgrade example

The walkthrough below uses a made-up migration so the steps stay easy to follow; it is
illustrative, not a record of something that happened. Imagine a future `v2.1.0` that ships a migration
`tubematic_core/migrations/NNNN_add_thumbnail_url.sql` (`NNNN` standing for whatever the next free number is then), adding a nullable `videos.thumbnail_url`
column, released after some earlier `v2.0.x`.

### Release install

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/v2.1.0/tubematic-v2.1.0.tar.gz
curl -LO https://github.com/teja156/tubematic/releases/download/v2.1.0/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-v2.1.0.tar.gz
cd tubematic-v2.1.0
python3 upgrade.py
```

This extracts into a **new, separate directory** (`tubematic-v2.1.0/`, alongside whatever
`tubematic-v2.0.x/` you installed from before) — nothing is overwritten in place. Both directories'
compose files point at the same named volumes over the same `~/.tubematic-data` device paths, so the
new stack picks up the existing database and files automatically the moment it starts. The migration
happens inside the containers, not in the installer bundle — see [What happens, either way](#what-happens-either-way).

**Do not delete the old directory until `upgrade.py` has finished in the new one.** The cron line
has two absolute paths baked in: the Python that wrote it (`sys.executable`) and
`<that directory>/scripts/poll.py`. Until something rewrites it, both still point at the *old*
directory. Delete it first and every cron tick fails with "No such file or directory" in
`cron.log`, with **no other visible symptom**: no failed video, no dashboard alert, the pipeline just
stops advancing. `upgrade.py` rewrites the line — after creating this directory's own `.venv` and
installing `scripts/requirements.txt` into it, since that venv is the Python cron will run — and
names the previous directory when it is done. It also copies the previous directory's
`.onboard-state.json`, which lives per directory, so `python onboard.py --status` here does not
report an uninstalled system. `python3 upgrade.py --check` confirms the cron entry points at the new
directory; after that, the old one holds no data of its own and can be removed.

### Source install

```bash
cd tubematic   # your source checkout
git fetch --tags
git checkout v2.1.0
python3 upgrade.py
```

### What happens, either way

**What runs.** `upgrade.py` pulls the new images (a source install builds them) while the old stack is still serving, stops the
stack, and starts it again on the new images. On that start, each of `tubematic-api`, `tubematic-mcp` and `tubematic-renderer` calls
`migrate()` on its own first database touch and sees `NNNN` is not in `schema_migrations`. The
backup happens *before* any of them takes the write lock, not inside it, so it is normal for **more
than one** to write `tubematic-before-v2.1.0-<timestamp>.db` into `backups-data` before one of them
wins the lock and actually applies `NNNN` — the loser(s) get a collision-suffixed name rather than
overwriting the first. Whichever container gets there first with the lock applies the migration; the
others then find nothing pending and pass straight through.

**What's preserved.** Everything: every video, comment, setting, job file and rendered mp4. An
additive migration touches only the schema, never existing rows or files outside the database.

**What you should see afterwards.** `docker compose logs tubematic-api` shows no migration error;
one or more new files have appeared under `~/.tubematic-data/backups/` (two is the normal case here,
not a sign something went wrong — see above); existing videos are unchanged and still show their
prior status; and (in this hypothetical) `videos.thumbnail_url` exists and is empty on every
pre-existing row, ready for new videos to populate.

## Versioning

Tubematic follows semantic versioning: `MAJOR.MINOR.PATCH`, with an optional `-prerelease` suffix.

| Bump | When | Example |
|---|---|---|
| **Patch** | A fix, or a small change a user would call a fix. It may carry a migration — including renaming a settings key — as long as `upgrade.py` applies it on its own, carries every stored value across, and nothing a user, an agent or a script relies on stops working | `1.2.3 → 1.2.4` |
| **Minor** | New capability that is backward compatible for everyone already running — a new MCP tool, a new setting with a sensible default, a new page | `1.2.3 → 1.3.0` |
| **Major** | A change that needs a person to act, or that breaks a contract callers depend on — a step to run by hand before upgrading, a changed or removed MCP tool argument or HTTP route, a removed capability | `1.2.3 → 2.0.0` |

**What the bump does not promise: rollback.** Several patches have shipped migrations an older
release cannot read back (a renamed key, a reshaped voice roster), so moving *down* a version, even
within one minor line, can need the pre-upgrade backup. [Rollback policy](#rollback-policy) is the
rule to follow, whatever the size of the bump.

**Where the line falls between patch and major.** A patch's **Upgrade notes** may advise — retune a
number whose meaning tightened, request a revision on a script the fix now refuses. If skipping a
step would leave the install broken, or make `upgrade.py` refuse to run, the change is a major.

A source checkout of the development branch has no number: the dashboard's version badge reads
`vdevelop` and `scripts/service.py status` reports `develop`. That is expected: a number is
only assigned when a release is cut — see
[Releases — Version numbers in the code](../developer/18-releases.md#version-numbers-in-the-code).

---

## Migrations

Some releases change the database schema. You never run a migration yourself: when the new
containers start, they apply any pending migrations, taking a [backup](#backups) of the database
first. `upgrade.py` only stops the old stack and starts the new one. A migration only ever moves the
database forward, which is why going back a version follows [Rollback policy](#rollback-policy)
rather than a reverse command. How migrations are written and shipped is
[Releases — Migrations](../developer/18-releases.md#migrations).

---

## Backups

How backups are taken, and why, is in [Infrastructure — Backups](../developer/16-infrastructure.md#backups). Snapshots are named
`tubematic-before-v<version>-<timestamp>.db`; the exact restore commands are under
[Rollback policy](#rollback-policy) below, where they're actually needed. What you need to know
when upgrading:

- A snapshot is taken **only when `migrate()` is about to apply something**, never on a no-op start
  and never for a brand-new database. A patch release with no migration in it produces no backup on
  upgrade, because there is nothing to protect against.
- **What is backed up is the database file, and only the database file.** Rendered videos, job
  files, and generated scene code are not duplicated into it — they live in their own volumes
  (`output-videos`, `jobs-data`, `scenes-generated`) and are untouched by a migration. A database
  backup is not a video backup.
- **Nothing prunes the backups directory automatically.** Every upgrade that has something pending
  adds at least one file — usually **two**, not one: `migrate()` backs up before it takes its write
  lock, and the three backend containers start close enough together that
  more than one reaches that point before the first has committed, so more than one snapshot gets
  written (the loser gets a collision-suffixed name rather than overwriting the first). Nothing ever
  removes one. Clean it out by hand if it grows large.

---

## Rollback policy

**Forward upgrades are supported. Automatic downgrades are not.** There is no "migrate backward"
operation anywhere in `tubematic_core.db` — migrations only ever move a database forward, and
nothing generates or applies a reverse migration.

Once a migration has actually run against your database, older code cannot be assumed to tolerate
the result. A `SELECT *` still works against an added column, but code that predates a rename or a
drop — the exact case the `producibility_score` rename is the standing example of — will not. The
safe assumption is that any code older than the last-applied migration may not work correctly
against a database that migration touched.

The supported path back to an older version is:

1. Stop the stack so nothing else touches the database mid-restore. From the install you are
   rolling back *from*:
   ```bash
   python3 scripts/service.py stop
   ```
   It refuses while work is in flight, for the reason [Upgrading](#upgrading--user-instructions)
   explains; `--force` stops anyway.
2. **Restore the pre-upgrade backup.** If the upgrade you're reverting added a migration, one was
   taken automatically before it ran, named `tubematic-before-v<version>-<timestamp>.db` under
   `~/.tubematic-data/backups/`. **This discards every row written since the upgrade** — every
   video, comment and setting change — and does not touch the mp4s and job files those rows point
   to, since [Backups](#backups) above covers only the database file: restoring leaves those on disk
   with nothing in the database referring to them. Don't run this step on a system that has done
   real work since the upgrade without accepting that loss.

   The backup file is **owned by root**, not your host user: the three backend containers run as
   root, and `backup_db()` only copies the live database's permission *bits* (`0660`) onto the
   snapshot, not its ownership — a plain `cp` as yourself fails with `Permission denied`. Use `sudo`
   to read it, then copy it back over the live database and drop its stale WAL/shm sidecars — they
   belong to the file you're replacing, not the backup:
   ```bash
   sudo cp ~/.tubematic-data/backups/tubematic-before-vX.Y.Z-<timestamp>.db ~/.tubematic-data/data/tubematic.db
   rm -f ~/.tubematic-data/data/tubematic.db-wal ~/.tubematic-data/data/tubematic.db-shm
   ```
   If the upgrade had no migration in it (a patch release, most likely), there is nothing to restore
   and you can skip this step.
3. **Go back to the prior code.** Source install: `git checkout v<old>`. Release install: use the
   prior version's extracted directory, if you kept it, or extract its tarball afresh.
4. **Bring the stack back up from that older install**, which also points cron back at it. Going
   back to a version before 2.0.0 does need step 2: 2.0.0 adds migrations, starting at `0013`
   (the per-domain topic cap), and the older `upgrade.py` refuses to start against a database a newer version has
   migrated. One of them, `0016`, deletes the `image_provider` setting: an older version reading
   that database falls back to the Gemini image provider while `image_model` holds an OpenAI model,
   and refuses every settings save. It needs nothing more for the login: it ignores the stored password
   and the files in `~/.tubematic-data/secrets/`, and an MCP server from before 2.0.0 ignores the
   header the agents send. Its own `upgrade.py` re-registers the agents the way it expects. If the
   older version ships `upgrade.py`, run `python3 upgrade.py` there. If it predates it, run
   `python onboard.py --step cron`, then `--step renderer` and `--step dashboard` — each needs a
   terminal.

There is no tooling that automates this sequence — it is a manual, deliberate operation, on purpose:
an automatic rollback that silently discarded a database backup or repointed images without
confirmation is a worse failure mode than a maintainer typing four commands. `upgrade.py` only ever
moves forward for the same reason.
