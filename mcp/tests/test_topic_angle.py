"""Tests for the angle a topic carries (TMDEV-214): the sentence saying what the
opening will use, its kind and its score.

What is easy to get wrong here:

- A research proposal with no angle must be refused, and a person's own topic
  must never be. The two share one tool.
- The agent fills a missing angle when it picks a video up at TOPIC_APPROVED.
  That write must never replace an angle a person saw and approved.
- A topic filed before angles existed has none. It must still be approved and
  read like any other video.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""
import json

import pytest

import server
from sample_angle import ANGLE, mined
from tubematic_core import angles as tangles

SENTENCE = "Deleting the file frees no space until the last program holding it lets go."
RESEARCH = ("curriculum", "trending", "mining")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, created_at) "
                    "VALUES ('dom', 'Domain', '2026-01-01T00:00:00Z')")


def _file(strategy="curriculum", **kw):
    return server.create_video("dom", "How deleting a file really works", strategy, 7, **kw)


def _video(video_id="vid_1", status="TOPIC_PROPOSED", angle="", kind="", score=0):
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, angle, angle_kind, angle_score, "
            "created_at, updated_at) VALUES (?, 'dom', 'a topic', ?, ?, ?, ?, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (video_id, status, angle, kind, score))
    return video_id


def _angle(video_id="vid_1") -> tuple:
    with server._conn() as con:
        row = con.execute("SELECT angle, angle_kind, angle_score FROM videos WHERE id = ?",
                          (video_id,)).fetchone()
    return tuple(row)


def _count() -> int:
    with server._conn() as con:
        return con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]


# ── create_video ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("strategy", RESEARCH)
def test_a_research_proposal_is_stored_with_its_angle(db, strategy):
    result = _file(strategy, angle=f"  {SENTENCE}\n", angle_kind="paradox", angle_score=8)
    assert "error" not in result
    assert _angle(result["video_id"]) == (SENTENCE, "paradox", 8)
    assert (result["angle"], result["angle_kind"], result["angle_score"]) == (SENTENCE, "paradox", 8)


@pytest.mark.parametrize("strategy", RESEARCH)
def test_a_research_proposal_without_an_angle_is_refused(db, strategy):
    result = _file(strategy)
    assert "not proposed" in result["error"]
    assert "run summary" in result["error"]
    assert _count() == 0


@pytest.mark.parametrize("strategy", RESEARCH)
def test_a_research_proposal_with_a_weak_angle_is_refused(db, strategy):
    result = _file(strategy, angle=SENTENCE, angle_kind="paradox", angle_score=4)
    assert f"below {tangles.ANGLE_MIN_SCORE}" in result["error"]
    assert _count() == 0


def test_a_persons_own_topic_needs_no_angle(db):
    result = _file("manual")
    assert "error" not in result
    assert _angle(result["video_id"]) == ("", "", 0)


def test_a_persons_own_topic_keeps_an_angle_it_is_given_whatever_its_score(db):
    result = _file("manual", angle=SENTENCE, angle_kind="paradox", angle_score=3)
    assert "error" not in result
    assert _angle(result["video_id"]) == (SENTENCE, "paradox", 3)


@pytest.mark.parametrize("kw, part", [
    ({"angle": SENTENCE}, "together"),
    ({"angle_kind": "myth"}, "together"),
    ({"angle": SENTENCE, "angle_kind": "surprise"}, "not a kind"),
    ({"angle": "x" * 301, "angle_kind": "myth"}, "300"),
    ({"angle": SENTENCE, "angle_kind": "myth", "angle_score": 11}, "angle_score"),
])
def test_a_malformed_angle_is_refused_on_any_strategy(db, kw, part):
    assert part in _file("manual", **kw)["error"]
    assert _count() == 0


@pytest.mark.parametrize("kw", [
    {"angle": None, "angle_kind": None, "angle_score": None},
    {"angle": "", "angle_kind": "", "angle_score": None},
    {"angle": "", "angle_kind": "", "angle_score": 3},
])
def test_a_persons_topic_with_no_angle_is_filed_however_none_is_said(db, kw, through_mcp):
    """/tubematic-submit-new-job has a path for a topic with no angle, and a
    model sends that as nulls, empty strings or a score for the angle it did
    not find. None of them may refuse a person's topic."""
    out, _ = through_mcp("create_video", project_id="dom", topic="A person's topic",
                         strategy="manual", producibility_score=7, **kw)
    assert "error" not in out, out
    assert _angle(out["video_id"]) == ("", "", 0)


@pytest.mark.parametrize("kw", [{"angle": "none", "angle_kind": "none"},
                                {"angle": "", "angle_kind": "None."},
                                {"angle": "N/A", "angle_kind": ""}])
