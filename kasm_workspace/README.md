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
| `registry/Tubematic/` | The workspace registry entry (schema 1.1) and its icon |

## The invariant: never rebuilt per release

The image never names a Tubematic version: the launch form picks one and the session downloads
it. Rebuild it **only** when the base image or the tooling in the Dockerfile changes. Do not add a
`COPY` of the repo; `scripts/tests/test_kasm_workspaces.py` fails if one appears.

## Building and pushing

```bash
kasm_workspace/build.sh                     # local: tubematic/tubematic-kasm-workspace:1.19.0
kasm_workspace/build.sh --image ghcr.io/<owner>/tubematic-kasm-workspace --push 1.19.0
```

The published image is built by the **Kasm workspace image** workflow
(`.github/workflows/kasm-workspace-image.yml`), run by hand from the Actions tab. The tag is the
Kasm release line the image targets. It is not a Tubematic version.

After the **first** push, open the package on GHCR and make sure it is **public**. Kasm pulls
it anonymously.

## Publishing the registry entry

The entry lives in this repo and is copied into the registry repo by hand. The registry repo is a
fork of Kasm's workspace-registry template, on its schema branch `1.1`:

```bash
cp -r kasm_workspace/registry/Tubematic <registry checkout>/workspaces/
# then commit and push on the 1.1 branch; the registry's own workflow rebuilds list.json
```

The registry's build copies every key of `workspace.json` into `list.json` verbatim, and
`launch_config` (including the form's own `file_mapping` for the answers) reaches Kasm that way.
**A registry entry cannot carry the workspace's File Mappings**, which is why the hook and bootstrap
are baked into the image rather than mapped like the testing workspace's.

When a release is cut, add its version to the front of `tubematic_version`'s `options`. Give it the
`(latest)` label, set it as the field's `value`, and remove `(latest)` from the previous version.
The list has no free-text fallback, so a version missing from it cannot be installed from the
form. The tests check that the list is newest first and that the default is the newest.

## Sizing

The registry entry asks for 4 cores and 8 GiB of memory, no GPU, and privileged mode.
- **Privileged** is needed for Docker-in-Docker.
- **No GPU:** an attached GPU crash-loops XFCE on an NVIDIA EGL failure.
- **Disk:** about 15 GB for the image, plus about 10 GB inside the session for Tubematic's own
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
