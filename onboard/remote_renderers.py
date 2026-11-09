"""Remote renderers: publishing the render gateway's port to other machines.

The render gateway (renderer/api/render_gateway.py) listens on port 4443 inside
the tubematic-api container. Out of the box it is reachable only on the Compose
network, by the built-in renderer. Renderers on other machines need the port
published on the host, and they need to know the address to dial — both are
set by the opt-in `renderers` onboarding step (`python3 onboard.py --step
renderers`), which this module supports. Everything here is host-side.

Why an override file under the data root, like onboard/gpu.py's: publishing a
port is a property of how the container is created, so it has to be in the
Compose configuration, and `docker-compose.yml` is the same file on every
install — a published 4443 there would open the gateway on machines that never
asked for it. Upgrades install into a new directory, so a file beside the
checkout would be left behind; ~/.tubematic-data is the machine-state root that
already carries the database, the secrets and compose.gpu.json across upgrades.

The address itself is the bare settings row `render_gateway_address` ('' =
off). The dashboard reads it to build enrollment tokens and to enable its "Add
renderer" button; the override only publishes the port.

JSON, which Compose reads as YAML, so writing and reading it back needs no YAML
library in the onboarding venv.
"""
import ipaddress
import json
import re
import socket
import sqlite3
import ssl
import time
from pathlib import Path

from onboard.config import DATA_ROOT

OVERRIDE_PATH = DATA_ROOT / "compose.renderers.json"
API_SERVICE = "tubematic-api"
GATEWAY_PORT = 4443          # inside the container; keep in sync with docker-compose.yml
DEFAULT_PORT = 4443          # on the host, when the address names none
SETTING_KEY = "render_gateway_address"  # keep in sync with renderer/api/pipeline.py

STEP_HINT = "python3 onboard.py --step renderers"
DOCS_HINT = "docs/user-guide/11-remote-renderers.md"
# The token is never part of the command: a command line is visible to every
# user of the renderer machine (ps, /proc) and lands in shell history. The
# script asks for the token with a hidden prompt instead.
# Keep in sync with renderer/api/pipeline.py::REMOTE_RENDERER_COMMAND.
HOST_COMMAND = "python3 tubematic_remote_renderer.py install"

# A DNS name: dot-separated labels of letters, digits and hyphens, none
# starting or ending with a hyphen.
_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_PORT_ENTRY = re.compile(r"^(?:0\.0\.0\.0|\[::\]):([0-9]{1,5}):" + str(GATEWAY_PORT) + r"$")


def override_path() -> Path:
    """Looked up at call time so tests can point it elsewhere."""
    return OVERRIDE_PATH


# ── The address ──────────────────────────────────────────────────────────────

def _check_host(host: str) -> None:
    if host.lower() in ("localhost", "localhost.localdomain"):
        raise ValueError("a renderer on another machine cannot reach this one at localhost — "
                         "give this machine's IP address or DNS name")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is None:
        if len(host) > 253:
            raise ValueError("that name is too long for a DNS name")
        labels = host.split(".")
        if not all(_LABEL.match(label) for label in labels):
            raise ValueError(f"{host!r} is not an IP address or a DNS name")
        if labels[-1].isdigit():
            # All-numeric last label: an IPv4 address that did not parse
            # (999.1.1.1, 10.0.0), never a real DNS name.
            raise ValueError(f"{host!r} is not a valid IPv4 address")
        return
    if ip.version == 6 and ip.is_link_local:
        raise ValueError(f"{host} is an IPv6 link-local address (fe80::/10): dialling it needs "
                         "the renderer's own interface name, which a token cannot carry — give "
                         "a routable address or a DNS name")
    # An IPv4 address written as IPv6 (::ffff:127.0.0.1, or the old ::127.0.0.1
    # form) is judged as the IPv4 address it is: Python's IPv6 checks do not
    # look inside it, so ::ffff:127.0.0.1 would pass as "not loopback".
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.packed[:12] == bytes(12) and int(ip) > 1:
            ip = ipaddress.IPv4Address(ip.packed[12:])
    if ip.is_unspecified:
        raise ValueError(f"{host} means \"every address\", which a renderer cannot dial — "
                         "give this machine's own address")
    if ip.is_loopback:
        raise ValueError(f"{host} is a loopback address; a renderer on another machine cannot "
                         "reach this one there")
    if ip.is_multicast:
        raise ValueError(f"{host} is a multicast address, not one machine's address")
    if ip == ipaddress.IPv4Address("255.255.255.255"):
        raise ValueError(f"{host} is the broadcast address, not one machine's address")


