"""run_code and mcp/sandbox_client.py (TMDEV-242).

The sandbox container is replaced by the real daemon (sandbox/daemon.py) run in
a thread against a temporary spool, as the current user. That exercises the
whole spool protocol: request files, results, the output re-check. What the
container itself refuses is test_container.py's job.
"""
import io
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

import sandbox_client as sc
import server
from tubematic_core import sandbox_protocol as P

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sandbox"))
import daemon as D  # noqa: E402

VID = "vid-1"


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A temporary DB, jobs dir and spool, with the real daemon looping in a thread."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    spool, work = tmp_path / "spool", tmp_path / "work"
    spool.mkdir()
    work.mkdir()
    monkeypatch.setenv("TUBEMATIC_SANDBOX_DIR", str(spool))
    # The interpreter running pytest, not "python3" on the daemon's fixed PATH: that one is the
    # machine's system Python, which has Pillow on a dev box and not on a CI runner.
    cfg = D.Config(spool=spool, work_root=work, run_as=None, nproc=None, python=sys.executable)
    D.prepare(cfg)
    server._init_db()
    with server._conn() as con:
        con.execute("INSERT INTO videos (id, topic, created_at, updated_at) VALUES (?, 'test topic', 'x', 'x')",
                    (VID,))
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            P.write_heartbeat(spool)
            if not D.serve_once(cfg):
                time.sleep(0.02)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    # Not before the first heartbeat: run_code answers sandbox_unavailable until the daemon has beaten.
    deadline = time.time() + 5
    while P.heartbeat_age(spool) is None and time.time() < deadline:
        time.sleep(0.01)
    yield tmp_path
    stop.set()
    t.join(timeout=5)


@pytest.fixture
def through_mcp():
    """Tools are plain functions here; a dict result is returned as is."""
    def call(tool, **kwargs):
        return getattr(server, tool)(**kwargs), None
    return call


def _png(w=8, h=8, color="red"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_a_python_run_returns_stdout(box, through_mcp):
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="print(sum(range(5)))")
    assert r["exit_code"] == 0 and r["stdout"] == "10\n" and r["files"] == [] and r["run_id"]


def test_an_image_input_goes_in_and_a_picture_comes_out_inline_and_stored(box, through_mcp):
    img = box / "jobs" / VID / "images"
    img.mkdir(parents=True)
    (img / "cat.png").write_bytes(_png(40, 20))
    code = ("from PIL import Image\n"
            "im = Image.open('in/cat.png'); print(im.size)\n"
            "im.crop((0, 0, 10, 10)).save('out/crop.png')")
    out = server.run_code(VID, "python", code, ["images/cat.png"])
    assert isinstance(out, list) and "crop.png" in out[0] and len(out) == 2
    rid = json.loads(out[0])["run_id"]
    stored = box / "jobs" / VID / "runs" / rid / "crop.png"
    assert Image.open(stored).size == (10, 10)
    # the run's file can feed a later run
    r, _ = through_mcp("run_code", video_id=VID, language="python",
                       code="from PIL import Image; print(Image.open('in/crop.png').size)",
                       inputs=[f"runs/{rid}/crop.png"])
    assert r["stdout"] == "(10, 10)\n"


def test_a_picture_that_is_not_one_is_not_kept(box, through_mcp):
    code = "open('out/fake.png', 'wb').write(b'not a png at all')\nopen('out/ok.txt', 'w').write('x')"
    r, _ = through_mcp("run_code", video_id=VID, language="python", code=code)
    assert [f["name"] for f in r["files"]] == ["ok.txt"]


def test_a_text_file_must_be_utf8(box, through_mcp):
    r, _ = through_mcp("run_code", video_id=VID, language="python",
                       code="open('out/b.txt', 'wb').write(b'\\xff\\xfe\\x00')")
    assert r["files"] == []


@pytest.mark.parametrize("bad", ["../x", "images/../../etc/passwd", "audio.mp3", "images", "runs/x",
                                 "images/treated/../a.png", "/etc/passwd", "images/a/b/c.png"])
