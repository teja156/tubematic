"""Mascots over HTTP: the library routes, the settings/project defaults, the
seeding of new videos, and the per-video pick (the Mascots feature).

A mascot is pickable once a version is approved and until it is archived. The
request loop is modelled in version rows: creating inserts version 1 and every
request-changes inserts a new draft version (change_request = the comment, code
''), so the highest version without approved_at is always the draft.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint
from tubematic_core import mascots as tm

NOW = "2026-01-01T00:00:00Z"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = p
    pipeline._init_db(p)
    return p


@pytest.fixture
def client(db_path):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sql(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(sql, params).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _gpu(db_path, status):
    probe = {"working": {"configured": True, "ok": True},
             "not_usable": {"configured": True, "ok": False},
             "not_configured": {"configured": False}}.get(status)
    _sql(db_path, "DELETE FROM settings WHERE key = ?", (pipeline.GPU_PROBE_RESULT_KEY,))
    if probe is not None:
        _sql(db_path, "INSERT INTO settings (key, value) VALUES (?, ?)",
             (pipeline.GPU_PROBE_RESULT_KEY, json.dumps(probe)))


def _agent(db_path, aid="claude", models=("sonnet", "opus")):
    _sql(db_path,
         "INSERT INTO agents (id, name, binary, run_path, install_scope, models, effort,"
         " is_default, weight, verified_at, created_at, updated_at)"
         " VALUES (?, ?, ?, ?, 'user', ?, 'high', 1, 1, ?, ?, ?)",
         (aid, aid.title(), f"/bin/{aid}", f"/home/u/.{aid}", json.dumps(list(models)),
          NOW, NOW, NOW))


def _mascot(db_path, mid="moss", status="READY", approved=1, archived=0, builtin=0):
    _sql(db_path,
         "INSERT INTO mascots (id, name, description, builtin, status, approved_version,"
         " archived, created_at, updated_at) VALUES (?, ?, 'd', ?, ?, ?, ?, ?, ?)",
         (mid, mid.title(), builtin, status, approved, archived, NOW, NOW))
    for v in range(1, approved + 1):
        _sql(db_path, "INSERT INTO mascot_versions (mascot_id, version, code, created_at,"
             " approved_at) VALUES (?, ?, 'code', ?, ?)", (mid, v, NOW, NOW))


def _draft(db_path, mid, version, code="draw()", status=None):
    _sql(db_path, "INSERT INTO mascot_versions (mascot_id, version, code, change_request,"
         " created_at) VALUES (?, ?, ?, 'fix', ?)", (mid, version, code, NOW))
    if status:
        _sql(db_path, "UPDATE mascots SET status = ? WHERE id = ?", (status, mid))


def _sheets(db_path, mid, version):
    base = os.path.dirname(db_path)
    for s in tm.SHEETS:
        p = tm.sheet_file(base, mid, version, s)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG-" + s.encode())


def _video(client, **extra):
    body = {"project_id": "p1", "topic": "t", "strategy": "curriculum", "producibility_score": 8}
    body.update(extra)
    return client.post("/videos", json=body)


def _project(client, **extra):
    body = {"id": "p1", "name": "P1"}
    body.update(extra)
    return client.post("/projects", json=body)


def _mascot_of(db_path, vid):
    return _sql(db_path, "SELECT mascot_id FROM videos WHERE id = ?", (vid,))[0][0]


# ---------- the library: list, get, pending ----------

def test_list_has_the_builtin_pickable_and_hides_archived(client, db_path):
    _mascot(db_path, "gone", archived=1)
    items = client.get("/mascots").get_json()
    assert [m["id"] for m in items] == ["tubi"]
    tubi = items[0]
    assert tubi["builtin"] and tubi["pickable"] and tubi["approved_version"] == 1
    assert tubi["draft_version"] is None
    assert tubi["sheets"]["draft"] is None
    assert client.get("/mascots/gone").status_code == 200   # by id, archived included


def test_a_mascot_without_an_approved_version_is_not_pickable(client, db_path):
    _mascot(db_path, "wip", status="PENDING", approved=0)
    item = {m["id"]: m for m in client.get("/mascots").get_json()}["wip"]
    assert item["pickable"] is False


def test_sheet_urls_list_only_files_that_exist(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, status="IN_REVIEW")
    _sheets(db_path, "moss", 2)
    item = {m["id"]: m for m in client.get("/mascots").get_json()}["moss"]
    assert item["approved_version"] == 1 and item["draft_version"] == 2
    assert item["sheets"]["approved"] is None           # v1 has no files
    assert item["sheets"]["draft"] == {
        s: f"/mascots/moss/versions/2/sheets/{s}" for s in tm.SHEETS}


def test_get_by_id_lists_versions_without_code(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, code="secret()", status="IN_REVIEW")
    body = client.get("/mascots/moss").get_json()
    assert [(v["version"], v["has_code"]) for v in body["versions"]] == [(1, True), (2, True)]
    assert "secret()" not in json.dumps(body)
    assert all("code" not in v for v in body["versions"])
    assert client.get("/mascots/nope").status_code == 404


def test_pending_is_pending_and_building_only(client, db_path):
    _mascot(db_path, "a", status="PENDING", approved=0)
    _mascot(db_path, "b", status="BUILDING", approved=0)
    _mascot(db_path, "c", status="IN_REVIEW", approved=0)
    _mascot(db_path, "d", status="PENDING", approved=0, archived=1)
    ids = sorted(m["id"] for m in client.get("/mascots/pending").get_json())
    assert ids == ["a", "b"]


def test_pipeline_status_counts_pending_mascots(client, db_path):
    _mascot(db_path, "a", status="PENDING", approved=0)
    _mascot(db_path, "b", status="BUILDING", approved=0)
    _mascot(db_path, "c", status="READY")
    assert client.get("/pipeline/status").get_json()["pending_mascots"] == 2


# ---------- creating ----------

def test_create_inserts_version_one_with_the_description_as_its_request(client, db_path):
    r = client.post("/mascots", json={"name": "Moss", "description": "a tardigrade"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["id"] == "moss" and body["status"] == "PENDING" and body["builtin"] is False
    assert body["approved_version"] == 0 and body["pickable"] is False
    rows = _sql(db_path, "SELECT version, change_request, code FROM mascot_versions"
                " WHERE mascot_id = 'moss'")
    assert rows == [(1, "a tardigrade", "")]


def test_create_slugs_the_id_and_deduplicates(client):
    ids = [client.post("/mascots", json={"name": "Moss!", "description": "x"}).get_json()["id"]
           for _ in range(3)]
    assert ids == ["moss", "moss-2", "moss-3"]


def test_create_requires_a_name_unless_surprise(client):
    assert client.post("/mascots", json={"description": "x"}).status_code == 400
    assert client.post("/mascots", json={"name": "  ", "description": "x"}).status_code == 400
    assert client.post("/mascots", json={"name": "N" * 61, "description": "x"}).status_code == 400
    r = client.post("/mascots", json={"surprise": True, "description": ""})
    assert r.status_code == 201 and r.get_json()["name"] == "Surprise mascot"


def test_create_needs_a_description_unless_surprise(client):
    assert client.post("/mascots", json={"name": "A", "description": ""}).status_code == 400
    assert client.post("/mascots", json={"name": "A", "description": "x" * 2001}).status_code == 400
    assert client.post("/mascots", json={"name": "A", "description": 5}).status_code == 400
    assert client.post("/mascots", json={"name": "A", "description": "x", "surprise": "y"}
                       ).status_code == 400


def test_create_validates_the_agent_picks(client, db_path):
    _agent(db_path)
    ok = client.post("/mascots", json={"name": "A", "description": "x", "agent_id": "claude",
                                       "agent_model": "opus", "agent_effort": "high"})
    assert ok.status_code == 201
    got = ok.get_json()
    assert (got["agent_id"], got["agent_model"], got["agent_effort"]) == ("claude", "opus", "high")
    for bad in ({"agent_id": "ghost"}, {"agent_id": "claude", "agent_model": "gpt"},
                {"agent_effort": "extreme"}, {"agent_id": 3}):
        r = client.post("/mascots", json={"name": "B", "description": "x", **bad})
        assert r.status_code == 400, bad
    assert len(client.get("/mascots").get_json()) == 2   # tubi + the one good create


def test_create_based_on_must_be_a_pickable_mascot(client, db_path):
    _mascot(db_path, "wip", status="PENDING", approved=0)
    ok = client.post("/mascots", json={"name": "Tubi Two", "description": "bluer",
                                       "based_on": "tubi"})
    assert ok.status_code == 201 and ok.get_json()["based_on"] == "tubi"
    for bad in ("wip", "ghost", 7):
        r = client.post("/mascots", json={"name": "X", "description": "y", "based_on": bad})
        assert r.status_code == 400, bad


# ---------- approve ----------

def test_approve_publishes_the_draft_and_makes_it_ready(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, status="IN_REVIEW")
    _sheets(db_path, "moss", 2)
    _sql(db_path, "UPDATE mascots SET error = 'old' WHERE id = 'moss'")
    r = client.post("/mascots/moss/approve")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "READY" and body["approved_version"] == 2 and body["error"] == ""
    assert body["draft_version"] is None
    assert _sql(db_path, "SELECT approved_at FROM mascot_versions WHERE mascot_id='moss'"
                " AND version=2")[0][0] != ""


def test_approve_is_refused_outside_in_review(client, db_path):
    _mascot(db_path, "moss")
    assert client.post("/mascots/moss/approve").status_code == 409
    assert client.post("/mascots/ghost/approve").status_code == 404


def test_approve_needs_code_and_all_three_sheets(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, code="", status="IN_REVIEW")
    _sheets(db_path, "moss", 2)
    assert client.post("/mascots/moss/approve").status_code == 409        # no code
    _sql(db_path, "UPDATE mascot_versions SET code = 'x' WHERE mascot_id='moss' AND version=2")
    tm.sheet_file(os.path.dirname(db_path), "moss", 2, "feels").unlink()
    r = client.post("/mascots/moss/approve")
    assert r.status_code == 409 and "feels" in r.get_json()["error"]
    assert _sql(db_path, "SELECT status, approved_version FROM mascots WHERE id='moss'"
                )[0] == ("IN_REVIEW", 1)


# ---------- request changes ----------

def test_request_changes_inserts_a_new_draft_version_and_requeues(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, status="IN_REVIEW")
    _sql(db_path, "UPDATE mascots SET attempt_count = 2, sheet_renders = 4, error = 'e'"
         " WHERE id = 'moss'")
    r = client.post("/mascots/moss/request-changes", json={"comment": "bigger eyes"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "PENDING" and body["attempt_count"] == 0 and body["error"] == ""
    assert body["draft_version"] == 3 and body["approved_version"] == 1   # v1 stays in use
    assert _sql(db_path, "SELECT sheet_renders FROM mascots WHERE id='moss'")[0][0] == 0
    assert _sql(db_path, "SELECT change_request, code, approved_at FROM mascot_versions"
                " WHERE mascot_id='moss' AND version=3")[0] == ("bigger eyes", "", "")


@pytest.mark.parametrize("status", ["IN_REVIEW", "READY", "FAILED"])
def test_request_changes_is_allowed_in_these_statuses(client, db_path, status):
    _mascot(db_path, "moss", status=status)
    assert client.post("/mascots/moss/request-changes", json={"comment": "x"}).status_code == 200


@pytest.mark.parametrize("status", ["PENDING", "BUILDING"])
def test_request_changes_is_refused_while_an_agent_holds_it(client, db_path, status):
    _mascot(db_path, "moss", status=status)
    assert client.post("/mascots/moss/request-changes", json={"comment": "x"}).status_code == 409


def test_request_changes_needs_a_comment_and_refuses_a_builtin(client, db_path):
    _mascot(db_path, "moss")
    for body in ({}, {"comment": ""}, {"comment": "  "}, {"comment": 3}, {"comment": "x" * 2001}):
        assert client.post("/mascots/moss/request-changes", json=body).status_code == 400
    r = client.post("/mascots/tubi/request-changes", json={"comment": "x"})
    assert r.status_code == 400 and "variation" in r.get_json()["error"]
    assert client.post("/mascots/ghost/request-changes", json={"comment": "x"}).status_code == 404


# ---------- record-attempt ----------

def test_record_attempt_builds_and_resets_the_sheet_render_count(client, db_path):
    _mascot(db_path, "wip", status="PENDING", approved=0)
    _sql(db_path, "UPDATE mascots SET sheet_renders = 5 WHERE id = 'wip'")
    r = client.post("/mascots/wip/record-attempt")
    assert r.status_code == 200
    assert r.get_json()["status"] == "BUILDING" and r.get_json()["attempt_count"] == 1
    assert _sql(db_path, "SELECT sheet_renders FROM mascots WHERE id='wip'")[0][0] == 0
    # a crashed session leaves BUILDING, which is retried
    assert client.post("/mascots/wip/record-attempt").get_json()["attempt_count"] == 2


def test_record_attempt_over_the_cap_fails_but_keeps_the_approved_version(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, status="BUILDING")
    _sql(db_path, "UPDATE mascots SET attempt_count = ? WHERE id = 'moss'",
         (tm.MAX_MASCOT_ATTEMPTS,))
    body = client.post("/mascots/moss/record-attempt").get_json()
    assert body["status"] == "FAILED"
    assert "Version 1" in body["error"] and "still in use" in body["error"]
    assert "request changes again" in body["error"]
    row = _sql(db_path, "SELECT status, approved_version, attempt_count FROM mascots"
               " WHERE id='moss'")[0]
    assert row == ("FAILED", 1, tm.MAX_MASCOT_ATTEMPTS)
    # still pickable: a failed revision does not take the working version away
    item = {m["id"]: m for m in client.get("/mascots").get_json()}["moss"]
    assert item["pickable"] is True


def test_a_failed_first_build_names_no_version_in_use(client, db_path):
    _mascot(db_path, "wip", status="BUILDING", approved=0)
    _sql(db_path, "UPDATE mascots SET attempt_count = ? WHERE id = 'wip'",
         (tm.MAX_MASCOT_ATTEMPTS,))
    body = client.post("/mascots/wip/record-attempt").get_json()
    assert body["status"] == "FAILED" and "still in use" not in body["error"]


def test_record_attempt_is_refused_unless_pending_or_building(client, db_path):
    _mascot(db_path, "moss", status="READY")
    assert client.post("/mascots/moss/record-attempt").status_code == 409
    assert client.post("/mascots/ghost/record-attempt").status_code == 404


# ---------- archive ----------

def test_delete_archives_even_a_builtin(client, db_path):
    assert client.delete("/mascots/tubi").status_code == 200
    assert [m["id"] for m in client.get("/mascots").get_json()] == []
    assert client.get("/mascots/tubi").get_json()["archived"] is True
    assert client.delete("/mascots/ghost").status_code == 404


# ---------- sheet files ----------

def test_sheet_route_serves_a_png_and_404s_the_rest(client, db_path):
    _mascot(db_path, "moss")
    _sheets(db_path, "moss", 1)
    r = client.get("/mascots/moss/versions/1/sheets/turn")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data == b"\x89PNG-turn"
    assert client.get("/mascots/moss/versions/2/sheets/turn").status_code == 404
    assert client.get("/mascots/moss/versions/1/sheets/other").status_code == 404
    assert client.get("/mascots/ghost/versions/1/sheets/turn").status_code == 404


def test_sheet_route_refuses_a_symlink(client, db_path, tmp_path):
    _mascot(db_path, "moss")
    _sheets(db_path, "moss", 1)
    p = tm.sheet_file(os.path.dirname(db_path), "moss", 1, "turn")
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")
    p.unlink()
    p.symlink_to(outside)
    assert client.get("/mascots/moss/versions/1/sheets/turn").status_code == 404


def test_builtin_sheets_come_from_the_repo_dir_as_jpeg(client, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REMOTION_DIR", tmp_path / "remotion")
    d = tm.builtin_dir(tmp_path / "remotion", "tubi", 1)
    d.mkdir(parents=True)
    (d / "turn.jpg").write_bytes(b"jpegbytes")
    r = client.get("/mascots/tubi/versions/1/sheets/turn")
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data == b"jpegbytes"
    assert client.get("/mascots/tubi/versions/1/sheets/feels").status_code == 404
    item = client.get("/mascots").get_json()[0]
    assert item["sheets"]["approved"] == {"turn": "/mascots/tubi/versions/1/sheets/turn"}


def test_a_symlinked_builtin_sheet_is_refused(client, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REMOTION_DIR", tmp_path / "remotion")
    d = tm.builtin_dir(tmp_path / "remotion", "tubi", 1)
    d.mkdir(parents=True)
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    (d / "turn.jpg").symlink_to(outside)
    assert client.get("/mascots/tubi/versions/1/sheets/turn").status_code == 404
    assert client.get("/mascots").get_json()[0]["sheets"]["approved"] is None


# ---------- the install default ----------

def test_default_mascot_id_is_a_setting_that_must_be_pickable(client, db_path):
    assert len(pipeline.SETTINGS_SPEC) == 42
    assert client.get("/settings").get_json()["default_mascot_id"] == ""
    _mascot(db_path, "wip", status="PENDING", approved=0)
    for bad in ("wip", "ghost", "none"):
        r = client.post("/settings", json={"default_mascot_id": bad})
        assert r.status_code == 400, bad
    assert client.post("/settings", json={"default_mascot_id": "tubi"}).status_code == 200
    assert client.get("/settings").get_json()["default_mascot_id"] == "tubi"
    assert client.post("/settings", json={"default_mascot_id": ""}).status_code == 200


def test_a_stored_default_that_stopped_being_pickable_reads_as_none(client, db_path):
    client.post("/settings", json={"default_mascot_id": "tubi"})
    client.delete("/mascots/tubi")
    assert client.get("/settings").get_json()["default_mascot_id"] == ""
    # and an unrelated save is not blocked by it
    assert client.post("/settings", json={"pipeline_paused": False}).status_code == 200


# ---------- the project default ----------

def test_project_default_is_stored_returned_and_resets_when_omitted(client):
    assert _project(client, default_mascot_id="tubi").get_json()["default_mascot_id"] == "tubi"
    assert _project(client, default_mascot_id="none").get_json()["default_mascot_id"] == "none"
    assert _project(client).get_json()["default_mascot_id"] == ""      # full replace


def test_project_default_must_be_pickable_on_change_only(client, db_path):
    _mascot(db_path, "wip", status="PENDING", approved=0)
    for bad in ("wip", "ghost", 4):
        assert _project(client, default_mascot_id=bad).status_code == 400, bad
    _project(client, default_mascot_id="tubi")
    client.delete("/mascots/tubi")                                      # now unpickable
    assert _project(client, default_mascot_id="tubi", name="Renamed").status_code == 201


# ---------- seeding new videos ----------

def test_a_new_video_is_seeded_from_the_project_default_when_the_gpu_works(client, db_path):
    _gpu(db_path, "working")
    _project(client, default_mascot_id="tubi")
    vid = _video(client).get_json()["id"]
    assert _mascot_of(db_path, vid) == "tubi"


def test_seeding_covers_every_strategy_and_inherits_the_install_default(client, db_path):
    _gpu(db_path, "working")
    client.post("/settings", json={"default_mascot_id": "tubi"})
    _project(client)                                                    # '' inherits
    assert _mascot_of(db_path, _video(client, strategy="trending").get_json()["id"]) == "tubi"
    _project(client, default_mascot_id="none")                          # opts out
    assert _mascot_of(db_path, _video(client, strategy="mining").get_json()["id"]) == ""


def test_no_seed_without_a_working_gpu(client, db_path):
    _project(client, default_mascot_id="tubi")
    for status in ("unknown", "not_usable", "not_configured"):
        _gpu(db_path, status)
        assert _mascot_of(db_path, _video(client).get_json()["id"]) == "", status


def test_no_seed_on_a_cartoon_3d_video(client, db_path):
    _gpu(db_path, "working")
    _project(client, default_mascot_id="tubi")
    vid = _video(client, visual_style="cartoon_3d").get_json()["id"]
    assert _mascot_of(db_path, vid) == ""
    _project(client, default_mascot_id="tubi", default_visual_style="cartoon_3d")
    assert _mascot_of(db_path, _video(client).get_json()["id"]) == ""


def test_an_archived_default_seeds_nothing(client, db_path):
    _gpu(db_path, "working")
    _project(client, default_mascot_id="tubi")
    client.delete("/mascots/tubi")
    assert _mascot_of(db_path, _video(client).get_json()["id"]) == ""


def test_a_manual_video_is_seeded_from_the_manual_domain_default(client, db_path):
    _gpu(db_path, "working")
    client.post("/projects", json={"id": "manual", "name": "Manual Videos",
                                   "default_mascot_id": "tubi"})
    r = client.post("/videos/manual", json={"title": "T", "topic": "A topic"})
    assert r.status_code == 201
    assert _mascot_of(db_path, r.get_json()["id"]) == "tubi"
    r = client.post("/videos/manual", json={"title": "T", "topic": "A topic",
                                            "visual_style": "cartoon_3d"})
    assert _mascot_of(db_path, r.get_json()["id"]) == ""


def test_the_video_response_carries_the_mascot(client, db_path):
    _gpu(db_path, "working")
    _project(client, default_mascot_id="tubi")
    body = _video(client).get_json()
    assert body["mascot_id"] == "tubi" and body["mascot_version"] == 0


# ---------- the per-video pick ----------

def _proposed(client):
    _project(client)
    return _video(client).get_json()["id"]


def test_patch_sets_a_pickable_mascot_while_the_gpu_works(client, db_path):
    _gpu(db_path, "working")
    vid = _proposed(client)
    r = client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    assert r.status_code == 200 and r.get_json()["mascot_id"] == "tubi"
    assert client.patch(f"/videos/{vid}", json={"mascot_id": ""}).get_json()["mascot_id"] == ""


def test_patch_refuses_an_unpickable_mascot(client, db_path):
    _gpu(db_path, "working")
    _mascot(db_path, "wip", status="PENDING", approved=0)
    vid = _proposed(client)
    for bad in ("wip", "ghost", 5):
        assert client.patch(f"/videos/{vid}", json={"mascot_id": bad}).status_code == 400, bad


def test_patch_refuses_a_mascot_without_a_working_gpu_with_the_right_message(client, db_path):
    vid = _proposed(client)
    for status, msg in (("unknown", tm.MASCOT_GPU_UNKNOWN), ("not_usable", tm.MASCOT_NEEDS_GPU),
                        ("not_configured", tm.MASCOT_NEEDS_GPU)):
        _gpu(db_path, status)
        r = client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
        assert r.status_code == 400 and r.get_json()["error"] == msg, status
    # clearing is always allowed
    assert client.patch(f"/videos/{vid}", json={"mascot_id": ""}).status_code == 200


def test_patch_gpu_refusal_is_on_change_only(client, db_path):
    _gpu(db_path, "working")
    vid = _proposed(client)
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    _gpu(db_path, "not_usable")
    assert client.patch(f"/videos/{vid}", json={"mascot_id": "tubi", "title": "t"}
                        ).status_code == 200


def test_patch_refuses_a_mascot_on_a_cartoon_3d_video(client, db_path):
    _gpu(db_path, "working")
    _project(client)
    vid = _video(client, visual_style="cartoon_3d").get_json()["id"]
    r = client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    assert r.status_code == 400 and "Cartoon 3D" in r.get_json()["error"]
    # judged with the style the video will have after this PATCH
    vid2 = _proposed(client)
    r = client.patch(f"/videos/{vid2}", json={"mascot_id": "tubi", "visual_style": "cartoon_3d"})
    assert r.status_code == 400
    assert _mascot_of(db_path, vid2) == ""


def test_switching_to_cartoon_3d_clears_the_mascot_in_the_same_update(client, db_path):
    _gpu(db_path, "working")
    vid = _proposed(client)
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    r = client.patch(f"/videos/{vid}", json={"visual_style": "cartoon_3d"})
    assert r.status_code == 200 and r.get_json()["mascot_id"] == ""
    assert _mascot_of(db_path, vid) == ""


def test_the_version_pin_follows_the_mascot_it_was_taken_for(client, db_path):
    _gpu(db_path, "working")
    _mascot(db_path, "fern")
    vid = _proposed(client)
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    _sql(db_path, "UPDATE videos SET mascot_version = 1 WHERE id = ?", (vid,))
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi", "title": "t"})      # echo keeps it
    assert _sql(db_path, "SELECT mascot_version FROM videos WHERE id = ?", (vid,))[0][0] == 1
    assert client.patch(f"/videos/{vid}", json={"mascot_id": "fern"}).status_code == 200
    assert _sql(db_path, "SELECT mascot_version FROM videos WHERE id = ?", (vid,))[0][0] == 0
    _sql(db_path, "UPDATE videos SET mascot_version = 1 WHERE id = ?", (vid,))
    client.patch(f"/videos/{vid}", json={"mascot_id": ""})
    assert _sql(db_path, "SELECT mascot_version FROM videos WHERE id = ?", (vid,))[0][0] == 0
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    _sql(db_path, "UPDATE videos SET mascot_version = 1 WHERE id = ?", (vid,))
    client.patch(f"/videos/{vid}", json={"visual_style": "cartoon_3d"})
    assert _sql(db_path, "SELECT mascot_id, mascot_version FROM videos WHERE id = ?", (vid,))[0] == ("", 0)


def test_mascot_id_freezes_after_topic_proposed(client, db_path):
    _gpu(db_path, "working")
    vid = _proposed(client)
    _sql(db_path, "UPDATE videos SET status = 'SCRIPT_READY' WHERE id = ?", (vid,))
    r = client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    assert r.status_code == 409 and "mascot_id" in r.get_json()["error"]


def test_approving_with_an_archived_mascot_is_refused(client, db_path):
    _gpu(db_path, "working")
    vid = _proposed(client)
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    client.delete("/mascots/tubi")
    r = client.patch(f"/videos/{vid}", json={"status": "TOPIC_APPROVED"})
    assert r.status_code == 409 and "tubi" in r.get_json()["error"]
    assert _sql(db_path, "SELECT status FROM videos WHERE id = ?", (vid,))[0][0] == "TOPIC_PROPOSED"
    # the approving PATCH may also replace it, or clear it
    r = client.patch(f"/videos/{vid}", json={"status": "TOPIC_APPROVED", "mascot_id": ""})
    assert r.status_code == 200


def test_approving_with_a_seeded_then_archived_mascot_checks_the_stored_value(client, db_path):
    _gpu(db_path, "working")
    _project(client, default_mascot_id="tubi")
    vid = _video(client).get_json()["id"]
    client.delete("/mascots/tubi")
    assert client.patch(f"/videos/{vid}", json={"status": "TOPIC_APPROVED"}).status_code == 409


# ---------- usage ----------

def test_agent_mascot_is_a_usage_operation():
    from tubematic_core import usage
    assert "agent_mascot" in usage.AGENT_OPERATIONS


def test_switching_to_cartoon_3d_clears_an_echoed_mascot_too(client, db_path):
    """The dashboard's approve PATCH re-sends the stored mascot."""
    _gpu(db_path, "working")
    vid = _proposed(client)
    client.patch(f"/videos/{vid}", json={"mascot_id": "tubi"})
    r = client.patch(f"/videos/{vid}", json={"visual_style": "cartoon_3d", "mascot_id": "tubi"})
    assert r.status_code == 200 and r.get_json()["mascot_id"] == ""
    assert _mascot_of(db_path, vid) == ""
    # and a cartoon_3d video holding nothing can still be approved
    assert client.patch(f"/videos/{vid}", json={"status": "TOPIC_APPROVED"}).status_code == 200


