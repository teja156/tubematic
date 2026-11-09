"""The opt-in `renderers` onboarding step and the Compose override it writes (TMDEV-190).

The step is the only way the render gateway's port reaches other machines: it
publishes the port on tubematic-api, stores the address remote renderers dial
(enrollment tokens carry it), recreates the API and checks that what answers
on the port is the gateway itself. A full install never runs it.
"""
import json
import socket
import sqlite3
import ssl
import subprocess
import threading

import pytest

from onboard import actions, checks, remote_renderers as rr
from onboard.executor import Executor, NullReporter
from onboard.steps import DEFAULT_STEPS, STEP_BY_KEY
from tubematic_core import auth
from tubematic_core import db as tdb
from tubematic_core import renderers as trenderers


class _Rep(NullReporter):
    def __init__(self):
        self.lines = []
    def ok(self, msg, *a, **k): self.lines.append(("ok", msg))
    def info(self, msg, *a, **k): self.lines.append(("info", msg))
    def warn(self, msg, *a, **k): self.lines.append(("warn", msg))
    def fail(self, msg, *a, **k):
        self.lines.append(("fail", msg))
        raise RuntimeError(msg)
    def text(self):
        return "\n".join(m for _, m in self.lines)


def _cp(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class _RecordingEx(Executor):
    """A live executor (files and rows really written) whose commands are
    recorded and never run, so no test can reach a real `docker compose`."""
    def __init__(self, dry_run=False):
        super().__init__(dry_run=dry_run)
        self.calls = []

    def run(self, cmd, cwd=None, **kw):
        if self.dry_run:
            return super().run(cmd, cwd=cwd, **kw)
        self.calls.append(list(cmd))
        return _cp()


# ── The address ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,stored", [
    ("render.example.com", "render.example.com:4443"),
    ("render.example.com:8443", "render.example.com:8443"),
    ("  192.168.1.20  ", "192.168.1.20:4443"),
    ("192.168.1.20:1", "192.168.1.20:1"),
    ("10.0.0.5:65535", "10.0.0.5:65535"),
    ("studio-pc", "studio-pc:4443"),
    ("[2001:db8::1]", "[2001:db8::1]:4443"),
    ("[2001:db8::1]:9443", "[2001:db8::1]:9443"),
])
def test_a_usable_address_is_stored_with_its_port(text, stored):
    assert rr.normalize_address(text) == stored


@pytest.mark.parametrize("text,needle", [
    ("", "required"),
    ("https://render.example.com", "without http"),
    ("http://render.example.com:4443", "without http"),
    ("render.example.com/gateway", "optionally with :port"),
    ("render example.com", "optionally with :port"),
    ("render.example.com:0", "between 1 and 65535"),
    ("render.example.com:65536", "between 1 and 65535"),
    ("render.example.com:", "must be a number"),
    ("render.example.com:44x3", "must be a number"),
    ("2001:db8::1", "in brackets"),
    ("[2001:db8::1", "closing ]"),
    ("[render.example.com]", "not an IPv6 address"),
    ("[2001:db8::1]4443", "only :port"),
    ("-bad-.example.com", "not an IP address or a DNS name"),
    ("under_score.example.com", "not an IP address or a DNS name"),
    ("999.1.1.1", "not a valid IPv4"),
    ("10.0.0", "not a valid IPv4"),
    ("0.0.0.0", "every address"),
    ("[::]", "every address"),
    ("127.0.0.1", "loopback"),
    ("[::1]:4443", "loopback"),
    ("localhost", "localhost"),
])
def test_an_unusable_address_is_refused_with_a_reason(text, needle):
    with pytest.raises(ValueError, match=needle):
        rr.parse_address(text)
    assert needle in rr.address_error(text)


def test_the_gateway_url_carries_the_port():
    assert rr.gateway_url("render.example.com") == "https://render.example.com:4443"
    assert rr.gateway_url("[2001:db8::1]:9443") == "https://[2001:db8::1]:9443"


# ── The override file ────────────────────────────────────────────────────────

def test_the_override_publishes_the_gateway_on_the_api_only():
    doc = json.loads(rr.render_override(8443))
    assert doc["services"] == {"tubematic-api": {"ports": ["0.0.0.0:8443:4443"]}}


def test_an_ipv6_address_also_publishes_on_ipv6():
    """Only then: a host with IPv6 disabled refuses a [::] bind, and `up` would fail."""
    doc = json.loads(rr.render_override(4443, ipv6=True))
    assert doc["services"]["tubematic-api"]["ports"] == ["0.0.0.0:4443:4443", "[::]:4443:4443"]


