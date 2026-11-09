# Releases

How a Tubematic release is put together: what it produces, how version numbers and release
branches relate, which image tags exist, and what the release model expects of migrations. This
page is for contributors. Someone running Tubematic and moving to a new version wants
[Upgrading](../user-guide/07-upgrading.md), which also owns the versioning policy (when a change is
a patch, a minor or a major) and the rollback policy. What each release script and CI job does,
mechanically, is in [Development — Release tooling](17-development.md#release-tooling) and
[Development — Continuous Integration](17-development.md#continuous-integration).

---

## What a release consists of

Pushing a `vX.Y.Z` tag is the **trigger**, not an output — a maintainer creates and pushes it by
hand. Three things come out of the one `.github/workflows/release.yml` run that tag starts, and
once they exist the run also publishes that release's docs (see
[Development — Publishing the docs](17-development.md#docs-siteyml--publishing-the-docs)):

| Artifact | What it is |
|---|---|
| A GitHub Release | Holds the release notes and three files: the tarball, `tubematic_remote_renderer.py`, and a `CHECKSUMS.txt` with the sha256 of both. The script is an asset of its own because the machine a [remote renderer](../user-guide/11-remote-renderers.md) runs on downloads it alone, with no tarball and no checkout; it is also in the tarball's `scripts/`. Before either is built, the workflow writes the owner the release pushed its images under into the script's `GITHUB_OWNER` (the script has no checkout to ask), so a fork's renderers pull the fork's backend image; the step fails if that line is not found exactly once, and the asset is compared with the tarball's copy, so the two cannot differ. A version with a `-prerelease` suffix is published as a GitHub **prerelease**, so GitHub never lists it as Latest |
| Two GHCR images | `tubematic-backend` (from `renderer/Dockerfile` — this is the same image that runs as `tubematic-api`, `tubematic-mcp`, `tubematic-worker` and `tubematic-renderer`) and `tubematic-dashboard`, each pushed under a single version tag — see [Image tags](#image-tags) |
| The release tarball | `tubematic-vX.Y.Z.tar.gz`, the installer bundle a release install downloads, with its own internal `CHECKSUMS.txt` — written last, once everything else is staged, so it covers every *other* file the tarball contains, not itself |

Nothing produces any of these by hand. `scripts/release.py` builds a local copy of the tarball for a
maintainer to sanity-check and prints the tag command — it does not tag, push, build an image, or
create a Release. Only pushing the tag does that, by triggering `release.yml`.

**The release notes are written as changes land, not at release time.** The Release body is the
matching `## vX.Y.Z` section of [Release Notes](../release-notes.md), extracted by
`scripts/release_notes.py` and published verbatim. `scripts/check_release.py` fails a release whose
section is missing or is still an unfilled skeleton, because a Release published without notes
cannot be repaired for anyone who has already downloaded it.

Maintainers follow a private, step-by-step release checklist built on this tooling. Everything a
contributor needs to know about the release model is on this page and in
[Development](17-development.md#release-tooling).

---

## Version numbers in the code

The version lives in one place, the `VERSION` file at the repo root, read at runtime through
`tubematic_core.version.version()` — never a literal — so the release tooling and the running
services can never disagree about what version is installed. `scripts/print_version.py` prints it.

`scripts/gen_release_compose.py::check_version_is_tag_safe` is the one place that defines which
strings are legal versions. It accepts SemVer's `-prerelease` grammar and rejects `+build metadata`,
which is legal SemVer but illegal inside a Docker image tag.

The development branch's `VERSION` holds no number at all, just the marker `develop`
(`tubematic_core.version.DEV_VERSION`). A release's number is decided when its release line is cut,
never guessed ahead of time on the development branch. The marker is a valid version wherever a
version is *used*: an image tag, a backup's file name, the dashboard's version badge. It is refused
only where a version is *released*: `check_release.py`'s version-format check fails on it, so the
development branch can never be tagged. The number is set on the release line, in a commit of its
own, as the first step of a release; that commit is never cherry-picked back, so the development
branch keeps its marker.

The install and upgrade commands in [Quickstart](../quickstart.md), [Installing](../user-guide/02-installing.md)
and [Upgrading](../user-guide/07-upgrading.md), and the script download in
[Remote renderers](../user-guide/11-remote-renderers.md), name a real version, never a `<version>`
placeholder, so they can be pasted as they are. On a release line they name that line's release;
on the development branch, the newest published release. GitHub's `releases/latest/download/` URL
cannot stand in for the number, because the tarball's file name carries the version. A release
updates them in a commit of its own on the line, next to the `VERSION` bump, and that commit is
cherry-picked to the development branch once the release is published and only if it is the newest
release. A patch on an older line must not move the development branch's commands back. One exception
while it lasts: the remote-renderer script first ships in 2.1.0, which no published release before
it has, so its download names 2.1.0 until that release exists.

---

## Release branches

Every published release is tagged on a **release line** — one long-lived branch per `MAJOR.MINOR`,
named `release/X.Y.x`. For example:

```
release/1.0.x  ──●  v1.0.0  ──●  v1.0.1  ──●  v1.0.2
release/1.1.x  ──●  v1.1.0  ──●  v1.1.1  ──●  v1.1.2
release/1.2.x  ──●  v1.2.0
```

The line is cut once, when that minor version first ships, and **patches are committed directly to
it**. `1.0.1` is not a new branch; it is the next tag on `release/1.0.x`. The branch is the
maintenance line, the tag is the release.

The `.x` in the name is doing real work. A branch named for a point release — `release/v1.0.0` —
that later contains `1.0.1` and `1.0.2` is a name that lies: checking it out gets you something that
is not `v1.0.0`. `release/1.0.x` describes a line, so it is still accurate every time it moves, and
moving is what it is for.

**The immutability that matters lives in the tags, not the branch.** `v1.0.0` points at one commit
permanently; `check_release.py` refuses to release a version whose tag already exists at a different
commit. That is the record of what shipped, and a branch advancing past it takes nothing away from
it.

That permanence starts when the Release is published. A tag whose `release.yml` run failed before
the Release step shipped nothing a user could download, so it is deleted (locally and on the remote)
and recreated at the commit that fixes the failure, rather than spending a new patch number on a
version that never existed. The re-run pushes the images under the same tag again. Once a Release is
published, a problem with it is fixed in the next patch.

### The one rule

**Never merge the development branch into a release line.** A fix reaches the line by
`git cherry-pick -x <sha>` (which records the commit it came from), or as a direct commit when it
only applies to that line. Merging development in drags every feature landed since the line was cut
and produces a minor release wearing a patch's version number — the failure this model exists to
prevent. A patch must be its predecessor plus the fix and nothing else.

Fixes normally land on the development branch first and are cherry-picked onto the line, so the
defect cannot resurface in the next minor release. When a fix applies *only* to a released line, it
is committed there directly and nothing is picked back.

---

## Image tags

`<owner>` throughout this page is the GitHub account or organization that published the release,
and `<repo>` is the repository it was published from. They stay placeholders because a release can
come from a fork, from a private repository, or from the public one.

Each of the two GHCR images is pushed under exactly **one** tag: `X.Y.Z`, the version with no `v`.
That is the tag a release install pulls, and it is the only image tag this project publishes.

Two others were pushed in earlier revisions and were dropped: `vX.Y.Z`, so the image tag read the
same as the git tag, which nothing ever consumed; and the commit SHA. Dropping the SHA is worth
naming as a trade rather than a tidy-up — it was the only tag immutable by construction, so
"which commit is this image built from" is now answered by the git tag carrying the same version,
not by the registry itself. One name per image, and nothing that can drift out of agreement with
the others.

The bare `X.Y.Z` form is load-bearing, not a stylistic choice.
`scripts/gen_release_compose.py::generate` bakes `ghcr.io/<owner>/tubematic-<role>:<version>` into
the tarball's `docker-compose.yml`, and the `<version>` it uses is the *bare* string —
`build_release_tarball.py --version` and the compose generator's `version` argument are the same
value everywhere in this toolchain, and that value never carries a leading `v` (the tarball's own
filename, `tubematic-v<version>.tar.gz`, is where the `v` gets added). If `release.yml` pushed any
other form, the compose file a release install actually runs would reference an image tag that was
never pushed, and `docker compose pull` would 404 on every fresh install. Getting it wrong would
break every release install, silently, until someone tried one. `scripts/tests/test_workflows.py`
pins its presence for that reason.

---

## Migrations

The full model — file layout, the `schema_migrations` tracking table, why migrations apply in
ascending numeric order, and why `0001_baseline.py` is Python while everything after it is plain
SQL — is in [Database — Migrations](03-database.md#migrations); the checklist for writing one is in
[Development — Schema changes](17-development.md#schema-changes). What the release model adds on
top of that:

- **A shipped migration is immutable.** Once a migration has gone out in a release, editing it
  diverges every database that already applied it (which stamped the old behaviour into
  `schema_migrations`) from every database that has not (which would apply the edited version). A
  schema change is always a new file.
- **`scripts/check_release.py` catches the common slip mechanically**: it runs `git diff HEAD` and
  fails if any migration file git already has committed history for shows as modified in your
  *working tree*. That catches editing a released migration by hand before you've noticed it already
  shipped — the check is only comparing your working tree to `HEAD`, though, so once that edit is
  itself committed, `git diff HEAD` has nothing left to show and the check passes. Immutability past
  that point is enforced by review and discipline, not by this script.
- **Migrations apply automatically.** Each of the three containers that open the database
  (`tubematic-api`, `tubematic-mcp` and `tubematic-worker`) calls `migrate()` on
  its own first database touch after starting, so an upgrade does not require running a migration
  script by hand — `upgrade.py` deliberately never runs one; it stops the old stack and starts the
  new one, and the containers do the rest. Whichever container reaches `migrate()` first takes a real
  write lock for the whole run, so the other two just see nothing pending and pass through. The
  backup each one takes first happens *before* that lock, which is why an upgrade usually leaves two
  snapshots rather than one — see [Infrastructure — Backups](16-infrastructure.md#backups).
- **`scripts/migrate_db.py`** exists for the one case that isn't "restart the stack": migrating a
  database from the host, outside any container, with the same pre-migration backup the containers
  take. Neither `check_release.py` nor the release workflow's smoke test calls it — the smoke test
  lets the containers migrate, then compares `schema_migrations` with the newest migration on
  disk. It is not a step anyone runs as part of a normal upgrade.

What a migration means for someone upgrading — that older code may not read the result, and that
going back needs the pre-upgrade backup — is in
[Upgrading — Rollback policy](../user-guide/07-upgrading.md#rollback-policy).

---

## `upgrade.py` in detail

The procedure a user follows is in [Upgrading](../user-guide/07-upgrading.md). This section holds the
detail behind three parts of it.

### The removed-component check

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

### `--no-stop`

Skips the stop, so containers are recreated one at a time. Only for an upgrade whose migrations you know are additive. Refused while any service token is missing (an upgrade from before 2.0.0): old and new containers would refuse each other's calls. Also refused while migration `0016` is pending: old containers would keep reading the `image_provider` setting it deletes. Also refused while the running `tubematic-renderer` still runs the old combined loop (an upgrade from before 2.1.0), whether or not a `tubematic-worker` container is also there: the old renderer would keep publishing, running Auto Pilot and sending notifications beside the new worker until it is recreated. Without `--no-stop` that upgrade is fine, and creates the worker. Also refused while migration `0019` is pending (an upgrade from before 2.1.0, again): from it on the renderer has no database and claims through the API's render gateway, and an old renderer recreated after the new API would keep claiming straight from the database beside the gateway

### What the containers do on the first start

The example below imagines a release whose one migration, `NNNN`, adds a nullable column.

**What runs.** `upgrade.py` pulls the new images (a source install builds them) while the old stack is still serving, stops the
stack, and starts it again on the new images. On that start, each of `tubematic-api`, `tubematic-mcp` and `tubematic-worker` calls
`migrate()` on its own first database touch (`tubematic-renderer` has no database) and sees `NNNN` is not in `schema_migrations`. The
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
