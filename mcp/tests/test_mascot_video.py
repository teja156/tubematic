"""Mascots on a video, from the MCP server: seeding, the per-video pick and its
refusals, the cue track in scene-config.json, the version pin, the Cartoon 3D
exclusion, and what validate_job / submit_render say about a mascot video.

Mirrors renderer/api/tests/test_mascots_api.py (the Flask copy of these rules).
"""
import json
from datetime import datetime, timezone

import pytest

import server
import text_audit
from tubematic_core import mascots as tmascots

VID = "vid_m"
CUES = [{"frame": 0, "on": True, "x": 0.5, "y": 0.45, "emotion": "happy"}]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    return tmp_path


def _gpu(status="working"):
    probe = {"working": dict(configured=True, ok=True), "not_usable": dict(configured=True, ok=False),
             "not_configured": dict(configured=False)}.get(status)
    server._set_setting("gpu_probe_result", json.dumps(probe) if probe else "")


def _mascot(mid="moss", approved=1, archived=0):
    with server._conn() as con:
        con.execute("INSERT INTO mascots (id, name, status, approved_version, archived, created_at, updated_at) "
                    "VALUES (?, 'Moss', 'READY', ?, ?, ?, ?)", (mid, approved, archived, _now(), _now()))
        for v in range(1, max(approved, 1) + 1):
            con.execute("INSERT INTO mascot_versions (mascot_id, version, code, created_at, approved_at) "
                        "VALUES (?, ?, '// c', ?, ?)", (mid, v, _now(), _now()))
    return mid


def _video(vid=VID, status="TOPIC_PROPOSED", style="motion_graphics", mascot="", mver=0, project=None):
    with server._conn() as con:
        con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, mascot_id, mascot_version, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (vid, project, "a topic", status, style, mascot, mver, _now(), _now()))
    return vid


def _project(pid="p1", default_style="", default_mascot="", seed=1):
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, is_curriculum_seed, default_visual_style, default_mascot_id, "
                    "created_at) VALUES (?, 'D', ?, ?, ?, ?)", (pid, seed, default_style, default_mascot, _now()))
    return pid


def _col(col, vid=VID):
    with server._conn() as con:
        return con.execute(f"SELECT {col} FROM videos WHERE id = ?", (vid,)).fetchone()[0]


def _create(project="p1", strategy="curriculum"):
    out = server.create_video(project, "topic", strategy, 8)
    assert "error" not in out, out
    return out


# ── seeding (create_video) ──────────────────────────────────────────────────

def test_a_project_default_seeds_every_strategy_while_the_gpu_works(db):
    _gpu()
    _mascot()
    _project(default_mascot="moss")
    for strategy in ("curriculum", "trending", "mining", "manual"):
        out = _create(strategy=strategy)
        assert out["mascot_id"] == "moss"
        assert _col("mascot_id", out["video_id"]) == "moss"
        assert _col("mascot_version", out["video_id"]) == 0


def test_the_install_default_seeds_when_the_project_inherits(db):
    _gpu()
    _mascot()
    _project()
    server._set_setting("default_mascot_id", "moss")
    assert _create()["mascot_id"] == "moss"


def test_none_on_the_project_beats_the_install_default(db):
    _gpu()
    _mascot()
    _project(default_mascot="none")
    server._set_setting("default_mascot_id", "moss")
    assert _create()["mascot_id"] == ""


@pytest.mark.parametrize("gpu", ["not_usable", "not_configured", "unknown"])
def test_no_working_gpu_seeds_nothing_and_never_refuses_the_video(db, gpu):
    _gpu(gpu if gpu != "unknown" else None)
    _mascot()
    _project(default_mascot="moss")
    assert _create()["mascot_id"] == ""


def test_an_archived_default_seeds_nothing(db):
    _gpu()
    _mascot(archived=1)
    _project(default_mascot="moss")
    assert _create()["mascot_id"] == ""


def test_a_cartoon_3d_video_is_seeded_without_a_mascot(db):
    _gpu()
    _mascot()
    _project(default_style="cartoon_3d", default_mascot="moss")
    assert _create()["mascot_id"] == ""


