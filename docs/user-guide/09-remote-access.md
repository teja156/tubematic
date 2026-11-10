# Remote Access

How to use the dashboard from a machine other than the one Tubematic is installed on. You can reach
it over a private network with Twingate, or over HTTPS through a reverse proxy, Caddy or nginx.

If you run Tubematic in [Kasm Workspaces](02-installing.md#installing-in-kasm-workspaces), you
already have remote access: open the dashboard in the session's own browser. The steps below are for
an install on an ordinary host.

---

## Why it needs setting up

The dashboard serves plain HTTP on port 3000, so your password and session cookie cross a network
unencrypted. What you set up depends on how you installed:

- A release install binds port 3000 to `127.0.0.1`, so only the machine itself can reach the
  dashboard. A program on that machine has to carry other machines' requests to it. Each method
  below provides one.
- A source install publishes port 3000 on every network interface, so the login page is already
  reachable from the network over plain HTTP. A proxy in front does not close that port. A host
  firewall such as `ufw` does not close it either, because Docker applies its own firewall rules for
  published ports ahead of `ufw`'s. To close the direct route, change the dashboard's `ports:` entry
  in `docker-compose.yml` from `"3000:3000"` to `"127.0.0.1:3000:3000"` and run
  `python3 scripts/service.py start tubematic-dashboard`. This edits a tracked file, so apply it
  again after each `git pull`.

[Network exposure](02-installing.md#network-exposure) lists every port Tubematic opens and who can
reach it.

## Choosing a method

| Method | What you need | What it gives you |
|---|---|---|
| [Twingate](#twingate) | A free Twingate account, and its app on each device you use | Access from your own signed-in devices only. Nothing is opened to the internet, and you need no domain or certificate |
| [Caddy](#caddy) | A domain name, or a certificate installed on each device | HTTPS with certificates obtained and renewed automatically. It needs the least configuration of the two proxies |
| [nginx](#nginx) | A domain name, and certbot for the certificate | HTTPS through a proxy you may already run for other sites |

Twingate is the safest choice for one person. The dashboard stays off the public internet, so only
your own devices can reach the login page. A reverse proxy on a public domain puts the login page on
the internet, protected by the dashboard password and its
[login backoff](04-dashboard.md#signing-in). Tailscale, WireGuard and similar private networks work
the same way as Twingate. Follow their own guides to set them up.

You can combine the methods. Caddy or nginx on the host, reached through Twingate, gives HTTPS and
puts nothing on the internet. See [HTTPS over Twingate](#https-over-twingate).

## What any reverse proxy must do

The sections below cover Caddy and nginx. Any other proxy works if it does all of the following:

- It serves the dashboard at the root of its own hostname, for example
  `https://tubematic.example.com/`. A sub-path such as `https://example.com/tubematic/` does not
  work. The dashboard has no setting for one, and its pages, API calls and video links all start at
  `/`.
- It sends `X-Forwarded-Proto: https`. The dashboard marks its session cookie `Secure` when it knows
  the browser used HTTPS, and behind a proxy this header is how it knows. Without the header the
  dashboard still works, and the browser also sends the cookie over plain HTTP.
- It passes `Range` requests through and does not cache. The video player seeks with range requests
  to `/stream/…`, and every `/api/…` answer is live data.
- It allows at least 60 seconds for a response. A voice preview waits on ElevenLabs before it
  answers, and can take that long.
- It leaves the browser's own `Origin` and `Sec-Fetch-Site` headers unchanged. The dashboard refuses
  any change (a save, an approval, a login) that the browser does not mark as coming from the
  dashboard's own page.

How the dashboard uses these headers is in
[Infrastructure](../developer/16-infrastructure.md#authentication).

---

## Twingate

[Twingate](https://www.twingate.com/) is a private-access network. A small program on the Tubematic
host, the **Connector**, makes an outbound connection to Twingate. The Twingate **Client** on your
laptop or phone reaches the dashboard through it. You open no port on the host or your router, and
the dashboard is not visible on the internet.

Twingate's terms, and what each one is in this setup:

| Term | Here |
|---|---|
| Network | Your Twingate account, at `<name>.twingate.com` |
| Remote Network | The place the Tubematic host is. One entry, for example "Home" |
| Connector | The program you run on the Tubematic host |
| Resource | The dashboard: an address and port the Connector can reach |
| Group | Who may use a Resource. Your own account is enough |
| Client | The app on each device you use the dashboard from |

Twingate's free Starter plan is enough for one person and a few devices. Check
[twingate.com/pricing](https://www.twingate.com/pricing) for its current limits.

### 1. Create the network and a Remote Network

1. Sign up at [twingate.com](https://www.twingate.com/) and choose a network name. It becomes
   `<name>.twingate.com`, which every Client asks for.
2. In the Admin Console, open **Network → Remote Networks**, add one, and give it a name such as
   "Home".

### 2. Run a Connector on the Tubematic host

Run the Connector on the Tubematic host itself, because a release install's dashboard answers only
on that machine's `127.0.0.1`.

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
only with host networking (`--network host`, or `network_mode: host` in a compose file). On Docker's
default network, `127.0.0.1` is the container itself and the dashboard is unreachable. The systemd
install does not have this problem.

Twingate recommends two Connectors per Remote Network for redundancy. One is enough for a dashboard
you use yourself. If it stops, you lose remote access until it is back, and Tubematic keeps running.

### 3. Add the dashboard as a Resource

In the Remote Network, add a Resource:

- **Address:** `127.0.0.1`. The Connector resolves it on the Tubematic host, so it means the host's
  own loopback, where the dashboard listens.
- **Alias:** a name you will type in the browser, such as `tubematic.internal`. Without an alias,
  the address you would type on your laptop is `127.0.0.1`, which your laptop reads as itself. Use a
  name with at least one dot, and avoid `.local`.
- **Ports:** allow TCP 3000 only, and block UDP and ICMP. The Resource then reaches the dashboard
  and nothing else on the host.
- **Access:** grant it to a Group your account is in.

On a source install, whose dashboard is published on every interface, the host's LAN address also
works as the Resource address. `127.0.0.1` works for both kinds of install.

### 4. Connect from your device

1. Install the Twingate Client from [get.twingate.com](https://get.twingate.com/).
2. Enter your network name and sign in.
3. Open `http://tubematic.internal:3000` (your alias) and sign in to the dashboard.

Plain HTTP is acceptable over Twingate. The Client and the Connector talk over an encrypted tunnel
that only they can read, and the last step, from the Connector to the dashboard, happens inside the
Tubematic host. Nothing crosses a network unencrypted. The session cookie is not marked `Secure`
here, which lets it work over `http://`.

### HTTPS over Twingate

Twingate has no HTTPS of its own. If you want the browser to see HTTPS as well, for example because
you also open the dashboard from other networks, run [Caddy](#caddy) or [nginx](#nginx) on the host.
Then make the proxy the Resource, on TCP 443, with an alias the proxy has a certificate for. The
alias can be a name in a domain you own, with a certificate from a DNS challenge, or a name served
with Caddy's own certificate authority. Both are under [On a private network](#on-a-private-network).

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

Point a DNS name at the host, for example an `A` record for `tubematic.example.com`. Make ports 80
and 443 reachable from the internet (forward them on your router if the host is at home). Then
replace the contents of `/etc/caddy/Caddyfile` with:

```
tubematic.example.com {
	reverse_proxy 127.0.0.1:3000
}
```

Reload Caddy. It obtains a certificate from Let's Encrypt, renews it before it expires, and
redirects `http://` to `https://`. Open `https://tubematic.example.com`.

### On a private network

If the host is not reachable from the internet, Caddy cannot prove the name to Let's Encrypt the
usual way. You have two options:

- Use Caddy's own certificate authority. Add `tls internal` to the site:

  ```
  tubematic.home.arpa {
  	tls internal
  	reverse_proxy 127.0.0.1:3000
  }
  ```

  Caddy then issues the certificate itself. Every device you browse from must trust Caddy's root
  certificate, or the browser shows a certificate warning. With the apt package the root is
  `/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`, readable only by the `caddy`
  user, so copy it out with `sudo`:

  ```bash
  sudo cat /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt > caddy-root.crt
  ```

  Install `caddy-root.crt` in each device's (or browser's) trusted certificates. `sudo caddy trust`
  does the same for the host only. The name (`tubematic.home.arpa` in this example) must resolve to
  the host on those devices, through an entry in your router's DNS or in each device's hosts file.
- Use a domain you own, with a DNS challenge. Caddy proves the name by writing a DNS record through
  your DNS provider's API. The host needs no open ports, and every device trusts the certificate
  with nothing to install. This needs a Caddy build that includes your provider's module. See
  Caddy's [DNS challenge documentation](https://caddyserver.com/docs/automatic-https#dns-challenge).

### Running Caddy in Docker

Run it with host networking (`network_mode: host`). Without host networking, `127.0.0.1` inside the
Caddy container is the container itself, and a release install's dashboard is unreachable from
there.

---

## nginx

[nginx](https://nginx.org/) works as well as Caddy and needs more configuration. Its defaults do not
meet [What any reverse proxy must do](#what-any-reverse-proxy-must-do). A bare `proxy_pass` gives a
working dashboard, but nginx sends no `X-Forwarded-Proto`, so the session cookie is not marked
`Secure`.

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

    # Video: hand it straight through. Do not buffer it to disk.
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

Keep the `proxy_set_header` lines at the server level. nginx applies them to a `location` only if
that `location` sets none of its own. If you add one `proxy_set_header` inside a `location`, nginx
drops all of the server-level ones for it and reports nothing.

### Add HTTPS with certbot

With a public DNS name pointing at the host and port 80 reachable from the internet,
[certbot](https://certbot.eff.org/) obtains a Let's Encrypt certificate and rewrites the server block
for HTTPS. On Debian or Ubuntu, install it with its nginx plugin from the distribution's packages:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tubematic.example.com
```

certbot adds a `listen 443 ssl` with the certificate and redirects `http://` to `https://`. The
package installs a timer that renews the certificate. certbot's own site recommends its snap, which
tracks the newest release. That route needs `snapd`, which Debian does not install by default.
Check that renewal works with:

```bash
sudo certbot renew --dry-run
```

`X-Forwarded-Proto $scheme` now sends `https`, which makes the session cookie `Secure`.

On a private network, use a certbot DNS plugin for your provider, or put a certificate from your own
certificate authority in `ssl_certificate` and `ssl_certificate_key`.

Be careful with HSTS (certbot's `--hsts`, or a `Strict-Transport-Security` header). It tells
browsers to refuse plain HTTP for that name for as long as the header says, and you cannot withdraw
it from a browser that has seen it. Leave it off unless you will serve the name over HTTPS only.

---

## Check that it works

Run these checks through the method you set up, from a device other than the Tubematic host:

1. Check that the login redirect stays on your address. When you open the dashboard's address with
   no session, you land on its `/login` page at the same address. From a terminal, this command
   prints `location: /login`:

   ```bash
   curl -sI https://tubematic.example.com/ | grep -i '^location'
   ```

2. Sign in. Over HTTPS, the browser's developer tools show the `tm_session` cookie with **Secure**
   ticked (in Chrome: Application → Cookies). Over Twingate's `http://` it is not ticked, which is
   expected.
3. Save something. Change a value in Settings and press **SAVE**, or pause and resume the pipeline.
   A `403 cross-site request refused` means something between the browser and the dashboard is
   rewriting the request.
4. Play a video in the Library and drag the playhead. If seeking works, range requests get through.

[Troubleshooting](08-troubleshooting.md#remote-access) lists remote access problems by symptom.
