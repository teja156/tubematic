#!/usr/bin/env python3
"""Run a Tubematic renderer on another machine (TMDEV-190).

    python3 tubematic_remote_renderer.py install --token '<token>' [--image TAG]
                                         [--gpu UUID | --no-gpu] [--name NAME] [--yes]
    python3 tubematic_remote_renderer.py upgrade [--image TAG] [--yes]
    python3 tubematic_remote_renderer.py remove [--yes]
    python3 tubematic_remote_renderer.py status

A remote renderer is one Docker container, `tubematic-remote-renderer`, running
the same backend image as main and talking only to main's render gateway over
HTTPS. This script sets that container up, keeps it on main's version, and
takes it away again. It is a single file with no dependencies beyond Python
3.10 and Docker, because the machine it runs on has no Tubematic checkout: it
is downloaded from the GitHub Release on its own.

Why it trusts what it trusts. The enrollment token (made on main's dashboard)
carries the gateway's address, a one-time secret and the sha256 pin of the
gateway's self-signed certificate. The script fetches that certificate,
compares its pin BEFORE sending a single request, and afterwards trusts that
certificate and nothing else. A machine that answers on the address with any
other certificate (a wrong address, a TLS-terminating proxy, an attacker) is
refused with nothing sent, so the one-time secret never leaves this machine
for anyone but main.

The token itself is never written anywhere by this script. It reaches the
container's environment once (the renderer trades it for a credential it keeps
in the `tubematic-renderer-state` volume and ignores it afterwards), and the
local state file holds only the gateway address, the pin, the image and the
GPU choice.
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONTAINER = "tubematic-remote-renderer"
STATE_VOLUME = "tubematic-renderer-state"
STATE_MOUNT = "/state"
STATE_FILE_NAME = ".tubematic-remote-renderer.json"

# Keep in sync with tubematic_core/version.py::GITHUB_REPO's owner (pinned by
# scripts/tests/test_tubematic_remote_renderer.py). Hardcoded because this
# script runs with no checkout, so it cannot import tubematic_core.
GITHUB_OWNER = "teja156"
# Keep in sync with scripts/gen_release_compose.py::_backend_image.
IMAGE_TEMPLATE = "ghcr.io/{owner}/tubematic-backend:{version}"

# Keep in sync with tubematic_core/renderers.py::TOKEN_PREFIX.
TOKEN_PREFIX = "tmr1."
_PIN = re.compile(r"^sha256:[0-9a-f]{64}$")

# Keep in sync with docker-compose.yml's tubematic-renderer service: its
# command, shm_size and the environment a renderer needs that is not specific
# to the built-in one (pinned by a test).
RENDER_COMMAND = ["python3", "/app/api/render_agent.py"]
SHM_SIZE = "2g"
BASE_ENV = ["PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium"]

# Keep in sync with onboard/gpu.py::DRIVER_CAPABILITIES and render_override's
# environment (pinned by a test that compares the two).
GPU_DRIVER_CAPABILITIES = "graphics,utility"

# Keep in sync with onboard/gpu.py::list_gpus: the same query, so
# TUBEMATIC_HOST_GPUS has the shape the renderer and dashboard already read.
NVIDIA_SMI_QUERY = ["nvidia-smi",
                    "--query-gpu=index,uuid,name,memory.total,driver_version",
                    "--format=csv,noheader,nounits"]

# Version strings the gateway may answer with that are safe as an image tag:
# tubematic_core.version.VERSION_RE plus the development branch's "develop".
_VERSION = re.compile(r"^(?:develop|\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)$")

NAME_MAX = 60   # keep in sync with PATCH /renderers/<id>'s name limit
TLS_TIMEOUT_SECS = 15
WAIT_SECS = 60
POLL_SECS = 2
LOG_LINES = 20

# What the render agent logs once it is connected. "enrolled" on the first
# start of a new renderer, "first heartbeat" on every start (an upgrade has no
# enrollment). Keep in sync with renderer/api/render_agent.py's log lines.
_READY = re.compile(r"\benrolled\b|\bfirst heartbeat\b", re.IGNORECASE)
_FAILED = re.compile(r"enrollment_invalid|enrollment (?:was )?refused|credential_expired"
                     r"|credential expired", re.IGNORECASE)
_NEEDS_UPGRADE = re.compile(r"needs[ _]upgrade", re.IGNORECASE)

DASHBOARD_HINT = "main's dashboard, Settings → Rendering → Renderers"


class RemoteError(Exception):
    """An expected failure: printed as one message, never as a traceback."""


# ── Commands run on this machine ─────────────────────────────────────────────

def run_cmd(argv, *, capture=True, extra_env=None, timeout=None):
    """Every docker and nvidia-smi call goes through here, so tests replace
    this one function. A missing executable is returned as exit 127 rather
    than raised, and extra_env reaches only this one call."""
    env = None
    if extra_env:
        env = {**os.environ, **extra_env}
    kwargs = {"text": True, "env": env, "timeout": timeout}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
    try:
        return subprocess.run(argv, **kwargs)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, f"{argv[0]}: command not found", "")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, f"{argv[0]} timed out", "")


def _out(result) -> str:
    return (result.stdout or "").strip()


def _last_line(result) -> str:
    lines = _out(result).splitlines()
    return lines[-1] if lines else f"exit {result.returncode}"


def docker_info() -> dict:
    """`docker info` as a dict. Raises when Docker is missing or unusable."""
    r = run_cmd(["docker", "info", "--format", "{{json .}}"], timeout=30)
    if r.returncode == 127:
        raise RemoteError("Docker is not installed on this machine (no `docker` command on PATH). "
                          "Install Docker Engine first.")
    info = None
    try:
        info = json.loads(_out(r) or "null")
    except ValueError:
        pass
    server_errors = info.get("ServerErrors") if isinstance(info, dict) else None
    if r.returncode != 0 or not isinstance(info, dict) or server_errors:
        detail = "; ".join(server_errors) if server_errors else _last_line(r)
        raise RemoteError(f"Docker is installed but not usable: {detail}. Is the Docker daemon "
                          "running, and may this user run docker (the `docker` group, or sudo)?")
    return info


def has_nvidia_runtime(info: dict) -> bool:
    """The same test as onboard/gpu.py::docker_has_nvidia_runtime: the
    `nvidia` runtime the NVIDIA Container Toolkit registers."""
    runtimes = info.get("Runtimes")
    return isinstance(runtimes, dict) and "nvidia" in runtimes


def parse_nvidia_smi(text: str) -> list:
    """Keep in sync with onboard/gpu.py::parse_nvidia_smi (pinned by a test):
    a row that does not parse is skipped, never guessed at."""
    gpus = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        index, uuid, driver, memory = parts[0], parts[1], parts[-1], parts[-2]
        name = ", ".join(parts[2:-2])
        if not index.isdigit() or not uuid.startswith("GPU-") or not name:
            continue
        gpus.append({"index": int(index), "uuid": uuid, "name": name,
                     "memory_mib": int(memory) if memory.isdigit() else None,
                     "driver": driver})
    return gpus


def list_gpus() -> list:
    r = run_cmd(NVIDIA_SMI_QUERY, timeout=30)
    if r.returncode != 0:
        return []
    return parse_nvidia_smi(r.stdout or "")


def gpu_label(gpu: dict) -> str:
    mem = f", {gpu['memory_mib'] // 1024} GB" if gpu.get("memory_mib") else ""
    return f"GPU {gpu['index']}: {gpu['name']}{mem} ({gpu['uuid']})"


def container_exists() -> bool:
    return run_cmd(["docker", "container", "inspect", CONTAINER], timeout=30).returncode == 0


def image_present(image: str) -> bool:
    return run_cmd(["docker", "image", "inspect", image], timeout=30).returncode == 0


def volume_exists() -> bool:
    return run_cmd(["docker", "volume", "inspect", STATE_VOLUME], timeout=30).returncode == 0


def pull(image: str) -> None:
    print(f"Pulling {image} …")
    r = run_cmd(["docker", "pull", image], capture=False)
    if r.returncode != 0:
        raise RemoteError(f"Could not pull {image}. If main runs a development build there is no "
                          "published image for it: build one and pass --image.")


# ── Interaction ──────────────────────────────────────────────────────────────

def interactive() -> bool:
    return sys.stdin.isatty()


def confirm(question: str, default: bool) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except EOFError:
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


# ── The token and the pinned gateway ─────────────────────────────────────────

def decode_token(tok) -> dict:
    """Keep in sync with tubematic_core/renderers.py::decode_enrollment_token
    (an agreement test runs both on the same inputs). {"url", "secret", "pin"};
    ValueError on anything malformed."""
    if not isinstance(tok, str):
        raise ValueError("the enrollment token is not a string")
    tok = tok.strip()
    if not tok.startswith(TOKEN_PREFIX):
        raise ValueError(f"the enrollment token does not start with {TOKEN_PREFIX!r}")
    body = tok[len(TOKEN_PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ValueError("the enrollment token is damaged (it was probably cut off when copied)") from None
    if not isinstance(data, dict):
        raise ValueError("the enrollment token is damaged")
    url, secret, pin = data.get("u"), data.get("s"), data.get("p")
    if not all(isinstance(v, str) and v for v in (url, secret, pin)):
        raise ValueError("the enrollment token is missing a field")
    if not url.startswith("https://"):
        raise ValueError("the enrollment token's gateway address is not https")
    if not _PIN.match(pin):
        raise ValueError("the enrollment token's certificate pin is malformed")
    return {"url": url, "secret": secret, "pin": pin}


def cert_pin(der: bytes) -> str:
    """Keep in sync with tubematic_core/renderers.py::cert_pin."""
    return "sha256:" + hashlib.sha256(der).hexdigest()


def gateway_address(url: str) -> tuple:
    """(host, port) of an https gateway URL; 443 when it names no port."""
    try:
        parts = urllib.parse.urlsplit(url)
        scheme, host, port = parts.scheme, parts.hostname, parts.port or 443
    except ValueError:   # a port that is not a number, or out of range
        scheme = host = None
    if scheme != "https" or not host:
        raise RemoteError(f"The gateway address {url!r} is not a valid https address.")
    return host, port


def fetch_pinned_cert(url: str, pin: str) -> str:
    """The gateway's certificate PEM, after checking it against the pin.

    The TLS handshake is the only thing sent before the check: no HTTP request
    goes out until the certificate is known to be main's."""
    host, port = gateway_address(url)
    try:
        pem = ssl.get_server_certificate((host, port), timeout=TLS_TIMEOUT_SECS)
    except (OSError, ssl.SSLError, ValueError) as e:
        raise RemoteError(
            f"Could not reach the render gateway at {host}:{port} ({e}). Check that main has "
            f"remote renderers turned on (`python3 onboard.py --step renderers` on main), that "
            f"the address in the token is one this machine can reach, and that a firewall "
            f"allows TCP {port} from here to main.") from None
    if cert_pin(ssl.PEM_cert_to_DER_cert(pem)) != pin:
        raise RemoteError(
            f"The machine answering at {host}:{port} is not your Tubematic main: its certificate "
            f"does not match the one in the token. Nothing was sent to it. Check the address "
            f"(on main: `python3 onboard.py --step renderers`), and make sure no proxy that "
            f"terminates TLS sits in front of port {port}.")
    return pem