# ── the per-video pick (update_video) ───────────────────────────────────────

def test_a_pick_is_stored_while_the_topic_is_proposed(db):
    _gpu()
    _mascot()
    _video()
    assert server.update_video(VID, mascot_id="moss") == {"video_id": VID, "updated_fields": ["mascot_id"]}
    assert _col("mascot_id") == "moss"


def test_clearing_is_always_allowed_even_with_the_gpu_down(db):
    _mascot()
    _video(mascot="moss")
    assert "error" not in server.update_video(VID, mascot_id="")
    assert _col("mascot_id") == ""


def test_a_pick_freezes_after_the_topic_stage(db):
    _gpu()
    _mascot()
    _video(status="SCRIPT_READY")
    assert "TOPIC_PROPOSED" in server.update_video(VID, mascot_id="moss")["error"]
    assert _col("mascot_id") == ""


@pytest.mark.parametrize("kind", ["missing", "archived", "unapproved"])
def test_a_mascot_that_cannot_be_chosen_is_refused(db, kind):
    _gpu()
    if kind == "archived":
        _mascot(archived=1)
    elif kind == "unapproved":
        _mascot(approved=0)
    _video()
    assert "that can be chosen" in server.update_video(VID, mascot_id="moss")["error"]
    assert _col("mascot_id") == ""


@pytest.mark.parametrize("gpu,msg", [("not_usable", tmascots.MASCOT_NEEDS_GPU), (None, tmascots.MASCOT_GPU_UNKNOWN)])
def test_a_new_pick_needs_a_working_gpu_and_unknown_has_its_own_message(db, gpu, msg):
    _gpu(gpu)
    _mascot()
    _video()
    assert server.update_video(VID, mascot_id="moss") == {"error": msg}


def test_echoing_the_stored_mascot_is_not_refused_for_a_gpu_that_has_gone(db):
    _mascot()
    _video(mascot="moss")
    assert "error" not in server.update_video(VID, mascot_id="moss", title="x")


def test_a_new_pick_is_refused_on_a_cartoon_3d_video(db):
    _gpu()
    _mascot()
    _video(style="cartoon_3d")
    assert server.update_video(VID, mascot_id="moss") == {"error": tmascots.MASCOT_NOT_ON_CARTOON_3D}


def test_auto_cannot_settle_on_cartoon_3d_while_a_mascot_is_chosen(db):
    """Else write_scene_config refuses both scene kinds and the video is wedged."""
    _gpu()
    _mascot()
    _video(style="auto", mascot="moss", mver=1)
    assert server.update_video(VID, resolved_renderer="cartoon_3d") == {"error": tmascots.MASCOT_NOT_ON_CARTOON_3D}
    assert _col("resolved_renderer") == ""
    assert "error" not in server.update_video(VID, resolved_renderer="dom")
    _video("vid_nomascot", style="auto")
    assert "error" not in server.update_video("vid_nomascot", resolved_renderer="cartoon_3d")


def test_switching_the_style_to_cartoon_3d_clears_the_mascot_in_the_same_write(db):
    _gpu()
    _mascot()
    _video(mascot="moss")
    assert "error" not in server.update_video(VID, visual_style="cartoon_3d")
    assert (_col("visual_style"), _col("mascot_id")) == ("cartoon_3d", "")


def test_an_echoed_mascot_beside_a_cartoon_3d_switch_does_not_survive_it(db):
    _gpu()
    _mascot()
    _video(mascot="moss")
    assert "error" not in server.update_video(VID, visual_style="cartoon_3d", mascot_id="moss")
    assert _col("mascot_id") == ""
    assert server.update_video(VID, mascot_id="moss") == {"error": tmascots.MASCOT_NOT_ON_CARTOON_3D}


def test_a_mascot_id_must_be_text_and_the_video_must_exist(db):
    assert "not found" in server.update_video("nope", mascot_id="moss")["error"]


# ── approving the topic (set_video_status) ──────────────────────────────────

