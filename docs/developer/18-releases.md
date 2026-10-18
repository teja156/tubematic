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
| A GitHub Release | Holds the release notes and two files: the tarball and a `CHECKSUMS.txt` for the tarball itself |
| Two GHCR images | `tubematic-backend` (from `renderer/Dockerfile` — this is the same image that runs as `tubematic-api`, `tubematic-mcp` and `tubematic-renderer`) and `tubematic-dashboard`, each pushed under a single version tag — see [Image tags](#image-tags) |
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
- **Migrations apply automatically.** Every one of the three backend containers calls `migrate()` on
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