def test_the_override_reads_back(tmp_path):
    path = tmp_path / "o.json"
    path.write_text(rr.render_override(9443, ipv6=True))
    assert rr.read_override(path) == {"port": 9443}


def test_no_override_reads_as_none_and_has_no_problems(tmp_path):
    assert rr.read_override(tmp_path / "missing.json") is None
    assert rr.override_problems(tmp_path / "missing.json") == []


@pytest.mark.parametrize("text", [
    "not json {",
    "services: {}\n",
    json.dumps({"services": {"tubematic-api": {"ports": ["127.0.0.1:4000:4000"]}}}),
    json.dumps({"services": {"tubematic-api": {"ports": []}}}),
])
def test_a_foreign_or_broken_file_is_a_problem_naming_the_step(tmp_path, text):
    path = tmp_path / "o.json"
    path.write_text(text)
    with pytest.raises(ValueError, match="not a remote-renderers override"):
        rr.read_override(path)
    [problem] = rr.override_problems(path)
    assert rr.STEP_HINT in problem


# ── _compose() ───────────────────────────────────────────────────────────────

def test_compose_names_every_existing_override_gpu_first():
    """A fixed order, so the argv is the same whichever was written last."""
    from onboard import gpu
    rr.override_path().write_text(rr.render_override(4443))
    gpu.override_path().write_text("{}")
    assert actions._compose() == [
        "docker", "compose", "-f", str(actions.REPO_ROOT / "docker-compose.yml"),
        "-f", str(gpu.override_path()), "-f", str(rr.override_path())]


def test_compose_names_the_renderers_override_alone():
    rr.override_path().write_text(rr.render_override(4443))
    assert actions._compose() == [
        "docker", "compose", "-f", str(actions.REPO_ROOT / "docker-compose.yml"),
        "-f", str(rr.override_path())]


def test_compose_is_bare_with_no_override():
    assert actions._compose() == ["docker", "compose"]


# ── The local TLS check, against a real TLS server ───────────────────────────

@pytest.fixture
def secrets(tmp_path):
    d = tmp_path / "secrets"
    auth.ensure_secrets(d)
    return d


class _Server:
    """A listener on 127.0.0.1:0 that, with `tls`, completes a TLS handshake
    with the given key pair; without, answers plain text and hangs up."""
    def __init__(self, secrets=None):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.ctx = None
        if secrets is not None:
            self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ctx.load_cert_chain(secrets / auth.TLS_CERT_NAME, secrets / auth.TLS_KEY_NAME)
        self.stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        self.sock.settimeout(0.2)
        while not self.stop:
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            try:
                if self.ctx is not None:
                    with self.ctx.wrap_socket(conn, server_side=True) as tls:
                        tls.recv(1)
                else:
                    conn.sendall(b"HTTP/1.0 200 OK\r\n\r\nhello")
                    conn.close()
            except (ssl.SSLError, OSError):
                conn.close()

    def close(self):
        self.stop = True
        self.thread.join(2)
        self.sock.close()


@pytest.fixture
def server():
    made = []

    def start(secrets=None):
        s = _Server(secrets)
        made.append(s)
        return s
    yield start
    for s in made:
        s.close()


def test_the_check_passes_when_the_gateway_certificate_answers(secrets, server):
    s = server(secrets)
    result, detail = rr.check_gateway(s.port, auth.gateway_pin(secrets))
    assert result == "ok", detail


def test_the_check_fails_on_a_different_certificate(secrets, server, tmp_path):
    """Another program, or a TLS-terminating proxy, on the port."""
    other = tmp_path / "other"
    auth.ensure_secrets(other)
    s = server(other)
    result, detail = rr.check_gateway(s.port, auth.gateway_pin(secrets))
    assert result == "wrong_cert"
    assert auth.gateway_pin(secrets) in detail


def test_the_check_fails_when_nothing_answers():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    result, _ = rr.check_gateway(port, "sha256:" + "0" * 64, timeout=1)
    assert result == "closed"


def test_the_check_fails_when_the_port_is_not_tls(server):
    s = server(None)
    result, _ = rr.check_gateway(s.port, "sha256:" + "0" * 64, timeout=2)
    assert result == "not_tls"