def test_approving_a_topic_whose_mascot_was_archived_is_refused(db):
    _mascot(archived=1)
    _video(mascot="moss")
    out = server.set_video_status(VID, "TOPIC_APPROVED")
    assert "can no longer be used" in out["error"]
    assert _col("status") == "TOPIC_PROPOSED"


def test_approving_passes_with_a_usable_mascot_or_none_or_a_cartoon_video(db):
    _mascot()
    _video("a", mascot="moss")
    _video("b")
    _mascot("gone", archived=1)
    _video("c", style="cartoon_3d", mascot="gone")
    for vid in "abc":
        assert server.set_video_status(vid, "TOPIC_APPROVED")["status"] == "TOPIC_APPROVED"


# ── get_video / get_pipeline_status ─────────────────────────────────────────

def test_get_video_names_the_mascot_and_the_version_it_will_use(db):
    _gpu()
    _mascot(approved=2)
    _video(mascot="moss")
    v = server.get_video(VID)
    assert v["mascot"] == {"id": "moss", "name": "Moss", "version": 2}       # not yet pinned: the approved one
    assert v["mascots_available"] is True
    with server._conn() as con:
        con.execute("UPDATE videos SET mascot_version = 1 WHERE id = ?", (VID,))
    assert server.get_video(VID)["mascot"]["version"] == 1                   # pinned wins


def test_get_video_has_no_mascot_by_default_and_reports_the_gpu(db):
    _video()
    v = server.get_video(VID)
    assert v["mascot"] is None and v["mascots_available"] is False
    _gpu()
    assert server.get_pipeline_status()["mascots_available"] is True


# ── upsert_project ──────────────────────────────────────────────────────────

def test_a_project_default_mascot_is_checked_only_on_change(db):
    _mascot()
    assert "error" not in server.upsert_project("d1", "D", default_mascot_id="moss")
    with server._conn() as con:
        con.execute("UPDATE mascots SET archived = 1 WHERE id = 'moss'")
    assert "error" not in server.upsert_project("d1", "D renamed", default_mascot_id="moss")
    assert "that can be chosen" in server.upsert_project("d2", "New", default_mascot_id="moss")["error"]


def test_a_project_default_can_be_none_or_blank_and_omission_keeps_it(db):
    _mascot()
    out = server.upsert_project("d1", "D", default_mascot_id="moss")
    assert out["default_mascot_id"] == "moss"
    assert server.upsert_project("d1", "D2")["default_mascot_id"] == "moss"
    assert server.upsert_project("d1", "D2", default_mascot_id="none")["default_mascot_id"] == "none"
    assert server.upsert_project("d1", "D2", default_mascot_id="")["default_mascot_id"] == ""


# ── scene-config: the cue track ─────────────────────────────────────────────

def _config(mascot=None, total=300):
    cfg = {"totalFrames": total, "fps": 30, "scenes": [
        {"type": "generated", "src": "intro", "startFrame": 0, "durationInFrames": total}], "sfx": []}
    if mascot is not None:
        cfg["mascot"] = mascot
    return cfg


def test_the_mascot_key_is_a_bare_list_of_cues_and_is_refused_without_a_mascot(db):
    _video(status="VOICE_READY")
    err = server.write_scene_config(VID, _config(CUES))["error"]
    assert "no mascot" in err


def test_valid_cues_are_written_as_they_are(db):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    assert "error" not in server.write_scene_config(VID, _config(CUES))
    written = json.loads((server.JOBS_DIR / VID / "scene-config.json").read_text())
    assert written["mascot"] == CUES


def test_bad_cues_are_refused_with_the_reasons_and_nothing_is_written(db):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    bad = [{"frame": 0, "on": True, "x": 0.5, "y": 0.45}, {"frame": 40, "talk": "hello"}]
    err = server.write_scene_config(VID, _config(bad))["error"]
    assert "talk" in err
    assert not (server.JOBS_DIR / VID / "scene-config.json").exists()


