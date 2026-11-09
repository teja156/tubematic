"""renderers.py: the rules every process reads about the machines that render.

The scheduler (pick_video, estimate_secs) is pure and tested exhaustively: a
wrong answer either hands a long job to a slow machine while a fast one sits
idle, or — worse — starves a video, or gives a GPU-only video to a CPU machine
that would take hours. The credential rules (authenticate, maybe_rotate,
enroll) are the gateway's whole access control, so every refusal sits beside
the case that must still pass.
"""
import json
import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import renderers as R  # noqa: E402

NOW = "2026-11-08T12:00:00Z"
V = "2.1.0"


def ts(secs_from_now: float) -> str:
    return R.ts_add(NOW, secs_from_now)


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


@pytest.fixture
def con(tmp_path):
    path = tmp_path / "data" / "tubematic.db"
    path.parent.mkdir(parents=True)
    tdb.migrate(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def renderer(rid, *, gpu=False, online=True, enabled=True, version=V, cpus=4, current=None,
             removed=None):
    return {"id": rid, "enabled": int(enabled), "removed_at": removed, "version": version,
            "gpu_verified": int(gpu), "last_heartbeat_at": ts(-10) if online else ts(-3600),
            "compute": json.dumps({"cpus": cpus}), "current": current}


def video(vid, *, waited=60, style="auto", renderer_kind="", mascot="", frames=900, scene_cartoon=False):
    return {"id": vid, "updated_at": ts(-waited), "visual_style": style, "resolved_renderer": renderer_kind,
            "mascot_id": mascot, "frames": frames, "scene_cartoon": scene_cartoon}


def timing(rid, kind, frames, seconds, tid):
    return {"id": tid, "renderer_id": rid, "kind": kind, "frames": frames, "seconds": seconds}


# ── time helpers ──────────────────────────────────────────────────────────────

def test_timestamps_round_trip_in_the_database_format():
    assert R.ts_add(NOW, 90) == "2026-11-08T12:01:30Z"
    assert R.age_secs("2026-11-08T11:59:00Z", NOW) == 60
    assert R.age_secs("", NOW) is None and R.age_secs("garbage", NOW) is None
    assert R.parse_ts(None) is None


# ── secrets, pins, tokens ─────────────────────────────────────────────────────

def test_hash_secret_is_sha256_hex_and_new_secrets_differ():
    assert R.hash_secret("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert R.new_secret() != R.new_secret()
    assert len(R.new_secret()) >= 40


def test_cert_pin_is_the_sha256_of_the_der():
    assert R.cert_pin(b"abc") == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


PIN = "sha256:" + "a" * 64


def test_an_enrollment_token_round_trips_with_no_padding():
    tok = R.encode_enrollment_token("https://10.0.0.5:4443", "s3cret", PIN)
    assert tok.startswith(R.TOKEN_PREFIX) and "=" not in tok
    assert R.decode_enrollment_token("  " + tok + "\n") == {
        "url": "https://10.0.0.5:4443", "secret": "s3cret", "pin": PIN}


@pytest.mark.parametrize("tok", [
    None, "", "tmr2.abc", "tmr1.", "tmr1.!!!!", "tmr1." + "eyJ1Ijo",            # prefix, base64, cut off
    R.encode_enrollment_token("http://10.0.0.5:4443", "s", PIN),               # not https
    R.encode_enrollment_token("https://h", "", PIN),                            # empty secret
    R.encode_enrollment_token("https://h", "s", "sha256:abc"),                  # short pin
    R.encode_enrollment_token("https://h", "s", "md5:" + "a" * 64),             # wrong pin scheme
    "tmr1.WzEsMl0",                                                             # JSON, but a list
])
def test_a_malformed_enrollment_token_is_refused(tok):
    with pytest.raises(ValueError):
        R.decode_enrollment_token(tok)


# ── video kinds ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("v, kind", [
    (video("a"), "dom"),
    (video("a", style="cartoon_3d"), "cartoon_3d"),
    (video("a", renderer_kind="cartoon_3d"), "cartoon_3d"),
    (video("a", scene_cartoon=True), "cartoon_3d"),
    (video("a", mascot="tubi"), "mascot"),
    (video("a", style="cartoon_3d", mascot="tubi"), "cartoon_3d"),
    ({"id": "a"}, "dom"),
    ({"id": "a", "visual_style": None, "mascot_id": None}, "dom"),
])
def test_video_kind_and_gpu_need(v, kind):
    assert R.video_kind(v) == kind
    assert R.requires_gpu(v) is (kind != "dom")