def test_waiting_retries_until_the_api_answers():
    answers = iter([("closed", "a"), ("not_tls", "b"), ("ok", "c")])
    slept = []
    assert rr.wait_for_gateway(4443, "pin", check=lambda p, pin: next(answers),
                               sleep=slept.append, delay=1) == ("ok", "c")
    assert slept == [1, 1]


def test_waiting_stops_at_a_wrong_certificate():
    calls = []

    def check(p, pin):
        calls.append(p)
        return ("wrong_cert", "x")
    assert rr.wait_for_gateway(4443, "pin", check=check, sleep=lambda s: None)[0] == "wrong_cert"
    assert len(calls) == 1


def test_waiting_gives_up_after_its_attempts():
    calls = []

    def check(p, pin):
        calls.append(p)
        return ("closed", "x")
    assert rr.wait_for_gateway(4443, "pin", check=check, attempts=3,
                               sleep=lambda s: None)[0] == "closed"
    assert len(calls) == 3


# ── apply_renderers ──────────────────────────────────────────────────────────

def _row(db_path, key=rr.SETTING_KEY):
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


@pytest.fixture
def step(tmp_path, monkeypatch):
    """apply_renderers with the questions, the TLS check and `docker inspect`
    faked; the gateway key pair really exists (TUBEMATIC_SECRETS_DIR is a
    temp dir, see conftest)."""
    db_path = tmp_path / "tubematic.db"
    tdb.migrate(db_path, backup=False)
    monkeypatch.setattr(actions, "DB_PATH", db_path)
    auth.ensure_secrets()
    api = {"exists": True}

    def inspect(argv, **kw):
        assert argv[:2] == ["docker", "inspect"]
        return _cp("running", 0) if api["exists"] else _cp("", 1)
    monkeypatch.setattr(actions.subprocess, "run", inspect)

    def run(*, on=True, address="render.example.com", token=False, check=("ok", "fine"),
            dry_run=False):
        rep, ex = _Rep(), _RecordingEx(dry_run=dry_run)
        asked = {"on": [], "address": [], "token": 0, "check": []}

        def ask_on(current):
            asked["on"].append(current)
            return on

        def ask_address(current):
            asked["address"].append(current)
            return address

        def confirm():
            asked["token"] += 1
            return token

        def fake_check(port, pin):
            asked["check"].append((port, pin))
            return check
        actions.apply_renderers(None, ex, rep, ask_on=ask_on, ask_address=ask_address,
                                confirm=confirm, check=fake_check)
        return rep, ex, asked
    run.api = api
    run.db_path = db_path
    return run


def test_turning_remote_renderers_on(step):
    rep, ex, asked = step(address="render.example.com:8443")
    assert rr.read_override() == {"port": 8443}
    assert _row(step.db_path) == "render.example.com:8443"
    # Only tubematic-api is recreated, with the new override named.
    [up] = ex.calls
    assert up[-3:] == ["up", "-d", "tubematic-api"]
    assert up[up.index(str(rr.override_path())) - 1] == "-f"
    # The port is checked locally against the gateway's own pin.
    assert asked["check"] == [(8443, auth.gateway_pin())]
    assert "TCP port 8443" in rep.text() and "DOCKER-USER" in rep.text()
    assert "answers on port 8443" in rep.text()


def test_the_current_address_is_offered_as_the_default(step):
    step(address="render.example.com")
    _, _, asked = step(address="render.example.com")
    assert asked["on"] == [True]
    assert asked["address"] == ["render.example.com:4443"]


def test_a_fresh_install_defaults_to_off(step):
    _, _, asked = step(on=False)
    assert asked["on"] == [False]


def test_an_unchanged_rerun_recreates_nothing_but_checks_again(step):
    step(address="render.example.com")
    rep, ex, asked = step(address="render.example.com:4443")
    assert ex.calls == []
    assert "unchanged" in rep.text()
    assert asked["check"] == [(4443, auth.gateway_pin())]


def test_changing_the_port_rewrites_and_recreates(step):
    step(address="render.example.com")
    rep, ex, _ = step(address="render.example.com:9443")
    assert rr.read_override() == {"port": 9443}
    assert _row(step.db_path) == "render.example.com:9443"
    assert len(ex.calls) == 1


def test_turning_remote_renderers_off(step):
    step(address="render.example.com")
    rep, ex, asked = step(on=False)
    assert not rr.override_path().exists()
    assert _row(step.db_path) == ""
    [up] = ex.calls
    assert up == ["docker", "compose", "up", "-d", "tubematic-api"]
    assert asked["address"] == [] and asked["check"] == []