def test_inputs_outside_the_allowlist_are_refused(box, through_mcp, bad):
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="print(1)", inputs=[bad])
    assert r["error"] == "bad_inputs"


def test_a_missing_input_a_symlink_and_a_big_file_are_refused(box, through_mcp, tmp_path):
    img = box / "jobs" / VID / "images"
    img.mkdir(parents=True)
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1", inputs=["images/none.png"])
    assert r["error"] == "bad_inputs"
    secret = tmp_path / "secret.png"
    secret.write_bytes(_png())
    (img / "link.png").symlink_to(secret)
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1", inputs=["images/link.png"])
    assert r["error"] == "bad_inputs"
    (img / "big.png").write_bytes(b"x" * (P.MAX_INPUT_FILE_BYTES + 1))
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1", inputs=["images/big.png"])
    assert r["error"] == "bad_inputs"


def test_two_inputs_with_one_base_name_are_refused(box, through_mcp):
    (box / "jobs" / VID / "images" / "treated").mkdir(parents=True)
    (box / "jobs" / VID / "images" / "a.png").write_bytes(_png())
    (box / "jobs" / VID / "images" / "treated" / "a.png").write_bytes(_png())
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1",
                       inputs=["images/a.png", "images/treated/a.png"])
    assert r["error"] == "bad_inputs"


@pytest.mark.parametrize("args,code", [
    ({"language": "ruby", "code": "x"}, "bad_language"),
    ({"language": "python", "code": "  "}, "bad_code"),
    ({"language": "python", "code": "x" * (P.MAX_CODE_BYTES + 1)}, "bad_code"),
    ({"language": "python", "code": "x", "timeout_s": 0}, "bad_timeout"),
    ({"language": "python", "code": "x", "timeout_s": 61}, "bad_timeout"),
])
def test_bad_arguments_are_refused(box, through_mcp, args, code):
    r, _ = through_mcp("run_code", video_id=VID, **args)
    assert r["error"] == code


def test_unknown_video_and_bad_id(box, through_mcp):
    r, _ = through_mcp("run_code", video_id="nope", language="python", code="1")
    assert "not found" in r["error"]
    r, _ = through_mcp("run_code", video_id="../x", language="python", code="1")
    assert "error" in r


def test_no_heartbeat_means_unavailable_and_nothing_runs_here(box, through_mcp, monkeypatch, tmp_path):
    empty = tmp_path / "empty-spool"
    (empty / "req").mkdir(parents=True)
    monkeypatch.setenv("TUBEMATIC_SANDBOX_DIR", str(empty))
    marker = tmp_path / "ran-here"
    r, _ = through_mcp("run_code", video_id=VID, language="python", code=f"open({str(marker)!r}, 'w')")
    assert r["error"] == "sandbox_unavailable" and not marker.exists()


def test_a_stale_heartbeat_means_unavailable(box, through_mcp, tmp_path, monkeypatch):
    stale = tmp_path / "stale"
    (stale / "req").mkdir(parents=True)
    P.write_heartbeat(stale, now=time.time() - 60)
    monkeypatch.setenv("TUBEMATIC_SANDBOX_DIR", str(stale))
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1")
    assert r["error"] == "sandbox_unavailable"


def test_a_sandbox_that_is_not_configured_is_unavailable(box, through_mcp, monkeypatch):
    monkeypatch.delenv("TUBEMATIC_SANDBOX_DIR")
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1")
    assert r["error"] == "sandbox_unavailable"


def test_a_full_queue_is_busy(box, through_mcp, tmp_path, monkeypatch):
    q = tmp_path / "q"
    (q / "req").mkdir(parents=True)
    for i in range(P.MAX_QUEUED):
        (q / "req" / (f"{i:016x}")).mkdir()
    P.write_heartbeat(q)
    monkeypatch.setenv("TUBEMATIC_SANDBOX_DIR", str(q))
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="1")
    assert r["error"] == "sandbox_busy"


