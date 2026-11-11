"""A topic's angle over HTTP (TMDEV-214): the sentence saying what the opening
will use, its kind and its score, as the dashboard reads and edits them.

What is easy to get wrong here:

- A person edits the angle at Topic Proposed and nowhere else. Past that the
  script may already be written from it.
- An edited angle must lose its score in the same statement: the number the
  agent gave described other words.
- The New Video page may send an angle or none. A person's topic is never
  refused for lacking one.

Research files topics through the MCP server, which is where a missing angle
is refused. POST /videos takes the fields and checks their shape only, like
the producibility score.

Run from repo root: pytest renderer/api/tests/
"""
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline  # noqa: E402
from pipeline import create_pipeline_blueprint  # noqa: E402
from tubematic_core import angles as tangles  # noqa: E402

NOW = "2026-11-11T00:00:00Z"
SENTENCE = "Deleting the file frees no space until the last program holding it lets go."


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


def _video(db_path, vid="vid_1", status="TOPIC_PROPOSED", angle="An old angle.", kind="myth",
           score=8):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, status, angle, angle_kind, angle_score, created_at, "
        "updated_at) VALUES (?, 't', ?, ?, ?, ?, ?, ?)", (vid, status, angle, kind, score, NOW, NOW))
    con.commit()
    con.close()
    return vid


def _angle(db_path, vid="vid_1") -> tuple:
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT angle, angle_kind, angle_score FROM videos WHERE id = ?",
                      (vid,)).fetchone()
    con.close()
    return tuple(row)


def _count(db_path) -> int:
    con = sqlite3.connect(db_path)
    n = con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    con.close()
    return n


# ── GET /angle-kinds ────────────────────────────────────────────────────────

def test_the_kinds_are_served_from_the_shared_list(client):
    res = client.get("/angle-kinds")
    assert res.status_code == 200
    assert res.get_json() == tangles.public_list()


# ── reading ─────────────────────────────────────────────────────────────────

def test_a_video_carries_its_angle(client, db_path):
    _video(db_path, angle=SENTENCE, kind="paradox", score=7)
    video = client.get("/videos/vid_1").get_json()
    assert (video["angle"], video["angle_kind"], video["angle_score"]) == (SENTENCE, "paradox", 7)
    listed = client.get("/videos").get_json()[0]
    assert (listed["angle"], listed["angle_kind"], listed["angle_score"]) == (SENTENCE, "paradox", 7)


# ── PATCH /videos/<id> ──────────────────────────────────────────────────────

def test_a_person_edits_the_angle_at_topic_proposed_and_the_score_goes(client, db_path):
    _video(db_path)
    res = client.patch("/videos/vid_1", json={"angle": f" {SENTENCE}\n", "angle_kind": "paradox"})
    assert res.status_code == 200
    assert _angle(db_path) == (SENTENCE, "paradox", 0)
    assert res.get_json()["angle_score"] == 0


def test_an_angle_only_edit_does_not_move_the_video(client, db_path):
    """The worker announces a topic when its status@updated_at is new. An edit
    that bumped updated_at would announce the same topic a second time."""
    _video(db_path)
    client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox"})
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT updated_at FROM videos").fetchone()[0] == NOW
    con.close()
    client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox", "title": "T"})
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT updated_at FROM videos").fetchone()[0] != NOW
    con.close()


def test_a_kind_is_matched_whatever_its_spelling(client, db_path):
    _video(db_path)
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "Broken expectation"})
    assert res.status_code == 200
    assert _angle(db_path)[1] == "broken_expectation"


def test_saving_the_same_angle_keeps_its_score(client, db_path):
    _video(db_path, angle=SENTENCE, kind="paradox", score=8)
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox"})
    assert res.status_code == 200
    assert _angle(db_path) == (SENTENCE, "paradox", 8)


def test_a_changed_kind_alone_resets_the_score(client, db_path):
    _video(db_path, angle=SENTENCE, kind="paradox", score=8)
    client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "myth"})
    assert _angle(db_path) == (SENTENCE, "myth", 0)


