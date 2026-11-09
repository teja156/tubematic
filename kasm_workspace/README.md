# The Tubematic workspace for Kasm Workspaces

This folder builds the Tubematic workspace that people install in
[Kasm Workspaces](https://kasmweb.com/), a platform that serves desktop sessions in a browser. A
user adds the workspace registry, installs the workspace and launches a session. The launch form
asks for a Tubematic version and an install method. A terminal then opens in the session,
downloads that version and runs `onboard.py`.

The image holds no Tubematic source. To test a branch, use
[`kasm_workspace_testing/`](../kasm_workspace_testing/README.md), whose image is built from a
worktree.

| To read about | Go to |
|---|---|
| Installing and using the workspace | [Installing in Kasm Workspaces](../docs/user-guide/02-installing.md#installing-in-kasm-workspaces) |
| How the launch hook, the bootstrap and the registry entry work | [Development: `kasm_workspace/`](../docs/developer/17-development.md#kasm_workspace-the-published-workspace) |
| The release job that publishes the registry entry | [Publishing the Kasm registry entry](../docs/developer/18-releases.md#publishing-the-kasm-registry-entry) |

## What is in this folder

| Path | Contents |
|---|---|
| `dockerfile_tubematic_kasm_workspace` | The image. It has the same base image and tooling as the testing image, and the same patch that keeps the nested Docker daemon from hiding `/tmp` |
| `build.sh` | Builds the image from `image/`. With `--push` it also pushes it |
| `image/kasm_post_run_root.sh` | Replaces Kasm's root post-run hook. It waits for the desktop and opens the installer terminal as `kasm-user` |
| `image/tubematic_bootstrap.py` | Reads the launch form's answers and looks for an existing install. It downloads and verifies the release, or clones the tag, then runs `onboard.py` |
| `image/tubematic-installer` | The command the terminal runs: the bootstrap, then an interactive shell |
| `image/tubematic-installer.desktop` | The desktop icon that opens the installer again |
| `registry/Tubematic/` | The workspace registry entry (`workspace.json`, registry schema 1.1) and its icon |
| `sync_registry.py` | Writes the entry into a checkout of the registry repository with a given list of releases. `release.yml` runs it |

## When to rebuild the image

Rebuild the image when its base image or the tooling in the Dockerfile changes. A Tubematic
release needs no rebuild, because the image names no Tubematic version: the launch form picks one
and the session downloads it.

Do not add a `COPY` of the repository to the Dockerfile.
`scripts/tests/test_kasm_workspaces.py` fails if one appears.

## Building and pushing

```bash
kasm_workspace/build.sh                     # local: tubematic/tubematic-kasm-workspace:1.19.0
kasm_workspace/build.sh --image ghcr.io/<owner>/tubematic-kasm-workspace --push 1.19.0
```

```
build.sh [--image NAME] [--push] [--no-cache] [tag]
```

- The tag is the Kasm release line the image targets, and defaults to `1.19.0`. It is not a
  Tubematic version.
- No workflow builds the published image. Build and push it by hand, from a machine that is
  logged in to `ghcr.io` with a token that can write packages.
- After the first push, open the package on GHCR and make it public. Kasm pulls it without
  logging in.

## Publishing the registry entry

Each release publishes the entry. `release.yml`'s `publish-kasm-registry` job runs
`sync_registry.py`, which copies `registry/Tubematic/` into the registry repository's
`workspaces/Tubematic/` and replaces the launch form's version list with the published releases,
newest first. The newest is the form's default. The registry is served at
`https://registry.tejaswaroop.com/`, the URL the install guide tells people to add.

- Push the image, and make it public, before a release that names it. The job checks that the
  entry's image can be pulled without logging in, and writes nothing if it cannot.
- To change the description, the sizing or the image tag, edit
  `registry/Tubematic/workspace.json`. The next release carries the change.
- Leave the version list in that file alone. It is a placeholder that the job replaces on each
  release.

A registry entry carries the launch form (`launch_config`) to Kasm. It cannot carry File Mappings,
the Kasm workspace setting that places a file in the session. For that reason the hook, the
bootstrap and the desktop icon are built into the image.

## Session settings

The registry entry asks for 4 cores, 8 GiB of memory, no GPU and privileged mode.

- Privileged mode is needed for Docker-in-Docker, because Tubematic's containers run inside the
  session.
- The entry asks for no GPU (`gpu_count` is 0), because a GPU attached to this desktop makes XFCE
  fail in a loop on an NVIDIA EGL error.
- The image takes about 15 GB of disk. The install inside the session needs the same free disk as
  any install, about 15 GB (see [Prerequisites](../docs/user-guide/02-installing.md#prerequisites)).
- Set a Persistent Profile Path on the workspace. Without one, the install, its data and the
  agent logins are deleted when the session ends.
- The image's clock is UTC (`TZ=Etc/UTC`, also written to `/etc/localtime`). The session is the
  machine Tubematic runs on, so the dashboard shows times in UTC.