def pinned_context(pem: str) -> ssl.SSLContext:
    """Trusts exactly the pinned certificate (no system roots, no hostname:
    the gateway's certificate is self-signed and names no host)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=pem)
    return ctx


def gateway_version(url: str, pin: str) -> str:
    """main's version, read over a connection that trusts only the pinned
    certificate, which is checked first."""
    pem = fetch_pinned_cert(url, pin)
    request = urllib.request.Request(url.rstrip("/") + "/v1/version",
                                     headers={"Accept": "application/json",
                                              "User-Agent": "tubematic-remote-renderer"})
    try:
        with urllib.request.urlopen(request, context=pinned_context(pem),
                                    timeout=TLS_TIMEOUT_SECS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RemoteError(f"The render gateway answered {e.code} to a version check.") from None
    except (OSError, ssl.SSLError, ValueError) as e:
        raise RemoteError(f"The render gateway's version check failed ({e}).") from None
    if not isinstance(body, dict) or body.get("gateway") != 1:
        raise RemoteError("The render gateway answered with something this script does not "
                          "understand. Download the script from main's own release.")
    version = body.get("version")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise RemoteError(f"The render gateway reported an unusable version {version!r}.")
    return version


# ── The container ────────────────────────────────────────────────────────────

def default_image(version: str) -> str:
    return IMAGE_TEMPLATE.format(owner=GITHUB_OWNER, version=version)


def gpu_env(gpu: dict, host_gpus: list) -> list:
    """The environment onboard/gpu.py::render_override gives a GPU renderer."""
    return [
        f"NVIDIA_DRIVER_CAPABILITIES={GPU_DRIVER_CAPABILITIES}",
        f"TUBEMATIC_GPU_UUID={gpu['uuid']}",
        f"TUBEMATIC_GPU_NAME={gpu['name']}",
        "TUBEMATIC_HOST_GPUS=" + json.dumps(
            [{k: g.get(k) for k in ("index", "uuid", "name", "memory_mib", "driver")}
             for g in host_gpus], separators=(",", ":")),
    ]


def run_argv(state: dict, *, with_token: bool) -> list:
    """`docker run` for the renderer container. The enrollment token is named
    with a bare `-e TUBEMATIC_ENROLL_TOKEN`, so Docker copies its value from
    this call's environment and it never appears on a command line."""
    argv = ["docker", "run", "-d", "--name", CONTAINER, "--restart", "unless-stopped",
            "--shm-size", SHM_SIZE, "-v", f"{STATE_VOLUME}:{STATE_MOUNT}",
            # The host's own name and clock: the dashboard shows the renderer's
            # host (a container ID otherwise) and its log times read in the
            # host's timezone, like main's containers (which mount the same file).
            "--hostname", socket.gethostname()]
    if os.path.exists("/etc/localtime"):
        argv += ["-v", "/etc/localtime:/etc/localtime:ro"]
    env = BASE_ENV + [
        f"TUBEMATIC_RENDERER_STATE={STATE_MOUNT}",
        f"TUBEMATIC_GATEWAY_URL={state['gateway_url']}",
        f"TUBEMATIC_RENDERER_NAME={state['name']}",
    ]
    gpu = state.get("gpu")
    if gpu:
        argv += ["--gpus", f"device={gpu['uuid']}"]
        env += gpu_env(gpu, state.get("host_gpus") or [gpu])
    for item in env:
        argv += ["-e", item]
    if with_token:
        argv += ["-e", "TUBEMATIC_ENROLL_TOKEN"]
    return argv + [state["image"]] + RENDER_COMMAND