def parse_address(text) -> tuple[str, int]:
    """(host, port) from `host`, `host:port`, `[ipv6]` or `[ipv6]:port`.
    The host comes back without brackets. ValueError (a sentence a person can
    act on) for anything else: a scheme, a path, a bare IPv6 address, a port
    outside 1-65535, a loopback or "any" address."""
    if not isinstance(text, str):
        raise ValueError("the address is not text")
    text = text.strip()
    if not text:
        raise ValueError("an address is required")
    if "://" in text or text.lower().startswith(("http:", "https:")):
        raise ValueError("give only the address, without http:// or https://")
    if any(c in text for c in "/@?# \t"):
        raise ValueError("give only a host name or IP address, optionally with :port")
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            raise ValueError("an IPv6 address opened with [ needs a closing ]")
        host, rest = text[1:end], text[end + 1:]
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError(f"{host!r} inside [ ] is not an IPv6 address") from None
        if rest and not rest.startswith(":"):
            raise ValueError("after ] only :port may follow")
        port_text = rest[1:] if rest else None
    else:
        if text.count(":") > 1:
            raise ValueError("write an IPv6 address in brackets, e.g. [2001:db8::1] or "
                             "[2001:db8::1]:4443")
        host, sep, port_text = text.partition(":")
        if not sep:
            port_text = None
    if port_text is None:
        port = DEFAULT_PORT
    else:
        if not port_text.isdigit():
            raise ValueError("the port must be a number")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError("the port must be between 1 and 65535")
    _check_host(host)
    return host, port


def format_address(host: str, port: int) -> str:
    """`host:port`, with an IPv6 host in brackets — the stored form, and what
    https://<address> in an enrollment token needs."""
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def normalize_address(text) -> str:
    return format_address(*parse_address(text))


def address_error(text) -> str | None:
    """None when `text` is a usable address, else why not (for a prompt's validator)."""
    try:
        parse_address(text)
    except ValueError as e:
        return str(e)
    return None


def gateway_url(address: str) -> str:
    """https://<address>, the default port added when the address names none."""
    return "https://" + normalize_address(address)


# ── The override ─────────────────────────────────────────────────────────────

def render_override(port: int, ipv6: bool = False) -> str:
    """The override file's text. Only tubematic-api changes: it publishes the
    gateway on every IPv4 address (and every IPv6 one when the renderers dial
    an IPv6 address — the "[::]" bind is only added then, because a host with
    IPv6 disabled refuses it and `up` would fail)."""
    ports = [f"0.0.0.0:{port}:{GATEWAY_PORT}"]
    if ipv6:
        ports.append(f"[::]:{port}:{GATEWAY_PORT}")
    doc = {
        "x-tubematic": ("Written by `python3 onboard.py --step renderers`. Re-run that step to "
                        "change the address or turn remote renderers off; do not edit this file "
                        "by hand."),
        "services": {API_SERVICE: {"ports": ports}},
    }
    return json.dumps(doc, indent=2) + "\n"


def read_override(path: Path = None) -> dict | None:
    """{"port"} from an existing override, None when there is none. Raises
    ValueError for a file that exists but is not exactly one this module
    writes: a host port outside 1-65535, a duplicate or extra ports entry, a
    bind other than 0.0.0.0 (plus [::]), another service or any other key.
    Compose would accept some of those (port 0 publishes a random port), so
    upgrade.py could not rely on `up` to refuse them after it has stopped
    everything."""
    path = path or override_path()
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text())
        ports = doc["services"][API_SERVICE]["ports"]
        if not isinstance(ports, list) or not ports:
            raise ValueError("no ports entry")
        match = _PORT_ENTRY.match(ports[0]) if isinstance(ports[0], str) else None
        if not match:
            raise ValueError(f"unexpected ports entry {ports[0]!r}")
        port = int(match.group(1))
        if not 1 <= port <= 65535:
            raise ValueError(f"host port {port} is outside 1-65535")
        expected = json.loads(render_override(port, ipv6=len(ports) > 1))
        if not isinstance(doc.get("x-tubematic", ""), str):
            raise ValueError("unexpected x-tubematic value")
        doc.pop("x-tubematic", None)
        expected.pop("x-tubematic", None)
        if doc != expected:
            raise ValueError("it holds something other than the one published port this "
                             f"installer writes (expected {expected['services']})")
        return {"port": port}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        raise ValueError(f"{path} is not a remote-renderers override this installer wrote "
                         f"({e})") from e


def override_problems(path: Path = None) -> list[str]:
    """Why `docker compose up` would fail or misbehave with the current
    override, if it would. Empty when there is none or it is usable. Compose
    refuses a file it cannot parse, so upgrade.py must see this before it
    stops anything."""
    try:
        read_override(path)
    except ValueError as e:
        return [f"{e}. Re-run: {STEP_HINT}"]
    return []


# ── The stored address ───────────────────────────────────────────────────────

