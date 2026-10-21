# Kasm Workspace — the published Tubematic workspace

The installable Tubematic workspace for [Kasm Workspaces](https://kasmweb.com/). A user adds a
workspace registry, installs this workspace, launches a session, and picks a **version** and an
**install method** on the launch form. A terminal then opens by itself, downloads that version, and
runs `onboard.py`, and the user finishes onboarding there.

This is not the QA environment. [`kasm_workspace_testing/`](../kasm_workspace_testing/README.md)
bakes a worktree's source into its image for testing a branch. This image bakes **no** Tubematic
source.

User-facing instructions are in
[Installing — Installing in Kasm Workspaces](../docs/user-guide/02-installing.md#installing-in-kasm-workspaces).
The design is in
[Development — `kasm_workspace/`](../docs/developer/17-development.md#kasm_workspace--the-published-workspace).

## Layout

| Path | What it is |
|---|---|
| `dockerfile_tubematic_kasm_workspace` | The image. It shares its base, tooling and dind `/tmp` patch with the testing Dockerfile, and has no source |
| `build.sh` | Builds (and, with `--push`, pushes) the image from `image/` |
| `image/kasm_post_run_root.sh` | Baked over Kasm's root post-run hook: it waits for the desktop and opens the installer terminal as `kasm-user` |
| `image/tubematic_bootstrap.py` | Reads the launch form, detects an existing install, then downloads and verifies, or clones, and runs `onboard.py` |
| `image/tubematic-installer` | What the terminal runs: the bootstrap, then always an interactive shell |
| `image/tubematic-installer.desktop` | Desktop launcher that reopens the installer |
| `registry/Tubematic/` | The workspace registry entry (schema 1.1) and its icon. Its version list is a seed |
| `sync_registry.py` | Writes the entry into a registry checkout with a given list of releases; run by `release.yml` |

## The invariant: never rebuilt per release

The image never names a Tubematic version: the launch form picks one and the session downloads
it. Rebuild it **only** when the base image or the tooling in the Dockerfile changes. Do not add a
`COPY` of the repo; `scripts/tests/test_kasm_workspaces.py` fails if one appears.

## Building and pushing

```bash
kasm_workspace/build.sh                     # local: tubematic/tubematic-kasm-workspace:1.19.0
kasm_workspace/build.sh --image ghcr.io/<owner>/tubematic-kasm-workspace --push 1.19.0
```

The published image is built and pushed **by hand**, from a machine logged in to `ghcr.io` with a
token that can write packages. No workflow builds it. The tag is the Kasm release line the image
targets. It is not a Tubematic version.

After the **first** push, open the package on GHCR and make sure it is **public**. Kasm pulls
it anonymously.

## Publishing the registry entry

Each release writes the entry for you. `release.yml`'s `publish-kasm-registry` job runs
`sync_registry.py`, which copies `registry/Tubematic/` into the registry repo's
`workspaces/Tubematic/` and replaces the launch form's version list with every published release,
newest first and the default. The registry repo is a copy of Kasm's workspace-registry template, on
its schema branch `1.1`, served at `https://registry.tejaswaroop.com/` (the URL the user guide tells
people to add). The job first checks the image above can be pulled anonymously, and writes nothing
if it cannot. So **push the image before the first release**.

To edit anything else on the entry (description, sizing, image tag), change
`registry/Tubematic/workspace.json` here; the next release carries it. The version list in this
repo is only a seed, so do not maintain it by hand.

The registry's build copies every key of `workspace.json` into `list.json` verbatim, and
`launch_config` (including the form's own `file_mapping` for the answers) reaches Kasm that way.
**A registry entry cannot carry the workspace's File Mappings**, which is why the hook and bootstrap
are baked into the image rather than mapped like the testing workspace's.

## Timezone

The image's clock is UTC (`TZ=Etc/UTC`, written to `/etc/localtime`). The session is Tubematic's
host, so every time Tubematic shows is in UTC. The testing image keeps its own fixed zone; the
published one is launched anywhere, so it names none.

## Sizing

The registry entry asks for 4 cores and 8 GiB of memory, no GPU, and privileged mode.
- **Privileged** is needed for Docker-in-Docker.
- **No GPU:** an attached GPU crash-loops XFCE on an NVIDIA EGL failure.
- **Disk:** about 15 GB for the image, plus about 15 GB inside the session for Tubematic's own
  images.
- **Persistent Profile Path:** recommended. Without one, the install, its data and the agent logins
  go when the session does.

## Live test (owed once v2.0.0 is published)

Use a fresh install, on the branch build:

1. Add the registry by URL. The workspace appears with its icon, description and sizing.
2. Install it and confirm the **launch form came through the registry**. This is the one
   assumption the published schema table does not back.
3. Launch. The baked hook fires with no File Mapping, the terminal opens by itself, and the desktop
   is usable (no blank screen).
4. Release method, newest version: the checksum is verified, onboarding completes, and the dashboard
   is reachable.
5. Source method: it clones the tag and onboarding completes.
6. Nothing the install created under `~` is root-owned.
7. Close the terminal: the desktop launcher reopens it. Relaunch: the install is detected and not
   clobbered. Pick a different version: it is refused, with the upgrade pointer.
8. Serve a tarball with a corrupted checksum: it aborts before extraction.
9. Check that `/tmp` is not hidden and that `/dockerstartup/tubematic_launch_selections.json` is
   readable.
10. The top bar of the dashboard shows UTC.