def test_video_kind_reads_sqlite_rows(con):
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at, mascot_id) "
                "VALUES ('v', 't', 'RENDER_QUEUED', 'x', 'x', 'tubi')")
    row = con.execute("SELECT * FROM videos").fetchone()
    assert R.video_kind(row) == "mascot" and R.requires_gpu(row)


# ── renderer predicates ───────────────────────────────────────────────────────

def test_online_is_a_heartbeat_within_online_secs():
    assert R.is_online({"last_heartbeat_at": ts(-R.ONLINE_SECS)}, NOW)
    assert not R.is_online({"last_heartbeat_at": ts(-R.ONLINE_SECS - 1)}, NOW)
    assert not R.is_online({"last_heartbeat_at": ""}, NOW)


def test_gpu_capable_needs_enabled_verified_and_not_removed_but_not_online():
    assert R.gpu_capable(renderer("a", gpu=True, online=False, version="1.0.0"))
    assert not R.gpu_capable(renderer("a", gpu=False))
    assert not R.gpu_capable(renderer("a", gpu=True, enabled=False))
    assert not R.gpu_capable(renderer("a", gpu=True, removed=NOW))


def test_needs_upgrade_only_for_a_reported_mismatch():
    assert R.needs_upgrade({"version": "2.0.0"}, V)
    assert not R.needs_upgrade({"version": V}, V)
    assert not R.needs_upgrade({"version": ""}, V)   # never connected is its own state


# ── estimate_secs ─────────────────────────────────────────────────────────────

def test_the_estimate_is_the_median_of_the_last_five_timings():
    r = renderer("a")
    # Six timings, oldest first by id: the first (a 10 s/frame outlier) is out
    # of the window; the median of 1,1,2,3,100 s/frame is 2.
    rows = [timing("a", "dom", 10, 100, 1), timing("a", "dom", 10, 10, 2), timing("a", "dom", 10, 10, 3),
            timing("a", "dom", 10, 20, 4), timing("a", "dom", 10, 30, 5), timing("a", "dom", 10, 1000, 6)]
    assert R.estimate_secs(rows, 100, r) == 200
    # Order comes from the ids, not the list order.
    assert R.estimate_secs(list(reversed(rows)), 100, r) == 200


def test_the_estimate_ignores_a_timing_with_no_frames():
    rows = [timing("a", "dom", 0, 50, 1), timing("a", "dom", 10, 5, 2)]
    assert R.estimate_secs(rows, 100, renderer("a")) == 50


def test_with_no_timings_a_verified_gpu_uses_the_gpu_prior():
    assert R.estimate_secs([], 1000, renderer("a", gpu=True)) == pytest.approx(250)


@pytest.mark.parametrize("cpus, expected", [(4, 1500), (8, 750), (2, 3000), (0, 6000), (None, 6000)])
def test_with_no_timings_a_cpu_prior_scales_with_cores(cpus, expected):
    r = renderer("a")
    r["compute"] = json.dumps({"cpus": cpus} if cpus is not None else {})
    assert R.estimate_secs([], 1000, r) == pytest.approx(expected)


def test_the_estimate_reads_compute_as_a_dict_or_bad_json():
    assert R.estimate_secs([], 100, {"compute": {"cpus": 8}}) == pytest.approx(75)
    assert R.estimate_secs([], 100, {"compute": "not json"}) == pytest.approx(600)


# ── pick_video ────────────────────────────────────────────────────────────────

