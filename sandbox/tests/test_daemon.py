"""The sandbox daemon's run loop, without a container (TMDEV-242).

These run the daemon as the current user (`run_as=None`), so they pin the
protocol, the limits and the output filtering. That the code cannot reach
anything is proven in test_container.py against a real container.
"""
import json
import os
import shutil
import time

import pytest

import daemon as D
from tubematic_core import sandbox_protocol as P

HAS_NODE = shutil.which("node") is not None


@pytest.fixture
def cfg(tmp_path):
    spool, work = tmp_path / "spool", tmp_path / "work"
    spool.mkdir()
    work.mkdir()
    c = D.Config(spool=spool, work_root=work, run_as=None, nproc=None)
    D.prepare(c)
    return c


def submit(cfg, code, language="python", timeout_s=10, inputs=None, files=None, rid="a" * 16):
    d = cfg.spool / "req" / rid
    (d / "in").mkdir(parents=True)
    for name, data in (files or {}).items():
        (d / "in" / name).write_bytes(data)
    (d / "request.json").write_text(json.dumps({"language": language, "code": code, "timeout_s": timeout_s,
                                                "inputs": inputs or list((files or {}))}))
    assert D.serve_once(cfg)
    return json.loads((cfg.spool / "done" / rid / "result.json").read_text())


def test_python_stdout_and_exit_code(cfg):
    r = submit(cfg, "print(2 + 2)")
    assert r["exit_code"] == 0 and r["stdout"] == "4\n" and not r["timed_out"] and r["error"] is None


def test_a_failing_run_reports_stderr_and_its_code(cfg):
    r = submit(cfg, "raise SystemExit(3)")
    assert r["exit_code"] == 3
    r = submit(cfg, "1/0", rid="b" * 16)
    assert r["exit_code"] == 1 and "ZeroDivisionError" in r["stderr"]


def test_the_request_is_consumed_and_the_work_folder_wiped(cfg):
    submit(cfg, "print(1)")
    assert not (cfg.spool / "req" / ("a" * 16)).exists()
    assert os.listdir(cfg.work_root) == []


def test_an_infinite_loop_is_killed_at_the_timeout(cfg):
    t = time.monotonic()
    r = submit(cfg, "while True: pass", timeout_s=1)
    assert r["timed_out"] and r["signal"] and time.monotonic() - t < 6


def test_a_grandchild_is_killed_with_the_process_group(cfg, tmp_path):
    marker = tmp_path / "alive"
    code = ("import subprocess,sys\n"
            f"subprocess.Popen([sys.executable,'-c','import time;time.sleep(3);open({str(marker)!r},\"w\")'])\n"
            "import time; time.sleep(30)")
    submit(cfg, code, timeout_s=1)
    time.sleep(3.5)
    assert not marker.exists()


def test_huge_output_is_cut_and_flagged(cfg):
    r = submit(cfg, "print('x' * 200000)")
    assert r["output_truncated"] and len(r["stdout"]) < P.MAX_STREAM_CHARS + 100


