"""scripts/tubematic_remote_renderer.py -- the stdlib-only script that sets up
a renderer on another machine.

It runs with no checkout, so it cannot import tubematic_core and carries its
own copies of the token decoder, the certificate pin, the image name and the
GPU environment. Every copy is checked here against the original. The two rules
that matter most are pinned with real sockets: nothing is sent to a gateway
before its certificate matches the token's pin, and the token is never written
to disk. No test runs Docker: every docker and nvidia-smi call goes through
`run_cmd`, which the tests replace.
"""
import base64
import http.server
import json
import os
import ssl
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import tubematic_remote_renderer as trr  # noqa: E402
from onboard import gpu as onboard_gpu  # noqa: E402
from tubematic_core import renderers as core  # noqa: E402
from tubematic_core.auth import TLS_CERT_NAME, TLS_KEY_NAME, ensure_secrets  # noqa: E402
from tubematic_core.version import GITHUB_REPO  # noqa: E402

import gen_release_compose  # noqa: E402

PIN_OK = "sha256:" + "a" * 64
GPU_SMI = ("0, GPU-11111111-2222-3333-4444-555555555555, NVIDIA GeForce GTX 1650, 4096, 550.54\n")
TWO_GPUS = GPU_SMI + "1, GPU-66666666-7777-8888-9999-000000000000, NVIDIA RTX A2000, 12288, 550.54\n"


def _raw_token(payload) -> str:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return "tmr1." + base64.urlsafe_b64encode(body).decode().rstrip("=")


# ── The token and the pin agree with tubematic_core ─────────────────────────

@pytest.mark.parametrize("url,secret,pin", [
    ("https://main.example:4443", "s3cret-ABC_def", PIN_OK),
    ("https://10.0.0.5:4443", "x" * 43, "sha256:" + "0123456789abcdef" * 4),
    ("https://[fd00::1]:4443", "a", PIN_OK),
])
def test_a_token_core_encodes_decodes_identically_here(url, secret, pin):
    tok = core.encode_enrollment_token(url, secret, pin)
    assert trr.decode_token(tok) == core.decode_enrollment_token(tok) == {
        "url": url, "secret": secret, "pin": pin}
    assert trr.decode_token(f"  {tok}\n") == core.decode_enrollment_token(f"  {tok}\n")


def test_a_hand_built_token_decodes_the_same_in_both():
    """The other direction: a token neither side produced (padding kept,
    extra keys) is read the same way by both."""
    tok = "tmr1." + base64.urlsafe_b64encode(json.dumps(
        {"u": "https://h:1", "s": "z", "p": PIN_OK, "extra": 1}).encode()).decode()
    assert trr.decode_token(tok) == core.decode_enrollment_token(tok)


@pytest.mark.parametrize("tok", [
    None, 42, "", "tmr2.abc", "tmr1.", "tmr1.!!!", _raw_token(b"\xff\xfe"), _raw_token(b"not json"),
    _raw_token([1, 2]), _raw_token({"u": "https://h:1", "s": "z"}),
    _raw_token({"u": "https://h:1", "s": "", "p": PIN_OK}),
    _raw_token({"u": "http://h:1", "s": "z", "p": PIN_OK}),
    _raw_token({"u": "https://h:1", "s": "z", "p": "sha256:abc"}),
    _raw_token({"u": "https://h:1", "s": "z", "p": "sha256:" + "A" * 64}),
    _raw_token({"u": "https://h:1", "s": 5, "p": PIN_OK}),
])
def test_a_malformed_token_is_refused_by_both(tok):
    with pytest.raises(ValueError):
        core.decode_enrollment_token(tok)
    with pytest.raises(ValueError):
        trr.decode_token(tok)


def test_the_token_prefix_matches():
    assert trr.TOKEN_PREFIX == core.TOKEN_PREFIX


def test_the_pin_matches_tubematic_core_on_a_real_certificate(tmp_path):
    ensure_secrets(tmp_path)
    der = ssl.PEM_cert_to_DER_cert((tmp_path / TLS_CERT_NAME).read_text())
    assert trr.cert_pin(der) == core.cert_pin(der)


# ── A real TLS gateway ───────────────────────────────────────────────────────