def test_a_lone_idle_renderer_takes_the_oldest_video():
    q = [video("new", waited=10), video("old", waited=100)]
    assert R.pick_video(q, [renderer("a")], [], "a", NOW, V) == "old"


def test_queue_ties_break_on_id():
    q = [video("b", waited=50), video("a", waited=50)]
    assert R.pick_video(q, [renderer("x")], [], "x", NOW, V) == "a"


def test_an_empty_queue_gives_nothing():
    assert R.pick_video([], [renderer("a")], [], "a", NOW, V) is None


@pytest.mark.parametrize("caller", [
    renderer("a", enabled=False), renderer("a", removed=NOW), renderer("a", version="2.0.0"),
    renderer("a", version=""),
])
def test_a_disabled_removed_or_mismatched_caller_gets_nothing(caller):
    assert R.pick_video([video("v")], [caller], [], "a", NOW, V) is None


def test_an_unknown_caller_gets_nothing():
    assert R.pick_video([video("v")], [renderer("a")], [], "ghost", NOW, V) is None


def test_the_caller_counts_as_online_even_with_a_stale_heartbeat():
    assert R.pick_video([video("v")], [renderer("a", online=False)], [], "a", NOW, V) == "v"


def test_a_gpu_video_is_skipped_by_a_cpu_renderer_which_takes_the_next():
    q = [video("cartoon", waited=300, style="cartoon_3d"), video("mascot", waited=200, mascot="tubi"),
         video("plain", waited=10)]
    assert R.pick_video(q, [renderer("cpu")], [], "cpu", NOW, V) == "plain"


def test_a_gpu_video_is_skipped_even_past_starvation():
    q = [video("cartoon", waited=R.STARVATION_SECS * 10, scene_cartoon=True)]
    assert R.pick_video(q, [renderer("cpu")], [], "cpu", NOW, V) is None


def test_a_gpu_renderer_takes_a_gpu_video():
    q = [video("cartoon", style="cartoon_3d")]
    assert R.pick_video(q, [renderer("g", gpu=True)], [], "g", NOW, V) == "cartoon"


def test_a_slow_caller_skips_a_video_a_much_faster_idle_renderer_will_finish_sooner():
    # The CPU caller's prior is 1.5 s/frame, the GPU renderer's 0.25.
    rs = [renderer("cpu"), renderer("gpu", gpu=True)]
    assert R.pick_video([video("v")], rs, [], "cpu", NOW, V) is None
    assert R.pick_video([video("v")], rs, [], "gpu", NOW, V) == "v"


def test_within_the_tolerance_the_caller_takes_it():
    rs = [renderer("a"), renderer("b")]
    t = [timing("a", "dom", 100, 120, 1), timing("b", "dom", 100, 100, 2)]   # 1.2 vs 1.0 s/frame
    assert R.pick_video([video("v")], rs, t, "a", NOW, V) == "v"
    t = [timing("a", "dom", 100, 130, 1), timing("b", "dom", 100, 100, 2)]   # 1.3 vs 1.0: over 1.25
    assert R.pick_video([video("v")], rs, t, "a", NOW, V) is None


def test_a_starved_video_goes_to_whoever_asks():
    rs = [renderer("cpu"), renderer("gpu", gpu=True)]
    q = [video("v", waited=R.STARVATION_SECS + 1)]
    assert R.pick_video(q, rs, [], "cpu", NOW, V) == "v"
    q = [video("v", waited=R.STARVATION_SECS)]
    assert R.pick_video(q, rs, [], "cpu", NOW, V) is None


def test_a_skipped_video_lets_the_caller_take_a_later_one_it_suits():
    # The fast renderer is busy for a long while; for the long video it would
    # still win, but for a later video nobody faster is free... both compared
    # per video. Here the slow caller skips v1 (the fast one is idle) and v2 too:
    rs = [renderer("cpu"), renderer("gpu", gpu=True)]
    q = [video("v1", waited=100), video("v2", waited=50)]
    assert R.pick_video(q, rs, [], "cpu", NOW, V) is None
    # ...but takes the GPU-free video once the fast renderer is busy for longer
    # than the caller would need.
    busy = renderer("gpu", gpu=True, current={"kind": "dom", "frames": 100000, "started_at": ts(-10)})
    assert R.pick_video(q, [renderer("cpu"), busy], [], "cpu", NOW, V) == "v1"


