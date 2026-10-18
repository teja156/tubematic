"""update_price_snapshot.py — the built-in model prices a fresh install starts from (TMDEV-107)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import update_price_snapshot as ups  # noqa: E402

OPENROUTER = {"data": [{"id": "google/gemini-2.5-flash",
                        "pricing": {"prompt": "0.0000003", "completion": "0.0000025"}}]}
LITELLM = {"gemini/gemini-2.5-flash": {"input_cost_per_token": 9e-07},
           "gpt-image-2.5-flare": {"input_cost_per_token": 5e-06}}


def test_build_applies_the_runtime_precedence(monkeypatch):
    monkeypatch.setattr(ups, "KNOWN_MODELS", [("gemini", "gemini-2.5-flash"),
                                              ("openai", "gpt-image-2.5-flare")])
    snap, missing = ups.build(OPENROUTER, LITELLM)
    assert missing == []
    assert snap["models"]["gemini/gemini-2.5-flash"]["source"] == "openrouter"
    assert snap["models"]["gemini/gemini-2.5-flash"]["rates"]["input"] == 3e-07
    assert snap["models"]["openai/gpt-image-2.5-flare"]["source"] == "litellm"


def test_a_missing_model_refuses_to_write(monkeypatch, tmp_path):
    monkeypatch.setattr(ups, "KNOWN_MODELS", [("gemini", "gemini-9-flash")])
    monkeypatch.setattr(ups.prices, "_fetch_json",
                        lambda url: OPENROUTER if "openrouter" in url else LITELLM)
    target = tmp_path / "snap.json"
    monkeypatch.setattr(ups.prices, "SNAPSHOT_PATH", target)
    assert ups.main([]) == 1
    assert not target.exists()


def test_the_shipped_snapshot_covers_every_known_model():
    """A known model missing from the committed snapshot is unpriced on every fresh install."""
    shipped = json.loads(ups.prices.SNAPSHOT_PATH.read_text())["models"]
    for service, model in ups.KNOWN_MODELS:
        assert f"{service}/{model}" in shipped, f"{service}/{model} missing from the snapshot"