def start_container(state: dict, token: str = None) -> None:
    extra = {"TUBEMATIC_ENROLL_TOKEN": token} if token else None
    r = run_cmd(run_argv(state, with_token=bool(token)), extra_env=extra, timeout=120)
    if r.returncode != 0:
        raise RemoteError(f"Docker could not start the renderer container: {_last_line(r)}")


def remove_container() -> None:
    run_cmd(["docker", "stop", CONTAINER], timeout=120)
    r = run_cmd(["docker", "rm", CONTAINER], timeout=60)
    if r.returncode != 0 and container_exists():
        raise RemoteError(f"Could not remove the {CONTAINER} container: {_last_line(r)}")


def container_state():
    """docker inspect's first object, or None when there is no container."""
    r = run_cmd(["docker", "container", "inspect", CONTAINER], timeout=30)
    if r.returncode != 0:
        return None
    try:
        data = json.loads(_out(r))
        return data[0] if isinstance(data, list) and data else None
    except ValueError:
        return None


def container_logs(lines: int) -> str:
    return _out(run_cmd(["docker", "logs", "--tail", str(lines), CONTAINER], timeout=30))


def wait_until_connected() -> bool:
    """Watch the new container's log for up to WAIT_SECS. True when the
    renderer reports it is connected; False when it failed or nothing showed
    in time (both are printed)."""
    deadline = time.monotonic() + WAIT_SECS
    print(f"Waiting up to {WAIT_SECS} s for the renderer to connect to main …")
    while True:
        logs = container_logs(200)
        if _FAILED.search(logs):
            print("The renderer could not connect: main refused it.\n" + _tail(logs))
            print("An enrollment token works once and for one hour: make a new one on "
                  f"{DASHBOARD_HINT}, then `remove` (deleting the state) and `install` again.")
            return False
        if _READY.search(logs):
            if _NEEDS_UPGRADE.search(logs):
                print("Connected, but main says this renderer needs an upgrade, so it takes no "
                      "work. Run `upgrade` here (without --image) once main is upgraded.")
            else:
                print(f"Connected. The renderer is listed on {DASHBOARD_HINT}.")
            return True
        st = container_state()
        if st is not None and not (st.get("State") or {}).get("Running", False):
            print("The renderer container stopped.\n" + _tail(logs))
            return False
        if time.monotonic() >= deadline:
            print(f"No sign of a connection after {WAIT_SECS} s. The container is running and "
                  "keeps retrying; check `status` in a minute.\n" + _tail(logs))
            return False
        time.sleep(POLL_SECS)