@pytest.mark.parametrize("style", ["under_the_hood", "cartoon_3d"])
def test_the_angle_can_be_edited_on_a_video_whose_style_takes_no_mascot(client, db_path, style):
    """Such a style makes the route rebuild its parameter list to drop the
    mascot. The score reset's two parameters must survive that, or the edit is
    a 500 on every topic of a domain that defaults to the style."""
    _video(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET visual_style = ? WHERE id = 'vid_1'", (style,))
    con.commit()
    con.close()
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox"})
    assert res.status_code == 200
    assert _angle(db_path) == (SENTENCE, "paradox", 0)
    # The same angle again, with the approval: the score reset reads the row.
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox",
                                               "status": "TOPIC_APPROVED",
                                               "onlyIfCurrentStatus": "TOPIC_PROPOSED"})
    assert res.status_code == 200
    assert res.get_json()["status"] == "TOPIC_APPROVED"


def test_an_angle_can_be_added_to_a_topic_that_has_none(client, db_path):
    _video(db_path, angle="", kind="", score=0)
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "incident"})
    assert res.status_code == 200
    assert _angle(db_path) == (SENTENCE, "incident", 0)


def test_an_angle_can_be_removed(client, db_path):
    _video(db_path)
    res = client.patch("/videos/vid_1", json={"angle": "", "angle_kind": ""})
    assert res.status_code == 200
    assert _angle(db_path) == ("", "", 0)


@pytest.mark.parametrize("status", ["TOPIC_APPROVED", "SCRIPT_READY", "REVISION_REQUESTED",
                                    "VIDEO_READY", "PUBLISHED"])
def test_the_angle_is_closed_to_a_person_after_the_topic(client, db_path, status):
    _video(db_path, status=status)
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox"})
    assert res.status_code == 409
    assert "TOPIC_PROPOSED" in res.get_json()["error"]
    assert _angle(db_path) == ("An old angle.", "myth", 8)


@pytest.mark.parametrize("body, part", [
    ({"angle": SENTENCE}, "together"),
    ({"angle_kind": "myth"}, "together"),
    ({"angle": SENTENCE, "angle_kind": "surprise"}, "not a kind"),
    ({"angle": "x" * 301, "angle_kind": "myth"}, "300"),
    ({"angle": 7, "angle_kind": "myth"}, "must be a string"),
    ({"angle": SENTENCE, "angle_kind": None}, "must be a string"),
])
def test_patch_refuses_a_malformed_angle(client, db_path, body, part):
    _video(db_path)
    res = client.patch("/videos/vid_1", json=body)
    assert res.status_code == 400
    assert part in res.get_json()["error"]
    assert _angle(db_path) == ("An old angle.", "myth", 8)


def test_a_person_cannot_set_the_angle_score(client, db_path):
    """The score is the agent's judgement of its own angle. A PATCH carrying
    only that has nothing it may write."""
    _video(db_path)
    res = client.patch("/videos/vid_1", json={"angle_score": 10})
    assert res.status_code == 400
    assert _angle(db_path) == ("An old angle.", "myth", 8)


def test_the_angle_and_the_approval_can_travel_together(client, db_path):
    _video(db_path)
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox",
                                               "status": "TOPIC_APPROVED",
                                               "onlyIfCurrentStatus": "TOPIC_PROPOSED"})
    assert res.status_code == 200
    assert _angle(db_path) == (SENTENCE, "paradox", 0)
    assert res.get_json()["status"] == "TOPIC_APPROVED"


class _RacingConn:
    """A real connection that, right after the first statement starting with
    `trigger`, commits `side_sql` on a second connection: a writer landing
    between two statements of the request being served."""

    def __init__(self, real, trigger, db_path, side_sql):
        self.__dict__.update(_real=real, _trigger=trigger, _db_path=db_path,
                             _side_sql=side_sql, _fired=False)

    def execute(self, sql, params=()):
        cur = self._real.execute(sql, params)
        if not self._fired and sql.strip().startswith(self._trigger):
            self.__dict__["_fired"] = True
            side = sqlite3.connect(self._db_path)
            side.execute(self._side_sql)
            side.commit()
            side.close()
        return cur

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __setattr__(self, name, value):
        setattr(self._real, name, value)


