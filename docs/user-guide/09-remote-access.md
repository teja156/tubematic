# Remote Access

How to use the dashboard from a machine other than the one Tubematic is installed on: over a private
network with **Twingate**, or over HTTPS with a reverse proxy, **Caddy** or **nginx**.

If you run Tubematic in [Kasm Workspaces](02-installing.md#installing-in-kasm-workspaces), you
already have remote access: open the dashboard in the session's own browser. This page is for
installs on an ordinary host.

---

## Why it needs setting up

The dashboard listens on port 3000 and speaks **plain HTTP**. It is password-protected, but over
plain HTTP the password and the session cookie cross the network readable.

- **A release install** binds port 3000 to `127.0.0.1`, so nothing but the machine itself can reach
  it. Something has to run on that machine and carry other machines' requests to it.
- **A source install** publishes port 3000 on every interface, so the login page is already reachable
  from the network — over plain HTTP. A proxy in front does **not** close that port, and a host
  firewall such as `ufw` does not either: Docker writes its own firewall rules for published ports,
  ahead of `ufw`'s. To stop the direct route on a source install, change the dashboard's `ports:` entry
  in `docker-compose.yml` from `"3000:3000"` to `"127.0.0.1:3000:3000"` and run
  `docker compose up -d tubematic-dashboard`. That is a local change to a tracked file, so carry it
  across each `git pull`. Or install from a release, which binds it this way for you.

What the network exposure is and why the other two ports are never exposed is in
[Installing — Network exposure](02-installing.md#network-exposure).

## Choosing a method

| Method | What you need | What it gives you |
|---|---|---|
| **[Twingate](#twingate)** | A free Twingate account; its app on each device you use | Access only from your own signed-in devices. Nothing is opened to the internet, and no domain or certificate is needed |
| **[Caddy](#caddy)** | A domain name, or a willingness to install a certificate on each device | HTTPS with certificates obtained and renewed automatically. The least configuration of any proxy |
| **[nginx](#nginx)** | A domain name, and certbot for the certificate | HTTPS through a proxy you may already run for other sites |

Twingate is the safest choice for a single person: the dashboard is never on the public internet, so
nothing but your own devices can reach even the login page. A reverse proxy on a public domain puts
the login page on the internet, behind only the dashboard password and its
[login backoff](04-dashboard.md#signing-in). Tailscale, WireGuard and similar private networks work
the same way as Twingate does here; this page does not cover them step by step.

You can combine them: Caddy or nginx on the host, reached through Twingate, gives HTTPS without
putting anything on the internet. See [HTTPS over Twingate](#https-over-twingate).

## What any reverse proxy must do

Caddy and nginx are covered below. Any other proxy works if it meets these points:

- **Serve the dashboard at the root of its own hostname** — `https://tubematic.example.com/`, not
  `https://example.com/tubematic/`. The dashboard has no setting for running under a sub-path, so its
  pages, API calls and video links all assume they start at `/`.
- **Send `X-Forwarded-Proto: https`.** The dashboard marks its session cookie `Secure` only when it
  knows the browser used HTTPS, and behind a proxy this header is the only way it can know. Without
  it, everything still works, but the browser would send the cookie over plain HTTP too.
- **Pass `Range` requests through and do not cache.** The video player seeks with range requests to
  `/stream/…`, and every `/api/…` answer is live data.
- **Allow at least 60 seconds for a response.** A voice preview waits on ElevenLabs before it
  answers, and can take that long.
- **Leave the browser's own `Origin` and `Sec-Fetch-Site` headers alone.** The dashboard refuses any
  change (a save, an approval, a login) that the browser does not mark as coming from the
  dashboard's own page.

How the dashboard uses these is explained in
[Infrastructure — Authentication](../developer/16-infrastructure.md#authentication).

---

## Twingate

[Twingate](https://www.twingate.com/) is a private-access network. A small program on the Tubematic
host, the **Connector**, makes an outbound connection to Twingate, and the Twingate **Client** on
your laptop or phone reaches the dashboard through it. No port is opened on the host or your
router, and the dashboard is never visible on the internet.

The pieces, in Twingate's terms:

| Term | Here |
|---|---|
| **Network** | Your Twingate account, at `<name>.twingate.com` |
| **Remote Network** | The place the Tubematic host is — one entry, for example "Home" |
| **Connector** | The program you run on the Tubematic host |
| **Resource** | The dashboard: an address and port the Connector can reach |
| **Group** | Who may use a Resource. Your own account is enough |
| **Client** | The app on each device you use the dashboard from |

Twingate's free **Starter** plan is enough for one person and a few devices; check
[twingate.com/pricing](https://www.twingate.com/pricing) for its current limits.

### 1. Create the network and a Remote Network

1. Sign up at [twingate.com](https://www.twingate.com/) and choose a network name. It becomes
   `<name>.twingate.com`, which every Client asks for.
2. In the Admin Console, open **Network → Remote Networks**, add one, and give it a name such as
   "Home".

### 2. Run a Connector on the Tubematic host

The Connector must run **on the Tubematic host itself**, because a release install's dashboard
answers only on that machine's `127.0.0.1`.

1. In the Remote Network, open a Connector and choose to deploy it on **Linux**. Generate its tokens
   when asked. The console then shows a one-line install command that carries them.
2. Run that command on the Tubematic host. It installs the Connector as a systemd service, with its
   tokens in `/etc/twingate/connector.conf`.
3. Confirm it is running:

   ```bash
   sudo systemctl status twingate-connector
   ```

   The Connector also shows as connected in the Admin Console.

The console offers Docker as well. A Connector in a Docker container reaches the host's `127.0.0.1`
**only** with host networking (`--network host`, or `network_mode: host` in a compose file); on
Docker's default network, `127.0.0.1` is the container itself and the dashboard is unreachable. The
systemd install has no such catch.

Twingate recommends two Connectors per Remote Network for redundancy. One is enough for a dashboard
you use yourself; if it stops, you lose remote access until it is back, and Tubematic itself is
unaffected.

### 3. Add the dashboard as a Resource

In the Remote Network, add a Resource:

- **Address:** `127.0.0.1`. The Connector resolves it on the Tubematic host, so it means the host's
  own loopback, where the dashboard listens.
- **Alias:** a name you will type in the browser, such as `tubematic.internal`. Without one, the
  address you would type on your laptop is `127.0.0.1`, which your laptop reads as itself. Use a
  name with at least one dot, and avoid `.local`.
- **Ports:** restrict it to **TCP 3000**, and block UDP and ICMP. Then the Resource reaches the
  dashboard and nothing else on the host.
- **Access:** grant it to a Group your account is in.

For a source install, whose dashboard is published on every interface, the host's LAN address works
as the Resource address too. `127.0.0.1` works for both kinds of install.

### 4. Connect from your device

1. Install the Twingate Client from [get.twingate.com](https://get.twingate.com/).
2. Enter your network name and sign in.
3. Open `http://tubematic.internal:3000` (your alias) and sign in to the dashboard.

**Plain HTTP is acceptable here.** The Client and the Connector talk over an encrypted tunnel that
only they can read, and the last step, from the Connector to the dashboard, happens inside the
Tubematic host. Nothing crosses a network in the clear. The session cookie is not marked `Secure`,
which is what lets it work over `http://`.

### HTTPS over Twingate

Twingate has no HTTPS of its own. If you want the browser to see HTTPS as well, for example because
you also open the dashboard from other networks, run Caddy or nginx on the host as below. Then make
the proxy the Resource instead, on TCP 443, with an alias the proxy has a certificate for: a name in
a domain you own, using a DNS challenge ([Caddy — on a private network](#on-a-private-network)), or
Caddy's own certificate authority.

---

## Caddy

[Caddy](https://caddyserver.com/) is a web server that obtains and renews HTTPS certificates by
itself. Its default proxy settings already meet everything in
[What any reverse proxy must do](#what-any-reverse-proxy-must-do): it passes `Host` through, sets
`X-Forwarded-Proto`, passes range requests and does not cache.

### Install

On Debian or Ubuntu, from Caddy's own package repository (see
[Caddy's install page](https://caddyserver.com/docs/install) for other systems):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
  /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

The package runs Caddy as the `caddy` systemd service, which reads `/etc/caddy/Caddyfile`. After any
change to that file, apply it with:

```bash
sudo systemctl reload caddy
```

### With a public domain name

Point a DNS name at the host — for example an `A` record for `tubematic.example.com` — and make
ports **80 and 443** reachable from the internet (forward them on your router if the host is at
home). Then replace the contents of `/etc/caddy/Caddyfile` with:

```
tubematic.example.com {
	reverse_proxy 127.0.0.1:3000
}
```

Reload Caddy. It obtains a certificate from Let's Encrypt, renews it before it expires, and
redirects `http://` to `https://`. Open `https://tubematic.example.com`.

### On a private network

If the host is not reachable from the internet, Caddy cannot prove the name to Let's Encrypt the
usual way. Two options:

- **Caddy's own certificate authority.** Add `tls internal` to the site:

  ```
  tubematic.home.arpa {
  	tls internal
  	reverse_proxy 127.0.0.1:3000
  }
  ```

  Caddy then issues the certificate itself, and **every device you browse from must trust Caddy's
  root certificate**, or the browser shows a certificate warning. With the apt package the root is
  `/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`, readable only by the `caddy`
  user, so copy it out with `sudo`:

  ```bash
  sudo cat /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt > caddy-root.crt
  ```

  Then install `caddy-root.crt` in each device's (or browser's) trusted certificates.
  `sudo caddy trust` does the same for the host itself only. The name (`tubematic.home.arpa` here)
  must resolve to the host on those devices: an entry in your router's DNS, or in each device's
  hosts file.
- **A domain you own, with a DNS challenge.** Caddy proves the name by writing a DNS record through
  your DNS provider's API, so the host needs no open ports and the certificate is trusted everywhere
  with nothing to install. This needs a Caddy build that includes your provider's module; see
  Caddy's [DNS challenge documentation](https://caddyserver.com/docs/automatic-https#dns-challenge).

### Running Caddy in Docker

Run it with **host networking** (`network_mode: host`). Without it, `127.0.0.1` inside the Caddy
container is the container itself, and a release install's dashboard is unreachable from there.

---

## nginx

[nginx](https://nginx.org/) works as well as Caddy, with more to configure. Unlike Caddy, its defaults
do **not** meet [What any reverse proxy must do](#what-any-reverse-proxy-must-do): a bare
`proxy_pass` gives a working dashboard, but nginx sends no `X-Forwarded-Proto`, so the session cookie
is never marked `Secure`.

### Install

On Debian or Ubuntu:

```bash
sudo apt install nginx
```

### The server block

Create `/etc/nginx/sites-available/tubematic`:

```nginx
server {
    listen 80;
    server_name tubematic.example.com;

    # The one the dashboard needs: without it the session cookie is never Secure.
    proxy_set_header X-Forwarded-Proto $scheme;

    # Ordinary proxy hygiene. nginx otherwise speaks HTTP/1.0 to the dashboard
    # (before nginx 1.29.7) and sends Host as "127.0.0.1:3000".
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    # A voice preview can take a minute; nginx gives up after 60 seconds.
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:3000;
    }

    # Video: hand it straight through rather than buffering it to disk.
    location /stream/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_buffering off;
    }
}
```

Enable it and check the syntax before reloading:

```bash
sudo ln -s /etc/nginx/sites-available/tubematic /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

The `proxy_set_header` lines are written once at the server level on purpose. nginx applies them to
a `location` only if that `location` sets none of its own; adding a single `proxy_set_header` inside
one silently drops all of these for it.

### Add HTTPS with certbot

With a public DNS name pointing at the host and port 80 reachable from the internet,
[certbot](https://certbot.eff.org/) obtains a Let's Encrypt certificate and rewrites the server block
for HTTPS. On Debian or Ubuntu, install it with its nginx plugin from the distribution's packages:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tubematic.example.com
```

The package installs a timer that renews the certificate. certbot adds a `listen 443 ssl` with the
certificate and redirects `http://` to `https://`. (certbot's own site recommends its snap, which
tracks the newest release; that route needs `snapd`, which Debian does not install by default.)
Check that renewal works with:

```bash
sudo certbot renew --dry-run
```

`X-Forwarded-Proto $scheme` now sends `https`, which is what makes the session cookie `Secure`.

On a private network, use a certbot DNS plugin for your provider instead, or a certificate from your
own certificate authority in `ssl_certificate` and `ssl_certificate_key`.

**Be careful with HSTS** (certbot's `--hsts`, or a `Strict-Transport-Security` header). It tells
browsers to refuse plain HTTP for that name for as long as it says, and cannot be withdrawn from a
browser that has seen it. Leave it off unless the name will only ever be served over HTTPS.

---

## Check that it works

Through whichever method you set up, from a device other than the Tubematic host:

1. **The login redirect stays on your address.** Opening the dashboard's address with no session
   lands on its `/login` page at the same address. From a terminal:

   ```bash
   curl -sI https://tubematic.example.com/ | grep -i '^location'
   ```

   should print `location: /login`.
2. **Sign in.** Over HTTPS, the browser's developer tools show the `tm_session` cookie with
   **Secure** ticked (in Chrome: Application → Cookies). Over Twingate's `http://` it is not ticked,
   and that is expected.
3. **Save something.** Change a value in Settings and press **SAVE**, or pause and resume the
   pipeline. A `403 cross-site request refused` means something between the browser and the
   dashboard is rewriting the request.
4. **Play a video** in the Library and drag the playhead. Seeking means range requests get through.

Problems, by symptom, are in [Troubleshooting — Remote access](08-troubleshooting.md#remote-access).