def test_approve_loses_to_a_request_changes_that_landed_first(client, db_path, monkeypatch):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, status="IN_REVIEW")
    _sheets(db_path, "moss", 2)
    real = pipeline.tmascots.sheet_file

    def racing(*a, **k):
        # a request-changes commits between approve's reads and its writes
        _sql(db_path, "UPDATE mascots SET status = 'PENDING' WHERE id = 'moss'")
        return real(*a, **k)

    monkeypatch.setattr(pipeline.tmascots, "sheet_file", racing)
    assert client.post("/mascots/moss/approve").status_code == 409
    assert _sql(db_path, "SELECT status, approved_version FROM mascots WHERE id='moss'"
                )[0] == ("PENDING", 1)
    assert _sql(db_path, "SELECT approved_at FROM mascot_versions WHERE mascot_id='moss'"
                " AND version=2")[0][0] == ""


@pytest.mark.parametrize("name", ["pending", "None", "!!!"])
def test_a_generated_id_never_shadows_a_route_or_the_none_sentinel(client, name):
    mid = client.post("/mascots", json={"name": name, "description": "x"}).get_json()["id"]
    assert mid not in ("pending", "none")
    assert client.get(f"/mascots/{mid}").get_json()["id"] == mid


def test_an_abandoned_draft_is_not_reported_after_a_later_version_is_approved(client, db_path):
    _mascot(db_path, "moss")
    _draft(db_path, "moss", 2, code="old()")                  # abandoned
    _sheets(db_path, "moss", 2)
    _draft(db_path, "moss", 3, status="IN_REVIEW")
    _sheets(db_path, "moss", 3)
    assert client.post("/mascots/moss/approve").status_code == 200
    item = {m["id"]: m for m in client.get("/mascots").get_json()}["moss"]
    assert item["approved_version"] == 3
    assert item["draft_version"] is None and item["sheets"]["draft"] is None