def test_cues_over_the_captions_are_refused_using_the_configs_own_subtitles(db):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    low = [{"frame": 0, "on": True, "x": 0.5, "y": 0.78}]
    assert "captions" in server.write_scene_config(VID, _config(low))["error"]
    cfg = _config(low)
    cfg["subtitles"] = {"enabled": False}
    assert "error" not in server.write_scene_config(VID, {**cfg, "mascot": [{"frame": 0, "on": True, "x": 0.5, "y": 0.6}]})


def test_a_mascot_video_may_write_a_config_without_cues_yet(db):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    assert "error" not in server.write_scene_config(VID, _config())


def test_the_mascot_version_is_pinned_on_the_first_write_and_kept_by_a_revision(db):
    _mascot(approved=1)
    _video(status="VOICE_READY", mascot="moss")
    server.write_scene_config(VID, _config(CUES))
    assert _col("mascot_version") == 1
    with server._conn() as con:
        con.execute("UPDATE mascots SET approved_version = 2 WHERE id = 'moss'")
        con.execute("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = ?", (VID,))
    server.write_scene_config(VID, _config(CUES))
    assert _col("mascot_version") == 1


def test_a_video_without_a_mascot_keeps_version_zero(db):
    _video(status="VOICE_READY")
    server.write_scene_config(VID, _config())
    assert _col("mascot_version") == 0


def _cartoon_config():
    return {"totalFrames": 300, "fps": 30, "scenes": [
        {"type": "generated", "src": f"{VID}/CartoonShort", "startFrame": 0, "durationInFrames": 300,
         "props": {"cartoon3d": {"beats": [{"start": 0, "end": 299, "shot": "wide"}]}}}],
        "sfx": []}


def test_a_cartoon_scene_is_refused_while_the_video_holds_a_mascot(db):
    _gpu()
    _mascot()
    _video(status="VOICE_READY", style="auto", mascot="moss")
    err = server.write_scene_config(VID, _cartoon_config())["error"]
    assert "mascot" in err and "Cartoon 3D" in err
    assert _col("resolved_renderer") == ""


# ── validate_job / submit_render ────────────────────────────────────────────

def _job_files(vid=VID, config=None):
    d = server.JOBS_DIR / vid
    d.mkdir(parents=True, exist_ok=True)
    (d / "audio.mp3").write_bytes(b"0" * 60_000)
    (d / "timeline.json").write_text(json.dumps({"totalFrames": 300, "fps": 30, "audioDurationSeconds": 10, "words": []}))
    (d / "scene-config.json").write_text(json.dumps(config or _config()))
    with server._conn() as con:
        con.execute("UPDATE videos SET voice_file_path='a', timeline_path='t', scene_config_path='s' WHERE id=?", (vid,))


def test_validate_job_errors_when_a_mascot_video_has_no_cues(db):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    _job_files()
    out = server.validate_job(VID)
    assert server.MASCOT_CUES_MISSING in out["errors"], out
    assert out["passed"] is False


def test_validate_job_accepts_a_mascot_video_with_cues(db, monkeypatch):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    _job_files(config={**_config(CUES), "scenes": []})
    seen = []
    monkeypatch.setattr("shutil.which", lambda *a, **k: None)      # no tsc: it is not what is tested
    monkeypatch.setattr(text_audit, "audit_text_layout", lambda *a, **k: seen.append(k) or [])
    out = server.validate_job(VID)
    assert server.MASCOT_CUES_MISSING not in out["errors"]
    assert seen and seen[0]["mascot_cues"] == CUES, out                 # the audit is told where the mascot stands


def test_validate_job_ignores_a_video_without_a_mascot(db):
    _video(status="VOICE_READY")
    _job_files()
    assert server.MASCOT_CUES_MISSING not in server.validate_job(VID)["errors"]


def test_submit_render_refuses_a_mascot_video_without_cues_and_queues_one_with(db):
    _mascot()
    _video(status="VOICE_READY", mascot="moss")
    _job_files()
    out = server.submit_render(VID)
    assert out["error"] == "mascot_cues_missing" and _col("status") == "VOICE_READY"
    _job_files(config=_config(CUES))
    assert server.submit_render(VID) == {"status": "queued", "video_id": VID}