def test_a_result_that_never_comes_is_dropped(tmp_path):
    spool = tmp_path
    (spool / "req" / ("a" * 16)).mkdir(parents=True)
    clock = iter(range(0, 1000, 5))
    with pytest.raises(sc.SandboxError) as e:
        sc.wait_for_result(spool, "a" * 16, 1, sleep=lambda s: None, clock=lambda: next(clock))
    assert e.value.code == "sandbox_timeout" and not (spool / "req" / ("a" * 16)).exists()


def test_a_result_with_odd_types_is_cleaned(tmp_path):
    out = sc.clean_result({"exit_code": "0", "signal": True, "timed_out": "yes", "stdout": 5, "stderr": None,
                           "duration_ms": 12, "error": 3, "extra": "ignored"})
    assert out == {"exit_code": None, "signal": None, "timed_out": False, "output_truncated": False,
                   "stdout": "", "stderr": "", "duration_ms": 12, "error": None}


def test_the_daemons_own_error_is_returned_as_an_error(box, through_mcp):
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="print(1)", timeout_s=1)
    assert r["exit_code"] == 0
    # a request the daemon rejects: bypass the client checks
    spool = Path(sc.spool_dir())
    rid = sc.submit(spool, "ruby", "x", 5, [])
    res = sc.wait_for_result(spool, rid, 5)
    assert res["error"] and res["exit_code"] is None


def test_old_runs_are_pruned(box):
    jobs = box / "jobs"
    for i in range(sc.MAX_RUNS_KEPT + 3):
        d = jobs / VID / "runs" / f"r{i:03d}"
        d.mkdir(parents=True)
        (d / "a.txt").write_text("x")
        t = time.time() - 1000 + i
        import os
        os.utime(d, (t, t))
    sc.prune_runs(jobs, VID)
    left = sorted(p.name for p in (jobs / VID / "runs").iterdir())
    assert len(left) == sc.MAX_RUNS_KEPT and "r000" not in left and f"r{sc.MAX_RUNS_KEPT + 2:03d}" in left


def test_run_files_never_land_in_images(box, through_mcp):
    r, _ = through_mcp("run_code", video_id=VID, language="python", code="open('out/a.txt', 'w').write('x')")
    assert not (box / "jobs" / VID / "images").exists()
    assert (box / "jobs" / VID / "runs" / r["run_id"] / "a.txt").read_text() == "x"


def test_the_validator_runner_returns_the_real_output_and_keeps_nothing(box):
    r = server._snippet_runner("python", "print('hi')")
    assert r["exit_code"] == 0 and r["stdout"] == "hi\n"
    assert list((box / "spool" / "done").iterdir()) == []


def test_the_validator_runner_is_none_when_the_sandbox_is_not_there(box, monkeypatch):
    monkeypatch.delenv("TUBEMATIC_SANDBOX_DIR")
    assert server._snippet_runner("python", "print(1)") is None


def test_a_wrong_output_pane_is_refused_end_to_end(box):
    import code_scenes as cs
    entry = {"props": {"codeScenes": {"lang": "python", "steps": [
        {"at": 0, "code": "print(6 * 7)", "output": {"lines": ["41"]}}]}}}
    out = cs.output_check(entry, server._snippet_runner)
    assert len(out) == 1 and "['42']" in out[0]
    entry["props"]["codeScenes"]["steps"][0]["output"]["lines"] = ["42"]
    assert cs.output_check(entry, server._snippet_runner) == []


def test_concurrent_calls_cannot_all_pass_the_queue_check(tmp_path, monkeypatch):
    """Without the admission lock every thread sees room and queues (TMDEV-242 review)."""
    spool = tmp_path
    (spool / "req").mkdir()
    P.write_heartbeat(spool)
    outcomes = []

    def go():
        try:
            sc._admit(spool, "python", "print(1)", 5, [])
            outcomes.append("queued")
        except sc.SandboxError as e:
            outcomes.append(e.code)

    real = sc.queue_length
    monkeypatch.setattr(sc, "queue_length", lambda s: (time.sleep(0.05), real(s))[1])
    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("queued") == P.MAX_QUEUED and outcomes.count("sandbox_busy") == 8 - P.MAX_QUEUED