def test_a_persons_topic_whose_angle_is_spelled_none_is_filed_without_one(db, kw):
    result = _file("manual", **kw)
    assert "error" not in result, result
    assert _angle(result["video_id"]) == ("", "", 0)


def test_a_research_topic_cannot_pass_with_none_spelled_out(db):
    """The words mean "no angle" only for a person's own topic. For research
    they are what they look like: a missing angle, refused."""
    assert "error" in _file("trending", angle="none", angle_kind="none", angle_score=7)


def test_a_research_proposal_that_left_out_its_score_is_told_to_score_it(db):
    """0 is unscored. Read as a weak angle, the refusal would tell the agent
    to drop a subject it had an angle for."""
    result = _file("trending", angle=SENTENCE, angle_kind="paradox")
    assert "angle_score was not passed" in result["error"]
    assert "run summary" not in result["error"]
    assert "angle_score" in _file("trending")["error"]


@pytest.mark.parametrize("spelled", ["Paradox", " paradox. ", "PARADOX"])
def test_a_kind_is_matched_whatever_its_spelling_on_every_route(db, spelled):
    result = _file("trending", angle=SENTENCE, angle_kind=spelled, angle_score=7)
    assert result["angle_kind"] == "paradox"
    _video("vid_2")
    assert "error" not in server.update_video("vid_2", angle=SENTENCE, angle_kind=spelled)
    assert _angle("vid_2")[1] == "paradox"


def test_the_score_floor_is_checked_before_the_angle(db):
    """A topic the pipeline cannot draw is dropped for that reason, whatever
    its angle: the producibility refusal is the older rule and keeps its text."""
    result = server.create_video("dom", "t", "trending", 4, **ANGLE)
    assert "producibility_score" in result["error"]


# ── get_video ───────────────────────────────────────────────────────────────

def test_get_video_names_the_formula_the_kind_points_to(db):
    _video(angle=SENTENCE, kind="incident", score=7)
    video = server.get_video("vid_1")
    assert (video["angle"], video["angle_kind"], video["angle_score"]) == (SENTENCE, "incident", 7)
    assert video["angle_formula"] == "incident-file"


def test_a_video_with_no_angle_reads_as_empty(db):
    _video()
    video = server.get_video("vid_1")
    assert (video["angle"], video["angle_kind"], video["angle_score"]) == ("", "", 0)
    assert video["angle_formula"] == ""


def test_a_topic_from_before_angles_still_approves(db):
    _video()
    result = server.set_video_status("vid_1", "TOPIC_APPROVED",
                                     only_if_current_status="TOPIC_PROPOSED")
    assert "error" not in result
    assert server.get_video("vid_1")["status"] == "TOPIC_APPROVED"


# ── update_video: who may write the angle, and when ─────────────────────────

@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "REVISION_REQUESTED"])
def test_the_agent_may_rewrite_an_angle_at_the_topic_and_on_a_revision(db, status):
    _video(status=status, angle="An old angle.", kind="myth", score=6)
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox", angle_score=8)
    assert "error" not in result
    assert sorted(result["updated_fields"]) == ["angle", "angle_kind", "angle_score"]
    assert _angle() == (SENTENCE, "paradox", 8)


def test_the_agent_fills_a_missing_angle_at_pickup(db):
    _video(status="TOPIC_APPROVED")
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox", angle_score=6)
    assert "error" not in result
    assert _angle() == (SENTENCE, "paradox", 6)


def test_the_pickup_fill_never_replaces_an_angle_a_person_approved(db):
    _video(status="TOPIC_APPROVED", angle="The approved angle.", kind="myth", score=0)
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox", angle_score=9)
    assert "already has an angle" in result["error"]
    assert _angle() == ("The approved angle.", "myth", 0)


@pytest.mark.parametrize("status", ["SCRIPT_READY", "VOICING", "VOICE_READY", "VIDEO_READY",
                                    "PUBLISHED"])
def test_the_angle_is_closed_once_the_script_exists(db, status):
    _video(status=status, angle="The angle.", kind="myth", score=6)
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox")
    assert status in result["error"]
    assert _angle() == ("The angle.", "myth", 6)


def test_a_rewrite_without_a_score_leaves_the_angle_unscored(db):
    """The stored number described other words."""
    _video(angle="An old angle.", kind="myth", score=8)
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox")
    assert sorted(result["updated_fields"]) == ["angle", "angle_kind"]
    assert _angle() == (SENTENCE, "paradox", 0)


def test_an_angle_can_be_cleared(db):
    _video(angle="An old angle.", kind="myth", score=8)
    assert "error" not in server.update_video("vid_1", angle="", angle_kind="")
    assert _angle() == ("", "", 0)