def test_time_until_free_is_the_estimate_minus_elapsed_and_never_negative():
    t = [timing("b", "cartoon_3d", 100, 50, 1)]   # 0.5 s/frame
    busy = renderer("b", gpu=True, current={"kind": "cartoon_3d", "frames": 1000, "started_at": ts(-100)})
    assert R.time_until_free(busy, t, NOW) == pytest.approx(400)
    done = renderer("b", gpu=True, current={"kind": "cartoon_3d", "frames": 1000, "started_at": ts(-9999)})
    assert R.time_until_free(done, t, NOW) == 0
    assert R.time_until_free(renderer("b"), t, NOW) == 0


@pytest.mark.parametrize("other", [
    renderer("fast", gpu=True, online=False),
    renderer("fast", gpu=True, enabled=False),
    renderer("fast", gpu=True, removed=NOW),
    renderer("fast", gpu=True, version="2.0.0"),
])
def test_an_offline_disabled_removed_or_outdated_renderer_does_not_hold_a_video_back(other):
    assert R.pick_video([video("v")], [renderer("slow"), other], [], "slow", NOW, V) == "v"


def test_only_gpu_capable_renderers_compete_for_a_gpu_video():
    # A super-fast CPU machine can't take a cartoon, so it does not make the GPU caller wait.
    rs = [renderer("g", gpu=True), renderer("cpu", cpus=1000)]
    t = [timing("cpu", "cartoon_3d", 100, 1, 1)]
    assert R.pick_video([video("c", style="cartoon_3d")], rs, t, "g", NOW, V) == "c"


def test_timings_are_per_kind():
    rs = [renderer("a"), renderer("b")]
    # a is fast at mascots but slow at dom; b the reverse.
    t = [timing("a", "dom", 100, 300, 1), timing("a", "mascot", 100, 10, 2),
         timing("b", "dom", 100, 10, 3), timing("b", "mascot", 100, 300, 4)]
    for r in rs:
        r["gpu_verified"] = 1
    assert R.pick_video([video("m", mascot="tubi")], rs, t, "a", NOW, V) == "m"
    assert R.pick_video([video("d")], rs, t, "a", NOW, V) is None


def test_a_video_with_no_frame_count_is_weighed_as_a_typical_short():
    # With frames=0 every estimate would be 0 and a busy renderer's head start
    # would decide alone; DEFAULT_FRAMES keeps the comparison realistic.
    busy_fast = renderer("fast", gpu=True, current={"kind": "dom", "frames": 400, "started_at": ts(0)})
    q = [video("v", frames=0)]
    # fast: 100 s left + 2700*0.25 = 775; caller: 2700*1.5*(4/16) = 1012 > 775*1.25? no (968.75) -> skip
    assert R.pick_video(q, [renderer("cpu", cpus=16), busy_fast], [], "cpu", NOW, V) is None
    assert R.pick_video(q, [renderer("cpu", cpus=20), busy_fast], [], "cpu", NOW, V) == "v"


# ── the database-backed state ─────────────────────────────────────────────────

def _add(con, rid, *, name=None, enabled=1, gpu=0, probe=None, hb="", version=V, removed=None, builtin=0):
    con.execute("INSERT INTO renderers (id, name, builtin, enabled, gpu_verified, gpu_probe, "
                "last_heartbeat_at, version, created_at, removed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, name or rid, builtin, enabled, gpu, json.dumps(probe) if probe is not None else "",
                 hb, version, NOW, removed))


def _set_builtin(con, *, probe=None, gpu=0, enabled=1, hb=""):
    con.execute("UPDATE renderers SET gpu_probe = ?, gpu_verified = ?, enabled = ?, last_heartbeat_at = ?, "
                "version = ? WHERE id = 'builtin'",
                (json.dumps(probe) if probe is not None else "", gpu, enabled, hb, V))


