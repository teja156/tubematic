"""A domain's whole topic history, and the topic cap that bounds it (TMDEV-153).

Research deduplicated with list_videos, which never lists an archived video,
so a topic deleted by a human or swept by retention was proposed again — and
under Auto Pilot approved and paid for. list_project_topics lists every topic
ever filed into a domain instead, archived and rejected ones included.

That history has to stay a size an agent can read, so each domain carries a
topic_cap. A domain whose count of videos ever filed reaches it is expired: it
is refused exactly like a paused domain, manual submissions exempt. Expired is
derived on read, never stored, so raising the cap re-opens the domain.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pytest

import server


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    return tmp_path / "test.db"


def _project(pid="db-internals", *, cap=25, seed=True, status="active", name="Database internals"):
    with server._conn() as con:
        con.execute(
            "INSERT INTO projects (id, name, is_curriculum_seed, status, topic_cap, created_at) "
            "VALUES (?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')",
            (pid, name, int(seed), status, cap),
        )
    return pid


def _videos(pid, n, *, start=0, status="PUBLISHED", archived=False, topic="Topic {i}",
            title=""):
    """n videos in pid, created one second apart so the order is unambiguous."""
    with server._conn() as con:
        for i in range(start, start + n):
            ts = f"2026-02-01T00:{i // 60:02d}:{i % 60:02d}Z"
            con.execute(
                "INSERT INTO videos (id, project_id, topic, title, status, archived_at, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"vid_{pid}_{i}", pid, topic.format(i=i), title, status,
                 ts if archived else None, ts, ts),
            )


def _count(pid="db-internals"):
    with server._conn() as con:
        return con.execute("SELECT COUNT(*) FROM videos WHERE project_id = ?",
                           (pid,)).fetchone()[0]


# ── list_project_topics ─────────────────────────────────────────────────────

def test_archived_and_rejected_topics_are_listed(db):
    """The whole point: list_videos hides these, so they were re-proposed."""
    _project()
    _videos("db-internals", 1, start=0, archived=True, topic="B-trees on disk")
    _videos("db-internals", 1, start=1, status="TOPIC_REJECTED", topic="LSM compaction")
    _videos("db-internals", 1, start=2, topic="WAL fsync")
    assert server.list_videos(project_id="db-internals") != []
    assert len(server.list_videos(project_id="db-internals")) == 2  # the archived one is hidden

    result = server.list_project_topics("db-internals")
    topics = {t["topic"]: t for t in result["topics"]}
    assert set(topics) == {"B-trees on disk", "LSM compaction", "WAL fsync"}
    assert topics["B-trees on disk"]["archived"] is True
    assert topics["LSM compaction"]["status"] == "TOPIC_REJECTED"
    assert topics["WAL fsync"]["archived"] is False


def test_topics_are_newest_first_and_limited_to_the_cap(db):
    _project(cap=25)
    _videos("db-internals", 30)  # past the cap: manual filing is exempt
    result = server.list_project_topics("db-internals")
    assert result["topic_count"] == 30
    assert result["topic_cap"] == 25
    assert result["expired"] is True
    assert len(result["topics"]) == 25
    assert result["topics"][0]["id"] == "vid_db-internals_29"
    assert result["topics"][-1]["id"] == "vid_db-internals_5"


def test_only_the_named_domain_is_listed(db):
    _project("a")
    _project("b")
    _videos("a", 2)
    _videos("b", 3)
    result = server.list_project_topics("a")
    assert result["topic_count"] == 2
    assert {t["id"] for t in result["topics"]} == {"vid_a_0", "vid_a_1"}


def test_a_long_brief_is_clipped_at_a_word_with_an_ellipsis(db):
    _project()
    brief = "How the write-ahead log " + "survives a crash mid-checkpoint " * 20
    _videos("db-internals", 1, topic=brief)
    topic = server.list_project_topics("db-internals")["topics"][0]["topic"]
    assert len(topic) <= server.TOPIC_BRIEF_LIST_CHARS
    assert topic.endswith("…")
    assert brief.startswith(topic[:-1])
    assert not topic[:-1].endswith(" ")


def test_a_short_brief_and_title_come_back_whole(db):
    _project()
    _videos("db-internals", 1, topic="B-trees\non   disk", title="B-trees")
    row = server.list_project_topics("db-internals")["topics"][0]
    assert row["topic"] == "B-trees on disk"  # whitespace collapsed, nothing cut
    assert row["title"] == "B-trees"


def test_an_over_length_legacy_title_is_clipped(db):
    _project()
    _videos("db-internals", 1, title="word " * 30)
    title = server.list_project_topics("db-internals")["topics"][0]["title"]
    assert len(title) <= server.VIDEO_TITLE_MAX_LEN


def test_an_unknown_project_is_an_error(db):
    assert "error" in server.list_project_topics("nope")


# ── an expired domain refuses research filing ───────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining"])
def test_a_domain_at_its_cap_refuses_every_sourced_strategy(db, strategy):
    _project(cap=25)
    _videos("db-internals", 25, archived=True)  # archived rows count toward the cap
    result = server.create_video("db-internals", "B-trees on disk", strategy, 7)
    assert "error" in result
    assert _count() == 25


def test_the_refusal_names_the_domain_the_count_and_the_cap(db):
    _project(cap=25)
    _videos("db-internals", 25, status="TOPIC_REJECTED")
    err = server.create_video("db-internals", "B-trees on disk", "trending", 7)["error"]
    assert "Database internals" in err
    assert "expired" in err
    assert "25" in err
    assert "Skip this candidate" in err
    assert "manual" not in err.lower()


def test_one_below_the_cap_still_files(db):
    _project(cap=25)
    _videos("db-internals", 24)
    result = server.create_video("db-internals", "B-trees on disk", "curriculum", 7)
    assert "error" not in result
    assert server.list_projects()[0]["expired"] is True


def test_a_manual_submission_is_accepted_into_an_expired_domain(db):
    _project(cap=25)
    _videos("db-internals", 25)
    result = server.create_video("db-internals", "B-trees on disk", "manual", 7)
    assert "error" not in result
    assert _count() == 26


def test_raising_the_cap_re_opens_the_domain(db):
    _project(cap=25)
    _videos("db-internals", 25)
    server.upsert_project("db-internals", "Database internals", topic_cap=26)
    result = server.create_video("db-internals", "B-trees on disk", "curriculum", 7)
    assert "error" not in result


def test_a_topic_landing_between_the_check_and_the_insert_still_refuses(db, monkeypatch):
    """Two research sessions can each pass the early count; the INSERT must
    re-count itself. _pick_agent_id runs in that window."""
    _project(cap=25)
    _videos("db-internals", 24)
    real_pick = server._pick_agent_id

    def _fill_then_pick(con, *a, **kw):
        _videos("db-internals", 1, start=24)
        return real_pick(con, *a, **kw)

    monkeypatch.setattr(server, "_pick_agent_id", _fill_then_pick)
    result = server.create_video("db-internals", "B-trees on disk", "trending", 7)
    assert "expired" in result["error"]
    assert _count() == 25


def test_a_pause_still_reads_as_a_pause_on_an_expired_domain(db):
    _project(cap=25, status="paused")
    _videos("db-internals", 25)
    err = server.create_video("db-internals", "B-trees on disk", "trending", 7)["error"]
    assert "paused" in err


def test_mining_into_an_expired_domain_is_refused_before_any_gemini_call(db, monkeypatch):
    import httpx
    _project(cap=25)
    _videos("db-internals", 25)
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")

    def _no_call(*a, **kw):
        raise AssertionError("Gemini must not be called for an expired domain")

    monkeypatch.setattr(httpx, "Client", _no_call)
    result = server.mine_youtube_topics(project_id="db-internals",
                                        youtube_urls=["https://youtu.be/xxxxxxxxxxx"])
    assert "expired" in result["error"]


class _Gemini:
    """A fake httpx.Client: every call returns `per_call` fresh candidates and
    is counted, so a test can tell how many paid calls a run made."""

    def __init__(self, per_call):
        self.per_call = per_call
        self.prompts = []

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        import json as _json
        self.prompts.append(json["contents"][0]["parts"][1]["text"])
        n = len(self.prompts)
        topics = [{"topic": f"Distinct mined subject {n}-{i} alpha{n}{i} beta{n}{i}",
                   "producibility_score": 8} for i in range(self.per_call)]

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"candidates": [{"content": {"parts": [{"text": _json.dumps(topics)}]}}],
                        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10}}
        return _Resp()


def _mine(monkeypatch, gemini, urls=3):
    import httpx
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "Client", gemini)
    return server.mine_youtube_topics(project_id="db-internals",
                                      youtube_urls=[f"https://youtu.be/{i:011d}" for i in range(urls)])


def test_mining_asks_only_for_the_room_left_under_the_topic_cap(db, monkeypatch):
    """Past the cap every insert is refused, so asking Gemini for more, or
    trying another URL, is spend with nothing to show."""
    _project(cap=25)
    _videos("db-internals", 23)
    server._set_setting("max_mining_per_run", "5")
    gemini = _Gemini(per_call=5)
    result = _mine(monkeypatch, gemini)
    assert len(gemini.prompts) == 1
    assert "pick at most 2 concepts" in gemini.prompts[0]
    assert result["proposed"] == 2
    assert {r["reason"] for r in result["not_filed"]} == {"the domain is at its topic cap"}
    assert _count() == 25


def test_a_domain_filled_mid_run_ends_the_run(db, monkeypatch):
    """Another writer fills the domain during the run: the first refusal ends
    it, rather than one paid Gemini call per URL still to come."""
    _project(cap=25)
    _videos("db-internals", 20)
    server._set_setting("max_mining_per_run", "5")
    real_pick = server._pick_agent_id

    def _fill_then_pick(con, *a, **kw):
        if _count() < 25:
            _videos("db-internals", 25 - _count(), start=100)
        return real_pick(con, *a, **kw)

    monkeypatch.setattr(server, "_pick_agent_id", _fill_then_pick)
    gemini = _Gemini(per_call=1)
    result = _mine(monkeypatch, gemini)
    assert len(gemini.prompts) == 1
    assert result["proposed"] == 0
    assert "expired" in result["not_filed"][0]["reason"]


# ── the cap on projects ─────────────────────────────────────────────────────

def test_a_new_project_gets_the_default_cap(db):
    project = server.upsert_project("db-internals", "Database internals")
    assert project["topic_cap"] == server.TOPIC_CAP_DEFAULT == 100
    assert project["topic_count"] == 0
    assert project["expired"] is False


def test_a_partial_upsert_keeps_the_stored_cap(db):
    server.upsert_project("db-internals", "Database internals", topic_cap=300)
    project = server.upsert_project("db-internals", "Database internals", description="x")
    assert project["topic_cap"] == 300


@pytest.mark.parametrize("cap", [25, 750])
def test_the_bounds_themselves_are_accepted(db, cap):
    assert server.upsert_project("db-internals", "D", topic_cap=cap)["topic_cap"] == cap


@pytest.mark.parametrize("cap", [24, 751, 0, -1, True, "100", 100.0])
def test_a_cap_outside_the_bounds_or_not_a_whole_number_is_refused(db, cap):
    server.upsert_project("db-internals", "D", topic_cap=300)
    result = server.upsert_project("db-internals", "D", topic_cap=cap)
    assert "topic_cap" in result["error"]
    assert server.list_projects()[0]["topic_cap"] == 300


def test_list_projects_carries_the_count_and_expiry(db):
    _project("a", cap=25)
    _project("b", cap=100)
    _videos("a", 25, archived=True)
    _videos("b", 3)
    by_id = {p["id"]: p for p in server.list_projects()}
    assert (by_id["a"]["topic_count"], by_id["a"]["expired"]) == (25, True)
    assert (by_id["b"]["topic_count"], by_id["b"]["expired"]) == (3, False)


def test_set_project_status_returns_the_same_shape(db):
    _project(cap=25)
    _videos("db-internals", 25)
    project = server.set_project_status("db-internals", "paused")
    assert project["expired"] is True
    assert project["topic_count"] == 25