@pytest.mark.parametrize("kw, part", [
    ({"angle": SENTENCE}, "together"),
    ({"angle_kind": "myth"}, "together"),
    ({"angle_score": 7}, "angle_score"),
    ({"angle": SENTENCE, "angle_kind": "surprise"}, "not a kind"),
    ({"angle": "x" * 301, "angle_kind": "myth"}, "300"),
    ({"angle": SENTENCE, "angle_kind": "myth", "angle_score": -1}, "angle_score"),
])
def test_update_video_refuses_a_malformed_angle(db, kw, part):
    _video(angle="An old angle.", kind="myth", score=8)
    assert part in server.update_video("vid_1", **kw)["error"]
    assert _angle() == ("An old angle.", "myth", 8)


@pytest.mark.parametrize("kw", [{"angle_score": 0}, {"angle_score": 7}, {"angle": ""},
                                {"angle_kind": ""}])
def test_only_naming_both_the_sentence_and_the_kind_can_clear_an_angle(db, kw):
    """A call that carries the score alone, or one half of the pair, is not a
    request to remove the angle. Read as one, "unscored" from an agent would
    wipe an angle a person approved."""
    _video(status="REVISION_REQUESTED", angle="The approved angle.", kind="myth", score=7)
    result = server.update_video("vid_1", **kw)
    assert "together" in result["error"]
    assert _angle() == ("The approved angle.", "myth", 7)


def test_resending_the_approved_angle_with_a_script_is_not_refused(db):
    """At TOPIC_APPROVED an angle is written only when there is none. The same
    angle sent again beside other fields is nothing to write, and must not take
    the rest of the call down with it."""
    _video(status="TOPIC_APPROVED", angle=SENTENCE, kind="paradox", score=7)
    result = server.update_video("vid_1", title="A new title", angle=SENTENCE,
                                 angle_kind="paradox", angle_score=7)
    assert "error" not in result, result
    assert result["updated_fields"] == ["title"]
    assert _angle() == (SENTENCE, "paradox", 7)
    assert server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox") == {
        "video_id": "vid_1", "updated_fields": []}
    # A different one is still refused.
    assert "already has an angle" in server.update_video(
        "vid_1", angle="Another.", angle_kind="myth")["error"]


def test_an_angle_rides_with_the_other_bound_fields(db, monkeypatch):
    """The angle shares the UPDATE's WHERE with the topic-only and agent
    fields. Written together, every check and every parameter must line up,
    and a status change landing in between must stop all of them."""
    with server._conn() as con:
        con.execute("INSERT INTO script_profiles (id, name, status, created_at, updated_at) "
                    "VALUES ('p1', 'P', 'READY', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    _video()
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox", angle_score=6,
                                 script_profile_id="p1", visual_style="stick",
                                 agent_effort="high")
    assert "error" not in result, result
    assert _angle() == (SENTENCE, "paradox", 6)
    with server._conn() as con:
        row = con.execute("SELECT script_profile_id, visual_style, agent_effort FROM videos").fetchone()
    assert tuple(row) == ("p1", "stick", "high")


def test_an_angle_write_does_not_need_a_weak_angle_to_pass_a_floor(db):
    """The floor is for filing. A person's topic picked up with a thin angle
    keeps it: the alternative is no angle at all."""
    _video(status="TOPIC_APPROVED")
    assert "error" not in server.update_video("vid_1", angle=SENTENCE, angle_kind="process",
                                              angle_score=3)


def test_the_update_repeats_the_window_check(db, monkeypatch):
    """The row is read, then the UPDATE runs. A change committed in between
    (simulated right after the read) must leave the angle as it was.
    Mutation-check: dropping either clause of the UPDATE's WHERE makes one of
    these land."""
    real = server._angle_window_row
    for start, change, part in (
        ("TOPIC_PROPOSED", "UPDATE videos SET status = 'SCRIPT_READY'", "SCRIPT_READY"),
        ("TOPIC_APPROVED", "UPDATE videos SET angle = 'Theirs.', angle_kind = 'myth'",
         "already has an angle"),
    ):
        with server._conn() as con:
            con.execute("DELETE FROM videos")
        _video(status=start)

        def racing(vid, _change=change):
            row = real(vid)
            with server._conn() as con:
                con.execute(_change + " WHERE id = 'vid_1'")
            return row

        monkeypatch.setattr(server, "_angle_window_row", racing)
        result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox")
        assert part in result["error"], change
        assert _angle()[0] != SENTENCE, change


def test_an_archived_video_keeps_its_angle(db):
    _video(angle="The angle.", kind="myth", score=6)
    with server._conn() as con:
        con.execute("UPDATE videos SET archived_at = '2026-02-01T00:00:00Z'")
    result = server.update_video("vid_1", angle=SENTENCE, angle_kind="paradox")
    assert result["error"] == "video_archived"
    assert _angle() == ("The angle.", "myth", 6)


# ── mining ──────────────────────────────────────────────────────────────────