FAILED = {"configured": True, "ok": False, "error": "WebGL fell back to SwiftShader", "gpu": {"name": "GTX 1650"}}
NONE = {"configured": False, "ok": False, "error": ""}
OK = {"configured": True, "ok": True, "error": "", "gpu": {"name": "GTX 1650"}}


def test_a_fresh_install_is_unknown_until_the_builtin_probes(con):
    assert R.gpu_status(con)["status"] == "unknown"


@pytest.mark.parametrize("probe, gpu, status", [
    (OK, 1, "working"), (FAILED, 0, "not_usable"), (NONE, 0, "not_configured"),
])
def test_gpu_status_from_the_builtin_probe(con, probe, gpu, status):
    _set_builtin(con, probe=probe, gpu=gpu)
    assert R.gpu_status(con)["status"] == status


def test_any_gpu_capable_renderer_makes_it_working_even_offline(con):
    _set_builtin(con, probe=NONE)
    _add(con, "r_1", probe=OK, gpu=1, hb="")
    assert R.gpu_status(con)["status"] == "working"


def test_unknown_outranks_not_usable(con):
    # One renderer has not probed yet: its GPU may yet work, so the gates must
    # say "test it", not "you need a GPU".
    _set_builtin(con, probe=FAILED)
    _add(con, "r_1")
    assert R.gpu_status(con)["status"] == "unknown"


def test_disabled_and_removed_renderers_do_not_count(con):
    _set_builtin(con, probe=NONE)
    _add(con, "r_off", enabled=0, gpu=1, probe=OK)
    _add(con, "r_gone", gpu=1, probe=OK, removed=NOW)
    _add(con, "r_new", enabled=0)                      # disabled and unprobed: not "unknown"
    status = R.gpu_status(con)
    assert status["status"] == "not_configured"
    assert [s["id"] for s in status["renderers"]] == ["builtin", "r_new", "r_off"]
    assert R.gpu_capable_exists(con) is False


def test_a_malformed_probe_reads_as_no_probe(con):
    con.execute("UPDATE renderers SET gpu_probe = 'not json' WHERE id = 'builtin'")
    assert R.gpu_status(con)["status"] == "unknown"


def test_the_status_summary_names_each_renderer_and_its_probe(con):
    _set_builtin(con, probe=FAILED)
    s = R.gpu_status(con)["renderers"][0]
    assert s == {"id": "builtin", "name": "Built-in renderer", "builtin": True, "enabled": True,
                 "gpu_verified": False, "configured": True, "ok": False, "gpu": "GTX 1650",
                 "error": "WebGL fell back to SwiftShader", "probe": FAILED}


def test_gpu_capable_exists(con):
    assert R.gpu_capable_exists(con) is False
    _add(con, "r_1", gpu=1, probe=OK)
    assert R.gpu_capable_exists(con) is True


def test_renderer_states(con):
    _set_builtin(con, probe=OK, gpu=1, hb=ts(-5))
    _add(con, "r_1", name="Studio", hb=ts(-500), version="2.0.0")
    states = R.renderer_states(con, NOW, V)
    assert [(s["id"], s["online"], s["needs_upgrade"], s["gpu_verified"]) for s in states] == [
        ("builtin", True, False, True), ("r_1", False, True, False)]
    assert set(states[0]) >= {"id", "name", "builtin", "enabled", "online", "state", "needs_upgrade",
                              "gpu_verified", "last_heartbeat_at", "current_video_id", "last_error",
                              "credential_expires_at"}


