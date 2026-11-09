# Infrastructure

Tubematic runs from `docker-compose.yml`: five services, six volumes and one network. One cron
entry on the host starts the poller. [Architecture](01-architecture.md) shows how the processes
talk to each other.

Start the stack with `python3 scripts/service.py start` or through onboarding. Both create any
missing data directory and reconcile the volume device paths before `up`. A bare
`docker compose up -d` does neither. It fails when a device path is missing, because
`local`-driver bind volumes do not create one. When a volume's recorded device has changed, it
mounts the old path, because Compose asks about the change and answers "no" without a terminal.

---

## Services

| Service | Command | Published port | Healthcheck |
|---|---|---|---|
| `tubematic-api` | `/app/entrypoint.sh python3 /app/api/server.py` | `127.0.0.1:4000` | `curl -fs http://127.0.0.1:4000/health` |
| `tubematic-mcp` | `/app/entrypoint.sh python3 /app/mcp/server.py` | `127.0.0.1:4100` | `curl -fs http://127.0.0.1:4100/health` |
| `tubematic-worker` | `python3 /app/api/worker.py` | none | none |
| `tubematic-renderer` | `python3 /app/api/render_agent.py` | none | none |
| `tubematic-dashboard` | the image's own `node server.js` | `3000` | `wget -q -T 5 --spider http://127.0.0.1:3000/login` |

Every service has `restart: unless-stopped` and a fixed `container_name` equal to its service
name. A healthcheck runs every 15 seconds with a 10-second timeout and 5 retries. Its
`start_period` is 30 seconds on the API and the MCP server and 45 seconds on the dashboard.
`tubematic-api` depends on nothing. The other four declare
`depends_on: tubematic-api: service_healthy`.

Four containers run one image. Only `tubematic-api` declares `build:`. The MCP server, the worker
and the renderer reuse its tag with a different `command:`, so a rebuild of `tubematic-api`
rebuilds all four.

| Mount (container path) | api | mcp | worker | renderer | dashboard |
|---|---|---|---|---|---|
| `output-videos` (`/output_videos`) | read-write | | read-write | | read-only |
| `jobs-data` (`/jobs`) | read-write | read-write | read-write | read-only | |
| `db-data` (`/data`) | read-write | read-write | read-write | | |
| `scenes-generated` (`/app/remotion/src/scenes/generated`) | read-write | read-write | | read-write | |
| `logs-data` (`/logs`) | read-write | read-write | read-write | read-write | |
| `backups-data` (`/backups`) | read-write | read-write | read-write | | |
| `/etc/localtime`, `/etc/timezone` (host files) | read-only | | read-only | read-only | |