class _Gemini:
    """httpx.Client stand-in that answers every call with the same candidates
    and keeps the prompts it was sent."""

    def __init__(self, answer):
        self.prompts = []
        self._answer = list(answer)

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None, _dumps=json.dumps):
        self.prompts.append(json["contents"][0]["parts"][1]["text"])
        text = _dumps(self._answer)

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"candidates": [{"content": {"parts": [{"text": text}]}}],
                        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}}
        return _Resp()


def _mine(monkeypatch, answer, cap=3):
    import httpx
    gemini = _Gemini(answer)
    server._set_setting("max_mining_per_run", str(cap))
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "Client", gemini)
    result = server.mine_youtube_topics(project_id="dom",
                                        youtube_urls=["https://youtu.be/aaaaaaaaaaa"])
    return result, gemini


def test_the_mining_prompt_asks_for_an_angle_of_a_known_kind(db, monkeypatch):
    _, gemini = _mine(monkeypatch, [])
    prompt = gemini.prompts[0]
    assert tangles.prompt_text() in prompt
    for key in ('"angle"', '"angle_kind"', '"angle_score"'):
        assert key in prompt


def test_a_mined_topic_is_filed_with_its_angle(db, monkeypatch):
    result, _ = _mine(monkeypatch, [mined("How copy on write shares memory", angle=SENTENCE,
                                          angle_kind="paradox", angle_score=8)])
    assert result["proposed"] == 1
    assert result["topics"][0]["angle"] == SENTENCE
    assert result["topics"][0]["angle_kind"] == "paradox"
    assert result["topics"][0]["angle_score"] == 8
    with server._conn() as con:
        row = con.execute("SELECT angle, angle_kind, angle_score FROM videos").fetchone()
    assert tuple(row) == (SENTENCE, "paradox", 8)


@pytest.mark.parametrize("spelled", ["Broken expectation", "broken-expectation",
                                     " BROKEN_EXPECTATION ", "broken expectation."])
def test_a_mined_kind_is_matched_whatever_its_spelling(db, monkeypatch, spelled):
    """The model's reply cannot be asked for again, so a kind written as its
    label still files the topic that was paid for."""
    result, _ = _mine(monkeypatch, [mined("How a retry storm starts", angle_kind=spelled)])
    assert result["proposed"] == 1
    assert result["topics"][0]["angle_kind"] == "broken_expectation"


@pytest.mark.parametrize("candidate, part", [
    ({"topic": "How page tables map memory", "producibility_score": 8}, "no angle"),
    (mined("How page tables map memory", angle=""), "no angle"),
    (mined("How page tables map memory", angle_kind="surprise"), "not a kind"),
    (mined("How page tables map memory", angle_score=4), "angle_score 4 is below 5"),
    (mined("How page tables map memory", angle_score="high"), "below 5"),
])
def test_a_mined_candidate_without_a_usable_angle_is_not_filed(db, monkeypatch, candidate, part):
    result, _ = _mine(monkeypatch, [candidate])
    assert result["proposed"] == 0
    assert _count() == 0
    assert result["not_filed"][0]["topic"] == "How page tables map memory"
    assert part in result["not_filed"][0]["reason"]


@pytest.mark.parametrize("sent, stored", [(7.6, 8), ("7", 7), (6.0, 6), (99, 10)])
def test_a_mined_score_is_brought_to_a_whole_number(db, monkeypatch, sent, stored):
    result, _ = _mine(monkeypatch, [mined("How a retry storm starts", angle_score=sent)])
    assert result["proposed"] == 1
    assert result["topics"][0]["angle_score"] == stored


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf"), 10 ** 400])
def test_a_score_that_is_not_a_number_does_not_end_the_run(db, monkeypatch, score):
    """json.loads reads NaN, Infinity and integers of any size. The run has
    paid for the reply by then, so one bad score must cost that candidate and
    nothing else."""
    bad = mined("How page tables map memory", angle_score=score)
    result, _ = _mine(monkeypatch, [bad, mined("How a retry storm starts")])
    assert [t["topic"] for t in result["topics"]] == ["How a retry storm starts"]
    assert "below 5" in result["not_filed"][0]["reason"]


def test_mining_files_the_strongest_candidates_first(db, monkeypatch):
    """The cap goes to the candidates with the best two scores together, so a
    well-drawn topic with a thin angle does not push out a stronger one."""
    result, _ = _mine(monkeypatch, [
        mined("How a bloom filter answers maybe", score=9, angle_score=5),
        mined("Why a hash table resizes at two thirds", score=7, angle_score=9),
        mined("How a trie stores a dictionary", score=6, angle_score=6),
    ], cap=1)
    assert [t["topic"] for t in result["topics"]] == ["Why a hash table resizes at two thirds"]
    assert {n["reason"] for n in result["not_filed"]} == {"over this run's mining cap"}