class _Gateway:
    """An HTTPS server on 127.0.0.1 serving GET /v1/version with a pair from
    ensure_secrets. Records every TLS connection and every HTTP request line."""

    def __init__(self, secrets_dir: Path, version="2.1.0"):
        ensure_secrets(secrets_dir)
        self.cert_pem = (secrets_dir / TLS_CERT_NAME).read_text()
        self.pin = core.cert_pin(ssl.PEM_cert_to_DER_cert(self.cert_pem))
        self.connections, self.requests, self.finished = [], [], []
        gw = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def setup(self):
                gw.connections.append(self.client_address)
                super().setup()

            def finish(self):
                super().finish()
                gw.finished.append(self.client_address)

            def parse_request(self):
                gw.requests.append(self.raw_requestline.decode(errors="replace").strip())
                return super().parse_request()

            def do_GET(self):
                body = json.dumps({"version": version, "gateway": 1}).encode()
                code = 200 if self.path == "/v1/version" else 404
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(secrets_dir / TLS_CERT_NAME, secrets_dir / TLS_KEY_NAME)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
        self.url = f"https://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def settle(self):
        """Wait for every connection's handler to finish: the client returns
        as soon as its handshake is done, before the server thread has read
        what (if anything) followed it."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.connections and len(self.finished) == len(self.connections):
                return
            time.sleep(0.02)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def gateway(tmp_path):
    gw = _Gateway(tmp_path / "gw-secrets")
    yield gw
    gw.close()


def test_the_right_pin_reads_the_version_with_one_request(gateway):
    assert trr.gateway_version(gateway.url, gateway.pin) == "2.1.0"
    assert gateway.requests == ["GET /v1/version HTTP/1.1"]


def test_a_wrong_pin_sends_nothing(gateway):
    """The handshake reaches the server (so this is not a test of an
    unreachable address), but not one HTTP request line does."""
    with pytest.raises(trr.RemoteError, match="Nothing was sent"):
        trr.gateway_version(gateway.url, "sha256:" + "0" * 64)
    gateway.settle()
    assert gateway.connections, "the pin check never reached the server"
    assert gateway.requests == []


def test_install_with_a_wrong_pin_sends_nothing_and_starts_nothing(gateway, docker, monkeypatch):
    docker.gpus = ""
    tok = core.encode_enrollment_token(gateway.url, "one-time", "sha256:" + "0" * 64)
    assert trr.main(["install", "--token", tok, "--yes"]) == 1
    gateway.settle()
    assert gateway.connections and gateway.requests == []
    assert not docker.called("pull") and not docker.called("run")
    assert not trr.state_path().exists()


def test_the_pinned_context_refuses_any_other_certificate(gateway, tmp_path):
    other = _Gateway(tmp_path / "other-secrets")
    try:
        req = trr.urllib.request.Request(other.url + "/v1/version")
        with pytest.raises((ssl.SSLError, OSError)):
            trr.urllib.request.urlopen(req, context=trr.pinned_context(gateway.cert_pem), timeout=5)
        assert other.requests == []
    finally:
        other.close()


def test_an_unreachable_gateway_is_a_clear_error():
    with pytest.raises(trr.RemoteError, match="Could not reach the render gateway"):
        trr.gateway_version("https://127.0.0.1:1", PIN_OK)


@pytest.mark.parametrize("url", ["https://", "http://h:1", "https://h:notaport", "https://h:99999"])
def test_a_bad_gateway_address_is_refused(url):
    with pytest.raises(trr.RemoteError):
        trr.gateway_address(url)


# ── Copies of other files agree with them ────────────────────────────────────

def test_the_image_owner_is_the_repos_owner():
    assert trr.GITHUB_OWNER == GITHUB_REPO.split("/")[0]


def test_the_image_name_matches_the_release_compose():
    assert trr.default_image("2.1.0") == gen_release_compose._backend_image(
        gen_release_compose.DEFAULT_OWNER, "2.1.0")


def test_the_container_matches_the_composed_renderer():
    svc = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())["services"]["tubematic-renderer"]
    assert " ".join(trr.RENDER_COMMAND) == svc["command"]
    assert trr.SHM_SIZE + "b" == svc["shm_size"]
    for item in trr.BASE_ENV:
        assert item in svc["environment"]


def test_nvidia_smi_parsing_matches_onboarding():
    text = TWO_GPUS + "garbage\n2, not-a-uuid, X, 1, 1\n3, GPU-abc, Name, with comma, N/A, 550\n"
    ours = trr.parse_nvidia_smi(text)
    theirs = [onboard_gpu.asdict(g) for g in onboard_gpu.parse_nvidia_smi(text)]
    assert ours == theirs
    assert ["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,driver_version",
            "--format=csv,noheader,nounits"] == trr.NVIDIA_SMI_QUERY


def test_the_gpu_environment_is_what_the_compose_override_gives():
    host = onboard_gpu.parse_nvidia_smi(TWO_GPUS)
    override = json.loads(onboard_gpu.render_override(host[1], host))
    svc = override["services"][onboard_gpu.RENDERER_SERVICE]
    gpus = trr.parse_nvidia_smi(TWO_GPUS)
    assert trr.gpu_env(gpus[1], gpus) == svc["environment"]
    device = svc["deploy"]["resources"]["reservations"]["devices"][0]
    argv = trr.run_argv({"gateway_url": "https://m:4443", "name": "n", "image": "img",
                         "gpu": {"uuid": gpus[1]["uuid"], "name": gpus[1]["name"]},
                         "host_gpus": gpus}, with_token=False)
    assert device["driver"] == "nvidia" and device["capabilities"] == ["gpu"]
    assert argv[argv.index("--gpus") + 1] == f"device={device['device_ids'][0]}"


# ── A fake Docker host ───────────────────────────────────────────────────────

class _Docker:
    """Answers run_cmd like a Docker host would, recording every call."""

    def __init__(self):
        self.calls = []
        self.runtimes = {"runc": {}, "nvidia": {}}
        self.gpus = GPU_SMI
        self.container = False
        self.volume = False
        self.images = set()
        self.logs = "2026-11-08T10:00:00+0000 [renderer] enrolled as r_0123456789ab\n"
        self.fail = set()

    def called(self, verb):
        return [c for c in self.calls if c["argv"][:2] == ["docker", verb]]

    def __call__(self, argv, *, capture=True, extra_env=None, timeout=None):
        self.calls.append({"argv": list(argv), "extra_env": extra_env})
        ok = lambda out="": subprocess.CompletedProcess(argv, 0, out, "")  # noqa: E731
        bad = lambda out="no": subprocess.CompletedProcess(argv, 1, out, "")  # noqa: E731
        if argv[0] == "nvidia-smi":
            return ok(self.gpus) if self.gpus else bad()
        verb = argv[1]
        if verb in self.fail:
            return bad(f"Error response from daemon: {verb} failed")
        if verb == "info":
            return ok(json.dumps({"ServerVersion": "28.0", "Runtimes": self.runtimes}))
        if argv[1:3] == ["container", "inspect"]:
            if not self.container:
                return bad("no such container")
            return ok(json.dumps([{"State": {"Status": "running", "Running": True,
                                             "StartedAt": "2026-11-08T10:00:00Z"},
                                   "Config": {"Image": "img"}, "RestartCount": 0}]))
        if argv[1:3] == ["image", "inspect"]:
            return ok("[]") if argv[3] in self.images else bad()
        if argv[1:3] == ["volume", "inspect"]:
            return ok("[]") if self.volume else bad()
        if argv[1:3] == ["volume", "rm"]:
            self.volume = False
            return ok()
        if verb == "run":
            self.container = self.volume = True
            return ok("abc123")
        if verb == "rm":
            self.container = False
            return ok()
        if verb == "logs":
            return ok(self.logs)
        return ok()


@pytest.fixture
def docker(monkeypatch, tmp_path):
    fake = _Docker()
    monkeypatch.setattr(trr, "run_cmd", fake)
    monkeypatch.setattr(trr, "interactive", lambda: False)
    monkeypatch.setattr(trr, "POLL_SECS", 0)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    return fake


@pytest.fixture
def main_version(monkeypatch):
    seen = []

    def fake(url, pin):
        seen.append((url, pin))
        return "2.1.0"
    monkeypatch.setattr(trr, "gateway_version", fake)
    return seen


TOKEN = core.encode_enrollment_token("https://main.lan:4443", "the-one-time-secret", PIN_OK)


def _run_call(docker):
    runs = docker.called("run")
    assert len(runs) == 1
    return runs[0]


def test_a_cpu_install_runs_exactly_this_container(docker, main_version):
    docker.gpus = ""
    assert trr.main(["install", "--token", TOKEN, "--name", "garage box", "--yes"]) == 0
    call = _run_call(docker)
    assert call["argv"] == [
        "docker", "run", "-d", "--name", "tubematic-remote-renderer",
        "--restart", "unless-stopped", "--shm-size", "2g",
        "-v", "tubematic-renderer-state:/state",
        "-e", "PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium",
        "-e", "TUBEMATIC_RENDERER_STATE=/state",
        "-e", "TUBEMATIC_GATEWAY_URL=https://main.lan:4443",
        "-e", "TUBEMATIC_RENDERER_NAME=garage box",
        "-e", "TUBEMATIC_ENROLL_TOKEN",
        "ghcr.io/teja156/tubematic-backend:2.1.0", "python3", "/app/api/render_agent.py",
    ]
    assert main_version == [("https://main.lan:4443", PIN_OK)]
    assert docker.called("pull")[0]["argv"] == ["docker", "pull", "ghcr.io/teja156/tubematic-backend:2.1.0"]


def test_the_token_reaches_only_the_run_calls_environment(docker, main_version):
    docker.gpus = ""
    trr.main(["install", "--token", TOKEN, "--yes"])
    for call in docker.calls:
        assert not any(TOKEN in a or "the-one-time-secret" in a for a in call["argv"])
        if call["argv"][:2] != ["docker", "run"]:
            assert not call["extra_env"]
    assert _run_call(docker)["extra_env"] == {"TUBEMATIC_ENROLL_TOKEN": TOKEN}


def test_a_gpu_install_hands_over_the_one_gpu(docker, main_version):
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 0
    argv = _run_call(docker)["argv"]
    uuid = "GPU-11111111-2222-3333-4444-555555555555"
    assert argv[argv.index("--gpus") + 1] == f"device={uuid}"
    envs = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    gpus = trr.parse_nvidia_smi(GPU_SMI)
    for item in trr.gpu_env(gpus[0], gpus):
        assert item in envs
    assert argv.index("--gpus") < argv.index("ghcr.io/teja156/tubematic-backend:2.1.0")


def test_a_named_gpu_is_chosen_among_several(docker, main_version):
    docker.gpus = TWO_GPUS
    uuid = "GPU-66666666-7777-8888-9999-000000000000"
    assert trr.main(["install", "--token", TOKEN, "--gpu", uuid, "--yes"]) == 0
    argv = _run_call(docker)["argv"]
    assert argv[argv.index("--gpus") + 1] == f"device={uuid}"
    assert f"TUBEMATIC_GPU_UUID={uuid}" in argv


def test_several_gpus_without_a_terminal_are_refused_naming_gpu(docker, main_version, capsys):
    docker.gpus = TWO_GPUS
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    err = capsys.readouterr().err
    assert "--gpu" in err and "GPU-66666666" in err and "GPU-11111111" in err
    assert not docker.called("run") and not docker.called("pull") and main_version == []


def test_several_gpus_with_a_terminal_ask(docker, main_version, monkeypatch):
    docker.gpus = TWO_GPUS
    monkeypatch.setattr(trr, "interactive", lambda: True)
    answers = iter(["9", "2", "y"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert trr.main(["install", "--token", TOKEN]) == 0
    assert "TUBEMATIC_GPU_UUID=GPU-66666666-7777-8888-9999-000000000000" in _run_call(docker)["argv"]


def test_an_unknown_gpu_is_refused(docker, main_version, capsys):
    assert trr.main(["install", "--token", TOKEN, "--gpu", "GPU-nope", "--yes"]) == 1
    assert "No GPU with UUID GPU-nope" in capsys.readouterr().err
    assert not docker.called("run")


def test_a_gpu_without_the_nvidia_runtime_is_refused_not_silently_dropped(docker, main_version, capsys):
    docker.runtimes = {"runc": {}}
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    err = capsys.readouterr().err
    assert "nvidia" in err and "--no-gpu" in err
    assert not docker.called("run")


def test_no_gpu_renders_on_the_cpu_without_asking_nvidia_smi(docker, main_version):
    assert trr.main(["install", "--token", TOKEN, "--no-gpu", "--yes"]) == 0
    assert "--gpus" not in _run_call(docker)["argv"]
    assert not [c for c in docker.calls if c["argv"][0] == "nvidia-smi"]


def test_an_existing_container_is_refused_before_anything_else(docker, main_version, capsys):
    docker.container = True
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    err = capsys.readouterr().err
    assert "already exists" in err and "upgrade" in err and "remove" in err
    assert main_version == [] and not docker.called("pull") and not docker.called("run")


def test_docker_not_installed_is_a_clear_error(docker, main_version, capsys, monkeypatch):
    monkeypatch.setattr(trr, "run_cmd", lambda argv, **k: subprocess.CompletedProcess(argv, 127, "", ""))
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    assert "Docker is not installed" in capsys.readouterr().err


def test_docker_without_a_daemon_is_a_clear_error(docker, main_version, capsys, monkeypatch):
    def run(argv, **k):
        return subprocess.CompletedProcess(argv, 1, json.dumps(
            {"ServerErrors": ["Cannot connect to the Docker daemon"]}), "")
    monkeypatch.setattr(trr, "run_cmd", run)
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    assert "Cannot connect to the Docker daemon" in capsys.readouterr().err


def test_a_local_image_is_used_without_pulling(docker, main_version):
    docker.gpus = ""
    docker.images = {"tubematic-backend:mine"}
    assert trr.main(["install", "--token", TOKEN, "--image", "tubematic-backend:mine", "--yes"]) == 0
    assert not docker.called("pull")
    assert "tubematic-backend:mine" in _run_call(docker)["argv"]


@pytest.mark.parametrize("image", ["--privileged", "a b", " "])
def test_an_image_that_could_be_read_as_a_flag_is_refused(docker, main_version, image):
    assert trr.main(["install", "--token", TOKEN, f"--image={image}", "--yes"]) == 1
    assert not docker.called("run")


def test_a_bad_token_is_refused_without_echoing_it(docker, main_version, capsys):
    bad = "tmr1.c2VjcmV0LXZhbHVl"
    assert trr.main(["install", "--token", bad, "--yes"]) == 1
    out = capsys.readouterr()
    assert "not valid" in out.err and bad not in out.err + out.out
    assert "Traceback" not in out.err
    assert docker.calls == []


def test_the_state_file_is_0600_and_never_holds_the_token(docker, main_version, capsys):
    trr.main(["install", "--token", TOKEN, "--yes"])
    path = trr.state_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text()
    assert TOKEN not in text and "the-one-time-secret" not in text
    state = json.loads(text)
    assert state["gateway_url"] == "https://main.lan:4443" and state["pin"] == PIN_OK
    assert state["image"] == "ghcr.io/teja156/tubematic-backend:2.1.0"
    assert state["gpu"]["uuid"] == "GPU-11111111-2222-3333-4444-555555555555"
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err and "the-one-time-secret" not in out.out + out.err


def test_a_refused_enrollment_is_reported(docker, main_version, capsys):
    docker.logs = "[renderer] enrollment refused by the gateway: enrollment_invalid\n"
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    assert "main refused it" in capsys.readouterr().out


def test_no_connection_within_the_wait_is_reported(docker, main_version, capsys, monkeypatch):
    docker.logs = "[renderer] render agent starting\n"
    monkeypatch.setattr(trr, "WAIT_SECS", 0)
    assert trr.main(["install", "--token", TOKEN, "--yes"]) == 1
    assert "No sign of a connection" in capsys.readouterr().out


# ── upgrade, remove, status ──────────────────────────────────────────────────

def _installed(docker, main_version, *extra):
    assert trr.main(["install", "--token", TOKEN, "--name", "box", "--yes", *extra]) == 0
    docker.calls.clear()
    main_version.clear()


def test_upgrade_recreates_the_same_container_without_the_token(docker, main_version, monkeypatch):
    _installed(docker, main_version)
    first = trr.run_argv(json.loads(trr.state_path().read_text()), with_token=False)
    monkeypatch.setattr(trr, "gateway_version", lambda url, pin: main_version.append((url, pin)) or "2.2.0")
    assert trr.main(["upgrade", "--yes"]) == 0
    assert main_version == [("https://main.lan:4443", PIN_OK)]
    verbs = [c["argv"][1] for c in docker.calls if c["argv"][0] == "docker"]
    assert verbs.index("pull") < verbs.index("stop") < verbs.index("rm") < verbs.index("run")
    call = _run_call(docker)
    assert call["extra_env"] is None
    assert not any("ENROLL_TOKEN" in a for a in call["argv"])
    expected = [a if a != "ghcr.io/teja156/tubematic-backend:2.1.0"
                else "ghcr.io/teja156/tubematic-backend:2.2.0" for a in first]
    assert call["argv"] == expected
    assert json.loads(trr.state_path().read_text())["image"] == "ghcr.io/teja156/tubematic-backend:2.2.0"


def test_a_failed_pull_leaves_the_old_container_running(docker, main_version, capsys):
    _installed(docker, main_version)
    docker.fail = {"pull"}
    assert trr.main(["upgrade", "--yes"]) == 1
    assert not docker.called("stop") and not docker.called("rm") and not docker.called("run")


def test_upgrade_without_an_install_says_so(docker, main_version, capsys):
    assert trr.main(["upgrade", "--yes"]) == 1
    assert "install" in capsys.readouterr().err


def test_remove_without_a_terminal_needs_yes(docker, capsys):
    assert trr.main(["remove"]) == 1
    assert "--yes" in capsys.readouterr().err
    assert docker.calls == []


def test_remove_asks_before_deleting_the_state(docker, main_version, monkeypatch, capsys):
    _installed(docker, main_version)
    monkeypatch.setattr(trr, "interactive", lambda: True)
    answers = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert trr.main(["remove"]) == 0
    assert docker.called("stop") and docker.called("rm")
    assert not [c for c in docker.calls if c["argv"][1:3] == ["volume", "rm"]]
    assert trr.state_path().exists()
    assert "dashboard" in capsys.readouterr().out


def test_remove_declined_changes_nothing(docker, main_version, monkeypatch):
    _installed(docker, main_version)
    monkeypatch.setattr(trr, "interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    assert trr.main(["remove"]) == 1
    assert not docker.called("stop") and not docker.called("rm")


def test_remove_yes_deletes_the_container_the_volume_and_the_state_file(docker, main_version):
    _installed(docker, main_version)
    assert trr.main(["remove", "--yes"]) == 0
    assert [c["argv"] for c in docker.calls if c["argv"][1:3] == ["volume", "rm"]] == [
        ["docker", "volume", "rm", "tubematic-renderer-state"]]
    assert not trr.state_path().exists()


def test_status_shows_the_container_and_its_log(docker, main_version, capsys):
    _installed(docker, main_version)
    capsys.readouterr()
    assert trr.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "running" in out and "enrolled as r_0123456789ab" in out and "box" in out
    assert ["docker", "logs", "--tail", "20", "tubematic-remote-renderer"] in [c["argv"] for c in docker.calls]


def test_status_without_a_container(docker, capsys):
    assert trr.main(["status"]) == 1
    assert "No tubematic-remote-renderer container" in capsys.readouterr().out


@pytest.mark.parametrize("cmd", ["install", "upgrade", "remove", "status"])
def test_every_subcommand_has_help(cmd, capsys):
    with pytest.raises(SystemExit) as e:
        trr.main([cmd, "--help"])
    assert e.value.code == 0
    assert cmd in capsys.readouterr().out


def test_the_script_imports_nothing_outside_the_standard_library():
    """It runs with no checkout: an import of tubematic_core (or a PyPI
    package) would fail on the machine it is meant for."""
    import ast
    tree = ast.parse((REPO_ROOT / "scripts" / "tubematic_remote_renderer.py").read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    assert modules and modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)