The secret files each service mounts are listed under
[The secrets directory](#the-secrets-directory).

### `tubematic-api`

Its `build:` section names `renderer/Dockerfile`, with the repository root as the build context,
and tags the image `tubematic-renderer-image`. It depends on no other service, so the dashboard
and the poller reach the pipeline through Flask while the MCP server is down.

The process runs Flask on port 4000. A thread of the same process runs
[the render gateway](19-render-gateway.md) on port 4443 (`TUBEMATIC_GATEWAY_PORT`), which every
renderer calls. The healthcheck probes port 4000 only, so the container's health says nothing
about the gateway. When the gateway cannot start, it logs `render gateway not started` with the
reason, and the API still serves the dashboard. See
[When the gateway cannot start](19-render-gateway.md#when-the-gateway-cannot-start).

`docker-compose.yml` does not publish 4443. The built-in renderer reaches it as
`https://tubematic-api:4443` over the Compose network. A renderer on another machine needs the
port published, which the [remote-renderers override](#remote-renderers-override) does.

Compose leaves `TUBEMATIC_MAX_OUTPUT_BYTES`, `TUBEMATIC_MAX_CONCURRENT_UPLOADS` and
`TUBEMATIC_MIN_FREE_BYTES` unset, so the upload limits keep their defaults. See
[The Render Gateway: Limits](19-render-gateway.md#limits).

The gateway writes each upload to `output_videos/.gateway-uploads/` and renames it to
`<project_id>/<video_id>.mp4` once it is complete. The staging directory is on the same volume,
so the move is a rename, and the temporary files stay out of the directories that list videos.

- The gateway creates the directory when it is missing, with the permissions of everything else
  the container writes there, so the host user can delete it.
- It deletes leftover `*.upload` files when it starts. When it admits an upload, it deletes those
  older than six hours that no upload is writing.
- It deletes only `*.upload` files there and follows nothing in the directory. If a symlink
  stands in place of the directory, every upload fails and the gateway logs why.

### `tubematic-mcp`

Its mounts are the minimum its tools use, because the server compiles agent-authored scene
code.

- It has no `output-videos` mount. Nothing in `mcp/` reads or writes rendered output, and Flask's
  preview endpoint writes the cached voice previews that live there.
- It has no `/etc/localtime` mount. No tool formats a local timestamp.
- It appends its own `mcp.*.jsonl` to `logs-data`. Flask is the only reader of that volume.
- It needs `backups-data`. Each of the three services that open the database calls `migrate()`
  itself, and `migrate()` does not run when its backup fails. See [Backups](#backups).

`TUBEMATIC_STILLS_SERVER=http://tubematic-renderer:4455` points the Cartoon 3D tools at the
renderer's [stills server](11-rendering-and-review.md#the-stills-server).

The `depends_on` is startup ordering only. `migrate()` holds a write lock for its whole run (see
[Database: Migrations](03-database.md#migrations)), so two containers that reach a new database
at once take turns. Nothing gates the MCP server at runtime: a Flask failure after startup does
not stop it, and Flask does not depend on the MCP server.

### `tubematic-worker`

It runs the background passes described in [The Worker](12-the-worker.md).

- It mounts `output-videos` and `jobs-data` because retention deletes a video's mp4 and job
  directory, and the AI review reads the uploaded mp4 and the job's scene-config.
- It mounts the two timezone files because Auto Pilot's daily numbers and a scheduled post's wall
  time are host-zone days.
- It has no `scenes-generated` mount, because it reads and writes no scene.
- It holds no secret file. The API keys it uses (Gemini for the review, postforme for publishing)
  are rows in the settings table.

Its `command:` is the bare interpreter, so it does not run `entrypoint.sh`. It applies its own
umask at startup.

### `tubematic-renderer`

The built-in renderer. It sets `shm_size: 2gb` for Chromium. It renders and tests its GPU. See
[Rendering and Review](11-rendering-and-review.md).

It talks to the render gateway over HTTPS as a renderer on another machine does: it claims a
video, downloads the job's files as one bundle and uploads the finished mp4. The gateway writes
the upload into the library and the worker runs the AI review, so the renderer mounts no
`db-data`, `output-videos` or `backups-data`.

| Mount, variable or secret | Purpose |
|---|---|
| `scenes-generated` | Renders compile the shared generated-scene tree. A remote renderer stages the bundle's copy |
| `jobs-data`, read-only | The stills server reads a video's job files. Renders use the bundle |
| `logs-data` | Its own JSONL log for the dashboard's Logs page |
| `/etc/localtime`, `/etc/timezone` | Log timestamps in the host zone |
| `TUBEMATIC_GATEWAY_URL=https://tubematic-api:4443` | Where the gateway is |
| `TUBEMATIC_RENDERER_BUILTIN=1` | Authenticate as the built-in renderer. A remote renderer reads an enrollment state file |
| `TUBEMATIC_STILLS_PORT=4455` | The stills server's port |
| `builtin_renderer_token` | Its credential, read on every request |
| `render_tls_cert` | The only certificate it trusts. It does not get the key |

Beside its renders it runs one child process, the Cartoon 3D
[stills server](11-rendering-and-review.md#the-stills-server), on the Compose network only. The
MCP container's gate and preview tools use it so that their stills render on this container's
GPU.

Like the worker, it does not run `entrypoint.sh` and applies its own umask at startup. It is the
only service that can get a GPU, and only through the override below. Its GPU test travels to the
API in its heartbeats, because the API has no GPU to test.

#### GPU override

`docker-compose.yml` reserves no GPU, because a device reservation that Docker cannot satisfy
stops the container from being created ("could not select device driver") and the file is the
same on every install. The `gpu` onboarding step (`onboard/gpu.py`) writes
`~/.tubematic-data/compose.gpu.json`, which changes `tubematic-renderer` only:

- `deploy.resources.reservations.devices`: `driver: nvidia`, `device_ids: [<the GPU's UUID>]`,
  `capabilities: [gpu]`. Compose requires `capabilities` and refuses `count` beside `device_ids`.
- `NVIDIA_DRIVER_CAPABILITIES=graphics,utility`. `graphics` brings the EGL and OpenGL driver
  libraries WebGL needs, and `utility` brings `nvidia-smi`. Toolkit 1.20 injects the graphics
  libraries for any GPU request. Older toolkits default to `compute,utility` and leave them out.
- `TUBEMATIC_GPU_UUID`, `TUBEMATIC_GPU_NAME`, and `TUBEMATIC_HOST_GPUS` (every NVIDIA GPU the
  host had when the step ran, for the dashboard's list).

The file is JSON, which Compose reads as YAML, so onboarding needs no YAML library. It lives under
the data root because an upgrade installs into a new directory. How the step applies a new
choice, the GPU test and the `upgrade.py` refusal (`gpu.py::override_problems`) are in
[GPU and Remote Renderers](20-gpu-and-remote-renderers.md#the-compose-override).

`onboard/actions.py::_compose()` builds the `docker compose` command for the onboarding steps,
`scripts/service.py` and `upgrade.py`. When the GPU override or the
[remote-renderers override](#remote-renderers-override) exists, the command is
`docker compose -f docker-compose.yml -f <each override that exists>`, GPU first. With neither
file it is the bare `docker compose`. Naming files with `-f` also stops Compose from loading a
stray `docker-compose.override.yml`.

A hand-run `docker compose up` does not go through `_compose()`. It recreates the renderer
without the GPU, which then renders on the CPU, and `tubematic-api` without the published gateway
port.

#### Remote-renderers override

The opt-in `renderers` onboarding step (`python3 onboard.py --step renderers`,
`onboard/actions.py::apply_renderers` with `onboard/remote_renderers.py`) lets renderers on other
machines reach the render gateway. It writes `~/.tubematic-data/compose.renderers.json`, which
changes `tubematic-api` only:

```json
{
  "x-tubematic": "Written by `python3 onboard.py --step renderers`. …",
  "services": { "tubematic-api": { "ports": ["0.0.0.0:4443:4443"] } }
}
```

The host port is the one in the address you give (4443 when it names none), and the container
port is 4443. For an IPv6 address the step adds a second entry, `[::]:<port>:4443`. It adds it
only then, because a host with IPv6 disabled refuses that bind and `up` would fail.

The step stores the address renderers dial, `host:port` with an IPv6 host in brackets, as the
settings row `render_gateway_address`
([Settings internals: Undeclared rows](04-settings.md#undeclared-rows)). An empty value or no row
means off. It then recreates `tubematic-api` (`up -d tubematic-api`) and checks that
`127.0.0.1:<port>` answers a TLS handshake with the gateway's own certificate
(`remote_renderers.py::wait_for_gateway`, retried while the container starts). It says that the
advertised address was not tested from another machine, prints a firewall note and offers a first
enrollment token. Choosing off deletes the file, blanks the row and recreates `tubematic-api`.

`remote_renderers.py::_check_host` refuses an address a renderer cannot dial: a loopback,
unspecified, multicast or broadcast address, and an IPv6 link-local address, which needs a zone
the token cannot carry. It judges an IPv4 address written as IPv6 (`::ffff:a.b.c.d`) as that IPv4
address, because Python's IPv6 checks do not look inside it.

The file, the row and the running container change together, because the dashboard hands out
tokens while the row is set and the container holds the published port. `apply_renderers` keeps
them in step:

- With `tubematic-api` running and a publish upload in flight (the upload runs inside an API
  request), it changes nothing and tells you to re-run the step later.
- If `up -d tubematic-api` fails, it puts the previous file and row back and runs `up` once more,
  because Compose may have removed the old container before the new one failed to start.
- It recreates the container only when its `State.Status` is `running`
  (`actions.py::_api_running`). On a stopped stack it stores the choice and starts nothing,
  because `up -d tubematic-api` there would start the API alone with the port published.

The port is in an override because `docker-compose.yml` is the same on every install, and a
published 4443 there would open the gateway on machines that did not ask for remote renderers.
The file is under the data root because the data root carries state across upgrades, which
install into a new directory. The address is a settings row because the dashboard builds every
enrollment token from it and disables **Add renderer** without it, and the API container cannot
read a host file. The row is outside `SETTINGS_SPEC`, so the dashboard cannot set it: turning
remote renderers on also publishes a port, which only the host can do.

Docker publishes the port on every interface (`0.0.0.0`), and `ufw` does not restrict it, because
Docker routes a published port in the `nat` table ahead of the `INPUT` chain. The `[::]` entry
is served by Docker's userland proxy as a host process, because Tubematic's Compose network is
IPv4-only, so its packets meet the host's IPv6 `INPUT` chain. The rules for both
(`DOCKER-USER`, `ip6tables`) are in
[Remote renderers](../user-guide/11-remote-renderers.md#allow-the-port-through-your-firewall-from-your-renderers-only).
Nothing may terminate TLS in front of the port, because renderers trust the gateway's own
certificate ([TLS and the certificate pin](19-render-gateway.md#tls-and-the-certificate-pin)).

`remote_renderers.py::read_override` accepts only the document `render_override` produces: one
`0.0.0.0` entry, optionally followed by one `[::]` entry, both to container port 4443 with the
same host port between 1 and 65535, and no other service, key or setting.
`remote_renderers.py::override_problems` reports anything else. The prerequisites check warns
about it, and `upgrade.py` refuses before it stops anything, because Compose rejects a file it
cannot parse and accepts some it should not (host port 0 publishes a random port, and 70000
fails only at `up`). A readable override is carried across an upgrade unchanged.

`scripts/service.py status` and `upgrade.py --check` report whether remote renderers are on. They
flag a half-done state: a port with no stored address, an address with no port, or the two
disagreeing. `uninstall.py` leaves the file when you keep the data root and names it, because a
reinstall would publish the port again.

### `tubematic-dashboard`

Built from `dashboard/Dockerfile`. It sets `RENDERER_URL=http://tubematic-api:4000` and mounts
only `output-videos`, read-only. It has no database access.

- It has no `logs-data` mount. The Logs page reads through Flask's `GET /logs`, so the dashboard
  needs no filesystem route to a log file and no Docker socket.
- It has no `/etc/localtime` mount. It learns the host zone over HTTP, so there is one source for
  the zone. See [HTTP API: Time](05-http-api.md#time).

The healthcheck probes `/login`, the one page that answers `200` without a session. Without a
healthcheck, Docker reports a container healthy as soon as it runs, before Next.js has bound its
port. Three details of it apply to any healthcheck:

- Keep the `start_period`. Failures inside it do not count toward `retries`, and a success inside
  it marks the container healthy at once. Without one, a slow start uses up the retries.
- Probe `127.0.0.1`. A container's `/etc/hosts` maps `localhost` to both `127.0.0.1` and `::1`,
  and the server binds IPv4 only (`HOSTNAME=0.0.0.0`). BusyBox `wget` resolves `localhost` to the
  IPv6 address first and does not fall back to IPv4, so a `localhost` probe fails on each attempt
  and logs nothing. `scripts/tests/test_gen_release_compose.py` fails if a healthcheck in
  `docker-compose.yml` names `localhost`.
- The probe uses `wget` because the runtime stage, `node:20-alpine`, ships BusyBox `wget` and no
  `curl`. The API and MCP image is Debian-based and uses `curl`.

### Why the ports bind to loopback

Flask and the MCP server publish on `127.0.0.1`. Container-to-container traffic goes over the
Compose network by service name and uses no published port, so the worker and the renderer need
no `ports:` entry. Publishing exists for callers on the host: the poller, the status script,
`curl` and the agent's MCP client, all of which use `localhost`. The MCP server's tools change
pipeline state, write files, spend money on paid APIs and render agent-authored scene code, so
it has both a token and the loopback binding.

A development checkout leaves the dashboard's port 3000 on all interfaces, behind its login, so
the UI is reachable from another device on the network. A release install binds it to
`127.0.0.1`, because `scripts/gen_release_compose.py` puts every published port on loopback. To
reach it from elsewhere, see
[Using the dashboard from another machine](#using-the-dashboard-from-another-machine).

---

## Authentication

Three containers listen. Each checks every request except its open routes.

| Service | Callers | Check | Open routes |
|---|---|---|---|
| `tubematic-dashboard` | Browsers | A signed session cookie, set after the dashboard password | The login page and its sign-in request |
| `tubematic-api` (4000) | The dashboard, the poller, `vqa/edit_settings.py`, `curl` | `Authorization: Bearer <api_token>` | `/health`, `/render/health` |
| `tubematic-api`, render gateway (4443) | The built-in renderer, and remote renderers once the port is published | TLS with a pinned certificate, then `Authorization: Bearer <renderer credential>` | `GET /v1/version`, and `POST /v1/enroll`, whose body carries the one-time secret |
| `tubematic-mcp` | The agent CLIs | `Authorization: Bearer <mcp_token>` | `/health` |

People get sessions and programs get tokens: a browser cannot hold a bearer token safely, and a
cron job cannot type a password. Flask exempts its two health routes by endpoint name
(`api_auth.py::OPEN_ENDPOINTS`), so a path that only starts with `/health` is still checked.

The worker and the renderer check nothing because neither publishes a port. The worker listens
on none, and the renderer's one listener, the stills server, is on the Compose network only. The
renderer is a caller of the render gateway, with its own credential.

The dashboard makes one outbound call of its own. The
[update check](15-dashboard.md#update-check) reads `api.github.com` at most once in two hours,
unauthenticated. Without internet access it fails and nothing else is affected.

### The secrets directory

`~/.tubematic-data/secrets/` holds one file per secret. Each of the four tokens is a random
256-bit value. The last two files are the render gateway's TLS pair.

| File | Mounted in | What it is |
|---|---|---|
| `api_token` | `tubematic-api`, `tubematic-dashboard` | Flask's bearer token. The poller and host scripts read it on the host |
| `mcp_token` | `tubematic-mcp` | The MCP server's bearer token. The agent CLIs read it on the host |
| `session_secret` | `tubematic-dashboard` | The key that signs session cookies |
| `builtin_renderer_token` | `tubematic-api`, `tubematic-renderer` | The built-in renderer's credential at the gateway |
| `render_tls_key` | `tubematic-api` | The gateway's EC P-256 private key |
| `render_tls_cert` | `tubematic-api`, `tubematic-renderer` | The gateway's self-signed certificate, which every renderer pins |

`tubematic_core/auth.py::ensure_secrets` creates any file that is missing or empty and replaces
none. Onboarding's `auth` step calls it, and so does every stack start and upgrade. It makes the
TLS pair with the `cryptography` package, so the dependency bootstrap
(`onboard/bootstrap.py::ensure_deps`) installs that package: a single `--step` run or an upgrade
reaches the secrets before the `python_deps` step has run.

Compose mounts each file read-only at `/run/secrets/<name>` (a top-level `secrets:` block with
`file:` sources), and the containers set `TUBEMATIC_SECRETS_DIR=/run/secrets`. No secret is an
environment variable, and `docker inspect` shows none. A missing file stops `up` with "bind source
path does not exist", so the stack does not start without its tokens.

The directory is `0700` and the files are `0644`. Compose mounts each file on its own, which
bypasses the directory's permissions inside the container, and the dashboard runs as uid 1001, so
a `0600` file would be unreadable there. The `0700` directory keeps other host users out. The TLS
key follows the same rule, and only `tubematic-api` mounts it.

The admin password is not a file. Its scrypt hash is the `settings` row `admin_password_hash`,
which is outside the settings API: `GET /settings` does not return it and `POST /settings` cannot
write it. A password has at least 12 characters (`auth.py::MIN_PASSWORD_LEN`).

#### The TLS pair

The four tokens are the only secrets that are replaced, and only by
`python3 onboard.py --rotate-tokens`. `auth.py::rotate_secrets` raises for a TLS name, because a
new certificate has a new pin
([TLS and the certificate pin](19-render-gateway.md#tls-and-the-certificate-pin)).

When either TLS file is missing or empty, `tubematic_core/auth.py::_ensure_tls` writes a fresh
key and certificate, because one half is useless without its partner. It writes each half to a
temporary file and renames it into place, the half that is still present first, so an
interrupted repair leaves one name missing and the next start makes the pair again. A rename is
safe here because the gateway loads the pair only when it starts.

After a new pair is made, restart `tubematic-api` and `tubematic-renderer`. The built-in renderer
then follows, because it reads the certificate from the same directory. Enrollment tokens issued
earlier carry the old pin and are useless, and each remote renderer must be
[enrolled again](19-render-gateway.md#enrollment). `renderers.py::enroll` matches the machine id,
so the same machine keeps its renderer row (its id, its enabled switch and its render timings).

`_ensure_tls` does not replace two non-empty files, even when they do not load as a pair (a key
and a certificate restored from different backups, or a truncated file), because that would
change the pin unasked. The gateway then logs
`render gateway not started: its TLS key and certificate cannot be used as a pair`. The recovery
is in [When the gateway cannot start](19-render-gateway.md#when-the-gateway-cannot-start).

### How each caller gets its token

- The API and the MCP server read their token once, when they start (`renderer/api/server.py`,
  `mcp/server.py`).
- The dashboard reads `api_token` and `session_secret` on every request
  (`dashboard/lib/session.ts::readSecret`), so a new password takes effect without a restart.
- The built-in renderer reads `builtin_renderer_token` and `render_tls_cert` on every request, and
  the gateway reads the token on every request.
- The poller reads the file for each request it makes to Flask, because it is a long-running
  process that outlives a rotation. It sends the token to Flask only.
- The agent CLIs do not hold the token in their own config. Claude Code and Codex run
  `scripts/mcp_auth_header.py` on every connection (Claude's `headersHelper`, Codex's
  `http_headers_helper`), and OpenCode reads the file through its `{file:}` substitution. See
  [The agent layer](07-agent-layer.md) for how each is registered.

### Changing the password and rotating tokens

`python3 onboard.py --set-password` sets or changes the dashboard password. A change also rotates
`session_secret`, which signs every browser out.

`python3 onboard.py --rotate-tokens` (`onboard/auth_commands.py::run_rotate_tokens`) does this:

1. Waits for in-flight work, as `upgrade.py` does. `--force` goes ahead.
2. Replaces the four tokens. It rewrites each file in place, because a bind mount pins the inode
   it started with and a rename would leave running containers reading the old value.
3. Restarts `tubematic-api`, `tubematic-mcp` and `tubematic-dashboard`.
4. Has OpenCode reload its config.

If a restart or a reload fails, the command still tries the rest and then exits non-zero, naming
what to run, because whatever kept an old token cannot authenticate until it picks up the new
one. Claude Code, Codex and the built-in renderer need nothing after a rotation, because each
reads the file on every connection. Every browser has to sign in again.

Failed logins back off across the whole install: five free attempts, then a wait that doubles up
to 15 minutes (`api_auth.py::LoginThrottle`). One password check runs at a time. See
[HTTP API: Dashboard login](05-http-api.md#dashboard-login). The backoff is install-wide because
every login reaches Flask from the dashboard container, and a forwarded client address can be
forged. It is held in memory, so restarting the API clears it.

### Using the dashboard from another machine

Put HTTPS in front of port 3000: a reverse proxy such as Caddy or nginx that terminates TLS, or a
private network such as Twingate. [Remote Access](../user-guide/09-remote-access.md) has the
steps. Tubematic does not manage certificates.

The session cookie is `HttpOnly` and `SameSite=Strict`. It is also `Secure` when the request
arrived over HTTPS, directly or as reported by the proxy's `X-Forwarded-Proto` header. Over plain
HTTP, the password and the cookie cross the network readable.

A proxy needs to forward `X-Forwarded-Proto` and nothing else, because the login redirect is
relative. Middleware builds its `/login` URL from `req.url`, which in the standalone server is the
server's own listen address (`http://0.0.0.0:3000/…`, from `HOSTNAME`). Next.js rewrites a
same-origin `Location` to a relative path before it sends it, so the browser resolves `/login`
against the address it used. The dashboard therefore sets no `trustHostHeader` and reads no
`X-Forwarded-Host`.

---

## Volumes

All six are named volumes with `o=bind` device paths under `${HOME}`:

| Volume | Device | Holds |
|---|---|---|
| `db-data` | `~/.tubematic-data/data` | The SQLite database |
| `jobs-data` | `~/.tubematic-data/jobs` | Per-video working files |
| `output-videos` | `~/.tubematic-data/output_videos` | Rendered mp4s and cached voice previews |
| `scenes-generated` | `~/.tubematic-data/scenes/generated` | Agent-authored scene TSX |
| `logs-data` | `~/.tubematic-data/logs` | JSONL logs. See [The log files](#the-log-files) |
| `backups-data` | `~/.tubematic-data/backups` | Pre-migration database snapshots. See [Backups](#backups) |

The data folder also holds `secrets/` and the two override files, `compose.gpu.json` and
`compose.renderers.json`. None of those is a volume.

- Compose pins `name: tubematic`, so volume and network names do not change with the name of the
  directory the checkout is in.
- The device paths use `${HOME}` because cron strips the environment to `HOME`, `LOGNAME`, `PATH`
  and `SHELL`, and `${PWD}` would put the data inside whichever directory Compose ran from.
- Removing one of these volumes does not delete the host files. Docker drops its own record,
  whatever its warning says.

`docker volume prune` removes every volume no container uses, and these hold the database and the
video library, so remove a volume by name. `docker image prune` without `-a` removes untagged
images only.

### Backups

`backups-data` (`~/.tubematic-data/backups` on the host, `/backups` in the containers) holds
pre-migration snapshots of the database file. The three services that open the database mount it
(`tubematic-api`, `tubematic-mcp`, `tubematic-worker`), and each calls `migrate()` itself. The
dashboard and the renderer do not mount it: a backup is a full copy of a database whose
`settings` table is the credential store.

`migrate()` writes a snapshot only when it is about to apply a migration to an existing database.
If the backup fails, the migration does not run. See
[Database: Migrations](03-database.md#migrations).

- The name is `tubematic-before-v<version>-<timestamp>.db`.
- `tubematic_core/db.py::backup_db` uses SQLite's online backup API. The database runs in WAL
  mode with concurrent writers, and a file copy taken during a transaction produces a torn file.
- The snapshot's permission bits match the source database's, so the copy is no more permissive
  than the credential store it came from.
- Ownership is not copied. The containers that migrate run as root, so each snapshot is owned by
  root. The live database is group-writable by the host user (see
  [`renderer/entrypoint.sh`](#rendererentrypointsh)).
- A backup that fails partway (a full disk, for example) is deleted, because a partial file with
  a valid name would look like a good one until someone restored it.
- Nothing prunes the directory. Delete old snapshots by hand, using the timestamp in each name.

An upgrade with a pending migration often leaves more than one snapshot. The backup happens
before `migrate()` takes its write lock, so each container that reaches that point before another
has committed writes its own. A name collision gets a counter suffix and overwrites nothing.

The restore procedure is in
[Upgrading: Rollback policy](../user-guide/07-upgrading.md#rollback-policy). Its steps have these
reasons:

- The `cp` needs `sudo` because the snapshot is owned by root. Without it the copy fails with
  `Permission denied`.
- The `-wal` and `-shm` sidecars belong to the file being replaced. Removing them forces a clean
  reopen, so stale WAL frames are not replayed against the restored file.
- A snapshot predates a migration, so the current code migrates a restored database forward
  again on its first `migrate()` call. A restore therefore goes with a return to the older code.

A restore discards every row written since the snapshot. The mp4s and job files those rows
pointed to stay on disk.

---

## Ports

| Port | Service | Bound to |
|---|---|---|
| 3000 | Dashboard | All interfaces in a checkout, `127.0.0.1` in a release install. Behind its login in both |
| 4000 | Flask API | `127.0.0.1` |
| 4100 | MCP server | `127.0.0.1` |
| 4443 | The render gateway (HTTPS) | The Compose network. The [remote-renderers override](#remote-renderers-override) publishes it on every interface, on the host port you choose (4443 by default) |
| 4455 | The renderer's stills server | The Compose network. It is not published |
| 3001, 4001 | The end-to-end test stack | All interfaces |

Container names are fixed, so two checkouts cannot run their stacks at the same time.

---

## Images

### `renderer/Dockerfile`

The base is `node:20-slim`, plus `chromium`, `ffmpeg`, `python3`, `curl` and three font packages:
`fonts-liberation`, `fonts-noto-color-emoji` and `fonts-freefont-ttf`.

The container has no DejaVu fonts. A hardcoded DejaVu path works on most developer machines and
fails in the container, and no host-run test catches it, so reuse the existing font candidate
lists. Pillow's `load_default()` returns a bitmap font with no `.size` and no stroke support, so a
fallback that uses those raises.

No NVIDIA library is installed. The NVIDIA Container Toolkit mounts the host driver's own
libraries and `10_nvidia.json` into a container that is given a GPU, so they match the host's
driver. `libglvnd0` and `libegl1`, which load them, come in with `chromium`.

The Dockerfile sets `PUPPETEER_EXECUTABLE_PATH` and the Chromium flags
(`--disable-dev-shm-usage --no-sandbox`), and creates `/data`, `/jobs`, `/output_videos`, `/logs`
and `/backups`. It then installs three source trees, dependencies first, so that a source edit
does not invalidate the dependency layers:

1. `renderer/remotion/package*.json`, then `npm ci`, then the rest of the Remotion project
2. `renderer/api/requirements.txt`, then pip, then `renderer/api/`
3. `mcp/requirements.txt`, then pip, then `mcp/`

Last, it copies `tubematic_core/` and `VERSION` to `/app/lib` and sets `PYTHONPATH=/app/lib`. The
path is `/app/lib` because `/app` also holds `api/`, `mcp/` and `remotion/`. With `/app` on
`sys.path`, `/app/mcp` would collide by name with the MCP SDK that `fastmcp` imports.

`/logs` exists in the image as well as being a bind mount, so a stack that does not mount it (the
end-to-end test stack) still writes logs, without persistence. The build context is the
repository root, because the build copies from `renderer/`, `mcp/` and `tubematic_core/`.

### `renderer/entrypoint.sh`

It runs for `tubematic-api` and `tubematic-mcp`. It fixes the permissions of the database and the
logs directory, then `exec`s the process it was given, so each container has one foreground
process. The Dockerfile's `CMD` supplies the Flask process as the default, and Compose overrides
it per service. With one process per container, a process that exits takes its container down and
`restart: unless-stopped` acts on it.

Both containers run the same permission block, and each operation tolerates failure and
repetition. The block has two branches:

- The data directory is owned by a host user. The script sets `umask 002`, changes the group of
  the database and its `-wal` and `-shm` sidecars to that directory's group, sets them to `0660`
  (`chmod 0660`), and sets the setgid bit on the directory so that new sidecars inherit the group.
- The data directory is owned by root, which happens when something created it before onboarding
  did (usually a bare `docker compose up`). The script makes the files world-writable and prints
  a warning to stderr that starts `entrypoint: /data is root-owned`. Fix the ownership on the
  host.

Both branches also apply to the logs directory (`/logs`, or `TUBEMATIC_LOG_DIR`). In the first
branch it gets the host group, group read, write and search (`g+rwx`) and setgid. In the second it
becomes world-writable. The directory has one writer outside the containers: `poll.py` runs from
cron as the host user and appends `poll.<date>.jsonl` beside the services' files. Setgid keeps
the files the containers create there in the host group.

On a new install the script runs before any process has created `tubematic.db`, so its `chgrp`
and `chmod` find nothing. The first process to open the database creates it, and `umask 002` with
the directory's setgid bit make it group-accessible.

Reading the database from the host needs write access. SQLite in WAL mode writes to the `-shm`
sidecar even for a `SELECT`, so a read-only caller fails with
`attempt to write a readonly database`. A reader that cannot write these files (CI, another
account) should read the database from inside a container that owns it.

### `dashboard/Dockerfile`

A multi-stage build on `node:20-alpine`: install, build with `output: "standalone"`, then a runner
stage that copies the standalone bundle and the static assets and runs as a non-root user (uid
1001).

---

## Cron

Onboarding writes one entry:

```
*/30 * * * * <python> <repo>/scripts/poll.py >> ~/.tubematic-agent/logs/cron.log 2>&1
```

[The Poller](13-the-poller.md) describes what the entry starts and why it names no agent. For
the install, three things matter:

- The cron step creates the log directory, because the shell redirect fails without it.
- `poll_interval_mins` is written into the line. Editing the settings row changes nothing until
  you re-run `python3 onboard.py --step cron`.
- Cron strips `TZ` along with the rest of the environment, so the host's `/etc/localtime` is the
  only timezone source for a cron-started process.

Unattended agent runs need permissions that `python3 onboard.py --install-agent <agent>` sets up
for each CLI. [The agent layer](07-agent-layer.md) describes them. Tubematic does not use
`--dangerously-skip-permissions`.

---

## Logging

Each process logs in two places. Its stdout goes to Docker
(`python3 scripts/service.py logs <service>`), and
`tubematic_core/logging.py::setup_json_logging` adds a JSONL file handler that redacts stored
secrets. When the log directory is missing or unwritable, the process logs to stdout only.

### The log files

Each service writes one JSONL file per UTC day to `~/.tubematic-data/logs`, mounted at `/logs`
in the containers. The name is `<service>.<date>.jsonl`, and the service names are fixed
(`logging.py::SERVICES`):

| File | Written by | Holds |
|---|---|---|
| `api.<date>.jsonl` | Flask and the render gateway | One record per request, with a `request_id` |
| `mcp.<date>.jsonl` | The MCP server | One record per tool call, with its duration and `outcome` |
| `worker.<date>.jsonl` | The worker | AI review, publishing, Auto Pilot, notifications, retention |
| `renderer.<date>.jsonl` | The built-in renderer | Render records, tagged with `video_id` |
| `poll.<date>.jsonl` | The poller, on the host | The poller's own records |

Flask reads the files back for `GET /logs`, which the dashboard's Logs page shows. Each service
deletes its own files older than `log_retention_days` (default 14). The poller also writes the
unstructured `~/.tubematic-agent/logs/poll.log`, and `cron.log` beside it catches only stray
output from the cron line.

### Tool-call records

Most MCP tools fail by returning an error to the agent, so the one record for each call carries
an `outcome`, and its level follows the cause:

| Level | `outcome` | Meaning |
|---|---|---|
| `error` | `error` | A paid provider call failed: ElevenLabs, Gemini or OpenAI answered with an error, sent a `200` with nothing usable in it, or did not answer |
| `error` | `partial` | The tool finished, and a provider call inside it failed. Mining carries on past a failed video URL |
| `error` | `exception` | The tool raised |
| `warning` | `error` | The tool refused before any paid call: a paused or expired domain, a frozen field, an empty prompt |
| `info` | `ok` | Success |

A provider failure's message names the provider, the model, the HTTP status (or "no response")
and the provider's reply, truncated and with credentials removed. For mining it also names the
video URL. The same details are in the record's `provider_service`, `provider_model`,
`provider_operation`, `provider_status`, `provider_body` and `provider_detail` fields, for `jq`.
Filtering the Logs page to level `error` shows the provider failures and exceptions. To see the
refusals too, search for `outcome`.

---

## Operating

```bash
python3 scripts/service.py status                        # version, schema, cron, container health, GPU, remote renderers
python3 scripts/service.py logs tubematic-api -f         # Flask
python3 scripts/service.py logs tubematic-mcp -f         # the agent's tools
python3 scripts/service.py logs tubematic-worker -f      # publishing, Auto Pilot, notifications
python3 scripts/service.py logs tubematic-renderer -f    # render output, gateway connection problems
python3 scripts/service.py restart tubematic-renderer
python3 upgrade.py                                       # picks up code changes
```

The [Command Reference](../user-guide/15-command-reference.md#scriptsservicepy) lists the
commands and flags. `scripts/service.py` runs `docker compose` through `_compose()`, so the
overrides apply, and adds two behaviours:

- `start`, and the start half of `restart`, create the data directories, reconcile the volumes
  and create any missing secret before `up`. `start` exits non-zero when a service it started
  fails its healthcheck or, for the worker and the renderer, is not running.
- `stop` and `restart` refuse while work is in flight, because stopping ends it: a video in
  `RENDERING` or `VOICING`, an agent session holding the poller's lock, or a publish that is
  still uploading. `--force` stops anyway.

Restarting `tubematic-dashboard` alone is not refused, since it holds no work. One case gates it,
and `start` too: when a volume has to be re-pointed, the reconcile runs `docker compose down`,
which takes down every container whichever service was named. Afterwards the script brings back
every service.

To pick up code changes, run `upgrade.py`. It stops the whole stack between the build and the
start, so new code does not migrate the database while old code runs against it. See
[Upgrading](../user-guide/07-upgrading.md#when-it-stops) and
[Releases: `upgrade.py` in detail](18-releases.md#upgradepy-in-detail).

`renderer/api/`, `mcp/`, the dashboard and the Remotion `src/` tree (including
`scenes/installed/`) are built into the images and need a rebuild. Only `scenes/generated/` and
the data directories are read live. After a rebuild, reconnect your agent session if an MCP
tool's signature changed, because an agent reads the tool schemas once, when its session starts.

```bash
sqlite3 ~/.tubematic-data/data/tubematic.db "SELECT id, status, title FROM videos ORDER BY updated_at DESC LIMIT 10;"
.venv/bin/python scripts/status.py  # health, checkpoints, costs, disk usage
python3 scripts/cleanup_jobs.py     # interactive: reclaim job directories (retention does published ones automatically)
python3 scripts/clear_db.py         # interactive: delete videos, reset statuses, full wipe
python3 scripts/collect_diagnostics.py  # a redacted report to attach to a bug report
```

What the collector removes, and what it cannot, is in
[Reporting a bug](../user-guide/08-troubleshooting.md#reporting-a-bug).

### Disk

Rendered video and `node_modules` take the most space.
[Troubleshooting](../user-guide/08-troubleshooting.md#the-disk-is-filling-up) says how to free
it. Measure with `df -h /`: `docker system df` double-counts shared layers in its per-image
sizes, and with the containerd snapshotter the image layers are outside `/var/lib/docker`.
Docker does not rotate container logs unless you set `log-opts` in the daemon config.

The renderer removes each job's directory under `/tmp/tubematic-render/` and its staged
`public/<video_id>/` when the job ends. It clears `/tmp/tubematic-render/` when it starts, so an
interrupted job leaves no copy behind.

---

## The test stack

`docker-compose.test.yml` is a second, isolated stack with its own project name
(`tubematic-test`), network, ports (3001 and 4001) and plain named volumes with no host bind.
Playwright's global setup brings it up and its teardown destroys it, so it can run beside a
development stack. It has no MCP container.

- Its tokens are fixed, public files in `dashboard/tests/e2e/secrets/`, because the stack lives
  for one run. The global setup sets a known test password before it signs in.
- The render gateway's TLS pair is not committed, because a private key does not belong in the
  repository. The global setup generates it with `openssl` into that directory when it is
  missing, and `.gitignore` keeps it for later runs.
- Its API, worker and renderer containers are pinned to `TZ=America/New_York`, a zone that is
  neither UTC nor the test browser's. The suite fails if the dashboard formats a time in the
  browser's zone.

[The end-to-end suite's page](test-suites/dashboard-e2e.md) covers the tests.

---

## Diagnosing a problem from the code's side

[Troubleshooting](../user-guide/08-troubleshooting.md) lists the symptoms a person running
Tubematic sees. The cases here need knowledge of the internals.

| Symptom | Cause | Explained in |
|---|---|---|
| `validate_job`: `Cannot find module '../installed/…'` | The import depth is wrong. Generated scenes are two levels down, so the path starts `../../` | [Scene Authoring](10-scene-authoring.md) |
| `validate_job`: a TypeScript error in a file you did not touch | The typecheck covers the whole project, so a broken scene from any video fails every validation | [MCP Server](06-mcp-server.md) |
| `validate_job`: a frame count mismatch | `scene-config.totalFrames` disagrees with `timeline.totalFrames`, usually after a re-voice changed the audio length | [MCP Server](06-mcp-server.md) |
| `validate_job`: an image path does not resolve | Image props must be `/public/<video_id>/images/…`, and the file must exist | [Scene Authoring](10-scene-authoring.md) |
| `Render failed: missing job file(s)`, video in `REVISION_REQUESTED` | The named file is not in `/jobs/<video_id>/`, usually because that step did not finish | [Refused before anything renders](11-rendering-and-review.md#refused-before-anything-renders) |
| `Render refused, moved to FAILED` | The video's id, or its domain's `project_id`, cannot be a path component. Edit the row in the database, or delete the video | [Refused before anything renders](11-rendering-and-review.md#refused-before-anything-renders) |
| A scene renders as a flat dark rectangle | Its dynamic import failed. `GeneratedScene` logs the error and continues. Check whether `validate_job` ran | [The Remotion Project](09-remotion-project.md) |
| The review reports a mispronunciation on a respelled word | `tts_text` is empty on the video, so the reviewer cannot compare the spoken text with the script | [AI Review](21-ai-review.md) |
| Every publishing route returns `503` | Publishing is disabled or no postforme key is stored. The API checks both before any outbound call | [Publishing](14-publishing.md) |
| A publish returns `502` with `"reconciling": true` | The post may exist although the response was lost. Do not retry. The worker looks the post up by the video's id | [Publishing](14-publishing.md) |

### Job files written from a host shell

The render gateway derives each job file's location from the video's id and ignores the path
stored in the database, so a host path in a path column does no harm. A script that drives the
MCP server from a host shell must write into the same jobs volume (`~/.tubematic-data/jobs`, the
default outside a container).

The MCP server reads each API key from the settings table on every call (`elevenlabs_api_key`)
and falls back to the environment variable (`ELEVENLABS_API_KEY`). Onboarding does not write the
variable. It exists so that a Compose `environment:` entry works, which is how the test stack
supplies its dummy keys. A host script that gets "ElevenLabs API key not set" is therefore
reading a database without the key: point it at the install's database with `TUBEMATIC_DB`.

### A video does not play

The stream route (`dashboard/app/stream/[...path]/route.ts`, described in
[Dashboard](15-dashboard.md)) serves only `.mp4` and `.mp3` files that are regular files under
`/output_videos`. It answers `404` for a path that escapes it, a missing file, a symlink or
symlinked directory whose target is outside it, a directory, and any other extension.

- The player asks for `/stream/<project_id>/<video_id>.mp4` whatever `video_path` says. Confirm
  that a regular file exists at `/output_videos/<project_id>/<video_id>.mp4` inside the container.
  A video with no domain uses `default_proj`.
- A `416` means the browser asked for a byte range past the end of the file, usually because the
  file was replaced while it was open. Reload the page.
- A `401` means the session expired. Sign in again.