def test_an_edit_that_loses_the_race_with_an_approval_writes_nothing(client, db_path, monkeypatch):
    """The status is read, then the UPDATE runs. An approval landing in
    between must leave the angle the agent is about to read untouched.
    Mutation-check: without the status in the UPDATE's WHERE the edit lands."""
    _video(db_path)
    real_connect = sqlite3.connect
    wrapped = []

    def connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        if not wrapped:
            wrapped.append(True)
            return _RacingConn(con, "SELECT status, archived_at FROM videos", db_path,
                               "UPDATE videos SET status = 'TOPIC_APPROVED' WHERE id = 'vid_1'")
        return con

    monkeypatch.setattr(sqlite3, "connect", connect)
    res = client.patch("/videos/vid_1", json={"angle": SENTENCE, "angle_kind": "paradox"})
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    assert res.status_code == 409
    assert _angle(db_path) == ("An old angle.", "myth", 8)


# ── POST /videos ────────────────────────────────────────────────────────────

def _post(client, **extra):
    return client.post("/videos", json={"topic": "A topic", "strategy": "trending",
                                        "producibility_score": 7, **extra})


def test_post_videos_stores_an_angle_it_is_sent(client, db_path):
    res = _post(client, angle=SENTENCE, angle_kind="paradox", angle_score=8)
    assert res.status_code == 201
    assert _angle(db_path, res.get_json()["id"]) == (SENTENCE, "paradox", 8)


def test_a_null_angle_score_on_post_videos_means_unscored(client, db_path):
    res = _post(client, angle=SENTENCE, angle_kind="paradox", angle_score=None)
    assert res.status_code == 201
    assert _angle(db_path, res.get_json()["id"]) == (SENTENCE, "paradox", 0)


def test_post_videos_does_not_require_an_angle(client, db_path):
    """This route seeds tests and tools, and checks no producibility floor
    either. The research rule lives in the MCP server's create_video."""
    res = _post(client)
    assert res.status_code == 201
    assert _angle(db_path, res.get_json()["id"]) == ("", "", 0)


@pytest.mark.parametrize("extra, part", [
    ({"angle": SENTENCE}, "together"),
    ({"angle": SENTENCE, "angle_kind": "surprise"}, "not a kind"),
    ({"angle": SENTENCE, "angle_kind": "myth", "angle_score": "8"}, "angle_score"),
    ({"angle": ["a"], "angle_kind": "myth"}, "must be a string"),
    ({"angle_score": 7}, "angle_score"),
])
def test_post_videos_refuses_a_malformed_angle(client, db_path, extra, part):
    res = _post(client, **extra)
    assert res.status_code == 400
    assert part in res.get_json()["error"]
    assert _count(db_path) == 0


# ── POST /videos/manual ─────────────────────────────────────────────────────

def _submit(client, **extra):
    return client.post("/videos/manual", json={"title": "A title", "topic": "A topic", **extra})


def test_a_manual_video_needs_no_angle(client, db_path):
    res = _submit(client)
    assert res.status_code == 201
    assert _angle(db_path, res.get_json()["id"]) == ("", "", 0)


@pytest.mark.parametrize("blank", [{"angle": "", "angle_kind": ""}, {"angle": None, "angle_kind": None},
                                   {"angle": "   ", "angle_kind": ""}])
def test_a_blank_angle_on_a_manual_video_is_no_angle(client, db_path, blank):
    res = _submit(client, **blank)
    assert res.status_code == 201
    assert _angle(db_path, res.get_json()["id"]) == ("", "", 0)


def test_a_manual_video_keeps_the_angle_its_author_gave(client, db_path):
    res = _submit(client, angle=SENTENCE, angle_kind="paradox")
    assert res.status_code == 201
    assert _angle(db_path, res.get_json()["id"]) == (SENTENCE, "paradox", 0)


@pytest.mark.parametrize("extra, part", [
    ({"angle": SENTENCE}, "together"),
    ({"angle": SENTENCE, "angle_kind": "surprise"}, "not a kind"),
    ({"angle": "x" * 301, "angle_kind": "myth"}, "300"),
    ({"angle": 7, "angle_kind": "myth"}, "must be a string"),
])
def test_a_manual_video_with_a_malformed_angle_writes_nothing(client, db_path, extra, part):
    res = _submit(client, **extra)
    assert res.status_code == 400
    assert part in res.get_json()["error"]
    assert _count(db_path) == 0
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
    con.close()
