"""Usage recording and pricing (TMDEV-107).

What this guards:
- the 0005 migration creates the ledger on a fresh DB and on one upgraded from 0004;
- the pricing ladder: manual beats synced beats the built-in snapshot, one
  source per model, and an unknown model is UNPRICED (NULL), never $0;
- the missing-rate rules (reasoning → output exactly; audio/image → input,
  estimated; anything else → unpriced);
- the price is snapshotted onto the event, so editing a rate never re-prices
  history — only unpriced events are filled in later;
- ElevenLabs is recorded in credits and never priced; reported costs (Claude,
  OpenCode) are stored as given;
- record_usage never raises, and logs when it could not record;
- the read side: per-video lines, the ÷N split of a shared agent session, and
  the spend summary buckets.
"""
import json
import pathlib
import shutil
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import prices, usage  # noqa: E402


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "data" / "tubematic.db"
    tdb.migrate(path)
    # A known snapshot, so tests never depend on whatever the release shipped.
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps({"models": {
        "gemini/gemini-2.5-flash": {"source": "openrouter", "tiered": False,
                                    "rates": {"input": 3e-07, "output": 2.5e-06,
                                              "input_audio": 1e-06}},
    }}))
    monkeypatch.setattr(prices, "SNAPSHOT_PATH", snap)
    usage._warned_unpriced.clear()
    return path


def _event(path, event_id):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM usage_events WHERE id = ?", (event_id,)).fetchone()
    con.close()
    return row


def _con(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def test_migration_upgrades_a_0004_database(tmp_path):
    older = tmp_path / "to_0004"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 4:
            shutil.copy(mig.path, older / mig.path.name)
    path = tmp_path / "data" / "tubematic.db"
    tdb.migrate(path, migrations_dir=older)
    tdb.migrate(path)
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"usage_events", "usage_event_videos", "model_prices"} <= tables
    # The old roll-up columns are left in place (0001 is immutable).
    cols = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    assert "cost_cents_elevenlabs" in cols


def test_snapshot_prices_a_known_model(db):
    eid = usage.record_usage(db, service="gemini", model="gemini-2.5-flash",
                             operation="ai_review", units={"input": 1_000_000, "output": 1000},
                             videos=["v1"])
    e = _event(db, eid)
    assert e["cost_basis"] == "priced"
    assert e["cost_usd"] == pytest.approx(0.30 + 0.0025)
    assert json.loads(e["price_snapshot"])["source"] == "built-in"


def test_unknown_model_is_unpriced_never_zero(db, caplog):
    eid = usage.record_usage(db, service="gemini", model="gemini-9-flash",
                             operation="ai_review", units={"input": 500}, videos=["v1"])
    e = _event(db, eid)
    assert e["cost_basis"] == "unpriced"
    assert e["cost_usd"] is None
    assert json.loads(e["units"]) == {"input": 500}
    assert "gemini-9-flash" in caplog.text


def test_unknown_model_is_logged_once_per_process(db, caplog):
    for _ in range(3):
        usage.record_usage(db, service="gemini", model="gemini-9-flash",
                           operation="ai_review", units={"input": 5})
    assert caplog.text.count("gemini-9-flash") == 1


def test_a_unit_with_no_rate_makes_the_call_unpriced(db):
    eid = usage.record_usage(db, service="gemini", model="gemini-2.5-flash",
                             operation="image", units={"input": 10, "output_image": 1290})
    assert _event(db, eid)["cost_basis"] == "unpriced"


def test_reasoning_bills_at_the_output_rate_exactly(db):
    eid = usage.record_usage(db, service="gemini", model="gemini-2.5-flash",
                             operation="ai_review", units={"reasoning": 1000})
    e = _event(db, eid)
    assert e["cost_usd"] == pytest.approx(1000 * 2.5e-06)
    assert e["estimated"] == 0


def test_image_input_without_its_own_rate_falls_back_to_input_estimated(db):
    eid = usage.record_usage(db, service="gemini", model="gemini-2.5-flash",
                             operation="ai_review", units={"input_image": 1000})
    e = _event(db, eid)
    assert e["cost_usd"] == pytest.approx(1000 * 3e-07)
    assert e["estimated"] == 1


def test_manual_rate_beats_synced_and_snapshot(db):
    con = sqlite3.connect(db)
    con.execute("INSERT INTO model_prices VALUES ('gemini','gemini-2.5-flash','input',1e-06,"
                "'openrouter','2026-01-01T00:00:00Z',0,0)")
    con.commit()
    price = prices.lookup_rates(con, "gemini", "gemini-2.5-flash")
    assert price["source"] == "openrouter" and price["rates"] == {"input": 1e-06}
    prices.set_manual_rates(con, "gemini", "gemini-2.5-flash", {"input": 2e-06})
    price = prices.lookup_rates(con, "gemini", "gemini-2.5-flash")
    assert price["source"] == "manual" and price["rates"] == {"input": 2e-06}
    prices.clear_manual_rates(con, "gemini", "gemini-2.5-flash")
    assert prices.lookup_rates(con, "gemini", "gemini-2.5-flash")["source"] == "built-in"