def _tail(logs: str, n: int = LOG_LINES) -> str:
    lines = logs.splitlines()[-n:]
    return "\n".join("  " + line for line in lines) if lines else "  (no log output yet)"


# ── Local state file ─────────────────────────────────────────────────────────

def state_path() -> Path:
    return Path.home() / STATE_FILE_NAME


def write_state(state: dict) -> None:
    """Atomically, mode 0600. It never holds the token or a credential."""
    path = state_path()
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)


def read_state() -> dict:
    path = state_path()
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        raise RemoteError(f"No remote renderer is installed by this user ({path} is missing). "
                          "Run `install --token …` first.") from None
    except (OSError, ValueError) as e:
        raise RemoteError(f"{path} could not be read ({e}). Run `remove`, then `install` again.") from None
    for key in ("gateway_url", "pin", "image", "name"):
        if not isinstance(state.get(key), str) or not state[key]:
            raise RemoteError(f"{path} is missing {key!r}. Run `remove`, then `install` again.")
    return state


# ── Argument checks ──────────────────────────────────────────────────────────

def check_image(image: str) -> str:
    image = (image or "").strip()
    if not image or image.startswith("-") or any(c.isspace() for c in image):
        raise RemoteError(f"--image {image!r} is not an image reference.")
    return image


def check_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > NAME_MAX or any(not c.isprintable() for c in name):
        raise RemoteError(f"--name must be 1–{NAME_MAX} printable characters.")
    return name


