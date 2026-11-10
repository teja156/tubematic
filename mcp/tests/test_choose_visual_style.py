"""Auto picks a style before the script (TMDEV-203): choose_visual_style,
get_video's style_routing, and the two rules that give a pick back.

What matters most here:

  * choose_visual_style is the one way a style changes after the topic
    checkpoint, so every condition it checks (TOPIC_APPROVED, still "auto",
    not decided, not archived, no mascot on a 3D world) must also hold in the
    UPDATE itself, or a write racing it lands on a video that moved on.
  * A pick of a pack is written INTO visual_style, so every existing reader
    (the gates, the review prompt, the authoring skill) sees it unchanged.
  * A topic revision gives an Auto pick back to Auto; a person's choice is
    never touched.

Run from repo root: pytest mcp/tests/
"""
from datetime import datetime, timezone

import pytest

import server
from builtin_gpu import store_builtin_probe
from tubematic_core import visual_styles as tvs


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    return tmp_path / "test.db"


def _gpu(ok=True):
    store_builtin_probe({"configured": True, "ok": ok})


def _video(vid="vid_1", status="TOPIC_APPROVED", style="auto", mascot="", project=None):
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, visual_style, mascot_id, "
            "created_at, updated_at) VALUES (?, ?, 'a topic', ?, ?, ?, ?, ?)",
            (vid, project, status, style, mascot, _now(), _now()))
    return vid


def _mascot(mid="moss"):
    with server._conn() as con:
        con.execute("INSERT INTO mascots (id, name, status, approved_version, archived, created_at, "
                    "updated_at) VALUES (?, 'Moss', 'READY', 1, 0, ?, ?)", (mid, _now(), _now()))
        con.execute("INSERT INTO mascot_versions (mascot_id, version, code, created_at, approved_at) "
                    "VALUES (?, 1, '// c', ?, ?)", (mid, _now(), _now()))
    return mid


def _row(vid="vid_1"):
    with server._conn() as con:
        return dict(con.execute(
            "SELECT status, visual_style, style_pick, style_runner_up, style_reason "
            "FROM videos WHERE id = ?", (vid,)).fetchone())


# ── choose_visual_style ──────────────────────────────────────────────────────

def test_a_pack_pick_becomes_the_videos_visual_style(db):
    _video()
    out = server.choose_visual_style("vid_1", "system_flow", "A packet's path through a network.",
                                     runner_up="stick")
    assert out["visual_style"] == "system_flow"
    assert out["style"]["authoring_skill"] == "tubematic-system-flow"
    assert out["style"]["script"]  # the style's own script guidance reaches the script writer
    assert _row() == {"status": "TOPIC_APPROVED", "visual_style": "system_flow",
                      "style_pick": "system_flow", "style_runner_up": "stick",
                      "style_reason": "A packet's path through a network."}
    # Every existing reader now sees the picked style.
    assert server.get_video("vid_1")["style"]["id"] == "system_flow"


def test_scenes_keeps_auto_and_records_the_decision(db):
    _video()
    out = server.choose_visual_style("vid_1", "scenes", "No one style carries these beats.")
    assert out["visual_style"] == "auto"
    assert out["style"]["authoring_skill"] == "tubematic-scene-config"
    row = _row()
    assert (row["visual_style"], row["style_pick"]) == ("auto", "scenes")
    assert server.get_video("vid_1")["style_routing"]["decided"] is True


def test_the_choice_is_made_once(db):
    _video()
    assert "error" not in server.choose_visual_style("vid_1", "stick", "A mechanism.")
    err = server.choose_visual_style("vid_1", "motion_graphics", "Changed my mind.")
    assert "made once" in err["error"]
    assert _row()["visual_style"] == "stick"


def test_a_person_chosen_style_is_never_overridden(db):
    _video(style="stick")
    err = server.choose_visual_style("vid_1", "system_flow", "Fits better.")
    assert "chosen by a person" in err["error"]
    assert _row()["visual_style"] == "stick"


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "SCRIPT_READY", "VOICE_READY",
                                    "REVISION_REQUESTED"])
