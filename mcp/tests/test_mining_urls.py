"""What mining may hand Gemini, and how much it may spend in one run.

A mining URL becomes Gemini's file_data.file_uri on a paid call. These pin
that only a YouTube video URL ever gets there (checked before the first call,
so a bad entry costs nothing), that one run makes at most one call per topic
it may file, and that two runs never overlap.
"""
import json
import threading

import pytest

import server

ID_A, ID_B, ID_C = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"


def _canon(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, created_at) "
                    "VALUES ('proj_1', 'P', '2026-01-01T00:00:00Z')")


class _Gemini:
    """httpx.Client stand-in that counts every paid call and answers []."""

    def __init__(self, answer=(), on_post=None):
        self.uris = []
        self._answer = list(answer)
        self._on_post = on_post

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None, _dumps=json.dumps):
        self.uris.append(json["contents"][0]["parts"][0]["file_data"]["file_uri"])
        if self._on_post:
            self._on_post()
        text = _dumps(self._answer)

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"candidates": [{"content": {"parts": [{"text": text}]}}],
                        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}}
        return _Resp()


def _mine(monkeypatch, urls, gemini=None):
    import httpx
    gemini = gemini or _Gemini()
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "Client", gemini)
    return server.mine_youtube_topics(project_id="proj_1", youtube_urls=urls), gemini


# ── only a YouTube video URL reaches Gemini ─────────────────────────────────

@pytest.mark.parametrize("bad", [
    "file:///etc/passwd",
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1:4000/settings",
    f"https://youtube.com.evil.com/watch?v={ID_A}",
    f"https://youtube.com@evil.com/watch?v={ID_A}",
    "https://youtu.be/tooShortId",
])
def test_one_bad_url_refuses_the_run_before_any_gemini_call(db, monkeypatch, bad):
    result, gemini = _mine(monkeypatch, [f"https://youtu.be/{ID_A}", bad])
    assert gemini.uris == []
    assert repr(bad) in result["error"]
    with server._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0


def test_a_good_list_is_handed_to_gemini_in_the_canonical_form(db, monkeypatch):
    server._set_setting("max_mining_per_run", "2")
    result, gemini = _mine(monkeypatch, [f"https://youtu.be/{ID_A}?si=tracking",
                                         f"https://m.youtube.com/shorts/{ID_B}"])
    assert "error" not in result
    assert gemini.uris == [_canon(ID_A), _canon(ID_B)]


def test_two_spellings_of_one_video_are_asked_once(db, monkeypatch):
    server._set_setting("max_mining_per_run", "3")
    _, gemini = _mine(monkeypatch, [f"https://youtu.be/{ID_A}",
                                    f"https://www.youtube.com/watch?v={ID_A}&t=9"])
    assert gemini.uris == [_canon(ID_A)]


# ── at most one paid call per topic the run may file ────────────────────────

def test_a_run_makes_no_more_calls_than_its_cap_when_urls_come_back_empty(db, monkeypatch):
    server._set_setting("max_mining_per_run", "2")
    urls = [f"https://youtu.be/{i:011d}" for i in range(6)]
    result, gemini = _mine(monkeypatch, urls)
    assert len(gemini.uris) == 2
    assert result["proposed"] == 0
    # The next run carries on where this one stopped.
    _, gemini = _mine(monkeypatch, urls)
    assert gemini.uris == [_canon(f"{i:011d}") for i in (2, 3)]


def test_a_run_whose_calls_all_fail_is_bounded_too(db, monkeypatch):
    import httpx

    class _Down:
        def __call__(self, *a, **kw):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        calls = 0

        def post(self, *a, **kw):
            type(self).calls += 1
            raise httpx.ConnectError("down")

    server._set_setting("max_mining_per_run", "3")
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "Client", _Down())
    result = server.mine_youtube_topics(
        project_id="proj_1", youtube_urls=[f"https://youtu.be/{i:011d}" for i in range(10)])
    assert _Down.calls == 3 and result["skipped"] == 3


# ── one run at a time ───────────────────────────────────────────────────────

def test_a_second_run_while_one_is_in_flight_is_refused(db, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def _hold():
        entered.set()
        assert release.wait(5)

    gemini = _Gemini(on_post=_hold)
    first = {}
    thread = threading.Thread(target=lambda: first.update(
        result=_mine(monkeypatch, [f"https://youtu.be/{ID_A}"], gemini)[0]))
    thread.start()
    try:
        assert entered.wait(5)
        second = server.mine_youtube_topics(project_id="proj_1",
                                            youtube_urls=[f"https://youtu.be/{ID_B}"])
    finally:
        release.set()
        thread.join(5)
    assert "only one runs at a time" in second["error"]
    assert gemini.uris == [_canon(ID_A)]          # the refused run made no call
    assert "error" not in first["result"]
    # Released afterwards: the next run goes ahead.
    third, _ = _mine(monkeypatch, [f"https://youtu.be/{ID_C}"])
    assert "error" not in third


def test_the_lock_is_released_when_a_run_is_refused_or_raises(db, monkeypatch):
    result, _ = _mine(monkeypatch, ["file:///x"])
    assert "error" in result
    monkeypatch.setattr(server, "_closed_domain_error",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        _mine(monkeypatch, [f"https://youtu.be/{ID_A}"])
    assert server._MINING_LOCK.acquire(blocking=False)
    server._MINING_LOCK.release()


# ── the guards that came before are unchanged ───────────────────────────────

def test_no_gemini_key_is_still_an_error_and_no_call(db, monkeypatch):
    import httpx
    gemini = _Gemini()
    monkeypatch.setattr(server, "_gemini_key", lambda: "")
    monkeypatch.setattr(httpx, "Client", gemini)
    result = server.mine_youtube_topics(project_id="proj_1",
                                        youtube_urls=[f"https://youtu.be/{ID_A}"])
    assert "Gemini API key not set" in result["error"] and gemini.uris == []


def test_an_empty_list_is_still_an_error(db, monkeypatch):
    result, gemini = _mine(monkeypatch, [])
    assert "get_mining_sources" in result["error"] and gemini.uris == []


# ── set_mining_sources ──────────────────────────────────────────────────────

def _stored():
    return json.loads(server._get_setting("mining_youtube_urls", "[]"))


def test_set_mining_sources_stores_the_canonical_deduplicated_list(db):
    out = server.set_mining_sources([f"https://youtu.be/{ID_A}?si=x",
                                     f"https://www.youtube.com/live/{ID_B}",
                                     f"https://m.youtube.com/watch?v={ID_A}"])
    assert out == {"youtube_urls": [_canon(ID_A), _canon(ID_B)]}
    assert _stored() == [_canon(ID_A), _canon(ID_B)]


def test_set_mining_sources_refuses_the_whole_list_and_stores_nothing(db):
    server.set_mining_sources([f"https://youtu.be/{ID_A}"])
    out = server.set_mining_sources([f"https://youtu.be/{ID_B}", "http://127.0.0.1/",
                                     "file:///etc/passwd"])
    assert "'http://127.0.0.1/'" in out["error"] and "'file:///etc/passwd'" in out["error"]
    assert _stored() == [_canon(ID_A)]


def test_set_mining_sources_caps_the_list(db):
    out = server.set_mining_sources([f"https://youtu.be/{i:011d}" for i in range(51)])
    assert "at most 50" in out["error"]
    assert server.set_mining_sources([])["youtube_urls"] == []