def test_editing_a_price_never_reprices_history(db):
    eid = usage.record_usage(db, service="gemini", model="gemini-2.5-flash",
                             operation="ai_review", units={"input": 1_000_000})
    con = sqlite3.connect(db)
    prices.set_manual_rates(con, "gemini", "gemini-2.5-flash", {"input": 1e-05})
    con.commit()
    assert _event(db, eid)["cost_usd"] == pytest.approx(0.30)


def test_adding_a_price_fills_in_unpriced_events(db):
    eid = usage.record_usage(db, service="gemini", model="gemini-9-flash",
                             operation="ai_review", units={"input": 1000})
    con = sqlite3.connect(db)
    n = prices.set_manual_rates(con, "gemini", "gemini-9-flash", {"input": 1e-06})
    con.commit()
    assert n == 1
    e = _event(db, eid)
    assert e["cost_basis"] == "priced" and e["cost_usd"] == pytest.approx(0.001)


def test_manual_rates_are_validated(db):
    con = sqlite3.connect(db)
    with pytest.raises(ValueError):
        prices.set_manual_rates(con, "gemini", "m", {"input": 0})
    with pytest.raises(ValueError):
        prices.set_manual_rates(con, "gemini", "m", {"bogus": 1e-06})


def test_elevenlabs_is_recorded_in_credits_and_never_priced(db):
    eid = usage.record_usage(db, service="elevenlabs", model="eleven_multilingual_v2",
                             operation="voice", units={"credits": 1240}, videos=["v1"])
    e = _event(db, eid)
    assert e["cost_basis"] == "credits" and e["cost_usd"] is None


def test_reported_cost_is_stored_as_given(db):
    eid = usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                             operation="agent_pipeline", units={"input": 10},
                             reported_cost_usd=0.4521)
    e = _event(db, eid)
    assert e["cost_basis"] == "reported" and e["cost_usd"] == pytest.approx(0.4521)


def test_record_usage_never_raises(tmp_path, caplog):
    missing_schema = tmp_path / "empty.db"
    assert usage.record_usage(missing_schema, service="gemini", model="x",
                              operation="ai_review", units={"input": 1}) is None
    assert "Could not record" in caplog.text


def test_gemini_units_split_modalities_cache_and_thinking():
    units = usage.gemini_units({
        "promptTokenCount": 10_000,
        "promptTokensDetails": [{"modality": "VIDEO", "tokenCount": 9000},
                                {"modality": "AUDIO", "tokenCount": 800},
                                {"modality": "TEXT", "tokenCount": 200}],
        "cachedContentTokenCount": 100,
        "cacheTokensDetails": [{"modality": "TEXT", "tokenCount": 100}],
        "candidatesTokenCount": 300,
        "thoughtsTokenCount": 700,
    })
    assert units == {"input": 9100, "input_audio": 800, "cache_read": 100,
                     "output": 300, "reasoning": 700}


def test_gemini_units_image_output():
    units = usage.gemini_units({"promptTokenCount": 12, "candidatesTokenCount": 1290,
                                "candidatesTokensDetails": [{"modality": "IMAGE",
                                                             "tokenCount": 1290}]})
    assert units == {"input": 12, "output_image": 1290}


def test_openai_image_units():
    assert usage.openai_image_units({
        "input_tokens": 60, "output_tokens": 4160,
        "input_tokens_details": {"text_tokens": 50, "image_tokens": 10},
    }) == {"input": 50, "input_image": 10, "output_image": 4160}


def test_video_costs_splits_a_shared_session_evenly(db):
    usage.record_usage(db, service="gemini", model="gemini-2.5-flash", operation="ai_review",
                       units={"input": 1_000_000}, videos=["v1"])
    usage.record_usage(db, service="elevenlabs", model="eleven_multilingual_v2",
                       operation="voice", units={"credits": 1240}, videos=["v1"])
    usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                       operation="agent_pipeline", reported_cost_usd=0.15, session_id="s1",
                       videos=[("v1", "TOPIC_APPROVED"), ("v2", "TOPIC_APPROVED"),
                               ("v3", "VOICE_READY")])
    usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                       operation="agent_pipeline", reported_cost_usd=0.08, session_id="s2",
                       videos=[("v1", "VOICE_READY")])
    out = usage.video_costs(_con(db), "v1")
    assert out["has_usage"]
    assert out["credits"] == 1240
    agent = out["agent"]
    assert agent["share_usd"] == pytest.approx(0.05 + 0.08)
    assert agent["session_total_usd"] == pytest.approx(0.23)
    assert agent["shared"] is True
    assert [s["stage"] for s in agent["sessions"]] == ["TOPIC_APPROVED", "VOICE_READY"]
    assert [s["batch_size"] for s in agent["sessions"]] == [3, 1]
    # Total adds the share, never the whole session.
    assert out["total_usd"] == pytest.approx(0.30 + 0.13)


def test_video_costs_for_a_video_with_no_usage(db):
    out = usage.video_costs(_con(db), "never-recorded")
    assert out == {"has_usage": False, "lines": [], "agent": None, "total_usd": 0.0,
                   "credits": 0, "unpriced_calls": 0}