def test_off_when_already_off_changes_nothing(step):
    rep, ex, _ = step(on=False)
    assert ex.calls == [] and not rr.override_path().exists()
    assert _row(step.db_path) is None
    assert "stay off" in rep.text()


def test_dry_run_writes_nothing(step):
    rep, ex, asked = step(dry_run=True, token=True)
    assert not rr.override_path().exists()
    assert _row(step.db_path) is None
    assert ex.calls == []
    assert asked["check"] == [] and asked["token"] == 0
    kinds = {i.kind for i in ex.intents}
    assert {"write_file", "sqlite_write", "run"} <= kinds
    con = sqlite3.connect(step.db_path)
    assert con.execute("SELECT COUNT(*) FROM renderer_enrollments").fetchone()[0] == 0
    con.close()


def test_a_stopped_api_is_not_started_or_checked(step):
    """`up -d tubematic-api` on a stopped install would start half a stack."""
    step.api["exists"] = False
    rep, ex, asked = step(token=True)
    assert ex.calls == [] and asked["check"] == [] and asked["token"] == 0
    assert rr.read_override() == {"port": 4443}
    assert "not running" in rep.text()


def test_a_publish_upload_in_flight_defers_the_recreate(step, monkeypatch):
    """The upload runs inside an API request, which a recreate would kill."""
    from onboard import stack
    monkeypatch.setattr(stack, "in_flight", lambda db: [
        "vid_x is PUBLISHING (A video): its upload has not finished"])
    rep, ex, asked = step()
    assert ex.calls == [] and asked["check"] == []
    assert "service.py start tubematic-api" in rep.text()


def test_a_render_in_flight_does_not_hold_the_recreate(step, monkeypatch):
    """Renderers reach the API only through the gateway and retry; a few
    seconds offline is well inside a render lease."""
    from onboard import stack
    monkeypatch.setattr(stack, "in_flight", lambda db: [
        "vid_x is RENDERING (A video): a render in progress — stopping it counts as a "
        "render failure"])
    _, ex, _ = step()
    assert len(ex.calls) == 1


def test_a_failed_check_warns_with_a_hint_and_offers_no_token(step):
    rep, ex, asked = step(check=("wrong_cert", "a different certificate"), token=True)
    assert ("warn", "The render gateway does not answer properly: a different certificate") \
        in rep.lines
    assert "TLS-terminating proxy" in rep.text()
    assert asked["token"] == 0


def test_no_token_unless_asked_for(step):
    rep, ex, asked = step(token=False)
    assert asked["token"] == 1
    assert trenderers.TOKEN_PREFIX not in rep.text()
    con = sqlite3.connect(step.db_path)
    assert con.execute("SELECT COUNT(*) FROM renderer_enrollments").fetchone()[0] == 0
    con.close()


def test_a_confirmed_first_token_names_this_gateway_and_its_pin(step):
    rep, ex, _ = step(address="render.example.com:8443", token=True)
    [token] = [m for _, m in rep.lines if m.startswith(trenderers.TOKEN_PREFIX)]
    decoded = trenderers.decode_enrollment_token(token)
    assert decoded["url"] == "https://render.example.com:8443"
    assert decoded["pin"] == auth.gateway_pin()
    # One-time and stored hashed: the secret itself is never in the database.
    con = sqlite3.connect(step.db_path)
    [(stored,)] = con.execute("SELECT secret_hash FROM renderer_enrollments").fetchall()
    con.close()
    assert stored == trenderers.hash_secret(decoded["secret"])
    assert f"python3 tubematic_remote_renderer.py install --token '{token}'" in rep.text()


def test_turning_on_without_the_gateway_certificate_fails(step, tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "empty"))
    with pytest.raises(RuntimeError, match="certificate is missing"):
        step()
    assert not rr.override_path().exists()


def test_no_database_means_install_first(step, tmp_path, monkeypatch):
    monkeypatch.setattr(actions, "DB_PATH", tmp_path / "missing.db")
    with pytest.raises(RuntimeError, match="no database"):
        step()


# ── The step itself: opt-in ──────────────────────────────────────────────────

def test_the_step_is_dispatched():
    assert actions.ACTIONS["renderers"] is actions.apply_renderers
    assert STEP_BY_KEY["renderers"].opt_in


