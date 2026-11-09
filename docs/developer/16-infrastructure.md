# Infrastructure

Everything runs from `docker-compose.yml`. Five services, six volumes, one network, one cron entry.

> **Start the stack with `python3 scripts/service.py start` (or through onboarding), not a bare
> `docker compose up -d`.** Both create any missing data directory and reconcile the volume device
> paths first. A bare `up` fails outright when a device path is missing — these are `local`-driver
> bind volumes, which never create one — and against a volume whose recorded device no longer
> matches it silently mounts the old path, because Compose prompts on a device change and answers
> "no" non-interactively.

---

## Services

### `tubematic-api`

| | |
|---|---|
| Build | `renderer/Dockerfile`, context = repo root, tagged `tubematic-renderer-image` |
| Ports | `127.0.0.1:4000` Flask; 4443, the render gateway over HTTPS, on the Compose network only (not published) |
| Command | `entrypoint.sh python3 /app/api/server.py` |
| Restart | `unless-stopped` |
| Healthcheck | `curl -fs localhost:4000/health`, every 15s, 5 retries |
| Mounts | all six data volumes, plus `/etc/localtime` and `/etc/timezone` read-only |
| Secrets | `api_token`, `builtin_renderer_token`, `render_tls_key`, `render_tls_cert` |
| Depends on | nothing |