def test_the_unavailable_reason_names_every_renderer_and_its_state(con):
    _set_builtin(con, probe=FAILED, hb=ts(-5))
    _add(con, "r_1", name="Studio PC", probe=OK, gpu=1, hb=ts(-3600))
    _add(con, "r_2", name="Laptop", probe=NONE, hb=ts(-5), version="2.0.0")
    _add(con, "r_3", name="Spare", enabled=0)
    _add(con, "r_4", name="New box")
    _add(con, "r_5", name="Gone", removed=NOW)
    reason = R.gpu_unavailable_reason(con, NOW, V)
    assert "Built-in renderer: GPU test failed: WebGL fell back to SwiftShader" in reason
    assert f"Studio PC: offline since {ts(-3600)}, GPU working" in reason
    assert f"Laptop: needs upgrade (runs 2.0.0, main runs {V}), no GPU configured" in reason
    assert "Spare: disabled" in reason
    assert "New box: never connected, GPU not tested yet" in reason
    assert "Gone" not in reason


def test_the_unavailable_reason_with_no_renderer_at_all(con):
    con.execute("DELETE FROM renderers")
    assert "no renderer is set up" in R.gpu_unavailable_reason(con, NOW, V)


def test_ensure_builtin_recreates_a_missing_row_and_never_changes_one(con):
    con.execute("UPDATE renderers SET name = 'Mine' WHERE id = 'builtin'")
    R.ensure_builtin(con, NOW)
    assert con.execute("SELECT name FROM renderers").fetchall()[0][0] == "Mine"
    con.execute("DELETE FROM renderers")
    R.ensure_builtin(con, NOW)
    assert tuple(con.execute("SELECT id, builtin, enabled FROM renderers").fetchone()) == ("builtin", 1, 1)


def test_recent_timings_keeps_the_last_five_per_renderer_and_kind(con):
    for i in range(7):
        con.execute("INSERT INTO render_timings (renderer_id, kind, on_gpu, frames, seconds, created_at) "
                    "VALUES ('a', 'dom', 0, 10, ?, 'x')", (i,))
    con.execute("INSERT INTO render_timings (renderer_id, kind, on_gpu, frames, seconds, created_at) "
                "VALUES ('a', 'mascot', 1, 10, 99, 'x')")
    rows = R.recent_timings(con)
    assert [r["seconds"] for r in rows if r["kind"] == "dom"] == [2, 3, 4, 5, 6]
    assert [r["seconds"] for r in rows if r["kind"] == "mascot"] == [99]


# ── enrollment ────────────────────────────────────────────────────────────────

def _enroll(con, secret, machine="m1", **kw):
    args = {"name": "host-name", "host": "studio.lan", "version": V, "compute": {"cpus": 8}, "now": NOW}
    args.update(kw)
    return R.enroll(con, secret, machine, args["name"], args["host"], args["version"], args["compute"],
                    args["now"])


def test_create_enrollment_stores_only_the_hash(con):
    secret, expires = R.create_enrollment(con, "Studio", now=NOW)
    assert expires == ts(R.ENROLLMENT_SECS)
    row = con.execute("SELECT * FROM renderer_enrollments").fetchone()
    assert row["secret_hash"] == R.hash_secret(secret) and secret not in tuple(row)


def test_enroll_creates_a_renderer_with_a_hashed_thirty_day_credential(con):
    secret, _ = R.create_enrollment(con, "Studio", now=NOW)
    out = _enroll(con, secret)
    assert out["renderer_id"].startswith("r_") and len(out["renderer_id"]) == 14
    assert out["credential_expires_at"] == ts(R.CREDENTIAL_DAYS * 86400)
    row = con.execute("SELECT * FROM renderers WHERE id = ?", (out["renderer_id"],)).fetchone()
    assert row["credential_hash"] == R.hash_secret(out["credential"])
    assert out["credential"] not in tuple(str(v) for v in tuple(row))
    assert (row["name"], row["machine_id"], row["host"], row["version"], json.loads(row["compute"])) == (
        "Studio", "m1", "studio.lan", V, {"cpus": 8})
    enr = con.execute("SELECT used_at, renderer_id FROM renderer_enrollments").fetchone()
    assert tuple(enr) == (NOW, out["renderer_id"])