def stored_address(db_path) -> str:
    """The settings row, '' when off, unset, or the database cannot be read.
    Read-only."""
    if not Path(db_path).exists():
        return ""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT value FROM settings WHERE key = ?",
                              (SETTING_KEY,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return ""
    return (row[0] or "").strip() if row else ""


# ── The local check ──────────────────────────────────────────────────────────

def check_gateway(port: int, expected_pin: str, *, host: str = "127.0.0.1",
                  timeout: float = 5.0) -> tuple[str, str]:
    """TLS handshake to host:port, comparing the certificate's pin with the
    gateway's. Returns (result, detail) with result "ok", "closed" (nothing
    answers — still starting, or not published), "not_tls" or "wrong_cert"."""
    from tubematic_core.renderers import cert_pin
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # The pin is compared by hand below: the gateway's certificate is
    # self-signed and carries no name, so normal verification cannot apply.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            try:
                with ctx.wrap_socket(sock) as tls:
                    der = tls.getpeercert(binary_form=True)
            except (ssl.SSLError, ConnectionError, socket.timeout) as e:
                return "not_tls", f"{host}:{port} answers, but not with TLS ({e})"
    except OSError as e:
        return "closed", f"nothing answers on {host}:{port} ({e.strerror or e})"
    pin = cert_pin(der or b"")
    if pin != expected_pin:
        return "wrong_cert", (f"{host}:{port} answers with a different certificate "
                              f"({pin}, expected {expected_pin})")
    return "ok", f"{host}:{port} answers with the render gateway's certificate"


def wait_for_gateway(port: int, expected_pin: str, *, attempts: int = 12, delay: float = 5.0,
                     check=None, sleep=time.sleep) -> tuple[str, str]:
    """check_gateway until it answers: a freshly recreated tubematic-api takes
    a few seconds to start serving. "closed" and "not_tls" are retried — while
    the container starts, Docker's port proxy accepts a connection and then
    drops it, which reads as a failed handshake. A wrong certificate will not
    fix itself, so it is returned at once."""
    check = check or check_gateway
    result = ("closed", "not checked")
    for i in range(attempts):
        result = check(port, expected_pin)
        if result[0] in ("ok", "wrong_cert"):
            return result
        if i < attempts - 1:
            sleep(delay)
    return result


def check_hint(result: str, port: int) -> str:
    service = ("Check that tubematic-api is running and healthy (python3 scripts/service.py "
               "status) and its log (python3 scripts/service.py logs tubematic-api).")
    if result == "closed":
        return (f"{service} Another program already using port {port} stops Docker "
                "publishing it.")
    if result == "not_tls":
        return (f"{service} If it is healthy, another program answers on port {port} — free "
                f"the port, or re-run `{STEP_HINT}` with another one.")
    return (f"Another program, or a TLS-terminating proxy, answers on port {port} instead of "
            "Tubematic's render gateway. Renderers trust only the gateway's own certificate, "
            "so nothing may sit in front of it — free the port, or re-run "
            f"`{STEP_HINT}` with another port.")


def untested_address_note(address: str) -> str:
    """The local check proves the port is published and that the gateway
    answers on it — on this machine. Whether the address in the tokens leads
    here from another machine (DNS, routing, NAT, a firewall) it cannot see."""
    return (f"Only this machine's port and certificate were checked. Whether {address} reaches "
            "this machine from your renderer machines was not tested here: the renderer's "
            "install checks it (and the certificate) when it first connects.")


def firewall_note(port: int) -> str:
    return (f"Allow TCP port {port} into this machine from your renderer machines only — at "
            "your network or cloud firewall, or in Docker's DOCKER-USER iptables chain: "
            "Docker publishes ports ahead of ufw's own rules, so a ufw rule alone does not "
            f"restrict it. See {DOCS_HINT}.")


# ── Readout for upgrade.py --check / service.py status ───────────────────────

def report_lines(db_path) -> list[tuple[str, str]]:
    """(level, text) where level is "ok", "warn" or "info". Read-only."""
    try:
        current = read_override()
    except ValueError as e:
        return [("warn", f"{e}. Re-run: {STEP_HINT}")]
    address = stored_address(db_path)
    if current is None and not address:
        return [("info", "Remote renderers: off — only the built-in renderer renders (to let "
                         f"renderers on other machines connect: {STEP_HINT})")]
    if current is None:
        return [("warn", f"Remote renderers are set to reach this machine at {address}, but no "
                         f"port is published for them — re-run: {STEP_HINT}")]
    if not address:
        return [("warn", f"Port {current['port']} is published for remote renderers, but no "
                         f"address is stored for them — re-run: {STEP_HINT}")]
    try:
        _, port = parse_address(address)
    except ValueError:
        port = None
    if port != current["port"]:
        return [("warn", f"Remote renderers reach this machine at {address}, but port "
                         f"{current['port']} is the one published — re-run: {STEP_HINT}")]
    return [("info", f"Remote renderers: on — they reach this machine at {address} "
                     f"(port {port} published)")]