# ── the text audit's mascot warning ─────────────────────────────────────────

def _el(x, y, w, h, text="Hello"):
    return {"index": 0, "x": x, "y": y, "width": w, "height": h, "opacity": 1, "text": text}


def test_mascot_overlaps_reports_text_under_a_box_and_ignores_clear_text():
    box = (100, 100, 660, 740)
    hits = text_audit.mascot_overlaps([_el(200, 300, 100, 40), _el(800, 900, 100, 40)], [box])
    assert len(hits) == 1 and hits[0]["element"]["x"] == 200 and hits[0]["fraction"] == 1.0


def test_mascot_overlaps_skips_unmeasurable_text_and_a_missing_box():
    faded = {**_el(200, 300, 100, 40), "opacity": 0.2}
    assert text_audit.mascot_overlaps([faded], [(0, 0, 1080, 1920)]) == []
    assert text_audit.mascot_overlaps([_el(200, 300, 100, 40)], []) == []


def test_summarise_warns_once_per_text_with_the_mascot_cues():
    out = {"passes": [{"scene": 0, "requestedFrames": [200, 250], "frames": [
        {"frame": 200, "elements": [_el(300, 800, 200, 40, "Look here")]},
        {"frame": 250, "elements": [_el(300, 800, 200, 40, "Look here")]}]}]}
    cfg = _config(CUES)
    warnings = text_audit.summarise(out, cfg, mascot_cues=CUES)
    mascot = [w for w in warnings if "mascot" in w.lower()]
    assert len(mascot) == 1 and "Look here" in mascot[0] and "scene 0" in mascot[0]
    assert not [w for w in text_audit.summarise(out, cfg) if "mascot" in w.lower()]


# ── the pin follows the mascot; focus checks ────────────────────────────────

def test_a_different_mascot_or_none_resets_the_version_pin(db):
    _gpu()
    _mascot("moss")
    _mascot("fern")
    _video(mascot="moss", mver=3)
    assert "error" not in server.update_video(VID, mascot_id="fern")
    assert (_col("mascot_id"), _col("mascot_version")) == ("fern", 0)
    with server._conn() as con:
        con.execute("UPDATE videos SET mascot_version = 2 WHERE id = ?", (VID,))
    server.update_video(VID, mascot_id="")
    assert _col("mascot_version") == 0


def test_echoing_the_same_mascot_keeps_its_pin_and_a_cartoon_switch_resets_it(db):
    _gpu()
    _mascot("moss")
    _video(mascot="moss", mver=3)
    server.update_video(VID, mascot_id="moss")
    assert _col("mascot_version") == 3
    server.update_video(VID, visual_style="cartoon_3d")
    assert (_col("mascot_id"), _col("mascot_version")) == ("", 0)


def test_a_never_approved_default_seeds_nothing(db):
    _gpu()
    _mascot(approved=0)
    _project(default_mascot="moss")
    assert _create()["mascot_id"] == ""


def test_a_failed_mascot_with_an_approved_version_is_still_pickable_and_seeds(db):
    _gpu()
    _mascot()
    with server._conn() as con:
        con.execute("UPDATE mascots SET status = 'FAILED' WHERE id = 'moss'")
    _project(default_mascot="moss")
    assert _create()["mascot_id"] == "moss"
    _video()
    assert "error" not in server.update_video(VID, mascot_id="moss")


def test_write_scene_config_docstring_lists_every_cue_value():
    """The agent learns the allowed values from the tool description, not from
    refusals: a value added to the shared module must be named there too."""
    doc = server.write_scene_config.fn.__doc__ if hasattr(server.write_scene_config, "fn") else server.write_scene_config.__doc__
    for name in (*tmascots.EMOTIONS, *tmascots.LOOKS, *tmascots.FACINGS):
        assert name in doc, name
    assert str(tmascots.MIN_REST_FRAMES) in doc
    assert str(tmascots.SCALE_MIN) in doc and str(tmascots.SCALE_MAX) in doc