@pytest.fixture
def wizard(monkeypatch, tmp_path):
    """run_wizard with every action, question and machine probe replaced, so
    the only thing observed is which steps it runs."""
    from onboard import config, plain, prompt
    ran = []
    monkeypatch.setattr(plain, "ACTIONS", {k: (lambda key: lambda cfg, ex, rep: ran.append(key))(k)
                                           for k in actions.ACTIONS})
    monkeypatch.setattr(prompt, "prompt_step", lambda *a, **k: None)
    monkeypatch.setattr(plain, "check_prerequisites", lambda mode="dev": [])
    monkeypatch.setattr(plain, "check_installation", lambda: {})
    monkeypatch.setattr(plain, "load_state", lambda: {})
    monkeypatch.setattr(plain, "read_agents", lambda: [{"archived_at": None}])
    monkeypatch.setattr(config.OnboardConfig, "load",
                        classmethod(lambda cls, *a, **k: cls(values={})))
    return ran


def test_a_full_install_skips_the_opt_in_step(wizard):
    from onboard import plain
    plain.run_wizard(dry_run=True)
    assert "renderers" not in wizard
    assert wizard == [s.key for s in DEFAULT_STEPS if s.key != "prerequisites"]


def test_force_still_skips_the_opt_in_step(wizard):
    from onboard import plain
    plain.run_wizard(dry_run=True, force_all=True)
    assert "renderers" not in wizard


def test_naming_the_step_runs_it(wizard):
    from onboard import plain
    plain.run_wizard(dry_run=True, step_key="renderers")
    assert wizard == ["renderers"]


def test_status_lists_the_opt_in_step_without_counting_it(monkeypatch):
    import io
    from rich.console import Console
    from onboard import plain
    buf = io.StringIO()
    monkeypatch.setattr(plain, "console", Console(file=buf, width=200))
    monkeypatch.setattr(plain, "load_state", lambda: {})
    plain.print_status()
    out = buf.getvalue()
    assert f"1/{len(DEFAULT_STEPS)}" in out
    assert "not used — run with --step renderers" in out


# ── Pre-flight and readout ───────────────────────────────────────────────────

def test_a_broken_override_is_a_prerequisite_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(checks, "DB_PATH", tmp_path / "data" / "tubematic.db")
    monkeypatch.setattr(checks, "_run", lambda cmd: _cp("v22.0.0"))
    rr.override_path().write_text("not json")
    [item] = [i for i in checks.check_prerequisites() if i.label.startswith("Remote-renderers")]
    assert not item.ok and item.severity == "warning"
    assert rr.STEP_HINT in item.hint


def test_a_usable_override_is_no_prerequisite_item(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(checks, "DB_PATH", tmp_path / "data" / "tubematic.db")
    monkeypatch.setattr(checks, "_run", lambda cmd: _cp("v22.0.0"))
    rr.override_path().write_text(rr.render_override(4443))
    assert not [i for i in checks.check_prerequisites() if i.label.startswith("Remote-renderers")]


@pytest.fixture
def readout(tmp_path):
    db_path = tmp_path / "r.db"
    tdb.migrate(db_path, backup=False)

    def store(address):
        con = sqlite3.connect(db_path)
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (rr.SETTING_KEY, address))
        con.commit()
        con.close()
    store.db_path = db_path
    return store


def test_the_readout_says_off(readout):
    [(level, text)] = rr.report_lines(readout.db_path)
    assert level == "info" and "off" in text and rr.STEP_HINT in text


def test_the_readout_names_the_address_when_on(readout):
    readout("render.example.com:4443")
    rr.override_path().write_text(rr.render_override(4443))
    [(level, text)] = rr.report_lines(readout.db_path)
    assert level == "info" and "render.example.com:4443" in text


@pytest.mark.parametrize("address,override,needle", [
    ("render.example.com:4443", None, "no port is published"),
    ("", 4443, "no address is stored"),
    ("render.example.com:9443", 4443, "port 4443 is the one published"),
])
def test_a_half_set_up_readout_is_a_warning(readout, address, override, needle):
    readout(address)
    if override:
        rr.override_path().write_text(rr.render_override(override))
    [(level, text)] = rr.report_lines(readout.db_path)
    assert level == "warn" and needle in text


def test_the_readout_reports_a_broken_override(readout):
    rr.override_path().write_text("nope")
    [(level, text)] = rr.report_lines(readout.db_path)
    assert level == "warn" and rr.STEP_HINT in text


def test_a_database_from_before_the_row_reads_as_off(tmp_path):
    assert rr.stored_address(tmp_path / "missing.db") == ""