def test_environment_is_scrubbed(cfg, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    r = submit(cfg, "import os; print(sorted(os.environ))")
    assert "OPENAI_API_KEY" not in r["stdout"] and "PATH" in r["stdout"]


def test_inputs_are_staged_in_in_and_outputs_come_back(cfg):
    code = ("import pathlib\n"
            "d = pathlib.Path('in/a.txt').read_text()\n"
            "pathlib.Path('out/b.txt').write_text(d.upper())")
    r = submit(cfg, code, files={"a.txt": b"hello"})
    assert r["files"] == [{"name": "b.txt", "size": 5}]
    assert (cfg.spool / "done" / ("a" * 16) / "out" / "b.txt").read_text() == "HELLO"


def test_only_regular_allowed_files_are_returned(cfg, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    code = ("import os, pathlib\n"
            "o = pathlib.Path('out')\n"
            "(o/'ok.png').write_bytes(b'x')\n"
            "(o/'bad.exe').write_bytes(b'x')\n"
            "(o/'.hidden.txt').write_bytes(b'x')\n"
            f"os.symlink({str(secret)!r}, o/'link.txt')\n"
            "(o/'dir.txt').mkdir()\n"
            "(o/'a b.txt').write_bytes(b'x')")
    r = submit(cfg, code)
    assert [f["name"] for f in r["files"]] == ["ok.png"]


def test_file_count_and_size_are_capped(cfg):
    code = ("import pathlib\n"
            "for i in range(20): pathlib.Path(f'out/f{i}.txt').write_text('x')\n"
            f"pathlib.Path('out/zbig.png').write_bytes(b'x' * {P.MAX_OUT_FILE_BYTES + 1})")
    r = submit(cfg, code)
    assert len(r["files"]) == P.MAX_OUT_FILES
    assert "zbig.png" not in [f["name"] for f in r["files"]]


@pytest.mark.parametrize("req", [
    {"language": "ruby", "code": "x", "timeout_s": 5},
    {"language": "python", "code": "  ", "timeout_s": 5},
    {"language": "python", "code": "x", "timeout_s": 0},
    {"language": "python", "code": "x", "timeout_s": P.MAX_TIMEOUT_S + 1},
    {"language": "python", "code": "x" * (P.MAX_CODE_BYTES + 1), "timeout_s": 5},
    {"language": "python", "code": "x", "timeout_s": 5, "inputs": ["../etc"]},
    {"language": "python", "code": "x", "timeout_s": 5, "inputs": "all"},
])
def test_a_bad_request_becomes_an_error_result_not_a_crash(cfg, req):
    d = cfg.spool / "req" / ("c" * 16)
    d.mkdir()
    (d / "request.json").write_text(json.dumps(req))
    assert D.serve_once(cfg)
    r = json.loads((cfg.spool / "done" / ("c" * 16) / "result.json").read_text())
    assert r["error"] and r["exit_code"] is None


def test_an_unreadable_request_is_an_error_result(cfg):
    d = cfg.spool / "req" / ("d" * 16)
    d.mkdir()
    (d / "request.json").write_text("{not json")
    D.serve_once(cfg)
    assert "unreadable" in json.loads((cfg.spool / "done" / ("d" * 16) / "result.json").read_text())["error"]


def test_the_loop_survives_a_crash_inside_a_run(cfg, monkeypatch):
    monkeypatch.setattr(D, "_stage", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = submit(cfg, "print(1)")
    assert r["error"].startswith("sandbox error")


def test_no_request_means_nothing_to_do(cfg):
    assert D.serve_once(cfg) is False


def test_temp_names_and_foreign_names_in_req_are_ignored(cfg):
    (cfg.spool / "req" / ".tmp").mkdir()
    (cfg.spool / "req" / "not-an-id").mkdir()
    assert D.pending(cfg) == []


def test_sweep_removes_old_results_and_half_written_temporaries(cfg):
    old, new = cfg.spool / "done" / ("e" * 16), cfg.spool / "done" / ("f" * 16)
    tmp = cfg.spool / "req" / ".x.tmp"
    for d in (old, new, tmp):
        d.mkdir()
    past = time.time() - P.STALE_AFTER_S - 5
    os.utime(old, (past, past))
    D.sweep(cfg)
    assert not old.exists() and tmp.exists() and new.exists()  # a fresh temporary may still be written
    os.utime(tmp, (past, past))
    D.sweep(cfg)
    assert not tmp.exists()


def test_the_heartbeat_is_fresh_after_a_beat(cfg):
    assert P.heartbeat_age(cfg.spool) is None
    P.write_heartbeat(cfg.spool)
    assert P.heartbeat_age(cfg.spool) < 2


def test_spool_dirs_are_private(cfg):
    assert oct((cfg.spool / "req").stat().st_mode & 0o777) == "0o700"
    assert oct((cfg.spool / "done").stat().st_mode & 0o777) == "0o700"


@pytest.mark.skipif(not HAS_NODE, reason="node not installed")
def test_javascript_runs(cfg):
    r = submit(cfg, "console.log([1,2,3].map(x=>x*2).join(','))", language="javascript")
    assert r["exit_code"] == 0 and r["stdout"] == "2,4,6\n"


@pytest.mark.skipif(not HAS_NODE, reason="node not installed")
def test_typescript_is_transpiled_then_run(cfg):
    esbuild = shutil.which("esbuild")
    local = os.path.join(os.path.dirname(__file__), "..", "..", "renderer", "remotion", "node_modules", ".bin", "esbuild")
    if esbuild is None and not os.path.exists(local):
        pytest.skip("esbuild not installed")
    cfg.esbuild = esbuild or os.path.abspath(local)
    r = submit(cfg, "const n: number = 5; console.log(n * 2)", language="typescript")
    assert r["exit_code"] == 0 and r["stdout"] == "10\n", r
    r = submit(cfg, "const n: number = ;", language="typescript", rid="9" * 16)
    assert r["exit_code"] != 0 and r["stderr"]


def test_wipe_owned_removes_only_what_the_uid_owns(tmp_path):
    (tmp_path / "mine.txt").write_text("x")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "f").write_text("x")
    assert D.wipe_owned(tmp_path, os.getuid()) == 2 and os.listdir(tmp_path) == []
    (tmp_path / "other").write_text("x")
    assert D.wipe_owned(tmp_path, os.getuid() + 1) == 0 and os.listdir(tmp_path) == ["other"]


def test_the_second_step_of_a_typescript_run_shares_the_first_ones_budget(cfg, monkeypatch):
    """esbuild and node together may take timeout_s, not twice it (TMDEV-242 review)."""
    calls = []

    def fake_run(cfg_, argv, work, runner, timeout, language, beat):
        calls.append(timeout)
        time.sleep(0.6)
        return {"exit_code": 0, "signal": None, "timed_out": False, "output_truncated": False,
                "stdout": "", "stderr": "", "duration_ms": 600}

    monkeypatch.setattr(D, "_run", fake_run)
    submit(cfg, "const a = 1", language="typescript", timeout_s=2)
    assert len(calls) == 2 and calls[0] <= 2 and calls[1] < calls[0] - 0.5


def test_wipe_also_covers_a_second_folder(cfg, tmp_path):
    shm = tmp_path / "shm"
    shm.mkdir()
    (shm / "stash").write_text("x")
    cfg.wipe_also = (shm,)
    cfg.run_as = None  # wiping happens only when the code ran as another uid
    assert D.wipe_owned(shm, os.getuid()) == 1 and os.listdir(shm) == []


def test_a_transpile_that_uses_the_whole_budget_is_a_timeout_not_a_success(cfg, monkeypatch):
    def fake_run(cfg_, argv, work, runner, timeout, language, beat):
        time.sleep(1.2)
        return {"exit_code": 0, "signal": None, "timed_out": False, "output_truncated": False,
                "stdout": "", "stderr": "", "duration_ms": 1200}

    monkeypatch.setattr(D, "_run", fake_run)
    r = submit(cfg, "const a = 1", language="typescript", timeout_s=1)
    assert r["timed_out"] is True and r["exit_code"] is None and "program started" in r["stderr"]


def test_a_request_dropped_while_listing_does_not_crash_pending(cfg, monkeypatch):
    d = cfg.spool / "req"
    (d / ("a" * 16)).mkdir()
    (d / ("b" * 16)).mkdir()
    real = D.Path.stat

    def flaky(self, *a, **k):
        if self.name == "a" * 16:
            raise FileNotFoundError(self)
        return real(self, *a, **k)

    monkeypatch.setattr(D.Path, "stat", flaky)
    assert [p.name for p in D.pending(cfg)] == ["b" * 16]
