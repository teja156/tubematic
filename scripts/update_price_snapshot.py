#!/usr/bin/env python3
"""Refresh tubematic_core/prices_snapshot.json — the built-in model prices.

The snapshot is what a fresh install prices calls with before its first
weekly sync, and what an install that can never reach the feeds uses forever.
A maintainer runs this before each release and commits the result.

It applies exactly the precedence the runtime sync uses — OpenRouter when it
lists a model, LiteLLM only when it does not — to KNOWN_MODELS, and fails
rather than writing a snapshot that is missing a model Tubematic can select:
a missing row silently means "unpriced" on every fresh install.

Run from the repo root:
    python scripts/update_price_snapshot.py [--allow-missing]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import prices  # noqa: E402

# Every model Tubematic itself can select for a table-priced call. Keep in sync
# with: renderer/api/pipeline.py AI_REVIEW_MODELS and OPENAI_IMAGE_MODELS; the
# GEMINI_MODEL default (mining, publish metadata); the character_model setting
# (the same OpenAI catalog); and the Codex models an install commonly runs.
# The three Gemini image models are no longer selectable (TMDEV-165) but stay
# listed: the snapshot is rebuilt from this list, and dropping them would leave
# an install's past image spend in the usage ledger unpriced.
# Claude and OpenCode are absent on purpose — they report their own cost.
# ElevenLabs is absent on purpose — voice is recorded in credits, never priced.
KNOWN_MODELS = [
    ("gemini", "gemini-2.5-flash"),
    ("gemini", "gemini-3.5-flash"),
    ("gemini", "gemini-3.6-flash"),
    ("gemini", "gemini-2.5-flash-image"),
    ("gemini", "gemini-3.1-flash-image"),
    ("gemini", "gemini-3-pro-image"),
    ("openai", "gpt-image-2.5-flare"),
    ("openai", "gpt-image-2.5-sunburst"),
    ("openai", "gpt-5.6-sol"),
    ("openai", "gpt-5.5"),
]


def build(openrouter_feed: dict, litellm_feed: dict) -> tuple:
    """(snapshot dict, [missing "service/model"]) from the two raw feeds."""
    openrouter = prices.normalize_openrouter(openrouter_feed)
    litellm = prices.normalize_litellm(litellm_feed)
    models, missing = {}, []
    for service, model in KNOWN_MODELS:
        found = prices.resolve_from_feeds(service, model, openrouter, litellm)
        if found:
            models[f"{service}/{model}"] = found
        else:
            missing.append(f"{service}/{model}")
    snapshot = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "USD per token. Built by scripts/update_price_snapshot.py — do not edit by hand.",
        "models": models,
    }
    return snapshot, missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-missing", action="store_true",
                        help="write the snapshot even if a known model is in neither feed")
    args = parser.parse_args(argv)
    snapshot, missing = build(prices._fetch_json(prices.OPENROUTER_URL),
                              prices._fetch_json(prices.LITELLM_URL))
    for key, entry in snapshot["models"].items():
        print(f"  {key:<36} {entry['source']:<11} {entry['rates']}")
    if missing:
        print(f"  Not in either feed: {', '.join(missing)}", file=sys.stderr)
        if not args.allow_missing:
            print("  Refusing to write — re-run with --allow-missing to accept.", file=sys.stderr)
            return 1
    prices.SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"  Wrote {prices.SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