def default_name() -> str:
    return (socket.gethostname() or "remote renderer").strip()[:NAME_MAX] or "remote renderer"


def choose_gpu(args, info: dict):
    """The GPU to hand the container, or None for a CPU renderer."""
    if args.no_gpu:
        return None, []
    gpus = list_gpus()
    if not gpus:
        if args.gpu:
            raise RemoteError(f"--gpu {args.gpu} was given, but nvidia-smi lists no NVIDIA GPU "
                              "here (is the NVIDIA driver installed and loaded?).")
        print("No NVIDIA GPU found: this renderer renders on the CPU.")
        return None, []
    if not has_nvidia_runtime(info):
        raise RemoteError(
            "This machine has an NVIDIA GPU, but Docker has no `nvidia` runtime (the NVIDIA "
            "Container Toolkit is missing or not configured: `sudo nvidia-ctk runtime configure "
            "--runtime=docker` and restart Docker). Fix that, or pass --no-gpu to render on the CPU.")
    if args.gpu:
        for g in gpus:
            if g["uuid"] == args.gpu:
                return g, gpus
        raise RemoteError(f"No GPU with UUID {args.gpu} here. Found:\n"
                          + "\n".join("  " + gpu_label(g) for g in gpus))
    if len(gpus) == 1:
        return gpus[0], gpus
    if not interactive():
        raise RemoteError("This machine has several GPUs; name one with --gpu <UUID>:\n"
                          + "\n".join("  " + gpu_label(g) for g in gpus))
    print("Which GPU should the renderer use?")
    for n, g in enumerate(gpus, 1):
        print(f"  {n}. {gpu_label(g)}")
    while True:
        try:
            answer = input(f"Number (1–{len(gpus)}): ").strip()
        except EOFError:
            raise RemoteError("No GPU chosen.") from None
        if answer.isdigit() and 1 <= int(answer) <= len(gpus):
            return gpus[int(answer) - 1], gpus