Flask, and in a thread of the same process the render gateway (`TUBEMATIC_GATEWAY_PORT=4443`), the
second Flask app every renderer calls — see [HTTP API — The render gateway](05-http-api.md#the-render-gateway).
The healthcheck names only port 4000, so this container's health says nothing about the gateway.
Three variables bound what renderers' uploads can put on the output volume, which holds the
database too; all are unset in Compose, so their defaults apply. `TUBEMATIC_MAX_OUTPUT_BYTES`
(8 GiB) caps one uploaded render, `TUBEMATIC_MAX_CONCURRENT_UPLOADS` (4) caps the uploads streaming
at once, and `TUBEMATIC_MIN_FREE_BYTES` (2 GiB) is the free space an upload must leave — see
[HTTP API — The render gateway](05-http-api.md#the-render-gateway) for the answers past each.
No variable sets the gateway's time bounds; they are fixed (see
[HTTP API — Time bounds](05-http-api.md#time-bounds)).

**Uploads land in `output_videos/.gateway-uploads/` first.** The gateway writes each upload there,
then renames it to `<project_id>/<video_id>.mp4` once it is complete — a rename, since the directory
is on the same volume. It is the gateway's own: it is created when missing (with the same
permissions as everything else the container writes there, so the host user can delete it), the
temporary files (`*.upload`) a crash mid-upload leaves behind are deleted when the gateway starts,
and any older than six hours that no upload is writing are deleted whenever an upload is admitted.
Only `*.upload` files are ever deleted there, and nothing in it is followed; a symlink in place of
the directory itself is refused (every upload then fails, and the gateway logs why). Keeping these
files out of the project directories is what keeps them away from everything that lists videos.
When the TLS pair is missing, or its two files are not a usable pair, the gateway does not start
and logs an error saying so; the API still serves the dashboard, and no renderer (the built-in one
included) can reach it until the pair is put right and the API is restarted — see
[The secrets directory](#the-secrets-directory).

**4443 is not published by `docker-compose.yml`.** The built-in renderer reaches it as
`https://tubematic-api:4443` over the Compose network, which needs no published port. A renderer on
another machine would need it published, and nothing in this release does that.

`tubematic-api` deliberately depends on no other service. The dashboard and the poller reach the
pipeline through Flask, and that path has to keep working when the MCP server is down.

### `tubematic-mcp`

| | |
|---|---|
| Image | `tubematic-renderer-image` — no `build:` section |
| Ports | `127.0.0.1:4100` MCP |
| Command | `entrypoint.sh python3 /app/mcp/server.py` |
| Restart | `unless-stopped` |
| Healthcheck | `curl -fs localhost:4100/health`, every 15s, 5 retries |
| Mounts | `db-data`, `jobs-data`, `scenes-generated`, `logs-data`, `backups-data` — and nothing else |
| Secrets | `mcp_token` |
| Depends on | `tubematic-api: service_healthy` |

**The mounts are the minimum its tools actually use**, which is narrower than the API's. No
`output-videos`: nothing in `mcp/` reads or writes rendered output, and the cached voice previews
that live there are written by Flask's preview endpoint, not by a tool. No `/etc/localtime`: no tool
formats a local timestamp. Adding either "to be safe" would widen the reach of a server that
compiles agent-authored scene code and renders it in a headless browser — a bearer token guards the
door, but the narrowest reach is still the right default behind it.

`logs-data` is a write path, not a read one: MCP appends its own `mcp.*.jsonl` and never reads
another service's — Flask is the only reader. `backups-data` is a write path too, and it is not
optional: every one of the three services that open the database calls `migrate()` itself rather than assuming
another process already has, and each one that migrates must be able to back up first — one that
silently could not would fail closed on every start. See [Backups](#backups).

**`depends_on` here is startup ordering only, and mild at that.** Schema creation no longer races —
`migrate()` (see [Database — Migrations](03-database.md#migrations)) holds a real write lock for its
whole run, so two containers reaching a brand-new database at once simply serialize rather than
corrupt anything. Waiting for a healthy Flask before starting MCP is a preference for a predictable
startup order, not a correctness requirement. Nothing gates the MCP server at runtime once it is up —
a later Flask crash does not stop it, and Flask never depends on MCP in either direction.

### `tubematic-worker`

The same image, no `build:` section, `command: python3 /app/api/worker.py`. No published ports, no
healthcheck, `depends_on: tubematic-api: service_healthy`. It runs the background passes that are not
rendering — publishing, Auto Pilot, analytics, price sync, retention, notifications and the
stalled-voicing check — see [The Worker](12-the-worker.md).

Its mounts are `output-videos`, `jobs-data`, `db-data`, `logs-data`, `backups-data` and the two
timezone files, and nothing else. `output-videos` and `jobs-data` because retention deletes a video's
mp4 and job directory, and the AI review reads the uploaded mp4 and the job's scene-config; the
timezone files because Auto Pilot's daily numbers and a scheduled post's wall time are host-zone days.
No `scenes-generated`: it never reads or writes a scene. It holds no secret file: the API keys it uses
(Gemini for the review, postforme for publishing) are rows in the settings table.

Like the renderer, its `command:` is the bare interpreter, so it never runs `entrypoint.sh` and
applies its own umask at startup.

### `tubematic-renderer`

The same image, no `build:` section, `command: python3 /app/api/render_agent.py`. The built-in
renderer. No published ports, `shm_size: 2gb` for Chromium, and
`depends_on: tubematic-api: service_healthy`. It renders and tests its GPU, and nothing else — see
[Rendering and Review](11-rendering-and-review.md).

**It has no database and no output volume.** It talks to the render gateway in `tubematic-api` over
HTTPS exactly as a renderer on another machine would: it claims a video, downloads the job's files as
one bundle and uploads the finished mp4. So `db-data`, `output-videos` and `backups-data` are not
mounted — the gateway writes the upload into the library, the worker runs the AI review, and this
container never migrates anything. What it mounts:

| Mount | Why |
|---|---|
| `scenes-generated` | Renders compile the shared generated-scene tree, as they always did (a remote renderer would stage the bundle's copy instead) |
| `jobs-data`, **read-only** | The stills server below reads a video's job files; renders use the bundle |
| `logs-data` | Its own JSONL log for the dashboard's Logs page |
| `/etc/localtime`, `/etc/timezone` | Log timestamps in the host zone |

| Environment / secret | |
|---|---|
| `TUBEMATIC_GATEWAY_URL=https://tubematic-api:4443` | Where the gateway is |
| `TUBEMATIC_RENDERER_BUILTIN=1` | Authenticate as the built-in renderer rather than from an enrollment state file |
| `builtin_renderer_token` | Its credential, read on every request |
| `render_tls_cert` | The only certificate it trusts. It never gets the key |

It runs one child process beside its
renders: the Cartoon 3D stills server on `TUBEMATIC_STILLS_PORT` (4455), reachable on the Compose network only,
which the MCP container's gate and preview tools use so their stills render on this container's GPU
(see [Rendering and Review](11-rendering-and-review.md#the-stills-server)).

Its `command:` is the bare interpreter, so unlike the API and the MCP server it **never runs
`entrypoint.sh`** — which is why it applies its own umask at startup rather than inheriting one.

It is the only service that can get a GPU, and only through the override below. Its GPU test
travels to the API in its heartbeats, so the API, which has no GPU, never guesses.

#### GPU override

`docker-compose.yml` reserves no GPU, and cannot: a device reservation Docker cannot satisfy stops
the container from being created ("could not select device driver"), and the file is the same on
every install. Instead the `gpu` onboarding step (`onboard/gpu.py`) writes
`~/.tubematic-data/compose.gpu.json`, which changes `tubematic-renderer` only:

- `deploy.resources.reservations.devices`: `driver: nvidia`, `device_ids: [<the GPU's UUID>]`,
  `capabilities: [gpu]`. Compose requires `capabilities`, and refuses `count` alongside
  `device_ids`.
- `NVIDIA_DRIVER_CAPABILITIES=graphics,utility`. `graphics` brings the EGL/OpenGL driver libraries
  WebGL needs, and `utility` brings `nvidia-smi`. Toolkit 1.20 injects the graphics libraries for any
  GPU request anyway, but older toolkits default to `compute,utility` and leave them out.
- `TUBEMATIC_GPU_UUID`, `TUBEMATIC_GPU_NAME`, and `TUBEMATIC_HOST_GPUS` (every NVIDIA GPU the host
  had when the step ran, for the dashboard's list).

It is JSON, which Compose reads as YAML, so onboarding needs no YAML library to write and read it.
It lives under the data root, not the install, because upgrades install into a new directory.

`onboard/actions.py::_compose()` adds `-f docker-compose.yml -f <override>` when the file exists, and
is the bare `docker compose` otherwise, so an install without a GPU keeps the argv it always had.
Everything that runs `up` goes through it: the onboarding steps, `scripts/service.py` and
`upgrade.py`. **A hand-run `docker compose up` does not**, and recreates the renderer without the
GPU. That is safe, because the renderer then simply renders on the CPU, but it is why the docs and
hints say `scripts/service.py start`. Naming files with `-f` also stops Compose loading a stray
`docker-compose.override.yml`, which only very old installs ever had.

`upgrade.py` refuses before stopping anything when the override names a GPU Docker cannot hand
over (`gpu.py::override_problems`: no `nvidia` runtime, no driver, or the GPU is gone). Without
that check, the upgrade would stop the stack and then fail at `up`. How the renderer decides whether
the GPU works is in [Rendering and Review](11-rendering-and-review.md#the-gl-renderer).

### `tubematic-dashboard`

Built from `dashboard/Dockerfile`. Port 3000. `RENDERER_URL=http://tubematic-api:4000`. It mounts
**only** `output-videos`, read-only — no database access at all.

It also has **no** `logs-data` mount, deliberately. The Logs page reads through Flask's `GET /logs`,
so the dashboard has no filesystem route to a log file and no Docker socket — the two ways a log
viewer usually acquires far more privilege than it needs.

It deliberately has **no** `/etc/localtime` mount, unlike the API, the worker and the renderer: a second source of
truth could disagree with the first, so it learns the host zone over HTTP instead. See
[HTTP API — Time](05-http-api.md#time).

**Healthcheck:** `wget -q -T 5 --spider http://127.0.0.1:3000/`, every 15s, 5 retries, with a 45s
`start_period` — the same shape as the API and MCP checks above (which use 30s), but `wget` rather
than `curl`. The `start_period` is the part that is easy to leave off and expensive to leave off:
failures inside it do not count toward `retries`, so without one the retry budget starts burning at
container start and a slow boot is indistinguishable from a broken service — the container is
declared unhealthy on a fixed schedule whether or not it was about to come up. It is a start budget,
not a timeout: a service that answers in two seconds is marked healthy in two seconds.

**The address is `127.0.0.1`, never `localhost`, and that is the difference between a probe that
works and one that can never succeed.** A container's `/etc/hosts` maps `localhost` to both
`127.0.0.1` and `::1`, while the server here binds IPv4 only (`HOSTNAME=0.0.0.0`). BusyBox `wget` —
the only HTTP client in the `node:20-alpine` runtime — resolves `localhost` to the IPv6 address
first and does **not** fall back to IPv4 when the connection is refused, so the probe fails every
time, immediately, with nothing logged anywhere: the container simply never becomes healthy. The
`curl` probes on the API and MCP containers tolerate `localhost` only because curl retries the other
address family, which makes their URL shape a dangerous thing to copy. All three use `127.0.0.1` for
that reason, and `scripts/tests/test_gen_release_compose.py` fails the build if any healthcheck
reintroduces the name. `dashboard/Dockerfile`'s
runtime stage is `node:20-alpine`, which ships BusyBox `wget` and no `curl` at all, unlike the
Debian-based API/MCP image. Without any healthcheck here, Docker reports a container "healthy" the
instant it is running, before Next.js has bound its port — a real race a release-workflow smoke test
would hit directly.

### Four containers, one image

Only `tubematic-api` declares `build:`. The MCP server, the worker and the renderer reuse the tag,
and the only difference between the four is the compose `command:`. One build covers all of them —
a rebuild of `tubematic-api` is a rebuild of the other three.

### Why the ports bind to loopback

Flask and the MCP server publish on `127.0.0.1` rather than every interface. This costs nothing
internally: container-to-container traffic goes over the compose network by service name and never
touches a published port, which is why the worker can use the database and the renderer can reach
the render gateway with no `ports:` entry at all. Publishing exists only for callers on the host — the poller, the status script, `curl`
and the agent's MCP client, all of which use `localhost`.

The MCP port is the one that matters. Its tools mutate pipeline state, write files, spend money on
paid APIs and render agent-authored scene code, so it has both a token and the narrowest binding.

The dashboard's port 3000 is left on all interfaces in a development checkout, so the UI stays
reachable from another device on the network — behind its login. A release install binds it to
`127.0.0.1` too; to reach it from elsewhere, put HTTPS in front of it (see below).

## Authentication

Three containers listen, and each one checks every request (the API on two ports):

| Service | Callers | Check |
|---|---|---|
| `tubematic-dashboard` | browsers | A signed session cookie, set after the dashboard password |
| `tubematic-api` | the dashboard, the poller, `vqa/edit_settings.py`, `curl` | `Authorization: Bearer <api_token>` |
| `tubematic-api`, render gateway (4443) | renderers | TLS with a pinned certificate, then `Authorization: Bearer <renderer credential>` |
| `tubematic-mcp` | the agent CLIs | `Authorization: Bearer <mcp_token>` |

**Sessions for people, tokens for programs.** A browser cannot hold a bearer token safely, and a
cron job cannot type a password, so each kind of caller gets the one that suits it. The only
unauthenticated routes are the health probes (`/health` on both servers, `/render/health` on
Flask), which return nothing a caller could use.

**The worker and the renderer have no check because they have nothing to protect**: neither
publishes a port, and the worker listens on none. The renderer's one listener, the stills server, is
on the Compose network only. The renderer is a *caller* instead: of the render gateway, with its own
credential.

The dashboard makes one outbound call of its own: the [update check](15-dashboard.md#update-check)
reads `api.github.com` at most every two hours, unauthenticated. Without internet access it fails
quietly and nothing else is affected.

### The secrets directory

`~/.tubematic-data/secrets/` holds one file per secret. The four tokens are each a random 256-bit
value; the last two are the render gateway's TLS pair:

| File | Read by | What it is |
|---|---|---|
| `api_token` | Flask, the dashboard, the poller, host scripts | Flask's bearer token |
| `mcp_token` | the MCP server, the agent CLIs | The MCP server's bearer token |
| `session_secret` | the dashboard | The key its session cookies are signed with |
| `builtin_renderer_token` | the render gateway, the built-in renderer | The built-in renderer's credential at the gateway |
| `render_tls_key` | the render gateway (`tubematic-api` only) | The gateway's EC P-256 private key |
| `render_tls_cert` | the render gateway, the built-in renderer | Its self-signed certificate, the one every renderer pins. Why it is pinned and never rotated: [HTTP API — TLS and the certificate pin](05-http-api.md#tls-and-the-certificate-pin) |

The TLS pair is made by `tubematic_core.auth.ensure_secrets` with the `cryptography` package, which is
why onboarding's and the upgrade's own dependency bootstrap (`onboard/bootstrap.py::ensure_deps`)
installs it: a single `--step` run, or an upgrade, reaches the secrets before `python_deps` has run.
Onboarding's `auth` step creates them, and so does any stack start or upgrade that finds one missing.
**The four tokens are the only secrets that are ever replaced**, and only by `onboard.py
--rotate-tokens`, which rewrites them in place and never touches the TLS pair. Compose mounts each file
read-only at `/run/secrets/<name>` (a top-level `secrets:` block with `file:` sources), so no secret
is ever an environment variable and `docker inspect` shows none. A missing file stops `up` with "bind
source path does not exist": the stack fails closed rather than starting open.

**The directory is `0700` but the files are `0644`, on purpose.** Compose mounts each file on its own,
which bypasses the directory's permissions inside the container — and the dashboard runs as uid
1001, not your user, so a `0600` file would be unreadable there. The `0700` directory is what keeps
other users on the host out. The TLS key follows the same rule, so there is one rule for every file;
only `tubematic-api` mounts it.

**A rotation rewrites each file in place.** A bind mount pins the inode it was started with, so an
atomic rename would leave every running container reading the old value until it was recreated.

**The TLS pair is made again only as a pair, and a new pair is a new pin.** When either file is
missing or empty, `tubematic_core/auth.py::_ensure_tls` writes a fresh key *and* certificate: a
lone half is useless without its partner. Each half is written to a temporary file and renamed into
place, the half still present first, so an interrupted repair leaves the missing name missing and
the next start simply makes the pair again; it never leaves two files that look whole but do not
belong together. (A rename is fine here, unlike for a rotated token: the gateway loads the pair only
when it starts, so a new pair needs `tubematic-api` and `tubematic-renderer` restarted anyway, and a
restarted container mounts the new file.) The new certificate has a new
[pin](05-http-api.md#tls-and-the-certificate-pin), so after it:

- the built-in renderer follows on its own once both containers are restarted (it reads the
  certificate from the same directory);
- every enrollment token issued before is useless — it carries the old pin, and a renderer enrolling
  with it refuses the new certificate before sending anything — so discard them and issue new ones;
- every remote renderer is cut off, since it trusts only the certificate it was enrolled with, and
  must be [enrolled again](05-http-api.md#enrollment) with a new token. Re-enrolling the same
  machine keeps its renderer row (its id, its enabled switch and its render timings): the renderer
  keeps its machine id in its state directory, and `renderers.py::enroll` updates the row with that
  machine id instead of adding one.

Two non-empty files are never replaced, **even when they are not a usable pair** — a key and a
certificate restored from different backups, or a truncated file — because replacing them would
change the pin silently. The gateway then logs `render gateway not started: its TLS key and
certificate cannot be used as a pair` and does not start, while the API serves the dashboard as
usual. To recover, either restore `render_tls_key` and `render_tls_cert` together from the same
backup (the pin is unchanged and nothing needs enrolling again), or delete both and run
`python3 scripts/service.py start` to make a new pair (a new pin, with the consequences above);
then restart `tubematic-api` and `tubematic-renderer`.

The admin password is not a file: its scrypt hash is a `settings` row (`admin_password_hash`) that is
outside the settings API, so `GET /settings` never returns it and `POST /settings` cannot write it.

### How each caller gets its token

- **The built-in renderer** reads `builtin_renderer_token` and `render_tls_cert` on every request,
  and the gateway reads the token on every request too, so a rotation needs no restart of either.
- **The dashboard** reads `api_token` and `session_secret` on every request rather than once at
  start-up, so a new password or a rotation takes effect without restarting it.
- **The poller** adds the token to every request it makes to Flask, reading the file each time,
  because it is a long-running supervisor that outlives a rotation. It sends the token to Flask and
  to nothing else.
- **The agent CLIs never hold the token in their own config.** Each one is pointed at the file:
  Claude Code and Codex run `scripts/mcp_auth_header.py` on every connection (Claude's
  `headersHelper`, Codex's `http_headers_helper`), and OpenCode reads it through its `{file:}`
  substitution. See [The agent layer](07-agent-layer.md) for how each is registered.

### Changing the password and rotating tokens

| Command | Effect |
|---|---|
| `python onboard.py --set-password` | Sets or changes the dashboard password. A change also rotates `session_secret`, which signs every browser out |
| `python onboard.py --rotate-tokens` | Replaces the four tokens (never the TLS pair), restarts the API, MCP and dashboard containers (they hold the old values), and has OpenCode reload its config. It waits for in-flight work like `upgrade.py` does; `--force` proceeds anyway. If a restart or a reload fails it still tries the rest, then **exits non-zero** naming what to run: the new tokens are already in place, so whatever kept an old one cannot authenticate until it picks them up |

Claude Code, Codex and the built-in renderer need nothing after a rotation, because each reads the
file on every connection. Signing in again in the browser is the only other visible effect.

Failed logins back off install-wide: five free attempts, then an exponentially growing wait of up
to 15 minutes. Only one password check runs at a time — see
[HTTP API — Dashboard login](05-http-api.md#dashboard-login) for why. It is install-wide rather than per client because every login reaches Flask from the
dashboard container, and a forwarded client address is spoofable. Restarting the API clears it.

### Using the dashboard from another machine

Put HTTPS in front of port 3000: a reverse proxy such as Caddy or nginx that terminates TLS, or a
private network such as Twingate. Step-by-step guides are in
[Remote Access](../user-guide/09-remote-access.md). The session cookie is marked `Secure` whenever the
request arrived over HTTPS — directly, or as reported by the proxy's `X-Forwarded-Proto` header — and
is `HttpOnly` and `SameSite=Strict` always. Over plain HTTP, the password and the cookie cross the
network readable. Tubematic does not manage certificates itself.

**The login redirect is relative, so no proxy needs to forward the public host name.** Middleware
builds its `/login` URL from `req.url`, which in the standalone server is the server's own listen
address (`http://0.0.0.0:3000/…`, from `HOSTNAME`), never the browser's `Host`. Next.js then rewrites
a same-origin `Location` to a relative path before sending it, so the browser resolves `/login` against
whatever address it used. That is why the dashboard sets no `trustHostHeader` and reads no
`X-Forwarded-Host`: a proxy that forwards only `X-Forwarded-Proto` is enough.

## Volumes

All six are named volumes with `o=bind` device paths under `${HOME}`:

| Volume | Device | Holds |
|---|---|---|
| `db-data` | `~/.tubematic-data/data` | The SQLite database |
| `jobs-data` | `~/.tubematic-data/jobs` | Per-video working files |
| `output-videos` | `~/.tubematic-data/output_videos` | Rendered mp4s and cached voice previews |
| `scenes-generated` | `~/.tubematic-data/scenes/generated` | Agent-authored scene TSX |
| `logs-data` | `~/.tubematic-data/logs` | Structured JSONL logs, one file per service per day |
| `backups-data` | `~/.tubematic-data/backups` | Pre-migration database snapshots — see [Backups](#backups) |

Compose pins `name: tubematic` explicitly, so volume and network names do not shift with the
directory basename — the permanent fix for two checkouts colliding.

`${HOME}` rather than `${PWD}` is required: cron strips the environment to `HOME`, `LOGNAME`, `PATH`
and `SHELL`.

Because they are `o=bind`, **removing one of these volumes does not delete the host files.** Docker
only drops its own record, despite the warning it prints.

> **`docker volume prune` is dangerous here.** These are the database and the entire video library.
> Remove them by name, deliberately, or not at all. `docker image prune` without `-a` is safe — it
> only removes untagged images.

### Backups

`backups-data` (`~/.tubematic-data/backups` on the host, `/backups` in the containers) holds
pre-migration snapshots of the database file — nothing else. It is mounted in the three services
that open the database (`tubematic-api`, `tubematic-mcp`, `tubematic-worker`), each of which calls
`migrate()` itself, but **deliberately not in `tubematic-dashboard`** or `tubematic-renderer`, which
have no database access: the dashboard has no database access at
all, and a backup is a full copy of a database whose `settings` table is the credential store, so it
has no reason to be able to read or write one.

A snapshot is written only when `migrate()` is actually about to apply something — never on a
no-op start, and never for a brand-new database that has nothing to lose. It is named
`tubematic-before-v<version>-<timestamp>.db`, taken with SQLite's own online backup API rather than a
file copy: the database runs in WAL mode with concurrent writers, and a plain file copy taken mid-
transaction produces a torn file that looks fine until the day someone restores it. If the backup
itself fails, the migration does not run either — see
[Database — Migrations](03-database.md#migrations).

The snapshot's permission *bits* are set to match the source database's rather than left at SQLite's
own default — it is a full copy of the same credential-store file, so it must never come out more
permissive than the file it was copied from. Bits are all that's copied, though, not ownership: the
containers that migrate run as root, so every snapshot lands **owned by root**, unlike the live
database, which `renderer/entrypoint.sh` deliberately keeps group-writable by the host user. A
backup that fails partway (disk full, mid-copy) is deleted rather than left behind: a
correctly-named, partially-written `.db` file here would be indistinguishable from a good one until
someone actually tried to restore it.

**Nothing prunes this directory automatically.** Every upgrade that has anything pending adds **at
least one** file — usually two: the backup happens before `migrate()` takes its write lock, not
inside it, so when more than one of the three containers that migrate reaches that point before any of
them has committed, each writes its own snapshot (the loser gets a collision-suffixed name rather
than overwriting the first). Nothing ever removes one. Clean it out by hand if it grows large; the
timestamp in each filename is enough to tell which ones are safe to delete.

**To restore one.** This discards every database row written since the snapshot was taken — every
video, comment and setting change — while the mp4s and job files those rows point to are untouched
(this section covers the database file only), so a restore after real usage leaves orphaned output
files and vanished rows behind. Only do this alongside reverting the code too — see
[Upgrading — Rollback policy](../user-guide/07-upgrading.md#rollback-policy) for the full
procedure this is one step of:

```bash
docker compose stop tubematic-api tubematic-mcp tubematic-worker tubematic-renderer
sudo cp ~/.tubematic-data/backups/tubematic-before-vX.Y.Z-<timestamp>.db ~/.tubematic-data/data/tubematic.db
rm -f ~/.tubematic-data/data/tubematic.db-wal ~/.tubematic-data/data/tubematic.db-shm
docker compose start tubematic-api tubematic-mcp tubematic-worker tubematic-renderer
```

`sudo` is required for the `cp` because the backup is root-owned (see above) — a plain copy as
yourself fails with `Permission denied`. The `-wal`/`-shm` sidecars belong to the file you are
replacing, not the backup — removing them forces a clean reopen instead of replaying stale WAL
frames against the restored file. A restored snapshot is, by construction, from just before some
migration ran, so the services that come back up will migrate it forward again on their first
`migrate()` call.

## Ports

| Port | Service |
|---|---|
| 3000 | Dashboard — all interfaces in a checkout, `127.0.0.1` in a release install; behind its login either way |
| 4000 | Flask API — `127.0.0.1` only |
| 4100 | MCP server — `127.0.0.1` only |
| 4443 | The render gateway (HTTPS) — Compose network only, not published |
| 4455 | The renderer's stills server — Compose network only, never published |
| 3001 / 4001 | The end-to-end test stack |

Container names are fixed, so two checkouts cannot run their stacks simultaneously.

---

## Images

### `renderer/Dockerfile`

`node:20-slim`, plus `chromium`, `ffmpeg`, `python3`, `curl`, and three font packages:
`fonts-liberation`, `fonts-noto-color-emoji`, `fonts-freefont-ttf`.

> **The container has no DejaVu fonts.** A hardcoded DejaVu path works on most developer machines and
> fails here, and no host-run test catches it. Reuse the existing font candidate lists rather than
> picking a path. Note also that Pillow's `load_default()` returns a bitmap font with no `.size` or
> stroke support, so a fallback using those raises rather than merely looking worse.

No NVIDIA library is installed: the NVIDIA Container Toolkit mounts the host driver's own libraries
and `10_nvidia.json` into a container that is given a GPU, so they always match the host's driver.
`libglvnd0` and `libegl1`, which load them, come in with `chromium`.

It sets `PUPPETEER_EXECUTABLE_PATH` and Chromium flags (`--disable-dev-shm-usage --no-sandbox`),
creates `/data`, `/jobs`, `/output_videos`, `/logs`, then installs three source trees in
dependency-first order so a source edit does not invalidate the dependency layers:

1. `renderer/remotion/package*.json` → `npm ci` → the rest of the Remotion project
2. `renderer/api/requirements.txt` → pip → `renderer/api/`
3. `mcp/requirements.txt` → pip → `mcp/`

Finally it copies `tubematic_core/` to `/app/lib` and sets `PYTHONPATH=/app/lib`.

> **`/app/lib`, not `/app`.** `/app` also holds `api/`, `mcp/` and `remotion/`, so putting it on
> `sys.path` would make all of them importable as a side effect — including `/app/mcp`, which
> collides by name with the MCP SDK that `fastmcp` imports. A directory holding exactly one package
> has no side effects to reason about.

`/logs` is created in the image as well as being a bind mount, so a stack that does not mount it —
the e2e test stack does not — still gets working logs, just without persistence.

The build context is the **repo root**, because it needs all four.

### `renderer/entrypoint.sh`

Runs for `tubematic-api` and `tubematic-mcp`. It fixes database and log-directory permissions, then
`exec`s whatever process it was given, so each container ends up with exactly one foreground
process. The Dockerfile's `CMD` supplies the Flask process as the default; compose overrides it per
service.

That shape matters, and it is why the script is a preamble rather than a launcher. It used to start
Flask in the background and `exec` the MCP server, putting two processes in one container. When
Flask died, the MCP server still held PID 1: the container stayed up, reported at most `unhealthy`,
and `restart: unless-stopped` had nothing to act on — a dead API behind a container that looked
alive. One foreground process per container is what makes the restart policy mean something.

Both containers therefore run the same permission block. It is idempotent and every operation is
failure-tolerant, so the two racing at startup is harmless.

The permission logic has two branches:

- **Normal:** the data directory is owned by a host user. Sets `umask 002`, `chgrp`s the database and
  its WAL/SHM sidecars to that directory's group, `chmod 0660`, and sets the setgid bit on the
  directory so new sidecars inherit the group.
- **Fallback:** the data directory is root-owned, which happens when Docker auto-created a missing
  bind-mount source. Falls back to world-writable and prints a warning to stderr.

Both branches also apply to the shared logs directory (`/logs`, or `TUBEMATIC_LOG_DIR`). In the
normal branch it gets the host group, group read, write and search (`g+rwx`) and setgid; in the fallback it becomes
world-writable. The containers write there as root and would not need it, but the directory has one
writer that is not a container: `poll.py` runs from cron as the host user and appends
`poll.<date>.jsonl` next to the services' files. A root-owned logs directory used to keep every poll
entry off the dashboard, and nothing repaired it. Setgid keeps the files the containers create there
in the host group too.

If you see that warning, something created the data directory before onboarding did.

**The normal branch cannot help a database that does not exist yet.** It runs at container start,
before anything has created `tubematic.db`, so the `chgrp`/`chmod` it means to apply find nothing
and silently succeed (every operation is failure-tolerant by design). The file is created moments
later by the first process to touch it, and only the `umask 002` plus the directory's setgid bit
make it group-accessible. That is enough for a host user in the right group — and it is *not*
something to rely on from a process that is not.

**Reading the database from the host needs write access, and that surprises people.** SQLite in WAL
mode requires write access to the `-shm` sidecar even for a pure `SELECT`, so a read-only caller
fails with `attempt to write a readonly database` on a statement that plainly writes nothing. It
reads like a bug in the query and is not. A host-side reader must therefore be a user who can write
these files; anything else — CI, another account, a hardened service — should read the database from
inside a container that owns it rather than across the mount.

### `dashboard/Dockerfile`

Multi-stage on `node:20-alpine`: install, build with `output: "standalone"`, then a runner stage that
copies only the standalone bundle and static assets and runs as a **non-root user**.

---

## Cron

One entry, written by onboarding:

```
*/30 * * * * <python> <repo>/scripts/poll.py >> ~/.tubematic-agent/logs/cron.log 2>&1
```

**The line names no agent.** The poller asks the API which agent each video belongs to — its binary,
workspace and model — on every tick, so installing, re-installing or uninstalling an agent never
touches cron. Until one is installed, every tick logs `No agent installed` and exits. The log
directory is the one fixed input, because logging starts before the first HTTP call and cron strips
the environment; see [The Poller](13-the-poller.md). The cron step creates that
directory, since the shell redirect — and the tick with it — fails if it is missing. There is
exactly one entry — no separate research schedule.

`poll_interval_mins` is baked into this line. Editing the settings row does nothing until you re-run
`python onboard.py --step cron`.

> **Cron strips `TZ`.** An injected timezone environment variable never reaches a cron-invoked
> process, so `/etc/localtime` is the only reliable path. A container can therefore legitimately show
> local time interactively and UTC in its cron logs at the same time.

Unattended agent runs are permitted by a scoped allowlist in the agent's workspace **plus** a trusted
project record in `~/.claude.json`, both written by `python onboard.py --install-agent claude`. Both are required — an allowlist alone is silently ignored. This pair is Claude Code's mechanism; a Codex install writes neither, because its equivalent is `-s read-only` on the command line, and an OpenCode install writes an ordered permission list into the workspace's `.opencode/opencode.json` and `.opencode/opencode.jsonc` instead.
`--dangerously-skip-permissions` is rejected by this project.

---

## Operating

```bash
python3 scripts/service.py status                        # version, schema, cron, container health, GPU
python3 scripts/service.py logs tubematic-api -f         # Flask
python3 scripts/service.py logs tubematic-mcp -f         # the agent's tools
python3 scripts/service.py logs tubematic-worker -f      # publishing, Auto Pilot, notifications
python3 scripts/service.py logs tubematic-renderer -f    # render output, gateway connection problems
python3 scripts/service.py restart tubematic-renderer
python3 upgrade.py                                       # picks up code changes
```

`scripts/service.py` is a thin layer over `docker compose` with two additions. `start` (and the
start half of `restart`) creates the data directories and reconciles the volumes first, for the
reason in the note at the top of this page. `stop` and `restart` refuse while work is in flight —
a video `RENDERING` or `VOICING`, an agent session holding the poller's lock, or a publish still
uploading — because stopping kills it. `--force` stops anyway. Restarting `tubematic-dashboard`
alone is not refused, since it holds no work, with one exception that also applies to `start`:
when a volume has to be re-pointed, the reconcile runs `docker compose down`, which takes every
container down whichever service was named, so that is gated too — and afterwards every service is
brought back, not only the named one. `start` exits non-zero when a service it started fails its
health check or, for the worker and the renderer, is not running. Read-only `docker compose` commands (`ps`,
`logs`) are as safe as ever.

To pick up code changes, run `upgrade.py`, not a bare build and `up -d`. It stops the whole stack
between the build and the start, so new code never migrates the database while old code is still
running against it — see [Upgrading](../user-guide/07-upgrading.md#upgrading--user-instructions)
for the full sequence.

Remember what is baked in: `renderer/api/`, `mcp/`, the dashboard, and the Remotion `src/` tree —
including `scenes/installed/` — all require a rebuild. Only `scenes/generated/` and the data
directories are live.

After rebuilding, **reconnect your agent session** if any MCP tool signature changed. Tool schemas
are read once at session start.

```bash
sqlite3 ~/.tubematic-data/data/tubematic.db "SELECT id, status, title FROM videos ORDER BY updated_at DESC LIMIT 10;"
python scripts/status.py        # health, checkpoints, costs, disk usage
python scripts/cleanup_jobs.py  # interactive: reclaim job directories (retention does published ones automatically)
python scripts/clear_db.py      # interactive: delete videos, reset statuses, full wipe
python3 scripts/collect_diagnostics.py  # a redacted report to attach to a bug report
```

What the collector removes, and what it cannot, is in
[Reporting a bug](../user-guide/08-troubleshooting.md#reporting-a-bug).

### Disk

Video and `node_modules` dominate. Two things are worth knowing before you go looking:

- **`docker system df` is unreliable in both directions.** Its per-image size double-counts shared
  layers. Measure with `df -h /`.
- **With the containerd snapshotter, image layers are not in `/var/lib/docker`.** They live under
  `/var/lib/containerd/…`, and a `du` on `/var/lib/docker` alone can understate Docker's footprint
  several-fold. Never hand-collect the containerd content store — Docker's own metadata references
  that namespace.

Container logs are unrotated unless you configure `log-opts` in the daemon config. That change needs
a daemon restart, which bounces every container on the host.

The renderer cleans up after itself: each job's directory under `/tmp/tubematic-render/` and its
staged `public/<video_id>/` are removed when the job ends, and `/tmp/tubematic-render/` is cleared at
start, so a job killed half-way does not leave its copy behind either.

---

## The test stack

`docker-compose.test.yml` is a fully isolated second stack — its own project name, network, ports
(3001/4001) and **plain named volumes with no host bind**. Playwright's global setup brings it up and
its teardown destroys it, so it is safe to run alongside a dev stack.

It uses fixed, public tokens from `dashboard/tests/e2e/secrets/` rather than random ones, because
it lives only for one run, and a known test password that its global setup sets before signing in.
The render gateway's TLS pair is the exception: a private key, even a test one, does not belong in
the repository, so the global setup generates the pair with `openssl` into that directory when it is
missing, and `.gitignore` keeps it there for later runs.

Its API container is pinned to a timezone that is deliberately neither UTC nor the browser's
configured zone. That is the assertion: if the dashboard ever started formatting in the browser's
zone rather than the host's, the suite would catch it.

---

## What is not tracked in git

`.env*`, key files (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), SQLite files (`*.db` and its `-wal`/`-shm`
companions — the database stores every API key, so a copy inside the checkout must never be committed),
`node_modules/`, `.venv/`, `.onboard-state.json`, `.worktrees/`, `logs/*.log`, every supported agent's
project-scope config (`.claude/`, `.agents/`, `.opencode/`, `.codex/`, `opencode.json`), a diagnostics
report written into the checkout (`tubematic-diagnostics-*/`), root-level `test_*.md` scratch notes, both
Kasm build-context scratch directories, the e2e suite's saved sign-in
(`dashboard/tests/e2e/.auth/`), the maintainer's private notes (`docs_private/`, including the release
procedure — the public side of releasing is [Releases](18-releases.md)), and the whole `mounted/` path — a
pre-migration data location kept ignored only so an un-migrated checkout does not show it as
untracked.

Pipeline data is outside the checkout entirely and is therefore not a gitignore concern.