def test_last_voice_model_is_the_latest_voicing_call_for_that_video(db):
    usage.record_usage(db, service="elevenlabs", model="eleven_multilingual_v2",
                       operation="voice", units={"credits": 900}, videos=["v1"])
    usage.record_usage(db, service="elevenlabs", model="eleven_v3",
                       operation="voice", units={"credits": 900}, videos=["v1"])
    # None of these is a voicing of v1: another video's, a preview (even one
    # linked to v1) and another provider's call.
    usage.record_usage(db, service="elevenlabs", model="eleven_flash_v2",
                       operation="voice", units={"credits": 900}, videos=["v2"])
    usage.record_usage(db, service="elevenlabs", model="eleven_turbo_v2",
                       operation="voice_preview", units={"credits": 90}, videos=["v1"])
    usage.record_usage(db, service="gemini", model="gemini-2.5-flash", operation="ai_review",
                       units={"input": 1000}, videos=["v1"])
    assert usage.last_voice_model(_con(db), "v1") == "eleven_v3"
    assert usage.last_voice_model(_con(db), "v2") == "eleven_flash_v2"


def test_last_voice_model_is_none_for_a_video_never_voiced(db):
    usage.record_usage(db, service="gemini", model="gemini-2.5-flash", operation="ai_review",
                       units={"input": 1000}, videos=["v1"])
    assert usage.last_voice_model(_con(db), "v1") is None
    assert usage.last_voice_model(_con(db), "never-recorded") is None


def test_spend_summary_buckets(db):
    usage.record_usage(db, service="gemini", model="gemini-2.5-flash", operation="ai_review",
                       units={"input": 1_000_000}, videos=["v1"])
    usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                       operation="agent_research", reported_cost_usd=0.5)
    usage.record_usage(db, service="gemini", model="gemini-2.5-flash", operation="mining",
                       units={"input": 1_000_000})
    usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                       operation="agent_unscoped", reported_cost_usd=0.2)
    usage.record_usage(db, service="elevenlabs", model="eleven_multilingual_v2",
                       operation="voice_preview", units={"credits": 90})
    usage.record_usage(db, service="gemini", model="gemini-9-flash", operation="mining",
                       units={"input": 5})
    out = usage.spend_summary(_con(db), "2000-01-01T00:00:00Z")
    assert out["videos"] == pytest.approx(0.30)
    assert out["research"] == pytest.approx(0.80)
    assert out["agent_other"] == pytest.approx(0.20)
    assert out["total_usd"] == pytest.approx(1.30)
    assert out["preview_credits"] == 90
    assert out["unpriced_calls"] == 1
    assert out["video_count"] == 1


def test_spend_summary_until_is_an_exclusive_upper_bound(db):
    """The Spend tab's range needs an end as well as a start. An event exactly
    at `until` belongs to the next range, so adjacent ranges never count it
    twice — and the video count honours the same window as the dollars."""
    inside = usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                                operation="agent_pipeline", reported_cost_usd=0.5,
                                videos=["v1"])
    at_bound = usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                                  operation="agent_pipeline", reported_cost_usd=0.25,
                                  videos=["v2"])
    con = _con(db)
    con.execute("UPDATE usage_events SET created_at = '2026-09-10T12:00:00Z' WHERE id = ?",
                (inside,))
    con.execute("UPDATE usage_events SET created_at = '2026-09-11T00:00:00Z' WHERE id = ?",
                (at_bound,))
    con.commit()
    out = usage.spend_summary(con, "2026-09-10T00:00:00Z", "2026-09-11T00:00:00Z")
    assert out["total_usd"] == pytest.approx(0.5)
    assert out["video_count"] == 1
    assert out["until"] == "2026-09-11T00:00:00Z"
    # No `until` keeps the open-ended behaviour every other caller relies on.
    assert usage.spend_summary(con, "2026-09-10T00:00:00Z")["total_usd"] == pytest.approx(0.75)


def test_a_billed_call_with_no_readable_usage_is_unpriced_not_free(db):
    """Callers record a billed 200 with empty units when its usage could not be
    read. Pricing that at $0 would understate spend with nothing to repair from."""
    eid = usage.record_usage(db, service="gemini", model="gemini-2.5-flash",
                             operation="ai_review", units={}, videos=["v1"])
    e = _event(db, eid)
    assert e["cost_basis"] == "unpriced" and e["cost_usd"] is None
    assert prices.price_units({"rates": {"input": 1e-06}}, {}) is None


def test_an_event_key_makes_a_resend_idempotent(db):
    first = usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                               operation="agent_pipeline", reported_cost_usd=0.2,
                               videos=["v1"], event_key="agent:s1:0")
    again = usage.record_usage(db, service="anthropic", model="claude-sonnet-5",
                               operation="agent_pipeline", reported_cost_usd=0.2,
                               videos=["v1"], event_key="agent:s1:0")
    assert again == first
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM usage_event_videos").fetchone()[0] == 1
