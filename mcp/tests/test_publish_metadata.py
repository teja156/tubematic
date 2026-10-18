"""Tests for the publish title and description the agent writes with the script.

The Publish dialog used to ask Gemini for these the first time it opened — a
paid, slow call in front of the one irreversible human action, re-reading a
script the agent had just written. The agent writes them now, in the same
update_video call as the script, and the dialog only reads them back.

They are required with every script write, including a pronunciation-only fix:
an optional pair is one the agent eventually forgets, and the dialog would then
open on the bare topic with nothing to say it was a fallback.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

from datetime import datetime, timezone

import pytest

import server


SEGMENTS = [{"id": "s1", "voice": "Packets take the short road home.", "visual": ""}]
PUBLISH = {"publish_title": "How packets find the short road home",
           "publish_description": "What a routing table actually decides, one hop at a time."}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, topic, status, created_at, updated_at) "
            "VALUES ('vid1', 'test topic', 'TOPIC_APPROVED', ?, ?)", (_now(), _now()))
    return "vid1"


def _row(video_id):
    with server._conn() as con:
        return dict(con.execute(
            "SELECT script, script_segments, publish_title, publish_description "
            "FROM videos WHERE id = ?", (video_id,)).fetchone())


def test_a_script_is_stored_with_its_publish_metadata(video):
    assert server.update_video(video, script_segments=SEGMENTS, **PUBLISH).get("updated_fields")
    got = server.get_video(video)
    assert got["publish_title"] == PUBLISH["publish_title"]
    assert got["publish_description"] == PUBLISH["publish_description"]


@pytest.mark.parametrize("missing", ["publish_title", "publish_description"])
def test_a_script_without_both_values_is_refused_and_nothing_is_written(video, missing):
    kwargs = {k: v for k, v in PUBLISH.items() if k != missing}
    result = server.update_video(video, script_segments=SEGMENTS, **kwargs)
    assert "error" in result and missing in result["error"]
    row = _row(video)
    assert row["script"] == "" and row["script_segments"] in (None, "")
    assert row["publish_title"] == "" and row["publish_description"] == ""


def test_the_refusal_says_how_to_keep_the_current_values(video):
    """A pronunciation fix changes no meaning, so the agent has nothing new to
    write — the error has to tell it to resend what get_video returns."""
    result = server.update_video(video, script_segments=SEGMENTS)
    assert "get_video" in result["error"]


def test_the_refusal_covers_a_video_that_has_none_stored_yet(video):
    """A video scripted before the agent wrote these has a blank pair, so
    "resend them unchanged" would resend blanks, which are refused too — and a
    pronunciation revision would never get past update_video."""
    error = server.update_video(video, script_segments=SEGMENTS)["error"]
    assert "blank" in error and "write" in error


def test_a_legacy_flat_script_needs_them_too(video):
    """Otherwise script= is a way round the requirement."""
    assert "error" in server.update_video(video, script="A flat script.")
    assert server.update_video(video, script="A flat script.", **PUBLISH).get("updated_fields")
    assert _row(video)["publish_title"] == PUBLISH["publish_title"]


@pytest.mark.parametrize("field", ["publish_title", "publish_description"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_value_is_refused(video, field, blank):
    result = server.update_video(video, script_segments=SEGMENTS, **{**PUBLISH, field: blank})
    assert "error" in result and field in result["error"]


def test_values_are_stored_trimmed(video):
    server.update_video(video, script_segments=SEGMENTS,
                        publish_title="  Padded title \n", publish_description="\tBody. ")
    row = _row(video)
    assert (row["publish_title"], row["publish_description"]) == ("Padded title", "Body.")


def test_the_title_cap_is_youtubes(video):
    cap = server.PUBLISH_TITLE_MAX_LEN
    assert cap == 100
    ok = server.update_video(video, script_segments=SEGMENTS,
                             **{**PUBLISH, "publish_title": "t" * cap})
    assert ok.get("updated_fields")
    over = server.update_video(video, script_segments=SEGMENTS,
                               **{**PUBLISH, "publish_title": "t" * (cap + 1)})
    assert "error" in over and str(cap) in over["error"]


def test_the_description_cap_keeps_the_caption_under_instagrams(video):
    """Instagram, TikTok and Facebook get title + blank line + description as
    one caption, and Instagram's limit is 2200."""
    cap = server.PUBLISH_DESCRIPTION_MAX_LEN
    assert server.PUBLISH_TITLE_MAX_LEN + 2 + cap <= 2200
    ok = server.update_video(video, script_segments=SEGMENTS,
                             **{**PUBLISH, "publish_description": "d" * cap})
    assert ok.get("updated_fields")
    over = server.update_video(video, script_segments=SEGMENTS,
                               **{**PUBLISH, "publish_description": "d" * (cap + 1)})
    assert "error" in over and str(cap) in over["error"]


def test_the_metadata_alone_can_be_rewritten(video):
    """Only a script write needs them; they need no script."""
    assert server.update_video(video, publish_title="Better title",
                               publish_description="Better body.").get("updated_fields")
    assert _row(video)["publish_title"] == "Better title"


def test_the_caps_match_the_flask_copy():
    """PATCH /videos/<id> enforces the same pair; each process carries its own
    constants behind a 'Keep in sync' comment."""
    import pathlib
    import re

    src = (pathlib.Path(__file__).resolve().parents[2]
           / "renderer" / "api" / "pipeline.py").read_text()
    for name in ("PUBLISH_TITLE_MAX_LEN", "PUBLISH_DESCRIPTION_MAX_LEN"):
        match = re.search(rf"^{name}\s*=\s*(\d+)$", src, re.M)
        assert match, f"renderer/api/pipeline.py no longer defines {name}"
        assert int(match.group(1)) == getattr(server, name)