def test_without_an_issued_name_the_renderer_names_itself_then_its_host(con):
    secret, _ = R.create_enrollment(con, now=NOW)
    rid = _enroll(con, secret)["renderer_id"]
    assert con.execute("SELECT name FROM renderers WHERE id = ?", (rid,)).fetchone()[0] == "host-name"
    secret, _ = R.create_enrollment(con, now=NOW)
    rid = _enroll(con, secret, machine="m2", name="")["renderer_id"]
    assert con.execute("SELECT name FROM renderers WHERE id = ?", (rid,)).fetchone()[0] == "studio.lan"


def test_an_enrollment_secret_works_once(con):
    secret, _ = R.create_enrollment(con, now=NOW)
    _enroll(con, secret)
    with pytest.raises(R.EnrollmentInvalid):
        _enroll(con, secret, machine="m2")


def test_an_expired_or_unknown_secret_is_refused(con):
    secret, _ = R.create_enrollment(con, now=NOW)
    with pytest.raises(R.EnrollmentInvalid):
        _enroll(con, secret, now=ts(R.ENROLLMENT_SECS))
    with pytest.raises(R.EnrollmentInvalid):
        _enroll(con, "never-issued")
    with pytest.raises(R.EnrollmentInvalid):
        _enroll(con, "")
    # A refused attempt never consumed the real secret.
    _enroll(con, secret, now=ts(R.ENROLLMENT_SECS - 1))


def test_re_enrolling_the_same_machine_replaces_its_row(con):
    s1, _ = R.create_enrollment(con, "Studio", now=NOW)
    first = _enroll(con, s1)
    con.execute("UPDATE renderers SET last_error = 'boom', previous_credential_hash = 'x' WHERE id = ?",
                (first["renderer_id"],))
    s2, _ = R.create_enrollment(con, now=NOW)
    second = _enroll(con, s2, version="2.2.0", compute={"cpus": 16}, host="new.lan")
    assert second["renderer_id"] == first["renderer_id"]
    rows = con.execute("SELECT * FROM renderers WHERE builtin = 0").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Studio"             # kept: the second token named nothing
    assert (row["version"], json.loads(row["compute"]), row["host"]) == ("2.2.0", {"cpus": 16}, "new.lan")
    assert (row["last_error"], row["previous_credential_hash"]) == ("", "")
    assert R.authenticate(con, first["credential"], NOW) is None
    assert R.authenticate(con, second["credential"], NOW)["id"] == first["renderer_id"]


def test_a_removed_renderer_is_not_revived_by_its_machine_enrolling_again(con):
    s1, _ = R.create_enrollment(con, now=NOW)
    first = _enroll(con, s1)
    con.execute("UPDATE renderers SET removed_at = ? WHERE id = ?", (NOW, first["renderer_id"]))
    s2, _ = R.create_enrollment(con, now=NOW)
    assert _enroll(con, s2)["renderer_id"] != first["renderer_id"]


def test_an_empty_machine_id_always_adds_a_row(con):
    for _ in range(2):
        secret, _ = R.create_enrollment(con, now=NOW)
        _enroll(con, secret, machine="")
    assert con.execute("SELECT COUNT(*) FROM renderers WHERE builtin = 0").fetchone()[0] == 2


# ── authenticate ──────────────────────────────────────────────────────────────

@pytest.fixture
def enrolled(con):
    secret, _ = R.create_enrollment(con, now=NOW)
    return _enroll(con, secret)


def test_the_builtin_token_authenticates_the_builtin_row(con):
    assert R.authenticate(con, "tok", NOW, builtin_token="tok")["id"] == R.BUILTIN_ID
    assert R.authenticate(con, "tok", NOW, builtin_token="other") is None
    assert R.authenticate(con, "tok", NOW) is None


def test_the_builtin_token_never_expires_and_a_disabled_renderer_still_authenticates(con):
    con.execute("UPDATE renderers SET enabled = 0, credential_expires_at = '2000-01-01T00:00:00Z'")
    assert R.authenticate(con, "tok", NOW, builtin_token="tok")["enabled"] == 0


