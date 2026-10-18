"""Price feeds and the unattended sync (TMDEV-107).

What this guards:
- source precedence is per model: OpenRouter when it lists the model, LiteLLM
  only when it does not — never a mix of fields from both;
- feed normalisation: zero rates are absent (a $0 rate would price a paid call
  as free), `:batch` variants are ignored, long-prompt tiers mark `tiered`;
- name mapping (claude-opus-5-5 → anthropic/claude-opus-5.5);
- the sync's safety rules: a manual row is never touched, a >5× move is
  rejected, and ANY failure keeps every existing price (all-or-nothing) and
  records the error for Settings to show;
- a sync that newly prices a model fills in its unpriced events.
"""
import json
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import prices, usage  # noqa: E402

OPENROUTER = {"data": [
    {"id": "google/gemini-2.5-flash",
     "pricing": {"prompt": "0.0000003", "completion": "0.0000025", "audio": "0.000001",
                 "image": "0", "web_search": "0.035"}},
    {"id": "google/gemini-2.5-flash:batch", "pricing": {"prompt": "0.00000015"}},
    {"id": "openai/gpt-5.6-sol",
     "pricing": {"prompt": "0.000002", "completion": "0.00001",
                 "overrides": [{"min_prompt_tokens": 272000, "prompt": "0.000004"}]}},
]}
LITELLM = {
    "gemini/gemini-2.5-flash": {"input_cost_per_token": 9e-07},
    "gpt-image-2.5-flare": {"input_cost_per_token": 5e-06, "output_cost_per_image_token": 3e-05},
}


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


@pytest.fixture
def con(tmp_path, monkeypatch):
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps({"models": {
        "gemini/gemini-2.5-flash": {"source": "openrouter", "tiered": False, "rates": {"input": 1}},
        "openai/gpt-image-2.5-flare": {"source": "litellm", "tiered": False, "rates": {"input": 1}},
        "openai/gpt-5.6-sol": {"source": "openrouter", "tiered": False, "rates": {"input": 1}},
    }}))
    monkeypatch.setattr(prices, "SNAPSHOT_PATH", snap)
    path = tmp_path / "data" / "tubematic.db"
    tdb.migrate(path)
    c = sqlite3.connect(path)
    yield c
    c.close()


def _fetch(openrouter=OPENROUTER, litellm=LITELLM):
    def fetch(url):
        return openrouter if "openrouter" in url else litellm
    return fetch


def _rates(con, service, model):
    return {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT unit_kind, usd_per_unit, source FROM model_prices WHERE service=? AND model=?",
        (service, model))}


def test_openrouter_normalisation_drops_zero_rates_and_batch_variants():
    out = prices.normalize_openrouter(OPENROUTER)
    assert set(out) == {"google/gemini-2.5-flash", "openai/gpt-5.6-sol"}
    assert out["google/gemini-2.5-flash"]["rates"] == {
        "input": 3e-07, "output": 2.5e-06, "input_audio": 1e-06}
    assert out["openai/gpt-5.6-sol"]["tiered"] is True


def test_name_mapping():
    assert prices.openrouter_id("anthropic", "claude-opus-5-5") == "anthropic/claude-opus-5.5"
    assert prices.openrouter_id("anthropic", "claude-haiku-4-5-20251001") == \
        "anthropic/claude-haiku-4.5"
    assert prices.openrouter_id("gemini", "gemini-2.5-flash") == "google/gemini-2.5-flash"
    assert prices.litellm_id("gemini", "gemini-2.5-flash") == "gemini/gemini-2.5-flash"
    assert prices.openrouter_id("elevenlabs", "eleven_v3") is None


def test_source_is_chosen_per_model_openrouter_first(con):
    result = prices.sync_prices(con, fetch=_fetch())
    assert result["ok"]
    gem = _rates(con, "gemini", "gemini-2.5-flash")
    # OpenRouter lists it, so LiteLLM's (different) input rate is ignored entirely.
    assert gem["input"] == (3e-07, "openrouter")
    assert {s for _, s in gem.values()} == {"openrouter"}
    # Only LiteLLM lists gpt-image-2.5-flare.
    assert _rates(con, "openai", "gpt-image-2.5-flare")["output_image"] == (3e-05, "litellm")
    assert con.execute("SELECT value FROM settings WHERE key='last_price_sync_ok_at'").fetchone()


def test_a_manual_row_is_never_overwritten(con):
    prices.set_manual_rates(con, "gemini", "gemini-2.5-flash", {"input": 7e-07})
    prices.sync_prices(con, fetch=_fetch())
    assert _rates(con, "gemini", "gemini-2.5-flash") == {"input": (7e-07, "manual")}


def test_an_implausible_move_is_rejected(con):
    prices.sync_prices(con, fetch=_fetch())
    jumped = json.loads(json.dumps(OPENROUTER))
    jumped["data"][0]["pricing"]["prompt"] = "0.00003"  # 100× the old input rate
    result = prices.sync_prices(con, fetch=_fetch(openrouter=jumped))
    assert "gemini/gemini-2.5-flash" in result["rejected"]
    assert _rates(con, "gemini", "gemini-2.5-flash")["input"] == (3e-07, "openrouter")


def test_a_failed_feed_keeps_every_price_and_records_the_error(con):
    prices.sync_prices(con, fetch=_fetch())
    before = con.execute("SELECT * FROM model_prices ORDER BY 1,2,3").fetchall()

    def broken(url):
        if "litellm" in url or "githubusercontent" in url:
            raise OSError("network unreachable")
        return OPENROUTER
    result = prices.sync_prices(con, fetch=broken)
    assert not result["ok"] and "unreachable" in result["error"]
    assert con.execute("SELECT * FROM model_prices ORDER BY 1,2,3").fetchall() == before
    err = con.execute("SELECT value FROM settings WHERE key='last_price_sync_error'").fetchone()
    assert "unreachable" in err[0]


def test_a_failure_part_way_through_rolls_back_everything(con, monkeypatch):
    real = prices.reprice_unpriced
    calls = []

    def explode(c, service, model):
        calls.append(model)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(c, service, model)
    monkeypatch.setattr(prices, "reprice_unpriced", explode)
    result = prices.sync_prices(con, fetch=_fetch())
    assert not result["ok"]
    assert con.execute("SELECT COUNT(*) FROM model_prices").fetchone()[0] == 0


def test_sync_prices_unpriced_events_for_a_newly_listed_model(con, tmp_path):
    db_path = con.execute("PRAGMA database_list").fetchone()[2]
    usage._warned_unpriced.clear()
    eid = usage.record_usage(db_path, service="openai", model="gpt-5.5",
                             operation="agent_pipeline", units={"input": 1000})
    feed = json.loads(json.dumps(OPENROUTER))
    feed["data"].append({"id": "openai/gpt-5.5", "pricing": {"prompt": "0.000005"}})
    prices.sync_prices(con, fetch=_fetch(openrouter=feed))
    con.commit()
    row = con.execute("SELECT cost_basis, cost_usd FROM usage_events WHERE id=?",
                      (eid,)).fetchone()
    assert row[0] == "priced" and row[1] == pytest.approx(0.005)