# ── Subcommands ──────────────────────────────────────────────────────────────

def cmd_install(args) -> int:
    try:
        token = decode_token(args.token)
    except ValueError as e:
        raise RemoteError(f"The enrollment token is not valid: {e}. Copy it again from "
                          f"{DASHBOARD_HINT} (Add renderer).") from None
    name = check_name(args.name) if args.name is not None else default_name()
    image_arg = check_image(args.image) if args.image is not None else None

    info = docker_info()
    if container_exists():
        raise RemoteError(f"A {CONTAINER} container already exists on this machine. Use "
                          "`upgrade` to move it to main's version, or `remove` first to start over.")
    gpu, host_gpus = choose_gpu(args, info)

    version = gateway_version(token["url"], token["pin"])
    image = image_arg or default_image(version)

    state = {"gateway_url": token["url"].rstrip("/"), "pin": token["pin"], "image": image,
             "name": name, "gpu": ({"uuid": gpu["uuid"], "name": gpu["name"]} if gpu else None),
             "host_gpus": host_gpus if gpu else []}

    print(f"Main's render gateway: {state['gateway_url']} (Tubematic {version}, certificate verified)")
    print(f"Renderer name:        {name}")
    print(f"Image:                {image}")
    print(f"GPU:                  {gpu_label(gpu) if gpu else 'none (CPU rendering)'}")
    if volume_exists():
        print(f"Note: the {STATE_VOLUME} volume is left from an earlier install. If it holds a "
              "credential, the renderer keeps using it and this token stays unused; to start "
              "fresh, run `remove` and delete the state when asked.")
    if not args.yes and interactive() and not confirm("Install it?", True):
        print("Nothing was changed.")
        return 1

    if image_arg and image_present(image):
        print(f"Using the local image {image}.")
    else:
        pull(image)
    start_container(state, token=args.token.strip())
    write_state(state)
    print(f"Started the {CONTAINER} container (restarts with Docker).")
    return 0 if wait_until_connected() else 1


def cmd_upgrade(args) -> int:
    state = read_state()
    image_arg = check_image(args.image) if args.image is not None else None
    docker_info()
    version = gateway_version(state["gateway_url"], state["pin"])
    image = image_arg or default_image(version)
    exists = container_exists()
    print(f"Main runs Tubematic {version}. The renderer will run {image}"
          + ("" if exists else f" (no {CONTAINER} container exists; one is created)") + ".")
    if exists and not args.yes and interactive() and not confirm(
            "Recreate the renderer container? A render in progress is handed back to main "
            "and rendered again.", True):
        print("Nothing was changed.")
        return 1
    if image_arg and image_present(image):
        print(f"Using the local image {image}.")
    else:
        pull(image)
    if exists:
        remove_container()
    new_state = {**state, "image": image}
    start_container(new_state)
    write_state(new_state)
    print(f"Recreated the {CONTAINER} container on {image}.")
    return 0 if wait_until_connected() else 1