@pytest.mark.parametrize("token", [None, "", 42])
def test_no_token_authenticates_nothing(con, token):
    assert R.authenticate(con, token, NOW, builtin_token="") is None


def test_a_remote_credential_authenticates_until_it_expires(con, enrolled):
    assert R.authenticate(con, enrolled["credential"], NOW)["id"] == enrolled["renderer_id"]
    just_before = R.ts_add(enrolled["credential_expires_at"], -1)
    assert R.authenticate(con, enrolled["credential"], just_before)["id"] == enrolled["renderer_id"]
    with pytest.raises(R.CredentialExpired) as e:
        R.authenticate(con, enrolled["credential"], enrolled["credential_expires_at"])
    assert e.value.renderer_id == enrolled["renderer_id"]
    assert con.execute("SELECT last_error FROM renderers WHERE id = ?",
                       (enrolled["renderer_id"],)).fetchone()[0] == R.CREDENTIAL_EXPIRED_ERROR


def test_a_removed_renderer_never_authenticates(con, enrolled):
    con.execute("UPDATE renderers SET removed_at = ? WHERE id = ?", (NOW, enrolled["renderer_id"]))
    assert R.authenticate(con, enrolled["credential"], NOW) is None


def test_a_remote_credential_never_authenticates_as_builtin(con, enrolled):
    # Passing it as the builtin token too must not turn a remote row into the builtin.
    row = R.authenticate(con, enrolled["credential"], NOW, builtin_token="x")
    assert row["id"] == enrolled["renderer_id"]


def test_an_empty_previous_hash_never_matches(con, enrolled):
    con.execute("UPDATE renderers SET credential_hash = 'other' WHERE id = ?", (enrolled["renderer_id"],))
    assert R.authenticate(con, "", NOW) is None
    assert R.authenticate(con, enrolled["credential"], NOW) is None


# ── rotation ──────────────────────────────────────────────────────────────────

def test_no_rotation_before_day_fifteen(con, enrolled):
    rid = enrolled["renderer_id"]
    when = ts(R.ROTATE_AFTER_DAYS * 86400 - 1)
    assert R.maybe_rotate(con, rid, when) == (None, enrolled["credential_expires_at"])


def test_rotation_from_day_fifteen_keeps_the_old_credential_until_the_new_is_used(con, enrolled):
    rid, old = enrolled["renderer_id"], enrolled["credential"]
    when = ts(R.ROTATE_AFTER_DAYS * 86400)
    new, expires = R.maybe_rotate(con, rid, when)
    assert new and new != old and expires == R.ts_add(when, R.CREDENTIAL_DAYS * 86400)
    # Both authenticate while the rotation is pending.
    assert R.authenticate(con, old, when)["id"] == rid
    assert R.authenticate(con, new, when)["id"] == rid
    # The new one's first use retired the old one.
    assert R.authenticate(con, old, when) is None
    assert R.authenticate(con, new, when)["id"] == rid
    assert R.maybe_rotate(con, rid, when) == (None, expires)


def test_an_undelivered_rotation_is_reissued_without_dropping_the_held_credential(con, enrolled):
    rid, old = enrolled["renderer_id"], enrolled["credential"]
    when = ts(R.ROTATE_AFTER_DAYS * 86400)
    lost, _ = R.maybe_rotate(con, rid, when)          # the reply never reached the renderer
    assert R.authenticate(con, old, when)["id"] == rid
    again, _ = R.maybe_rotate(con, rid, when)         # its next heartbeat, still on `old`
    assert again and again != lost
    assert R.authenticate(con, lost, when) is None    # the undelivered one is gone
    assert R.authenticate(con, old, when)["id"] == rid  # the held one still works
    assert R.authenticate(con, again, when)["id"] == rid


def test_the_builtin_and_unknown_renderers_never_rotate(con):
    assert R.maybe_rotate(con, R.BUILTIN_ID, ts(400 * 86400)) == (None, "")
    assert R.maybe_rotate(con, "r_ghost", NOW) == (None, "")
