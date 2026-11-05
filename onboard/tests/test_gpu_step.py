"""The `gpu` onboarding step and the Compose override it writes (TMDEV-178).

The override is the only way a GPU reaches the renderer, and Docker refuses to
create a container whose GPU it cannot hand over — so a wrong override is a
stack that will not start, and a missing one is a GPU nobody uses.
"""
import json
import sqlite3
import subprocess

import pytest

from onboard import actions, gpu
from onboard.executor import Executor, NullReporter
from tubematic_core import db as tdb

GTX = gpu.Gpu(0, "GPU-aaaa", "NVIDIA GeForce GTX 1650", 4096, "595.91.07")
RTX = gpu.Gpu(1, "GPU-bbbb", "NVIDIA GeForce RTX 4090", 24564, "595.91.07")


class _Rep(NullReporter):
    def __init__(self):
        self.lines = []
    def ok(self, msg, *a, **k): self.lines.append(("ok", msg))
    def info(self, msg, *a, **k): self.lines.append(("info", msg))
    def warn(self, msg, *a, **k): self.lines.append(("warn", msg))
    def fail(self, msg, *a, **k): self.lines.append(("fail", msg))
    def text(self):
        return "\n".join(m for _, m in self.lines)


def _cp(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class _RecordingEx(Executor):
    """A live executor (files really written) whose commands are recorded and
    never run, so no test can reach a real `docker compose`."""
    def __init__(self, dry_run=False):
        super().__init__(dry_run=dry_run)
        self.calls = []

    def run(self, cmd, cwd=None, **kw):
        if self.dry_run:
            return super().run(cmd, cwd=cwd, **kw)
        self.calls.append(list(cmd))
        return _cp()


# ── nvidia-smi and docker info ───────────────────────────────────────────────

def test_parse_nvidia_smi_reads_every_gpu():
    text = ("0, GPU-aaaa, NVIDIA GeForce GTX 1650, 4096, 595.91.07\n"
            "1, GPU-bbbb, NVIDIA GeForce RTX 4090, 24564, 595.91.07\n")
    assert gpu.parse_nvidia_smi(text) == [GTX, RTX]


def test_a_name_with_a_comma_stays_whole():
    [g] = gpu.parse_nvidia_smi("0, GPU-cccc, NVIDIA A100, PCIe, 40960, 550.1\n")
    assert g.name == "NVIDIA A100, PCIe" and g.memory_mib == 40960


@pytest.mark.parametrize("line", [
    "No devices were found",
    "x, GPU-aaaa, NVIDIA, 4096, 1",          # index not a number
    "0, aaaa, NVIDIA GeForce, 4096, 1",      # not a GPU UUID
    "0, GPU-aaaa, 4096, 1",                  # too few fields
])
def test_a_row_that_does_not_parse_is_skipped_not_guessed(line):
    """A mangled UUID offered as a choice would write an override that fails
    at `up`."""
    assert gpu.parse_nvidia_smi(line) == []


def test_memory_that_is_not_a_number_is_unknown():
    [g] = gpu.parse_nvidia_smi("0, GPU-aaaa, NVIDIA T4, [N/A], 550.1")
    assert g.memory_mib is None


def test_no_nvidia_smi_means_no_gpus():
    def missing(*a, **k):
        raise FileNotFoundError("nvidia-smi")
    assert gpu.list_gpus(run=missing) is None


def test_a_failing_nvidia_smi_means_no_gpus():
    """How a driver that is installed but not loaded presents — including a
    kernel module Secure Boot refused."""
    assert gpu.list_gpus(run=lambda *a, **k: _cp("NVIDIA-SMI has failed", 9)) is None


@pytest.mark.parametrize("stdout,expected", [
    ('{"nvidia":{"path":"nvidia-container-runtime"},"runc":{"path":"runc"}}', True),
    ('{"runc":{"path":"runc"}}', False),
    ("not json", None),
])
def test_the_nvidia_runtime_is_read_from_docker_info(stdout, expected):
    assert gpu.docker_has_nvidia_runtime(run=lambda *a, **k: _cp(stdout)) is expected


# ── The override file ────────────────────────────────────────────────────────

def test_the_override_hands_exactly_one_gpu_to_the_renderer_only():
    doc = json.loads(gpu.render_override(RTX, [GTX, RTX]))
    assert list(doc["services"]) == ["tubematic-renderer"]
    svc = doc["services"]["tubematic-renderer"]
    [device] = svc["deploy"]["resources"]["reservations"]["devices"]
    # Compose rejects a device request without `capabilities`, and `count`
    # with `device_ids`.
    assert device == {"driver": "nvidia", "device_ids": ["GPU-bbbb"], "capabilities": ["gpu"]}
    env = dict(item.split("=", 1) for item in svc["environment"])
    # graphics is what carries the EGL/GL libraries WebGL needs; older
    # toolkits leave it out unless asked.
    assert env["NVIDIA_DRIVER_CAPABILITIES"] == "graphics,utility"
    assert env["TUBEMATIC_GPU_UUID"] == "GPU-bbbb"
    assert env["TUBEMATIC_GPU_NAME"] == "NVIDIA GeForce RTX 4090"
    assert [g["uuid"] for g in json.loads(env["TUBEMATIC_HOST_GPUS"])] == ["GPU-aaaa", "GPU-bbbb"]


def test_the_override_reads_back(tmp_path):
    path = tmp_path / "o.json"
    path.write_text(gpu.render_override(GTX, [GTX]))
    assert gpu.read_override(path) == {"uuid": "GPU-aaaa", "name": "NVIDIA GeForce GTX 1650"}


def test_no_override_reads_as_none(tmp_path):
    assert gpu.read_override(tmp_path / "missing.json") is None


def test_a_foreign_file_at_the_override_path_is_an_error_not_a_gpu(tmp_path):
    path = tmp_path / "o.json"
    path.write_text("services: {}\n")
    with pytest.raises(ValueError, match="not a GPU override"):
        gpu.read_override(path)


@pytest.fixture
def override(tmp_path, monkeypatch):
    path = tmp_path / "compose.gpu.json"
    monkeypatch.setattr(gpu, "OVERRIDE_PATH", path)
    return path


def test_no_override_has_no_problems(override):
    assert gpu.override_problems() == []


def test_a_usable_override_has_no_problems(override, monkeypatch):
    override.write_text(gpu.render_override(GTX, [GTX]))
    monkeypatch.setattr(gpu, "docker_has_nvidia_runtime", lambda run=None: True)
    monkeypatch.setattr(gpu, "list_gpus", lambda run=None: [GTX])
    assert gpu.override_problems() == []


@pytest.mark.parametrize("runtime,gpus,needle", [
    (False, [GTX], "no `nvidia` runtime"),
    (True, None, "nvidia-smi does not run"),
    (True, [RTX], "no longer on this machine"),
])
def test_an_override_docker_cannot_satisfy_is_a_problem(override, monkeypatch,
                                                        runtime, gpus, needle):
    override.write_text(gpu.render_override(GTX, [GTX]))
    monkeypatch.setattr(gpu, "docker_has_nvidia_runtime", lambda run=None: runtime)
    monkeypatch.setattr(gpu, "list_gpus", lambda run=None: gpus)
    [problem] = gpu.override_problems()
    assert needle in problem and gpu.STEP_HINT in problem


# ── _compose() ───────────────────────────────────────────────────────────────

def test_compose_is_bare_without_an_override(override):
    """Every install without a GPU keeps the exact argv it has always had."""
    assert actions._compose() == ["docker", "compose"]


def test_compose_names_both_files_with_an_override(override):
    override.write_text(gpu.render_override(GTX, [GTX]))
    argv = actions._compose()
    assert argv[:2] == ["docker", "compose"]
    assert argv[2:] == ["-f", str(actions.REPO_ROOT / "docker-compose.yml"), "-f", str(override)]


# ── apply_gpu ────────────────────────────────────────────────────────────────

@pytest.fixture
def step(override, tmp_path, monkeypatch):
    """apply_gpu with the host probes faked and the renderer container absent
    unless a test says otherwise."""
    db_path = tmp_path / "tubematic.db"
    tdb.migrate(db_path, backup=False)
    monkeypatch.setattr(actions, "DB_PATH", db_path)
    container = {"exists": False}

    def inspect(argv, **kw):
        assert argv[:2] == ["docker", "inspect"]
        return _cp("running", 0) if container["exists"] else _cp("", 1)
    monkeypatch.setattr(actions.subprocess, "run", inspect)

    def run(*, gpus=(GTX,), runtime=True, answer=None, dry_run=False):
        asked = []
        rep, ex = _Rep(), _RecordingEx(dry_run=dry_run)

        def ask(choices, default):
            asked.append((choices, default))
            return answer(choices) if answer else default
        actions.apply_gpu(None, ex, rep, list_gpus=lambda: list(gpus) if gpus is not None else None,
                          has_runtime=lambda: runtime, ask=ask)
        return rep, ex, asked
    run.container = container
    run.db_path = db_path
    return run


def test_no_nvidia_gpu_asks_nothing_and_writes_nothing(step, override):
    rep, ex, asked = step(gpus=None)
    assert asked == []
    assert not override.exists()
    assert "No NVIDIA GPU found" in rep.text()


def test_no_nvidia_gpu_removes_a_stale_override(step, override):
    """A GPU that was taken out: keeping the override would fail every `up`."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    step(gpus=[])
    assert not override.exists()


def test_docker_unreachable_asks_nothing_and_keeps_an_existing_override(step, override):
    """Not deleted on a guess: an override may be fine while Docker is briefly
    unreachable."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    rep, ex, asked = step(runtime=None)
    assert asked == []
    assert override.exists()
    assert "NVIDIA Container Toolkit" in rep.text()


def test_no_toolkit_on_a_clean_install_asks_nothing(step, override):
    rep, ex, asked = step(runtime=False)
    assert asked == [] and not override.exists()
    assert "NVIDIA Container Toolkit" in rep.text()


def test_no_toolkit_with_an_override_offers_to_go_back_to_the_cpu(step, override):
    """Found live: with the toolkit gone, every `up` fails while the override
    stays, and the step used to point back at itself with no way out."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    rep, ex, [(choices, default)] = step(runtime=False)
    assert choices == [actions.CPU_CHOICE, actions.KEEP_CHOICE]
    assert default == actions.CPU_CHOICE
    assert not override.exists()


def test_no_toolkit_can_keep_the_override_on_purpose(step, override):
    """Someone halfway through installing the toolkit keeps their choice."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    step(runtime=False, answer=lambda c: actions.KEEP_CHOICE)
    assert override.exists()


def test_no_toolkit_dry_run_asks_and_removes_nothing(step, override):
    override.write_text(gpu.render_override(GTX, [GTX]))
    rep, ex, asked = step(runtime=False, dry_run=True)
    assert asked == [] and override.exists()


def test_a_fresh_install_offers_every_gpu_and_the_cpu_defaulting_to_the_first(step, override):
    rep, ex, [(choices, default)] = step(gpus=[GTX, RTX])
    assert choices == [GTX.label(), RTX.label(), actions.CPU_CHOICE]
    assert default == GTX.label()
    assert gpu.read_override(override)["uuid"] == "GPU-aaaa"


def test_the_current_choice_is_the_default_on_a_rerun(step, override):
    override.write_text(gpu.render_override(RTX, [GTX, RTX]))
    _, _, [(_, default)] = step(gpus=[GTX, RTX])
    assert default == RTX.label()


def test_picking_another_gpu_rewrites_the_override(step, override):
    override.write_text(gpu.render_override(GTX, [GTX, RTX]))
    step(gpus=[GTX, RTX], answer=lambda c: RTX.label())
    assert gpu.read_override(override)["uuid"] == "GPU-bbbb"


def test_picking_the_cpu_removes_the_override(step, override):
    override.write_text(gpu.render_override(GTX, [GTX]))
    step(answer=lambda c: actions.CPU_CHOICE)
    assert not override.exists()


def test_dry_run_asks_nothing_and_writes_nothing(step, override):
    rep, ex, asked = step(dry_run=True)
    assert asked == []
    assert not override.exists()
    assert ex.intents == []


def test_a_fresh_install_does_not_recreate_a_renderer_that_does_not_exist(step):
    """The renderer step creates it next, with the override."""
    rep, ex, _ = step()
    assert ex.calls == []


def test_a_rerun_on_a_running_install_recreates_only_the_renderer(step, override):
    """A device reservation is fixed when a container is created: `restart`
    would keep the old one, so this has to be `up`."""
    step.container["exists"] = True
    rep, ex, _ = step()
    assert ex.calls == [[*actions._compose(), "up", "-d", "tubematic-renderer"]]
    assert str(override) in ex.calls[0]


def test_turning_the_gpu_off_recreates_the_renderer_without_it(step, override):
    step.container["exists"] = True
    override.write_text(gpu.render_override(GTX, [GTX]))
    rep, ex, _ = step(answer=lambda c: actions.CPU_CHOICE)
    assert ex.calls == [["docker", "compose", "up", "-d", "tubematic-renderer"]]


def test_an_unchanged_choice_recreates_nothing(step, override):
    step.container["exists"] = True
    override.write_text(gpu.render_override(GTX, [GTX]))
    rep, ex, _ = step()
    assert ex.calls == []
    assert "unchanged" in rep.text()


def test_a_render_in_progress_is_not_killed_to_apply_the_change(step):
    step.container["exists"] = True
    con = sqlite3.connect(step.db_path)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('vid_1', 't', 'RENDERING', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    rep, ex, _ = step()
    assert ex.calls == []
    assert "service.py start tubematic-renderer" in rep.text()


def _hold(db_path):
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?",
                          (gpu.RENDER_HOLD_KEY,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def test_render_claims_are_held_while_the_renderer_is_recreated(step, override, monkeypatch):
    """Codex review: a render claimed between the look for one and the
    recreate was killed. The hold is written before the look and is still in
    place while compose runs, then released."""
    step.container["exists"] = True
    seen = {}
    from onboard import stack
    real = stack.in_flight

    def looking(db_path):
        seen["hold_at_look"] = _hold(db_path)
        return real(db_path)
    monkeypatch.setattr(stack, "in_flight", looking)
    orig_run = _RecordingEx.run

    def run(self, cmd, cwd=None, **kw):
        seen["hold_at_up"] = _hold(step.db_path)
        return orig_run(self, cmd, cwd=cwd, **kw)
    monkeypatch.setattr(_RecordingEx, "run", run)
    rep, ex, _ = step()
    assert ex.calls == [[*actions._compose(), "up", "-d", "tubematic-renderer"]]
    assert seen["hold_at_look"] and seen["hold_at_up"]
    assert _hold(step.db_path) is None


def test_an_overlapping_run_leaves_the_other_runs_hold_alone(step):
    """Codex review: the hold is one shared row, so a second run that wrote
    and then released it would lift the first run's hold mid-recreate. While
    another run holds the recreate lock, this one recreates nothing and does
    not touch the row."""
    step.container["exists"] = True
    con = sqlite3.connect(step.db_path)
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                (gpu.RENDER_HOLD_KEY, "2999-01-01T00:00:00Z"))
    con.commit()
    con.close()
    from onboard import stack
    with stack.poll_lock(step.db_path.parent / actions.RECREATE_LOCK_NAME) as acquired:
        assert acquired
        rep, ex, _ = step()
    assert ex.calls == []
    assert _hold(step.db_path) == "2999-01-01T00:00:00Z"
    assert "Another" in rep.text()


def test_a_deferred_recreate_releases_the_hold(step):
    step.container["exists"] = True
    con = sqlite3.connect(step.db_path)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('vid_1', 't', 'RENDERING', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    rep, ex, _ = step()
    assert ex.calls == []
    assert _hold(step.db_path) is None


def test_an_unreadable_database_defers_the_recreate(step, monkeypatch):
    """Codex review: the RENDERING-only filter dropped stack.in_flight's
    "cannot read the database" reason and recreated anyway."""
    step.container["exists"] = True
    from onboard import stack
    monkeypatch.setattr(stack, "in_flight", lambda db_path: ["cannot read the database at x"])
    rep, ex, _ = step()
    assert ex.calls == []
    assert "cannot read the database" in rep.text()


def test_a_hold_that_cannot_be_written_defers_the_recreate(step, monkeypatch):
    step.container["exists"] = True

    def refuse(self, db_path, fn, detail):
        raise sqlite3.OperationalError("attempt to write a readonly database")
    monkeypatch.setattr(_RecordingEx, "sqlite_write", refuse)
    rep, ex, _ = step()
    assert ex.calls == []
    assert "readonly" in rep.text()


def test_a_voicing_video_does_not_hold_up_the_renderer(step):
    """Voicing runs in the MCP container; recreating the renderer cannot hurt it."""
    step.container["exists"] = True
    con = sqlite3.connect(step.db_path)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('vid_1', 't', 'VOICING', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    rep, ex, _ = step()
    assert ex.calls == [[*actions._compose(), "up", "-d", "tubematic-renderer"]]


# ── upgrade.py --check / service.py status ───────────────────────────────────

def _store_probe(db_path, probe):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (gpu.PROBE_RESULT_KEY, json.dumps(probe)))
    con.commit()
    con.close()


@pytest.fixture
def readout(override, tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    tdb.migrate(db_path, backup=False)
    monkeypatch.setattr(gpu, "docker_has_nvidia_runtime", lambda run=None: True)
    monkeypatch.setattr(gpu, "list_gpus", lambda run=None: [GTX])
    return db_path


def test_the_readout_says_cpu_without_an_override(readout):
    [(level, text)] = gpu.report_lines(readout)
    assert level == "info" and "CPU" in text


def test_the_readout_names_the_gpu_the_probe_confirmed(readout, override):
    override.write_text(gpu.render_override(GTX, [GTX]))
    _store_probe(readout, {"configured": True, "ok": True, "renderer": "ANGLE (NVIDIA …)",
                           "gpu": {"uuid": GTX.uuid, "name": GTX.name}})
    [(level, text)] = gpu.report_lines(readout)
    assert level == "ok" and "NVIDIA GeForce GTX 1650" in text


def test_the_readout_warns_when_the_chosen_gpu_is_not_usable(readout, override):
    """Renders still succeed — on the CPU, several times slower — so this is
    the line that explains a slow install."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    _store_probe(readout, {"configured": True, "ok": False, "error": "no WebGL context",
                           "gpu": {"uuid": GTX.uuid, "name": GTX.name}})
    [(level, text)] = gpu.report_lines(readout)
    assert level == "warn" and "no WebGL context" in text


def test_the_readout_warns_when_the_renderer_never_got_the_override(readout, override):
    """A hand-run `docker compose up` without the override: the worker probed
    with no GPU configured."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    _store_probe(readout, {"configured": False, "ok": False})
    [(level, text)] = gpu.report_lines(readout)
    assert level == "warn" and "service.py start tubematic-renderer" in text


def test_the_readout_rejects_a_probe_from_the_previous_gpu(readout, override, monkeypatch):
    """A change whose recreate was deferred behind a render: the running
    renderer, and so its probe, is still on the old GPU. Reporting the new
    one as working would be false."""
    monkeypatch.setattr(gpu, "list_gpus", lambda run=None: [GTX, RTX])
    override.write_text(gpu.render_override(RTX, [GTX, RTX]))
    _store_probe(readout, {"configured": True, "ok": True, "renderer": "ANGLE (NVIDIA GTX …)",
                           "gpu": {"uuid": GTX.uuid, "name": GTX.name}})
    [(level, text)] = gpu.report_lines(readout)
    assert level == "warn"
    assert GTX.name in text and RTX.name in text
    assert "service.py start tubematic-renderer" in text


def test_the_readout_does_not_say_cpu_while_the_old_gpu_still_renders(readout, override):
    """GPU switched off, recreate deferred: the renderer is still on the GPU."""
    _store_probe(readout, {"configured": True, "ok": True,
                           "gpu": {"uuid": GTX.uuid, "name": GTX.name}})
    [(level, text)] = gpu.report_lines(readout)
    assert level == "warn" and GTX.name in text and "the CPU is chosen" in text


def test_the_readout_gives_no_recreate_advice_for_an_override_that_cannot_apply(readout, override,
                                                                                monkeypatch):
    """Found live: with no `nvidia` runtime the readout also said to recreate
    the renderer with the override, which fails for the same reason."""
    override.write_text(gpu.render_override(GTX, [GTX]))
    monkeypatch.setattr(gpu, "docker_has_nvidia_runtime", lambda run=None: False)
    _store_probe(readout, {"configured": False, "ok": False})
    [(level, text)] = gpu.report_lines(readout)
    assert level == "warn" and "no `nvidia` runtime" in text