def test_only_at_topic_approved(db, status):
    _video(status=status)
    err = server.choose_visual_style("vid_1", "stick", "A mechanism.")
    assert "TOPIC_APPROVED" in err["error"]
    assert _row()["style_pick"] == ""


def test_an_archived_video_is_refused(db):
    _video()
    with server._conn() as con:
        con.execute("UPDATE videos SET archived_at = ? WHERE id = 'vid_1'", (_now(),))
    assert server.choose_visual_style("vid_1", "stick", "A mechanism.")["error"] == "video_archived"


@pytest.mark.parametrize("args, fragment", [
    (("nonsense", "r"), "Invalid style"),
    (("auto", "r"), "Invalid style"),
    (("stick", "r", "nonsense"), "Invalid runner_up"),
    (("stick", "r", "stick"), "different style"),
    (("stick", "   "), "reason is required"),
    (("stick", "x" * 301), "limit is 300"),
])
def test_bad_arguments_are_refused(db, args, fragment):
    _video()
    assert fragment in server.choose_visual_style("vid_1", *args)["error"]
    assert _row()["style_pick"] == ""


def test_an_unavailable_style_or_runner_up_is_refused_with_the_reason(db):
    _video()
    err = server.choose_visual_style("vid_1", "illustrated", "Recurring characters.")
    assert "needs an OpenAI key" in err["error"]
    err = server.choose_visual_style("vid_1", "stick", "Roles.", runner_up="illustrated")
    assert "runner_up" in err["error"] and "needs an OpenAI key" in err["error"]
    err = server.choose_visual_style("vid_1", "cartoon_3d", "A place.")
    assert "GPU not tested yet" in err["error"]
    server._set_setting("openai_api_key", "sk-test")
    _gpu(ok=True)
    assert "error" not in server.choose_visual_style("vid_1", "cartoon_3d", "A place.",
                                                     runner_up="illustrated")


def test_a_mascot_rules_out_a_3d_world(db):
    _gpu(ok=True)
    _video(mascot=_mascot())
    err = server.choose_visual_style("vid_1", "cartoon_3d", "A place.")
    assert tvs.MASCOT_EXCLUDES_3D in err["error"]


def test_the_update_repeats_every_check(db, monkeypatch):
    """The row is read, then the UPDATE runs: a change committed in between
    (simulated right after the read) must leave the video untouched.
    Mutation-check: dropping any clause of the UPDATE's WHERE makes one of
    these land."""
    _video()
    real_row = server._style_choice_row

    for change in ("UPDATE videos SET status = 'SCRIPT_READY'",
                   "UPDATE videos SET visual_style = 'stick'",
                   "UPDATE videos SET style_pick = 'stick'",
                   f"UPDATE videos SET archived_at = '{_now()}'"):
        with server._conn() as con:
            con.execute("UPDATE videos SET status = 'TOPIC_APPROVED', visual_style = 'auto', "
                        "style_pick = '', archived_at = NULL WHERE id = 'vid_1'")

        def racing(vid, _change=change):
            row = real_row(vid)
            with server._conn() as con:
                con.execute(_change + " WHERE id = 'vid_1'")
            return row

        monkeypatch.setattr(server, "_style_choice_row", racing)
        err = server.choose_visual_style("vid_1", "system_flow", "A path.")
        assert "changed while the call was in flight" in err["error"], change
        assert _row()["visual_style"] != "system_flow", change


def test_a_mascot_landing_mid_call_stops_a_3d_pick(db, monkeypatch):
    _gpu(ok=True)
    _video()
    mid = _mascot()
    real_row = server._style_choice_row

    def racing(vid):
        row = real_row(vid)
        with server._conn() as con:
            con.execute("UPDATE videos SET mascot_id = ? WHERE id = 'vid_1'", (mid,))
        return row

    monkeypatch.setattr(server, "_style_choice_row", racing)
    assert "error" in server.choose_visual_style("vid_1", "cartoon_3d", "A place.")
    assert _row()["visual_style"] == "auto"