def cmd_remove(args) -> int:
    if not args.yes and not interactive():
        raise RemoteError("`remove` asks before deleting anything; pass --yes to run it "
                          "without a terminal.")
    docker_info()
    exists = container_exists()
    if exists:
        if not args.yes and not confirm(f"Stop and remove the {CONTAINER} container?", False):
            print("Nothing was changed.")
            return 1
        remove_container()
        print(f"Removed the {CONTAINER} container.")
    else:
        print(f"No {CONTAINER} container exists.")
    has_volume, path = volume_exists(), state_path()
    if has_volume or path.exists():
        if args.yes or confirm(f"Also delete the renderer's saved credential (the {STATE_VOLUME} "
                               f"volume) and {path}? Installing again then needs a new token.", False):
            if has_volume:
                r = run_cmd(["docker", "volume", "rm", STATE_VOLUME], timeout=60)
                if r.returncode != 0:
                    raise RemoteError(f"Could not delete the {STATE_VOLUME} volume: {_last_line(r)}")
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            print("Deleted the renderer's saved state.")
        else:
            print(f"Kept the {STATE_VOLUME} volume and {path}.")
    print(f"Also remove this renderer on {DASHBOARD_HINT}, or main keeps listing it as offline.")
    return 0


def cmd_status(args) -> int:
    docker_info()
    try:
        state = read_state()
    except RemoteError:
        state = None
    if state:
        gpu = state.get("gpu")
        print(f"Renderer name:  {state['name']}")
        print(f"Render gateway: {state['gateway_url']}")
        print(f"GPU:            {gpu['name'] + ' (' + gpu['uuid'] + ')' if gpu else 'none (CPU)'}")
    st = container_state()
    if st is None:
        print(f"No {CONTAINER} container exists on this machine.")
        return 1
    s = st.get("State") or {}
    print(f"Container:      {s.get('Status', 'unknown')}"
          + (f" since {s.get('StartedAt')}" if s.get("Running") else "")
          + (f", restarted {st.get('RestartCount')} time(s)" if st.get("RestartCount") else ""))
    print(f"Image:          {(st.get('Config') or {}).get('Image', '?')}")
    print(f"Last {LOG_LINES} log lines:")
    print(_tail(container_logs(LOG_LINES)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tubematic_remote_renderer.py",
        description="Run a Tubematic renderer on this machine, connected to your Tubematic main "
                    "over its render gateway. Needs Docker; an NVIDIA GPU is optional.")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    i = sub.add_parser("install", help="set up the renderer with an enrollment token",
                       description="Check Docker and the GPU, verify main's certificate against "
                                   "the token, pull main's image and start the renderer container.")
    i.add_argument("--token", required=True,
                   help="the enrollment token from main's dashboard (Settings → Rendering → Add renderer)")
    i.add_argument("--image", help="run this image instead of main's published one "
                                   "(a local image is used without pulling)")
    g = i.add_mutually_exclusive_group()
    g.add_argument("--gpu", metavar="UUID", help="the NVIDIA GPU to use (see `nvidia-smi -L`)")
    g.add_argument("--no-gpu", action="store_true", help="render on the CPU even if a GPU is present")
    i.add_argument("--name", help=f"the name main shows for it (default: this machine's host "
                                  f"name; at most {NAME_MAX} characters)")
    i.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    i.set_defaults(func=cmd_install)

    u = sub.add_parser("upgrade", help="move the renderer to main's current version",
                       description="Ask main for its version (over the pinned certificate), pull "
                                   "the matching image and recreate the container with the same "
                                   "state, name and GPU. Run it after every upgrade of main.")
    u.add_argument("--image", help="run this image instead of main's published one")
    u.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    u.set_defaults(func=cmd_upgrade)

    r = sub.add_parser("remove", help="stop and delete the renderer",
                       description="Stop and remove the container and, after asking, its saved "
                                   "credential and the local state file.")
    r.add_argument("--yes", action="store_true", help="delete everything without asking")
    r.set_defaults(func=cmd_remove)

    s = sub.add_parser("status", help="show the container and its last log lines",
                       description="Show the renderer container's state, image and its last "
                                   f"{LOG_LINES} log lines.")
    s.set_defaults(func=cmd_status)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RemoteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        sys.exit("tubematic_remote_renderer.py needs Python 3.10 or newer.")
    sys.exit(main())