def test_availability_is_read_under_the_write_lock(db, monkeypatch):
    """A key removed in Settings, or a GPU probe result, cannot commit between
    the availability check and the write: while the check runs, any other
    writer is locked out. Mutation-check: drop BEGIN IMMEDIATE and the write
    below goes through."""
    import sqlite3
    _video()
    real = tvs.routing_candidates
    seen = []

    def probing(*a, **kw):
        other = sqlite3.connect(str(server.DB_FILE), timeout=0)
        try:
            other.execute("UPDATE settings SET value = value WHERE key = 'nothing'")
            other.execute("INSERT INTO settings (key, value) VALUES ('lock_probe', 'x')")
            other.commit()
            seen.append("wrote")
        except sqlite3.OperationalError as exc:
            seen.append(str(exc))
        finally:
            other.close()
        return real(*a, **kw)

    monkeypatch.setattr(tvs, "routing_candidates", probing)
    assert "error" not in server.choose_visual_style("vid_1", "system_flow", "A path.")
    assert seen == ["database is locked"]


# ── get_video's style_routing ────────────────────────────────────────────────

def test_style_routing_lists_every_candidate_and_the_domain(db):
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, description, created_at) VALUES "
                    "('p1', 'Networking', 'How the internet works', ?)", (_now(),))
    _video(project="p1")
    sr = server.get_video("vid_1")["style_routing"]
    assert sr["decided"] is False and sr["pick"] == ""
    assert [c["id"] for c in sr["candidates"]] == list(tvs.ROUTE_CHOICES)
    assert sr["domain"] == {"name": "Networking", "description": "How the internet works"}
    by_id = {c["id"]: c for c in sr["candidates"]}
    assert by_id["illustrated"]["available"] is False


def test_a_person_chosen_style_reads_as_decided(db):
    _video(style="motion_graphics")
    sr = server.get_video("vid_1")["style_routing"]
    assert sr["decided"] is True and sr["pick"] == ""


# ── giving a pick back ───────────────────────────────────────────────────────

def test_a_topic_revision_gives_an_auto_pick_back_to_auto(db):
    _video()
    server.choose_visual_style("vid_1", "system_flow", "A path.", runner_up="stick")
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = 'vid_1'")
    assert server.set_video_status("vid_1", "TOPIC_PROPOSED")["status"] == "TOPIC_PROPOSED"
    assert _row() == {"status": "TOPIC_PROPOSED", "visual_style": "auto", "style_pick": "",
                      "style_runner_up": "", "style_reason": ""}


def test_the_guarded_status_write_resets_too(db):
    _video()
    server.choose_visual_style("vid_1", "stick", "A mechanism.")
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = 'vid_1'")
    server.set_video_status("vid_1", "TOPIC_PROPOSED", only_if_current_status="REVISION_REQUESTED")
    assert _row()["visual_style"] == "auto"


def test_a_person_chosen_style_survives_a_topic_revision(db):
    _video(status="REVISION_REQUESTED", style="stick")
    server.set_video_status("vid_1", "TOPIC_PROPOSED")
    assert _row()["visual_style"] == "stick"


def test_other_transitions_keep_the_pick(db):
    _video()
    server.choose_visual_style("vid_1", "system_flow", "A path.")
    server.set_video_status("vid_1", "SCRIPT_READY")
    assert _row()["style_pick"] == "system_flow"


def test_a_changed_style_clears_the_pick_and_the_same_one_keeps_it(db):
    _video()
    server.choose_visual_style("vid_1", "system_flow", "A path.", runner_up="stick")
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'TOPIC_PROPOSED' WHERE id = 'vid_1'")
    assert "error" not in server.update_video("vid_1", visual_style="system_flow")
    assert _row()["style_pick"] == "system_flow"
    assert "error" not in server.update_video("vid_1", visual_style="stick")
    assert _row() == {"status": "TOPIC_PROPOSED", "visual_style": "stick", "style_pick": "",
                      "style_runner_up": "", "style_reason": ""}
