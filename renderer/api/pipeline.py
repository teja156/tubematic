"""Flask blueprint for pipeline data API.

Reads/writes tubematic.db directly via sqlite3.
DB path is read from env var TUBEMATIC_DB (default: /data/tubematic.db).
This module does NOT import the MCP server — it accesses SQLite directly
using the same canonical schema.

Canonical schema column names (must match mcp/server.py):
  projects: id, name, description, is_curriculum_seed, status, created_at
  videos:   script, video_path (spend lives in usage_events, not on the video)
"""
import datetime as dt
import hashlib
import logging
import pathlib
import sys
import json as _json
import math
import os
import math
import random
import re
import shutil
import sqlite3
import time
import uuid
import zoneinfo
from contextlib import contextmanager
from pathlib import Path

from flask import Blueprint, g, jsonify, request

import discord_notify
import hosttz
import metrics as metrics_poll
import postforme
import transcripts
# The shared package lives at the repo root on the host and on PYTHONPATH
# (/app/lib) in the container. Host-side callers — vqa/make_seed_db.py,
# vqa/edit_settings.py, vqa/review_video.py — import this module with only its
# own directory on sys.path, so a bare import fails for them.
#
# Guarded rather than unconditional: in the container the first import succeeds
# and sys.path is left alone. That matters because the repo root holds an `mcp`
# directory whose name collides with the MCP SDK, and not touching sys.path when
# we do not have to is the cheapest way to keep that question closed.
try:
    from tubematic_core import logging as tlog
    from tubematic_core import db as tdb
    from tubematic_core import ids as tids
    from tubematic_core import jobfiles as tjobs
    from tubematic_core import prices as tprices
    from tubematic_core import usage as tusage
    from tubematic_core import version as tversion
    from tubematic_core import voice_models as tvoice
    from tubematic_core import youtube as tyoutube
except ModuleNotFoundError:  # pragma: no cover - exercised by the vqa scripts
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from tubematic_core import logging as tlog
    from tubematic_core import db as tdb
    from tubematic_core import ids as tids
    from tubematic_core import jobfiles as tjobs
    from tubematic_core import prices as tprices
    from tubematic_core import usage as tusage
    from tubematic_core import version as tversion
    from tubematic_core import voice_models as tvoice
    from tubematic_core import youtube as tyoutube

SETTINGS_SPEC = {
    "pipeline_paused":        ("bool",      "false"),
    # Off by default, and experimental (TMDEV-165). Keep in sync: onboard/
    # config.py GEMINI_REVIEW_ENABLED, its actions.py fallbacks, worker.py.
    "gemini_review_enabled":  ("bool",      "false"),
    # max_render_retries caps RENDER retries only — crash, timeout and
    # worker-restart reconciliation (worker.py::_max_render_retries). It used
    # to double as the AI-review loop cap; VQA-7 split those apart. It was
    # called max_feedback_loops until TMDEV-74, which renamed it because the
    # old name read like the AI-review loop it no longer governs — see the
    # one-time key rename in _init_db.
    "max_render_retries":     ("int",       "1"),
    "ai_review_max_loops":    ("int",       "1"),
    "ai_review_model":        ("str",       "gemini-2.5-flash"),
    "ai_review_fps":          ("int",       "10"),
    "max_curriculum_per_run": ("int",       "2"),
    "max_trending_per_run":   ("int",       "2"),
    "max_mining_per_run":     ("int",       "2"),
    "research_pending_cap":   ("int",       "15"),
    "max_research_runs_per_day": ("int",    "8"),
    "trending_sources":       ("json_list", '["GitHub Trending","Hacker News"]'),
    # elevenlabs_voice_id is the *default* voice — must be "" or the voice_id
    # of an entry in elevenlabs_voices. That invariant is enforced on read
    # (see _read_all_settings), not by rejecting writes here (TMDEV-51).
    "elevenlabs_voice_id":    ("str",       ""),
    # Each entry is {name, voice_id, model_id}: the ElevenLabs model follows
    # the voice (TMDEV-121). There is no install-wide model any more —
    # migration 0006 stamped every voice with the one the install was using.
    "elevenlabs_voices":      ("voice_list", "[]"),
    "pronunciation_lexicon":  ("lexicon",   "[]"),
    # Scene images; OpenAI is the only provider (TMDEV-165).
    # Keep in sync: mcp/server.py and onboard/config.py DEFAULT_IMAGE_MODEL.
    "image_model":            ("str",       "gpt-image-2.5-flare"),
    # The Illustrated style's transparent cut-outs.
    # Keep in sync: mcp/server.py DEFAULT_CHARACTER_MODEL.
    "character_model":        ("str",       "gpt-image-2.5-flare"),
    "render_timeout_secs":    ("int",       "2400"),
    # The cron poller's supervisor (TMDEV-129). max_concurrent_agent_sessions
    # caps the pipeline lane only — research and script profiles run beside it
    # in lanes of one each. Its default applies to an upgraded install too,
    # since spec defaults merge on read; the release notes tell a tight-budget
    # operator to set 1. agent_session_timeout_secs bounds one session, the
    # whole effort/model retry chain included; stored in seconds like
    # render_timeout_secs and shown in minutes.
    "max_concurrent_agent_sessions": ("int", "3"),
    "agent_session_timeout_secs":    ("int", "5400"),
    # Advisory pre-render text-layout audit in validate_job (VQA-9). A kill
    # switch, not a tuning knob — the audit's own time budget is a constant in
    # mcp/text_audit.py, since at ~0.3% of a render there is nothing to tune.
    "text_layout_audit_enabled": ("bool",   "true"),
    # The "Made with tubematic.ai" mark burned into every render (TMDEV-141).
    # A setting, and deliberately NOT a scene-config.json key: the agent writes
    # that file and has no tool that writes settings, so only a human can
    # switch the mark off. The worker reads this per render and passes it to
    # the composition as a prop.
    "watermark_enabled":      ("bool",      "true"),
    # Publishing to social platforms via postforme.dev (TMDEV-83). Off by
    # default — an install with no postforme account must behave exactly as it
    # did before the feature existed, with VIDEO_APPROVED reading as terminal.
    # Named "publishing", NOT "auto publishing": with this key alone every step
    # is human-driven (pick accounts, edit metadata, confirm), and a name
    # implying otherwise would invite a later reading that the cron agent may
    # post unattended. Unattended posting is Auto Pilot's, below, and it is the
    # worker that does it — still never the agent.
    "publishing_enabled":     ("bool",      "false"),
    # ── Discord notifications (TMDEV-5) ───────────────────────────────────────
    # Off by default in two independent ways: no webhook URL, and all three
    # triggers false. Both have to be set before anything is ever sent, so an
    # install that never opens this tab behaves exactly as it did before.
    #
    # discord_webhook_url is `secret`-typed, not `str`: the URL *is* the
    # credential — anyone holding it can post to that channel — so it is masked
    # at both /settings boundaries alongside the API keys below.
    "discord_webhook_url":    ("secret",    ""),
    "notify_topic_proposed":  ("bool",      "false"),
    "notify_script_ready":    ("bool",      "false"),
    "notify_video_ready":     ("bool",      "false"),
    # Where the dashboard is reachable from wherever Discord is read, e.g.
    # "http://192.168.1.20:3000". Blank means notifications carry no links at
    # all — there is no sane default to guess, since the container has no idea
    # what hostname a human reaches it by.
    "dashboard_base_url":     ("str",       ""),
    # ── Credentials (TMDEV-73) ────────────────────────────────────────────────
    # The DB is the single source of truth for API keys; .env is gone. Stored
    # raw — every consumer (mcp/server.py, worker.py, this module) reads SQLite
    # directly, none over HTTP — and masked only at the two /settings route
    # boundaries, never in _read_all_settings, which internal callers use.
    "elevenlabs_api_key":         ("secret", ""),
    "gemini_api_key":             ("secret", ""),
    "openai_api_key":             ("secret", ""),
    "youtube_transcript_api_key": ("secret", ""),
    # The highest-blast-radius credential here (TMDEV-83): it grants posting to
    # real social accounts, and postforme's own responses hand back the
    # connected channel's live OAuth tokens. Masked at both /settings
    # boundaries like the other four.
    "postforme_api_key":          ("secret", ""),
    # agent_model was retired as a settings key by TMDEV-90: the install-wide
    # default model is now each agent's models[0] in the agents table. See the
    # one-way delete in _init_db.
    # How long structured JSONL logs are kept (TMDEV-86). Applied by a
    # maintenance pass at service startup and at each daily rollover, so unlike
    # every other key here a change lands at the next pass rather than the next
    # read. That is still restart-free; it is just not instant.
    "log_retention_days":     ("int",       "14"),
    # Days after publishing before a PUBLISHED video's mp4 and job dir are
    # deleted and the row archived (TMDEV-84). 0 disables the sweep. Applied by
    # the render worker's hourly pass, so a change lands within the hour.
    "retention_days":         ("int",       "7"),
    # Days after a FAILED or TOPIC_REJECTED video last changed before its files
    # are deleted and the row archived (TMDEV-134). A separate key, off by
    # default, because retention_days governs output a human has already seen
    # published, while a failed video is paid-for output someone may still want
    # to inspect. Same hourly pass as retention_days.
    "unpublished_retention_days": ("int",   "0"),
    # The operator's standing preferences for every video, free text written in
    # the dashboard's Preferences tab (TMDEV-117). poll.py fences it into every
    # agent prompt and get_pipeline_status() returns it to interactive
    # sessions; "" means no block at all. Capped by MAX_USER_PREFERENCES_CHARS.
    "user_preferences":       ("str",       ""),
    # Auto Pilot (TMDEV-139): the worker approves every human checkpoint and
    # schedules the post, for the projects named in the auto_pilot_config row.
    # Off by default, and inert until a project is selected even when on. The
    # gap is the minimum time between two posts on one account, in minutes.
    # The in-progress limit (TMDEV-150, replacing TMDEV-143's scheduled-post
    # ceiling) is how many videos may be past the paid gate and unpublished
    # (in_flight_count) before Auto Pilot stops voicing new scripts and
    # approving topics; 0 means no limit.
    "auto_pilot_enabled":     ("bool",      "false"),
    "auto_pilot_gap_mins":    ("int",       "240"),
    "auto_pilot_max_in_flight": ("int",     "0"),
}

# How many trailing characters of a stored key a mask reveals. Enough to tell
# two keys apart when rotating; too few to be useful to anyone reading it.
SECRET_MASK_TAIL = 4

# Max named voices in the roster (TMDEV-51). Keep in sync with mcp/server.py,
# onboard/config.py and dashboard/app/settings/page.tsx.
MAX_VOICES = 10

# Voice preview generation (TMDEV-51 follow-up). Sample text is fixed, not a
# setting — nobody asked for it to be configurable, and it would need a
# fourth "keep in sync" copy alongside MAX_VOICES above.
OUTPUT_DIR = Path(os.getenv("OUTPUT_BASE_PATH", "/output_videos"))
VOICE_PREVIEW_SAMPLE_TEXT = (
    "Here's a quick preview of this voice, narrating a short animated explainer "
    "the way it would sound in a real Tubematic video."
)


def _elevenlabs_credits(resp, text: str) -> tuple:
    """(credits, estimated) for a 200 from ElevenLabs TTS.

    The `character-cost` header is the exact number of plan credits the call
    deducted, after the model's discount — verified against the account's
    credit counter. Only a response without it falls back to the character
    count, marked estimated.
    """
    try:
        return int(resp.headers.get("character-cost")), False
    except (TypeError, ValueError):
        return len(text), True

# Defensive cap on the install-wide pronunciation lexicon (TMDEV-26 follow-up)
# — generous relative to expected size (tens of terms), just a backstop
# against unbounded growth. Keep in sync with mcp/server.py MAX_LEXICON_ENTRIES.
MAX_LEXICON_ENTRIES = 500

# How many agent sessions a script profile gets before it is marked FAILED
# (TMDEV-81). Counted as *invocations*, not retries-after-the-first:
# record-attempt refuses at attempt_count >= this and never increments past
# it, so exactly this many agent sessions ever run for one profile.
MAX_PROFILE_ATTEMPTS = 2
# Defensive cap on one profile's source list — a corpus is a handful of
# videos, and each URL is a sequential network fetch inside one request.
MAX_PROFILE_URLS = 10
SCRIPT_PROFILE_STATUSES = ("PENDING", "GENERATING", "READY", "FAILED")

# How much of gemini_feedback a LIST payload carries (VQA-7). The stored value
# is uncapped, and GET /videos returns every row, so the list ships a preview
# and a gemini_feedback_truncated flag; GET /videos/<id> returns the whole
# thing. Generous enough that the overall critique and the first must-fix
# survive, since that is all any list view renders.
GEMINI_FEEDBACK_LIST_PREVIEW_CHARS = 1200

# The ElevenLabs model sets live in tubematic_core.voice_models (TMDEV-121) —
# the MCP server and this API both decide whether a voice can speak a script,
# and two hand-synced copies of that answer is how they would drift apart.
# Re-exported under their old names for the tests and the dashboard sync test.
PHONEME_COMPATIBLE_MODELS = tvoice.PHONEME_COMPATIBLE_MODELS
IPA_COMPATIBLE_MODELS = tvoice.IPA_COMPATIBLE_MODELS
DICTIONARY_COMPATIBLE_MODELS = tvoice.DICTIONARY_COMPATIBLE_MODELS

# The image-model catalog. OpenAI is the only image provider (TMDEV-165).
# Every model here must support transparent backgrounds — character_model
# is allowlisted against this same list (see mcp/server.py, TMDEV-148).
# Keep in sync with mcp/server.py, dashboard/app/settings/page.tsx and
# onboard/config.py.
OPENAI_IMAGE_MODELS = ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]

# Gemini models usable for the AI review (VQA-7). Distinct from the image
# catalogs above — these are video-understanding text models, and the review
# is the only call site with a video in it. Keep in sync with
# onboard/config.py, dashboard/app/settings/page.tsx, and the measured
# _TOKENS_PER_FRAME table in renderer/api/ai_review.py (a model listed here
# but missing there is charged the conservative fallback rate by the clamp,
# which is safe but throttles it unnecessarily).
#
# Cost, measured 2026-08-11 rather than read off the pricing page: per second
# of reviewed video the 3.x flash models are only ~1.4x gemini-2.5-flash, not
# the 5x their headline $1.50/M vs $0.30/M input price suggests — they
# tokenise video ~3.7x more cheaply (71 vs 263 tokens/frame).
# gemini-3.6-flash strictly dominates gemini-3.5-flash: same input price,
# cheaper output.
AI_REVIEW_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]
# Gemini's documented valid range for videoMetadata.fps is (0, 24].
# Keep in sync with ai_review.MAX_REVIEW_FPS.
MAX_AI_REVIEW_FPS = 24
# Ceiling on ai_review_max_loops, per VQA-7 ("default 1 and max to 2").
MAX_AI_REVIEW_LOOPS = 2

# Bounds on log_retention_days (TMDEV-86). The floor is 1 because 0 would mean
# "prune today's file", i.e. delete the logs a service is actively writing; the
# ceiling exists only so a fat-fingered value cannot quietly commit the host to
# keeping years of JSONL. Keep in sync with dashboard/app/settings/page.tsx.
MIN_LOG_RETENTION_DAYS = 1
MAX_LOG_RETENTION_DAYS = 365

# Bounds on retention_days (TMDEV-84). Unlike log retention, 0 is allowed and
# means "never sweep" — the one key has to carry the opt-out, because the
# default of 7 would otherwise fire on the first pass after an upgrade against
# every video published more than a week ago. Keep in sync with
# onboard/config.py and dashboard/app/settings/page.tsx.
MIN_RETENTION_DAYS = 0
MAX_RETENTION_DAYS = 365

# Bounds on Auto Pilot (TMDEV-139). The gap ceiling is a week: anything longer
# is a typo, and a daily number already caps the rate. The per-account daily
# number's ceiling stops a fat-fingered value flooding a real account; an
# account with no stored number posts AUTO_PILOT_DEFAULT_DAILY a day.
# Keep in sync with dashboard/lib/autoPilot.ts.
MAX_AUTO_PILOT_GAP_MINS = 7 * 24 * 60
MAX_AUTO_PILOT_DAILY = 50
AUTO_PILOT_DEFAULT_DAILY = 1
# The in-progress limit's own ceiling (TMDEV-143, renamed by TMDEV-150): far
# above any backlog a real install keeps, so it only catches a typo.
MAX_AUTO_PILOT_IN_FLIGHT = 500

# Ceiling on max_concurrent_agent_sessions (TMDEV-129). Each session is a paid
# agent run, so the ceiling exists to stop a fat-fingered value, not because 10
# is a tested limit. Keep in sync with dashboard/app/settings/page.tsx.
MAX_CONCURRENT_AGENT_SESSIONS = 10

# How many sessions in a row may leave a video at the status they found it at
# before the poller stops dispatching it (TMDEV-129). The looping supervisor
# would otherwise re-run a video the agent cannot move every few minutes; the
# cron tick used to be the only throttle. A constant by decision — a human
# releases a stuck video either way, so there is little to tune.
AGENT_NO_PROGRESS_CAP = 3

# Per-video job working files (audio, timeline, scene-config, images) live in
# JOBS_DIR/<video_id>. Same env var and default as mcp/server.py's JOBS_DIR,
# which is what writes them.
JOBS_DIR = Path(os.getenv("TUBEMATIC_JOBS_DIR", "/jobs"))

# The videos columns naming those files and the render. Written only by the
# code that writes the files; readers derive the real location from the ids
# (tubematic_core.jobfiles). Keep in sync with mcp/server.py.
SERVER_OWNED_PATH_FIELDS = frozenset(
    {"voice_file_path", "timeline_path", "scene_config_path", "video_path"})

# Where the structured JSONL logs live. /logs inside the container; overridable
# so host-side callers and tests can point somewhere writable, since a missing
# directory degrades to stdout-only rather than failing.
LOG_DIR = Path(os.getenv("TUBEMATIC_LOG_DIR", "/logs"))

# How many of a request's records a single GET /logs answer may carry, and the
# default when the caller does not say. The cap is a memory bound, not a policy:
# the reader holds every matched record in memory to merge the four services'
# files into one newest-first list.
DEFAULT_LOG_LIMIT = 200
MAX_LOG_LIMIT = 2000

log = logging.getLogger("api")

# Longest short display name a video may carry. Sized to the dashboard Kanban
# card: a 256px column less 12px padding each side leaves ~232px, which at the
# card's 13.5px sans fits ~34 characters per line, so 70 fills exactly two
# lines. Keep in sync: mcp/server.py's VIDEO_TITLE_MAX_LEN.
VIDEO_TITLE_MAX_LEN = 70

# The publish pair written with the script (TMDEV-132): YouTube's title limit,
# and a description that keeps postforme.compose_caption's title + blank line +
# description under Instagram's 2200. Keep in sync: mcp/server.py's copies.
PUBLISH_TITLE_MAX_LEN       = 100
PUBLISH_DESCRIPTION_MAX_LEN = 2000

# The one domain every video submitted from the dashboard's New Video page is
# filed into (TMDEV-118). Created on first use by POST /videos/manual, never by
# a migration, so an install that never uses the form never shows an empty
# domain. Not a curriculum seed, so research never generates topics for it and
# it cannot be paused. The description is what the research agent sees in
# list_projects(), and is what keeps its subject matching from filing a
# researched topic here.
MANUAL_PROJECT_ID = "manual"
MANUAL_PROJECT_NAME = "Manual Videos"
MANUAL_PROJECT_DESCRIPTION = (
    "Videos submitted by hand from the dashboard's New Video page. Not a subject domain: "
    "never file researched topics here."
)

# Longest user_preferences text (TMDEV-117). poll.py passes the whole prompt as
# ONE argv element, and Linux caps a single argument at 128 KiB (MAX_ARG_STRLEN)
# — past that every agent run would fail with E2BIG. The cap sits far below
# that because the text rides on every cron tick and is paid for in tokens each
# time. Keep in sync with dashboard/app/settings/page.tsx.
MAX_USER_PREFERENCES_CHARS = 6000


# ── Agent effort (TMDEV-106) ─────────────────────────────────────────────────
# The effort level the agent CLI runs at, the sibling of its model: an
# install-wide default on agents.effort, overridable per video on
# videos.agent_effort, and — like agent_model — settable only at a human
# checkpoint (AGENT_CHECKPOINT_FIELDS, TMDEV-110).
#
# A blank videos.agent_effort means "use this video's agent's effort", exactly
# as a blank agent_model means "use the agent's models[0]".
#
# Unlike a model, this is a closed set the CLI documents in its own --help, so
# it can be checked at write time rather than only from a finished run's
# output. Deliberately NOT a SETTINGS_SPEC key — TMDEV-90 removed agent_model
# from the spec on purpose, and the agents table is where per-agent defaults
# live now.
#
# Keep in sync: mcp/server.py's AGENT_EFFORTS, scripts/agent_adapters.py's
# ClaudeAdapter.EFFORTS (the canonical, CLI-facing copy) and
# dashboard/lib/agents.ts's AGENT_EFFORTS. Pinned by a cross-copy test.
AGENT_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_AGENT_EFFORT = "high"


# ── Visual register (TMDEV-101) ──────────────────────────────────────────────
# A video's visual_style is a PERMISSION SET, not a look. It says which
# vocabularies the agent may draw from, and which canvas the video is painted
# on. The per-beat treatment is still derived from each beat's subject.
#
#   motion_graphics — dark canvas. Vector animation and full-bleed generated
#                     imagery. No figures.
#   stick           — light canvas. HAND-DRAWN StickFigure line art, line-art
#                     diagrams, imagery contained in panels.
#   illustrated     — characters are GENERATED illustrated assets
#                     (generate_character) rather than line art, held
#                     consistent across scenes. It does NOT fix a drawing
#                     style: the agent picks one from the topic — playful
#                     stick-ish figures, or serious rendered illustration —
#                     and holds it video-wide. It does not fix the canvas
#                     either; the agent resolves that too.
#   auto            — no restriction at all. The agent picks the canvas and
#                     may use any vocabulary.
#
# Only motion_graphics and stick fix a canvas. illustrated and auto leave it to
# the agent, which is why CANVAS_BY_STYLE is a partial map and membership in it
# — not equality with "auto" — is the test for "has this been settled yet".
#
# The two named options are restrictions; auto is the absence of one. That is
# why auto can produce a video neither named option could: white-line-art
# figures for the role beats of an otherwise image-led, dark-canvas video.
# Keep in sync: the other copy of this block, and dashboard/lib/types.ts.
VISUAL_STYLES = ("auto", "motion_graphics", "stick", "illustrated")
DEFAULT_VISUAL_STYLE = "auto"

# "illustrated" draws its characters with OpenAI, the only provider with a
# transparent-background option, so without a key it cannot be produced at
# all. The key used to be consulted only by generate_character, after voicing,
# on a video whose style was already frozen — so the refusal now happens where
# the style is chosen. A key stored but later revoked is still caught only at
# use: probing the provider on every write would be worse than the problem.
# Keep in sync: the other copy of this block (pinned by an agreement test).
ILLUSTRATED_NEEDS_OPENAI_KEY = (
    "OpenAI API key not set. The illustrated visual style needs it — Gemini has no "
    "transparency option, so there is no fallback. Add an OpenAI key on the dashboard "
    "Settings page, or choose another visual style."
)

# Mining is the one strategy that needs a key: it sends YouTube URLs to Gemini.
# With no Gemini key it is off — derived at every read, never stored — so a
# key added later brings it back without re-ticking anything (TMDEV-165).
# Keep in sync: the other copy in mcp/server.py (pinned by an agreement test).
MINING_NEEDS_GEMINI_KEY = (
    "Gemini API key not set. The mining strategy sends YouTube videos to Gemini, so it "
    "cannot be turned on without one. Add a Gemini key on the dashboard Settings page "
    "(API Keys), or leave mining off."
)

# The canvas is the one property that cannot vary between the scenes of one
# video — alternating light and dark frames flashes, and a viewer reads that as
# a broken render rather than a style. It is therefore a single top-level key
# in scene-config.json, and the renderer paints it under every scene.
#
# The figure vocabulary is deliberately NOT tied to it. A stick figure is line
# art; it is black on light and white on dark, same geometry either way. Those
# two things were coupled in the first cut of this feature, and the coupling
# was what forced an entire image-led video onto a white canvas because one
# beat happened to be about "an attacker".
# Keep in sync: the other copy of this block and
# renderer/remotion/src/CompositionBuilder.tsx.
VALID_CANVASES = ("dark", "light")
CANVAS_BY_STYLE = {"motion_graphics": "dark", "stick": "light"}
DEFAULT_CANVAS = "dark"

# What videos.resolved_visual_style holds: the canvas "auto" settled on, and
# nothing else. It is named for the column rather than the concept; what it
# stores is a canvas, because the canvas is the only thing "auto" must fix for
# the life of the video. Everything else stays free per beat.
RESOLVED_VISUAL_STYLES = VALID_CANVASES


def effective_canvas(visual_style: str, resolved_visual_style: str) -> str:
    """The canvas a video is painted on, or "" if "auto" has not settled yet.

    A forced choice wins outright and the recorded resolution is ignored, so a
    video switched off "auto" cannot be held to an older automatic decision.
    Under "auto" the answer is whatever the agent recorded — and "" until it
    has recorded anything, which callers must handle rather than guessing: that
    is exactly the window in which a scene config may legitimately arrive
    carrying the agent's choice.
    Keep in sync: the other copy (pinned by an agreement test).
    """
    chosen = (visual_style or "").strip()
    if chosen in CANVAS_BY_STYLE:
        return CANVAS_BY_STYLE[chosen]
    return (resolved_visual_style or "").strip()


def figures_allowed(visual_style: str) -> bool:
    """Whether this video may contain character figures at all, of either kind.

    False only under a forced motion_graphics: that option's whole purpose is
    to exclude them. "auto" permits everything, and both stick options are
    built on them.
    Keep in sync: the other copy (pinned by an agreement test).
    """
    return (visual_style or "").strip() != "motion_graphics"


def line_art_allowed(visual_style: str) -> bool:
    """Whether this video's figures may be simple hand-drawn line art.

    Narrower than figures_allowed, and the difference is the whole point:
    "illustrated" HAS figures but they are generated character artwork, and
    hand-authored line art is exactly what that tier excludes. Telling the AI
    review that line art is intended on an illustrated video would license the
    one mistake the register forbids.

    True under "stick" (line art is the register) and "auto" (unrestricted, so
    a beat may legitimately reach for it). False under "illustrated" and under
    "motion_graphics", which has no figures at all.
    Keep in sync: the other copy (pinned by an agreement test).
    """
    return (visual_style or "").strip() in ("stick", "auto")


def characters_allowed(visual_style: str) -> bool:
    """Whether GENERATED character art (generate_character) is permitted.

    A narrower question than figures_allowed. Plain "stick" means hand-drawn
    StickFigure line art — that is what distinguishes it from "illustrated",
    and letting it reach for generated art would erase the difference the human
    chose between them. "auto" permits everything, by definition.

    The two must not be mixed inside one video: a line-art figure standing next
    to a rendered, shaded one reads as an asset that failed to load rather than
    as a style. That is prose in the skill; this is the tool-level guard.
    Keep in sync: the other copy (pinned by an agreement test).
    """
    return (visual_style or "").strip() in ("auto", "illustrated")


# ── Agents (TMDEV-90) ────────────────────────────────────────────────────────
# Rows are written only by the host-side installer (`python onboard.py
# --install-agent <name>`), never over HTTP: binary, run_path and models are
# validated there, against the real CLI. Every helper below is hand-duplicated
# in mcp/server.py (separate process). Keep in sync: mcp/server.py's copies.

def _agent_models(raw) -> list:
    """An agent row's models column as a list of strings; [] if corrupt.

    Failing to [] rather than raising means a broken row rejects every
    non-empty agent_model — the safe direction for a value that ends up on an
    external CLI's argv — instead of 500ing every read that touches it.
    """
    try:
        models = _json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
        return []
    return models


def _agent_dict(row) -> dict:
    return {
        "id":            row["id"],
        "name":          row["name"],
        "binary":        row["binary"],
        "run_path":      row["run_path"],
        "install_scope": row["install_scope"],
        "models":        _agent_models(row["models"]),
        "effort":        row["effort"],
        "is_default":    bool(row["is_default"]),
        "weight":        int(row["weight"]),
        "verified_at":   row["verified_at"],
        "archived_at":   row["archived_at"],
        "created_at":    row["created_at"],
        "updated_at":    row["updated_at"],
    }


def _pick_agent_id(con, rng=random):
    """The agent a new video is dealt, or None when none is installed. A human
    may move it to another at a checkpoint (TMDEV-110); that neither takes nor
    returns a card.

    Dealt from a shuffled deck, not drawn independently (user decision, for a
    deterministic split): each live agent with weight > 0 gets weight/gcd cards,
    the deck is shuffled, and each new video takes the next card. Every full
    deck therefore splits exactly by weight — 3:1 is 3 and 1 of every 4 — in a
    random order. The deck lives in agent_deck because Flask and MCP both create
    videos, and it is rebuilt when it runs out or when the live weights no
    longer match its signature. Candidates are ordered in SQL (created_at, then
    id — two installs in the same second share a created_at) so a seeded rng
    deals reproducibly. When every live weight is 0 the default agent wins,
    else the oldest, and the deck is left alone: a weight of 0 means "deal me no
    cards", not "never run anything".

    Call it inside the transaction that inserts the video. Its first statement
    is a write, which takes SQLite's write lock before the deck is read, so two
    processes can never deal the same card, and a rolled-back insert returns
    its card to the deck.

    Keep in sync: mcp/server.py's _pick_agent_id (pinned by an agreement test).
    """
    rows = con.execute(
        "SELECT id, is_default, weight FROM agents WHERE archived_at IS NULL "
        "ORDER BY created_at, id"
    ).fetchall()
    if not rows:
        return None
    candidates = [(r[0], r[2]) for r in rows if r[2] > 0]
    if not candidates:
        for r in rows:
            if r[1]:
                return r[0]
        return rows[0][0]
    divisor = math.gcd(*(w for _, w in candidates))
    signature = _json.dumps([[aid, w // divisor] for aid, w in candidates])
    con.execute("INSERT OR IGNORE INTO agent_deck (id, signature, cards) VALUES (1, '', '[]')")
    stored = con.execute("SELECT signature, cards FROM agent_deck WHERE id = 1").fetchone()
    try:
        cards = _json.loads(stored[1]) if stored[0] == signature else []
    except ValueError:
        cards = []
    if not cards:
        cards = [aid for aid, w in candidates for _ in range(w // divisor)]
        rng.shuffle(cards)
    card = cards.pop()
    con.execute("UPDATE agent_deck SET signature = ?, cards = ? WHERE id = 1",
                (signature, _json.dumps(cards)))
    return card


def _effective_agent(con, agent_id):
    """The agent a video runs under, as a dict, or None.

    A pinned agent_id resolves to that row even when archived, so a video keeps
    showing (and being checked against) the agent it was created with. NULL
    means "the default at dispatch time": the live is_default agent, else the
    oldest live one.
    """
    if agent_id:
        row = con.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    else:
        row = con.execute(
            "SELECT * FROM agents WHERE archived_at IS NULL "
            "ORDER BY is_default DESC, created_at, id LIMIT 1"
        ).fetchone()
    return _agent_dict(row) if row else None


def _agent_model_error(con, agent_id, model: str):
    """Why `model` cannot be a video's agent_model, or None if it can.

    "" is always allowed — it means the agent's own default model. Anything
    else must be one of the video's agent's installed models, and that agent
    must still be live.
    """
    if not model:
        return None
    agent = _effective_agent(con, agent_id)
    if agent is None:
        if agent_id:
            return (f"This video's agent {agent_id!r} is not installed, so agent_model "
                    f"cannot be set")
        return ("No agent is installed, so agent_model cannot be set. Install one on the "
                "host with: python onboard.py --install-agent <agent>")
    if agent["archived_at"]:
        return (f"This video's agent {agent['id']!r} is uninstalled, so agent_model can no "
                f"longer be set (its models were {agent['models']})")
    if not agent["models"]:
        return (f"Agent {agent['id']!r} has no usable model list (empty or unreadable). "
                f"Re-run on the host: python onboard.py --install-agent {agent['id']}")
    if model not in agent["models"]:
        return (f"agent_model {model!r} is not one of agent {agent['id']!r}'s installed "
                f"models: {agent['models']}")
    return None


def _agent_id_error(con, stored_agent_id, agent_id: str):
    """Why a video cannot be moved to `agent_id`, or None if it can (TMDEV-110).

    Only a live agent can be handed new work. The one exception is the video's
    own stored agent: naming it again is a no-op, so a client echoing the
    current value never fails — even when that agent has since been uninstalled.
    Keep in sync: mcp/server.py's _agent_id_error.
    """
    if agent_id == stored_agent_id:
        return None
    row = con.execute("SELECT archived_at FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if row is None:
        return (f"agent_id {agent_id!r} is not an installed agent. Pick one from GET /agents, "
                f"or install it on the host with: python onboard.py --install-agent {agent_id}")
    if row["archived_at"]:
        return (f"agent_id {agent_id!r} is uninstalled, so no work can be handed to it. Pick a "
                f"live agent, or re-install it with: python onboard.py --install-agent {agent_id}")
    return None


def _script_profile_error(con, profile_id: str):
    """Why `profile_id` cannot be a video's script profile, or None if it can.
    Only a READY, unarchived profile can be written in; the caller skips ""
    (no profile), which is always allowed."""
    row = con.execute(
        "SELECT status FROM script_profiles WHERE id = ? AND archived = 0", (profile_id,)
    ).fetchone()
    if not row or row["status"] != "READY":
        return f"script_profile_id {profile_id!r} is not a READY script profile"
    return None


def _truncate_title(title: str) -> tuple:
    """Clip an over-length display name to VIDEO_TITLE_MAX_LEN.

    Returns (title, warning); warning is "" when nothing was clipped. Cuts at
    the last whitespace at or before the cap so the name does not end mid-word,
    falling back to a hard cut for a single long token. Deliberately adds no
    ellipsis — one inside a display name reads as corruption, and the full text
    is always still in the video's topic.

    Keep in sync: mcp/server.py's _truncate_title.
    """
    if len(title) <= VIDEO_TITLE_MAX_LEN:
        return title, ""
    head = title[:VIDEO_TITLE_MAX_LEN]
    cut = head.rstrip()
    if " " in head.strip():
        cut = head[:head.rstrip().rfind(" ")].rstrip()
    cut = cut or head
    return cut, (f"title was {len(title)} characters and was clipped to "
                 f"{len(cut)} (max {VIDEO_TITLE_MAX_LEN}); the full text is in topic")


# Domain pause (TMDEV-115). Pausing used to be honoured only because prose
# asked the agent to, so create_video now refuses a paused domain itself.
# The refusal deliberately never mentions that strategy="manual" is exempt:
# the agent supplies strategy, so saying so would teach it to relabel a
# candidate and walk past the pause. It says "skip" because an agent refused
# on the direct path looks for another one — refiling into a sibling domain or
# creating a new one would defeat the pause just as surely.
#
# Domain topic cap (TMDEV-153). Research deduplicates against a domain's whole
# topic history, archived videos included (list_project_topics), so each domain
# caps how many topics it may ever hold. A domain whose count of videos ever
# filed — archived, rejected and failed included — has reached its topic_cap is
# expired, and is refused exactly like a paused one, manual exemption and all.
# Expired is derived on every read, never stored, so raising the cap re-opens
# the domain with nothing to keep in sync. The bounds keep the history list a
# size an agent can read. Keep in sync: dashboard/app/topics/page.tsx's copies
# of the bounds and tubematic_core/migrations/0013's column default.
#
# Keep in sync: mcp/server.py's copies of this whole block, pinned by
# tests/test_project_pause.py::test_the_messages_match_the_mcp_copy.
TOPIC_CAP_MIN = 25
TOPIC_CAP_MAX = 750
TOPIC_CAP_DEFAULT = 100

# A domain's count of videos ever filed, for a projects row aliased p.
_TOPIC_COUNT_SQL = "(SELECT COUNT(*) FROM videos v WHERE v.project_id = p.id)"

# Every project read returns the derived topic_count; _project_out adds expired.
_PROJECT_SELECT = f"SELECT p.*, {_TOPIC_COUNT_SQL} AS topic_count FROM projects p"

# _DOMAIN_OPEN_GUARD is the pause and the cap as a WHERE clause for an
# INSERT ... SELECT, so the write re-checks them atomically: an early SELECT
# runs outside any transaction and cannot see a pause, or another session's
# topic, that commits after it. An unknown project_id passes, as before.
# Parameters, in order: strategy, project_id.
_DOMAIN_OPEN_GUARD = ("(? = 'manual' OR NOT EXISTS "
                      "(SELECT 1 FROM projects p WHERE p.id = ? AND "
                      f"(p.status = 'paused' OR {_TOPIC_COUNT_SQL} >= p.topic_cap)))")


def _project_out(row) -> dict:
    """A projects row read through _PROJECT_SELECT, with expired derived."""
    out = dict(row)
    out["expired"] = out["topic_count"] >= out["topic_cap"]
    return out


def _paused_domain_error(project_id: str, name: str) -> str:
    return (f"Project '{name}' ({project_id}) is paused: topic generation for this domain is "
            f"stopped. Skip this candidate. Do not file it into another domain and do not "
            f"create a new domain for it.")


def _expired_domain_error(project_id: str, name: str, count: int, cap: int) -> str:
    return (f"Project '{name}' ({project_id}) is expired: it holds {count} topics and its topic "
            f"cap is {cap}, so it takes no new topics. Skip this candidate. Do not file it into "
            f"another domain and do not create a new domain for it.")


def _closed_domain_error(con, project_id) -> str | None:
    """Why research may not file into project_id — paused or expired — or None
    when it may (an unknown project_id included)."""
    row = con.execute(f"{_PROJECT_SELECT} WHERE p.id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    if row["status"] == "paused":
        return _paused_domain_error(project_id, row["name"])
    if row["topic_count"] >= row["topic_cap"]:
        return _expired_domain_error(project_id, row["name"], row["topic_count"],
                                     row["topic_cap"])
    return None


def _topic_cap_error(value) -> str | None:
    """Why value cannot be a domain's topic_cap, or None. bool is refused
    although it is an int: True would quietly store a cap of 1."""
    if isinstance(value, bool) or not isinstance(value, int) or not (
            TOPIC_CAP_MIN <= value <= TOPIC_CAP_MAX):
        return (f"topic_cap must be a whole number from {TOPIC_CAP_MIN} to {TOPIC_CAP_MAX}, "
                f"got {value!r}")
    return None

# A domain's description is a scope statement the agent reads on every research
# run: list_projects() returns every domain's full row, so the cost is this cap
# times the number of domains, on every call (TMDEV-170). Counted in code points,
# as len() counts. Checked only when the description CHANGES — POST /projects is
# a full replace the dashboard re-sends on every edit, so a longer one stored
# before the cap must not block unrelated edits. Keep in sync:
# dashboard/app/topics/page.tsx's MAX_DOMAIN_DESCRIPTION_CHARS.
PROJECT_DESCRIPTION_MAX_CHARS = 2000


def _description_error(value) -> str | None:
    """Why value cannot be a domain's description, or None."""
    if not isinstance(value, str):
        return f"description must be a string, got {type(value).__name__}"
    if len(value) > PROJECT_DESCRIPTION_MAX_CHARS:
        return (f"description must be at most {PROJECT_DESCRIPTION_MAX_CHARS} characters, "
                f"got {len(value)}")
    return None



def _non_seed_pause_error(project_id: str) -> str:
    return (f"Project '{project_id}' is not a curriculum seed, and only a curriculum seed can "
            f"be paused. Pausing stops topics being generated FROM a seed; any other domain "
            f"only receives topics researched elsewhere, so a pause there could not stop them.")


def _coerce_setting(key: str, raw) -> tuple:
    """Coerce raw value for key according to SETTINGS_SPEC.

    Returns (python_value, string_for_db).
    Raises ValueError on invalid input.
    """
    if key not in SETTINGS_SPEC:
        raise KeyError(f"Unknown setting: {key}")
    typ, _ = SETTINGS_SPEC[key]

    if typ == "bool":
        if isinstance(raw, bool):
            py_val = raw
        elif isinstance(raw, str) and raw.lower() in ("true", "false"):
            py_val = raw.lower() == "true"
        else:
            raise ValueError(f"Expected true/false for {key}, got {raw!r}")
        return (py_val, "true" if py_val else "false")

    if typ == "int":
        try:
            int_val = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Expected integer for {key}, got {raw!r}")
        if int_val < 0:
            raise ValueError(f"Expected non-negative integer for {key}, got {int_val}")
        # A too-low render_timeout_secs isn't just unwise, it's self-defeating:
        # below some floor no render can ever complete before timing out, and
        # every attempt burns a retry (TMDEV-57).
        if key == "render_timeout_secs" and int_val < 60:
            raise ValueError(
                f"render_timeout_secs must be at least 60 seconds — a lower value "
                f"guarantees every render times out before completing, got {int_val}"
            )
        # A timeout under a minute kills every session before the agent CLI
        # has even connected to MCP; 0 concurrent sessions would stop the
        # pipeline in a way that reads as a fault rather than a pause.
        if key == "agent_session_timeout_secs" and int_val < 60:
            raise ValueError(
                f"agent_session_timeout_secs must be at least 60 seconds, got {int_val}"
            )
        if key == "max_concurrent_agent_sessions" and not (
            1 <= int_val <= MAX_CONCURRENT_AGENT_SESSIONS
        ):
            raise ValueError(
                f"max_concurrent_agent_sessions must be between 1 and "
                f"{MAX_CONCURRENT_AGENT_SESSIONS} (pause the pipeline to stop it), got {int_val}"
            )
        # Gemini rejects an fps outside (0, 24] with a 400, and this pipeline
        # fails open on a review error — so an out-of-range value here would
        # silently ship every video unreviewed rather than erroring loudly.
        if key == "ai_review_fps" and not (1 <= int_val <= MAX_AI_REVIEW_FPS):
            raise ValueError(
                f"ai_review_fps must be between 1 and {MAX_AI_REVIEW_FPS} "
                f"(Gemini's valid videoMetadata.fps range), got {int_val}"
            )
        # 0 would mean "delete the file this service is writing right now".
        if key == "log_retention_days" and not (
            MIN_LOG_RETENTION_DAYS <= int_val <= MAX_LOG_RETENTION_DAYS
        ):
            raise ValueError(
                f"log_retention_days must be between {MIN_LOG_RETENTION_DAYS} and "
                f"{MAX_LOG_RETENTION_DAYS}, got {int_val}"
            )
        if key in ("retention_days", "unpublished_retention_days") and not (
            MIN_RETENTION_DAYS <= int_val <= MAX_RETENTION_DAYS
        ):
            raise ValueError(
                f"{key} must be between {MIN_RETENTION_DAYS} and "
                f"{MAX_RETENTION_DAYS} (0 disables the sweep), got {int_val}"
            )
        if key == "auto_pilot_gap_mins" and int_val > MAX_AUTO_PILOT_GAP_MINS:
            raise ValueError(
                f"auto_pilot_gap_mins must be between 0 and "
                f"{MAX_AUTO_PILOT_GAP_MINS}, got {int_val}"
            )
        if key == "auto_pilot_max_in_flight" and int_val > MAX_AUTO_PILOT_IN_FLIGHT:
            raise ValueError(
                f"auto_pilot_max_in_flight must be between 0 and "
                f"{MAX_AUTO_PILOT_IN_FLIGHT} (0 means no limit), got {int_val}"
            )
        # 0 would disable the revision loop entirely rather than meaning
        # "review once", because the routing boundary is `count > cap`.
        if key == "ai_review_max_loops" and not (1 <= int_val <= MAX_AI_REVIEW_LOOPS):
            raise ValueError(
                f"ai_review_max_loops must be between 1 and {MAX_AI_REVIEW_LOOPS}, "
                f"got {int_val}"
            )
        return (int_val, str(int_val))

    if typ == "json_list":
        if isinstance(raw, str):
            try:
                parsed = _json.loads(raw)
            except _json.JSONDecodeError:
                raise ValueError(f"Expected JSON list for {key}, got {raw!r}")
        elif isinstance(raw, list):
            parsed = raw
        else:
            raise ValueError(f"Expected list for {key}, got {raw!r}")
        if not all(isinstance(e, str) for e in parsed):
            raise ValueError(f"All elements in {key} must be strings")
        return (parsed, _json.dumps(parsed))

    if typ == "voice_list":
        if isinstance(raw, str):
            try:
                parsed = _json.loads(raw)
            except _json.JSONDecodeError:
                raise ValueError(f"Expected JSON list for {key}, got {raw!r}")
        elif isinstance(raw, list):
            parsed = raw
        else:
            raise ValueError(f"Expected list for {key}, got {raw!r}")
        if len(parsed) > MAX_VOICES:
            raise ValueError(f"{key} allows at most {MAX_VOICES} voices, got {len(parsed)}")
        names, ids = set(), set()
        for entry in parsed:
            if not isinstance(entry, dict) or set(entry) != {"name", "voice_id", "model_id"}:
                raise ValueError(f"Each entry in {key} must be {{name, voice_id, model_id}}, "
                                 f"got {entry!r}")
            name, voice_id = entry["name"], entry["voice_id"]
            # Type first: a list or dict is unhashable, and a TypeError here
            # would escape both this 400 and _read_all_settings' fallback.
            if not isinstance(entry["model_id"], str) \
                    or entry["model_id"] not in DICTIONARY_COMPATIBLE_MODELS:
                raise ValueError(f"Voice {name!r} in {key} has model_id {entry['model_id']!r}; "
                                 f"it must be one of {sorted(DICTIONARY_COMPATIBLE_MODELS)}")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Each voice name in {key} must be a non-empty string")
            if not isinstance(voice_id, str) or not voice_id.strip():
                raise ValueError(f"Each voice_id in {key} must be a non-empty string")
            if name in names:
                raise ValueError(f"Duplicate voice name {name!r} in {key}")
            if voice_id in ids:
                raise ValueError(f"Duplicate voice_id {voice_id!r} in {key}")
            names.add(name)
            ids.add(voice_id)
        return (parsed, _json.dumps(parsed))

    if typ == "lexicon":
        if isinstance(raw, str):
            try:
                parsed = _json.loads(raw)
            except _json.JSONDecodeError:
                raise ValueError(f"Expected JSON list for {key}, got {raw!r}")
        elif isinstance(raw, list):
            parsed = raw
        else:
            raise ValueError(f"Expected list for {key}, got {raw!r}")
        if len(parsed) > MAX_LEXICON_ENTRIES:
            raise ValueError(f"{key} allows at most {MAX_LEXICON_ENTRIES} entries, got {len(parsed)}")
        terms = set()
        for entry in parsed:
            if not isinstance(entry, dict) or set(entry) != {"term", "respell"}:
                raise ValueError(f"Each entry in {key} must be {{term, respell}}, got {entry!r}")
            term, respell = entry["term"], entry["respell"]
            if not isinstance(term, str) or not term.strip():
                raise ValueError(f"Each term in {key} must be a non-empty string")
            if not isinstance(respell, str) or not respell.strip():
                raise ValueError(f"Each respell in {key} must be a non-empty string")
            if re.search(r"\s", respell):
                # Keep the advice in sync with mcp/server.py's two equivalent
                # messages (_validate_respell_tags and
                # upsert_pronunciation_lexicon). This is the path a
                # vqa/edit_settings.py user hits; those are the paths an agent
                # hits. All three must teach the same form, or the no-hyphen
                # rule is learnable from one route and missable from another.
                raise ValueError(f"respell {respell!r} for term {term!r} in {key} contains "
                                  "whitespace — it must be a single token. To spell a SOUND, "
                                  "use one plain word ('Daymon', not 'Day-mon': ElevenLabs "
                                  "does not speak a hyphenated respelling correctly). To "
                                  "spell an ACRONYM out letter by letter, join the letters "
                                  "with hyphens ('S-Y-N')")
            if term in terms:
                raise ValueError(f"Duplicate term {term!r} in {key}")
            terms.add(term)
        return (parsed, _json.dumps(parsed))

    if typ == "str":
        if not isinstance(raw, str):
            raise ValueError(f"Expected string for {key}, got {raw!r}")
        stripped = raw.strip()
        if key == "image_model" and stripped not in OPENAI_IMAGE_MODELS:
            raise ValueError(
                f"image_model must be one of {OPENAI_IMAGE_MODELS}, got {stripped!r}"
            )
        if key == "character_model" and stripped not in OPENAI_IMAGE_MODELS:
            raise ValueError(
                f"character_model must be one of {OPENAI_IMAGE_MODELS} (models that can draw "
                f"a transparent background), got {stripped!r}"
            )
        # Allowlisted, unlike TUBEMATIC_AGENT_MODEL (TMDEV-63, free-text): the
        # review clamp needs a measured tokens-per-frame figure per model, so
        # an unvetted id would silently fall back to the conservative rate.
        if key == "ai_review_model" and stripped not in AI_REVIEW_MODELS:
            raise ValueError(
                f"ai_review_model must be one of {sorted(AI_REVIEW_MODELS)}, got {stripped!r}"
            )
        # Stored without a trailing slash so every consumer can concatenate a
        # rooted path without producing "//" (TMDEV-5). "" stays "" — that is
        # how links are turned off.
        if key == "dashboard_base_url" and stripped:
            if not re.match(r"^https?://[^\s/]+", stripped):
                raise ValueError(
                    f"dashboard_base_url must start with http:// or https://, got {stripped!r}"
                )
            stripped = stripped.rstrip("/")
        # The text is carried inside an agent's argv, and exec refuses an
        # argument with an embedded NUL — stored, it would fail every tick.
        if key == "user_preferences" and "\x00" in stripped:
            raise ValueError("user_preferences must not contain a NUL character")
        if key == "user_preferences" and len(stripped) > MAX_USER_PREFERENCES_CHARS:
            raise ValueError(
                f"user_preferences must be at most {MAX_USER_PREFERENCES_CHARS} characters, "
                f"got {len(stripped)}"
            )
        return (stripped, stripped)

    if typ == "secret":
        if not isinstance(raw, str):
            raise ValueError(f"Expected string for {key}, got {raw!r}")
        # Strip before validating: a key pasted from a provider dashboard
        # routinely carries a trailing newline, and an un-stripped one fails
        # later as an opaque 401 rather than here as a clear error.
        stripped = raw.strip()
        # "" is legal and means "unset" — that is how a key is cleared.
        if stripped and re.search(r"\s", stripped):
            raise ValueError(
                f"{key} must not contain whitespace — check for a partial paste"
            )
        # Shape only — the live probe that decides whether this webhook still
        # exists lives in post_settings, because it needs the network and this
        # function is called from places that must stay pure (TMDEV-5).
        if key == "discord_webhook_url" and stripped:
            discord_notify.parse_webhook_url(stripped)
        return (stripped, stripped)

    raise ValueError(f"Unknown type {typ!r} for {key}")


# YouTube classifies a Short from the file itself — vertical aspect AND
# duration at or under 3 minutes. There is no flag to send: neither postforme
# nor the YouTube Data API has one. Aspect always qualifies here (every render
# is 1080x1920), so duration is the only thing that decides it, and nothing
# enforces it: TMDEV-81 left the ~450-word script budget to prose in the skill.
YOUTUBE_SHORTS_MAX_SECS = 180


def _video_duration_secs(video_id: str):
    """Finished duration from the video's own timeline.json, or None.

    Read from the file rather than probed from the mp4: it is already written by
    generate_voice, it is authoritative (the render is built to it), and it
    costs no subprocess. The path is derived from the id, never taken from
    videos.timeline_path, which a caller could once write (TMDEV-162).
    """
    try:
        path = tjobs.job_file(JOBS_DIR, video_id, tjobs.TIMELINE)
        with open(path) as fh:
            timeline = _json.load(fh)
    except (OSError, ValueError):  # UnsafePath is a ValueError
        return None
    if not isinstance(timeline, dict):
        return None
    duration = timeline.get("audioDurationSeconds")
    if isinstance(duration, (int, float)) and duration > 0:
        return float(duration)
    frames, fps = timeline.get("totalFrames"), timeline.get("fps") or 30
    if isinstance(frames, (int, float)) and frames > 0 and fps:
        return float(frames) / float(fps)
    return None


def _output_path(project_id: str, video_id: str):
    """Where the worker renders this video's mp4, or None if it cannot be named.

    Derived from the ids (tubematic_core.jobfiles.output_file), never from
    videos.video_path. That column was writable by PATCH and update_video, and
    archive, retention and publish all used its basename, so one video's row
    could name another's render to be deleted or posted (TMDEV-159). An id
    that would escape OUTPUT_DIR answers None: there is nothing to touch.
    """
    try:
        return tjobs.output_file(OUTPUT_DIR, project_id, video_id)
    except tjobs.UnsafePath as e:
        log.warning("refusing output path for %s: %s", video_id, e,
                    extra={"video_id": video_id})
        return None


def _elevenlabs_pool(api_key: str):
    """The plan's credit pool from ElevenLabs, or None.

    Needs the key's optional `user_read` permission; any failure — no key, a
    scoped key's 401, a timeout — is None, never an error, because this is a
    convenience on the Analytics card and must never fail it.
    """
    if not api_key:
        return None
    try:
        import httpx as _httpx
        resp = _httpx.get("https://api.elevenlabs.io/v1/user/subscription",
                          headers={"xi-api-key": api_key}, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {"tier": data.get("tier"), "used": int(data.get("character_count") or 0),
                "limit": int(data.get("character_limit") or 0),
                "resets_at_unix": data.get("next_character_count_reset_unix")}
    except Exception:
        return None


def _mask_secret(value: str) -> str:
    """Render a stored secret for display. Never reveals a usable key."""
    if not value:
        return ""
    if len(value) <= SECRET_MASK_TAIL:
        return "•" * len(value)
    return "•" * 8 + value[-SECRET_MASK_TAIL:]


def _secret(settings: dict, key: str, env_var: str) -> str:
    """A credential from the settings table, falling back to the environment.

    The DB is the source of truth (TMDEV-73); env survives only so a compose
    `environment:` entry still works, which is how docker-compose.test.yml
    supplies its dummy keys. Callers pass an already-read settings dict, since
    both call sites hold one anyway.
    """
    return settings.get(key, "") or os.environ.get(env_var, "")


def _mining_available(con) -> bool:
    """Whether a Gemini key is stored — settings row, then environment, the same
    way mcp/server.py's _gemini_key reads it."""
    return bool(_secret(_read_all_settings(con), "gemini_api_key", "GEMINI_API_KEY"))


def _stored_strategies(con) -> list:
    row = con.execute("SELECT value FROM settings WHERE key = 'active_strategies'").fetchone()
    stored = row[0].split(",") if row else ["curriculum", "trending", "mining"]
    return [s for s in stored if s]


def _active_strategies(con) -> list:
    """The research strategies in effect: the stored list, minus mining while
    no Gemini key is stored. The row itself is left alone (TMDEV-165)."""
    mining_available = _mining_available(con)
    return [s for s in _stored_strategies(con) if s != "mining" or mining_available]


def _illustrated_needs_key(con, style: str) -> bool:
    """True when `style` is "illustrated" and no OpenAI key is stored.

    Reads the key the same way mcp/server.py's _openai_key does — settings row,
    then environment — so the two write paths agree on what "stored" means.
    """
    if style != "illustrated":
        return False
    return not _secret(_read_all_settings(con), "openai_api_key", "OPENAI_API_KEY")


def _voice_state(video: dict, settings: dict) -> tuple:
    """(effective_voice_id, voice_conflicts) for a video whose script_segments
    are already decoded (TMDEV-121).

    effective_voice_id is the voice generate_voice would use — the video's
    own, else the install default — or "" when neither is in the roster.
    voice_conflicts maps every roster voice that cannot speak this video's
    script to the reason. It is what patch_video refuses on AND what the
    dashboard greys out, computed in one place so the two cannot disagree.
    An unscripted video conflicts with nothing, and neither does one at
    TOPIC_PROPOSED (TMDEV-127): a topic revision can send a scripted video
    back there with its old script still stored, but approving the topic has
    that script rewritten for whichever voice the human picks, so refusing a
    voice over it would block the one checkpoint built for choosing freely.
    Keep in sync with mcp/server.py's update_video.
    """
    roster = settings["elevenlabs_voices"]
    current = tvoice.resolve_voice(video.get("voice_id") or "",
                                   settings["elevenlabs_voice_id"], roster)
    segments, script = video.get("script_segments"), video.get("script") or ""
    conflicts = {}
    if (segments or script) and video.get("status") != "TOPIC_PROPOSED":
        for v in roster:
            err = tvoice.markup_conflict(segments, script, v["model_id"], voice_label=v["name"])
            if err:
                conflicts[v["voice_id"]] = err
    return (current["voice_id"] if current else ""), conflicts


# Statuses before a video's audio exists. A video here may still hold a ledger
# row from an earlier voicing that a revision is about to redo, possibly with
# another voice, so that row's model says nothing about the next one.
_PRE_VOICE_STATUSES = frozenset({"TOPIC_PROPOSED", "TOPIC_APPROVED", "SCRIPT_READY", "VOICING"})


def _voice_info(con, video: dict, settings: dict) -> dict:
    """The voice and ElevenLabs model the video modal shows (TMDEV-147).

    The voice is the video's own voice_id, else the install default — kept
    even when it has left the roster, so a removed voice still reads as its id.
    The model is the one the latest voicing call was sent with, read from the
    usage ledger: a roster voice's model can be edited after voicing, so the
    roster cannot say what the audio was made with. Before voicing, or for a
    video voiced before the ledger existed, it is the voice's current roster
    model, and model_voiced says which of the two it is.
    """
    voice_id = video.get("voice_id") or settings["elevenlabs_voice_id"] or ""
    entry = next((v for v in settings["elevenlabs_voices"] if v["voice_id"] == voice_id), None)
    voiced = None
    if video.get("status") not in _PRE_VOICE_STATUSES:
        voiced = tusage.last_voice_model(con, video["id"])
    return {
        "voice_id": voice_id,
        "name": entry["name"] if entry else "",
        "model_id": voiced or (entry["model_id"] if entry else ""),
        "model_voiced": bool(voiced),
    }


def _project_default_voice(con, project_id, settings: dict) -> str:
    """The voice a new video in project_id is seeded with (TMDEV-121): the
    project's default_voice_id while that voice is still in the roster, else
    "" (the install default). Seeded, never resolved later, so changing a
    project's default never reaches back to videos already filed there."""
    if not project_id:
        return ""
    row = con.execute("SELECT default_voice_id FROM projects WHERE id = ?",
                      (project_id,)).fetchone()
    voice_id = (row[0] if row else "") or ""
    roster_ids = {v["voice_id"] for v in settings["elevenlabs_voices"]}
    return voice_id if voice_id in roster_ids else ""


def _mask_settings(data: dict) -> dict:
    """Copy of `data` with every secret-typed value replaced by its mask.

    Applied at the /settings route boundary only — _read_all_settings stays raw
    because five internal callers (roster checks, the research cap, the
    post_settings cross-field merge) need real values.
    """
    masked = dict(data)
    for key, (typ, _) in SETTINGS_SPEC.items():
        if typ == "secret":
            masked[key] = _mask_secret(masked.get(key, ""))
    return masked


def _read_all_settings(con) -> dict:
    """Read all settings from DB, merge with SETTINGS_SPEC defaults, coerce types."""
    rows = con.execute("SELECT key, value FROM settings").fetchall()
    stored = {r[0]: r[1] for r in rows}
    result = {}
    for key, (typ, default) in SETTINGS_SPEC.items():
        raw_str = stored.get(key, default)
        try:
            py_val, _ = _coerce_setting(key, raw_str)
        except (ValueError, KeyError):
            # Stored value is corrupt — fall back to spec default. Note this
            # resets an over-cap/malformed elevenlabs_voices to [] rather than
            # truncating it.
            py_val, _ = _coerce_setting(key, default)
        result[key] = py_val
    # Normalize the default-voice invariant here rather than rejecting writes
    # in post_settings: elevenlabs_voices can independently reset to [] above
    # (a corrupt stored list) while elevenlabs_voice_id still names a real
    # voice_id, and a hard cross-field check would then reject the next
    # unrelated settings save with a 400 that has nothing to do with voices.
    # Blanking it here instead makes "default is '' or in the roster" true
    # everywhere these settings are read (get_settings, get_pipeline_status).
    roster_ids = {v["voice_id"] for v in result["elevenlabs_voices"]}
    if result["elevenlabs_voice_id"] and result["elevenlabs_voice_id"] not in roster_ids:
        result["elevenlabs_voice_id"] = ""
    return result

# Keep in sync with mcp/server.py's equivalent research-run-window helper.
def _research_run_window(con, now: dt.datetime | None = None) -> tuple:
    """Read research_run_timestamps, drop entries older than 24h.

    Returns (pruned_timestamps, resets_at) where resets_at is the ISO-Z
    moment the oldest surviving entry ages out of the window (the next slot
    to free), or None if the window is empty. Does not persist the prune —
    callers that want to keep the trimmed list call _write_research_run_window.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'research_run_timestamps'"
    ).fetchone()
    raw = row["value"] if row else None
    try:
        stored = _json.loads(raw) if raw else []
    except _json.JSONDecodeError:
        stored = []

    kept = []
    for ts in stored:
        try:
            parsed = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
        except (ValueError, TypeError, AttributeError):
            continue
        if (now - parsed).total_seconds() < 24 * 3600:
            kept.append((ts, parsed))

    pruned = [ts for ts, _ in kept]
    resets_at = None
    if kept:
        oldest = min(parsed for _, parsed in kept)
        resets_at = (oldest + dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return pruned, resets_at


def _write_research_run_window(con, timestamps: list) -> None:
    con.execute(
        "INSERT INTO settings (key, value) VALUES ('research_run_timestamps', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_json.dumps(timestamps),),
    )


ACTIONABLE_STATUSES = {"TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"}
# The per-video choices, split by how long a human may change them (TMDEV-110).
# The topic group shapes what the script *is*, so it is asked once, at the
# topic. The agent group only decides who does the next piece of work, so it
# stays open at every human checkpoint — ACTIONABLE_STATUSES, above — and is
# frozen only while an agent or the renderer holds the video.
# Keep in sync: mcp/server.py's TOPIC_ONLY_FIELDS, AGENT_CHECKPOINT_FIELDS and
# HUMAN_CHECKPOINT_STATUSES.
TOPIC_ONLY_FIELDS = ("script_profile_id", "visual_style")
AGENT_CHECKPOINT_FIELDS = ("agent_id", "agent_model", "agent_effort")
# VIDEO_APPROVED is deliberately absent (TMDEV-83): publishing is never agent
# work — a human does it from the dashboard, or Auto Pilot's worker pass does
# (TMDEV-139) — and no MCP tool can, so an agent woken for one of
# these videos has nothing it is allowed to do — and poll.py would wake it every
# tick forever, burning a paid session each time.
# Keep in sync: the other copy of this list, and the operator skill's
# "Status → Action" table.
WORKABLE_STATUSES = [
    "TOPIC_APPROVED", "VOICING", "VOICE_READY",
    "REVISION_REQUESTED",
]

# Canonical set of every valid videos.status value. Keep in sync with
# dashboard/lib/types.ts VideoStatus and mcp/server.py VALID_VIDEO_STATUSES.
VALID_VIDEO_STATUSES = {
    "TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED", "SCRIPT_READY",
    "VOICING", "VOICE_READY", "RENDER_QUEUED", "RENDERING", "VIDEO_READY",
    "VIDEO_APPROVED", "REVISION_REQUESTED", "SCHEDULED", "PUBLISHING", "PUBLISHED",
    "FAILED",
}

# Statuses a human may delete a video from (TMDEV-84). Excluded are the four
# processing statuses — something is actively working on the video — and the
# two scene-claim statuses, VOICE_READY and REVISION_REQUESTED. The scene-work
# claim lives only in the MCP process, so Flask cannot ask whether an agent
# holds one; blocking the statuses the claim can exist in is strictly stronger
# than a claim read, and keeps Flask free of any dependency on MCP being up.
# The cost is that an unclaimed video at either status cannot be deleted.
# SCHEDULED is excluded too: postforme holds a post that will go out, and
# deleting the video would leave it with nothing local to settle or cancel it.
# Keep in sync with dashboard/lib/videoStatus.ts DELETABLE_STATUSES.
DELETABLE_STATUSES = VALID_VIDEO_STATUSES - {
    "VOICING", "RENDER_QUEUED", "RENDERING", "SCHEDULED", "PUBLISHING",
    "VOICE_READY", "REVISION_REQUESTED",
}

# Scheduled publishing (TMDEV-133). The floor gives the human a real window to
# cancel in and keeps the upload (about a minute) well inside the lead; the
# ceiling is a typo guard, not a postforme limit — it has none.
SCHEDULE_MIN_LEAD_SECS = 5 * 60
SCHEDULE_MAX_LEAD_DAYS = 365
# A schedule this close by the time create_post runs is sent as "post now":
# the time has effectively arrived, and postforme refuses a scheduled_at in
# the past, which the publish path would have to treat as ambiguous.
SCHEDULE_POST_NOW_SECS = 60


def resolve_schedule(schedule, now: dt.datetime) -> tuple[str, str]:
    """{"local": "YYYY-MM-DDTHH:MM", "timezone": IANA} -> (UTC "…Z", zone).

    The wall time is converted here, never in the browser: the zone is data the
    human picked, and zoneinfo is the one place DST is handled correctly.
    A wall time inside a DST gap does not exist, but zoneinfo still returns a
    datetime for it — the round trip below is what catches that. An ambiguous
    wall time (the repeated hour) takes its first occurrence (fold=0), unless
    that one is already too soon and the second is not.

    Raises ValueError with a message fit for the human.
    """
    if not isinstance(schedule, dict):
        raise ValueError("schedule must be an object with local and timezone")
    local, tz_name = schedule.get("local"), schedule.get("timezone")
    if not isinstance(tz_name, str) or not tz_name:
        raise ValueError("schedule.timezone is required")
    try:
        zone = zoneinfo.ZoneInfo(tz_name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone: {tz_name}") from None
    try:
        wall = dt.datetime.strptime(local, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        raise ValueError("schedule.local must be a date and time, YYYY-MM-DDTHH:MM") from None
    try:
        utc = wall.replace(tzinfo=zone).astimezone(dt.timezone.utc)
        exists = utc.astimezone(zone).replace(tzinfo=None) == wall
    except OverflowError:
        raise ValueError("That date is out of range.") from None
    if not exists:
        raise ValueError(f"{local.replace('T', ' ')} does not exist in {tz_name} — the clocks "
                         f"skip it for daylight saving. Pick another time.")
    lead = (utc - now).total_seconds()
    if lead < SCHEDULE_MIN_LEAD_SECS:
        # A repeated hour whose first occurrence is already (nearly) past: the
        # second is the only one the human can mean. This is what "In 1 hour"
        # produces during the first occurrence — the same wall time again.
        second = wall.replace(tzinfo=zone, fold=1).astimezone(dt.timezone.utc)
        if second != utc:
            utc, lead = second, (second - now).total_seconds()
    if lead < SCHEDULE_MIN_LEAD_SECS:
        raise ValueError(f"A scheduled time must be at least "
                         f"{SCHEDULE_MIN_LEAD_SECS // 60} minutes from now.")
    if lead > SCHEDULE_MAX_LEAD_DAYS * 86400:
        raise ValueError(f"A scheduled time can be at most {SCHEDULE_MAX_LEAD_DAYS} days ahead.")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ"), tz_name


# Statuses unpublished_retention_days sweeps (TMDEV-134), and the word each is
# reported under by GET /retention/backlog and the sweep's comment. Every row is
# eligible, files or not: a direct PATCH can reject a video at any stage, so
# "rejected means no files" is a UI convention the sweep must not rely on.
UNPUBLISHED_RETENTION_STATUSES = {"FAILED": "failed", "TOPIC_REJECTED": "rejected"}


def _file_bytes(path) -> int:
    """Size of a regular file; 0 for anything else, a directory included."""
    try:
        return os.path.getsize(path) if path is not None and os.path.isfile(path) else 0
    except OSError:
        return 0


def _job_dir_bytes(video_id: str) -> int:
    """Size of every file under a video's job dir. 0 if absent.

    The id is caller-supplied through POST /videos and is a path segment, so,
    as in archive_video, only a direct child of JOBS_DIR is ever walked — '.'
    would otherwise size the whole jobs tree on every Settings load. Unreadable
    entries are skipped: this feeds a disk-usage estimate, never a 500.
    """
    job_dir = JOBS_DIR / video_id
    if job_dir.resolve().parent != JOBS_DIR.resolve() or not job_dir.is_dir():
        return 0
    total = 0
    for root, _dirs, files in os.walk(job_dir):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _init_db(db_path: str) -> None:
    """Bring the database up to date. Idempotent.

    The schema itself lives in tubematic_core/migrations/ (TMDEV-91) — this
    function used to hold a full copy of it, hand-synced with mcp/server.py's.
    The name and signature are unchanged because ~50 tests and
    vqa/make_seed_db.py call it.
    """
    tdb.migrate(db_path)


def log_secret_provider(db_path: str):
    """A zero-arg callable yielding the stored credential values, for redaction.

    Reads sqlite3 directly and swallows everything. It is called from inside the
    log formatter, so it must not log and must not raise: the line being written
    is quite often itself a database error, and either would recurse.

    Deliberately not `_read_all_settings` — that coerces, normalises and derives,
    none of which is wanted here, and any of which could raise.
    """
    def provider():
        try:
            con = sqlite3.connect(db_path, timeout=1)
            try:
                keys = [k for k, (typ, _) in SETTINGS_SPEC.items() if typ == "secret"]
                rows = con.execute(
                    "SELECT value FROM settings WHERE key IN (%s)"
                    % ",".join("?" * len(keys)), keys
                ).fetchall()
            finally:
                con.close()
            return [r[0] for r in rows if r[0]]
        except Exception:  # noqa: BLE001 - see docstring
            return []
    return provider


def log_retention_days(db_path: str) -> int:
    """Read log_retention_days before logging is configured. Never raises."""
    default = int(SETTINGS_SPEC["log_retention_days"][1])
    try:
        con = sqlite3.connect(db_path, timeout=2)
        try:
            row = con.execute(
                "SELECT value FROM settings WHERE key = 'log_retention_days'"
            ).fetchone()
        finally:
            con.close()
        value = int(row[0]) if row and row[0] else default
        return value if MIN_LOG_RETENTION_DAYS <= value <= MAX_LOG_RETENTION_DAYS else default
    except Exception:  # noqa: BLE001
        return default


def archive_video(db_path: str, video_id: str, allowed_statuses, author: str,
                  comment: str, updated_before: str | None = None) -> dict:
    """Delete a video's mp4 and job dir, keeping and archiving its row (TMDEV-84).

    The one implementation behind both the manual DELETE route and the render
    worker's retention sweep, so "delete" means the same thing everywhere.

    Returns {"result": "archived", "archived_at", "file_errors"}, or
    {"result": "not_found"}, or {"result": "conflict", "status", "archived_at"}
    when the row is already archived or not in allowed_statuses.

    Order matters. The paths are resolved first. Both are derived from the ids,
    never read from video_path: that column was once caller-writable, and its
    basename let one video's archive delete another's render (TMDEV-159). The
    status check lives in the UPDATE's own WHERE clause, so it
    is atomic with the archive — a render claim or status change racing this
    cannot slip between a read and the write. Files go last: once the row is
    archived nothing will use them, so a failed removal only strands disk, and
    is reported rather than rolled back.

    video_path is cleared so "the file is gone" is a DB fact. The dashboard
    shows a player whenever it is set, and the stream route caches for an hour.

    updated_before, when given, joins the status in the UPDATE's WHERE clause
    (TMDEV-134): the unpublished retention sweep's clock is updated_at, and an
    edit landing between its SELECT and this call restarts that clock.
    """
    allowed = sorted(allowed_statuses)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT status, project_id FROM videos WHERE id = ?",
            (video_id,)).fetchone()
        if row is None:
            return {"result": "not_found"}
        mp4 = _output_path(row["project_id"], video_id)
        job_dir = JOBS_DIR / video_id
        age_sql, age_args = (" AND updated_at < ?", [updated_before]) if updated_before else ("", [])
        cur = con.execute(
            "UPDATE videos SET archived_at = ?, video_path = '', updated_at = ?"
            " WHERE id = ? AND archived_at IS NULL"
            f" AND status IN ({','.join('?' * len(allowed))}){age_sql}",
            [now, now, video_id, *allowed, *age_args])
        if cur.rowcount == 0:
            con.rollback()
            fresh = con.execute(
                "SELECT status, archived_at FROM videos WHERE id = ?", (video_id,)).fetchone()
            return {"result": "conflict", "status": fresh["status"],
                    "archived_at": fresh["archived_at"]}
        con.execute(
            "INSERT INTO comments (video_id, author, content, created_at) VALUES (?, ?, ?, ?)",
            (video_id, author, comment, now))
        con.commit()
    finally:
        con.close()

    file_errors = []
    if mp4 is not None:
        try:
            mp4.unlink(missing_ok=True)
        except OSError as e:
            file_errors.append(f"{mp4}: {e}")
    # The id came from our own DB row, but it is still a path segment — never
    # remove anything that is not a direct child of JOBS_DIR.
    if job_dir.resolve().parent != JOBS_DIR.resolve():
        file_errors.append(f"{job_dir}: not a direct child of {JOBS_DIR}, left alone")
    elif job_dir.is_dir():
        try:
            shutil.rmtree(job_dir)
        except OSError as e:
            file_errors.append(f"{job_dir}: {e}")
    for err in file_errors:
        log.warning("archive %s: could not remove %s", video_id, err,
                    extra={"video_id": video_id})
    return {"result": "archived", "archived_at": now, "file_errors": file_errors}


SPEND_PRESETS = ("today", "week", "month")


def _preset_first_day(preset: str, today: dt.date) -> dt.date:
    """First day of a Spend-tab preset that ends `today`. Weeks start on Monday."""
    if preset == "week":
        return today - dt.timedelta(days=today.weekday())
    if preset == "month":
        return today.replace(day=1)
    return today


@contextmanager
def _db(db_path: str):
    """A committed-or-rolled-back connection for code shared with the worker.

    Module level because start_publish runs in both processes; the blueprint's
    own _conn is the same thing bound to its db_path.
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _allowed_account_ids(con) -> list:
    """The accounts a human has permitted Tubematic to post to.

    A bare settings row rather than a SETTINGS_SPEC key, exactly like
    mining_youtube_urls: it is a list managed by its own routes, not a
    dashboard-editable scalar.
    """
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'publishing_accounts'").fetchone()
    if not row:
        return []
    try:
        value = _json.loads(row["value"])
    except (ValueError, TypeError):
        return []
    return [a for a in value if isinstance(a, str)] if isinstance(value, list) else []


def _auto_pilot_config(con) -> dict:
    """{"projects": {project_id: [account_id]}, "account_limits": {account_id: n}}.

    A bare settings row like publishing_accounts, managed by /autopilot. A
    project being a key is what puts it on Auto Pilot; its list may be empty.
    Tolerant of a missing or malformed row: Auto Pilot acting on nothing is
    the safe reading of a value it cannot parse.
    """
    empty = {"projects": {}, "account_limits": {}}
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'auto_pilot_config'").fetchone()
    if not row:
        return empty
    try:
        value = _json.loads(row["value"])
    except (ValueError, TypeError):
        return empty
    if not isinstance(value, dict):
        return empty
    projects, limits = value.get("projects"), value.get("account_limits")
    return {
        "projects": {
            pid: [a for a in ids if isinstance(a, str)]
            for pid, ids in (projects.items() if isinstance(projects, dict) else [])
            if isinstance(ids, list)
        },
        "account_limits": {
            aid: n for aid, n in (limits.items() if isinstance(limits, dict) else [])
            if isinstance(n, int) and not isinstance(n, bool)
            and 0 <= n <= MAX_AUTO_PILOT_DAILY
        },
    }


# Statuses a video only reaches by passing SCRIPT_READY -> VOICING, the paid
# gate. A video at VOICING has no voice file yet, so "has been voiced" needs
# this list as well as the column.
AUTO_PILOT_PAST_GATE = ("VOICING", "VOICE_READY", "RENDER_QUEUED", "RENDERING",
                        "VIDEO_READY", "VIDEO_APPROVED", "PUBLISHING", "SCHEDULED")


def in_flight_count(con, project_ids) -> int:
    """Videos past the paid gate and not yet published — what
    auto_pilot_max_in_flight is held to (TMDEV-150). One per video, however
    many accounts it posts to.

    Two terms, OR-ed so a row matching both counts once:

    - In the Auto Pilot projects, every video that has been voiced and has not
      published, failed or been rejected. Keyed on the voice file, not on a
      status list: a revision goes back to SCRIPT_READY (or TOPIC_PROPOSED) and
      must keep its slot, or it would free one for a new script and then queue
      behind it. Project-scoped, so a human's unrelated manual project cannot
      freeze Auto Pilot. A VIDEO_APPROVED row on auto_pilot_hold is left out:
      it cannot be scheduled and nothing in the dashboard clears the hold, so
      counting it would shut the gate for good, silently.
    - Every post waiting to go out at a future time, install-wide and whoever
      scheduled it (TMDEV-143's rule: the calendar is shared). An overdue
      SCHEDULED row or an ambiguous PUBLISHING one in another project is not
      counted, because neither leaves the count by itself.

    Archived rows never count.
    """
    project_ids = list(project_ids)
    past_gate = ",".join("?" * len(AUTO_PILOT_PAST_GATE))
    production = "0"
    params: list = []
    if project_ids:
        production = (
            "(project_id IN (%s)"
            " AND status NOT IN ('PUBLISHED', 'FAILED', 'TOPIC_REJECTED')"
            " AND (voice_file_path != '' OR status IN (%s))"
            " AND NOT (status = 'VIDEO_APPROVED' AND auto_pilot_hold = 1))"
            % (",".join("?" * len(project_ids)), past_gate))
        params = project_ids + list(AUTO_PILOT_PAST_GATE)
    return con.execute(
        "SELECT COUNT(*) AS c FROM videos WHERE archived_at IS NULL AND (%s"
        " OR (status = 'SCHEDULED' AND scheduled_at > ?))" % production,
        params + [_utc_now()]).fetchone()["c"]


_PUBLISH_COMMENT_MAX = 1500


def _publish_note(db_path: str, video_id: str, text: str) -> None:
    """Append a publishing note. Never raises — losing the record of a
    failure must not also break the response that reports it."""
    try:
        with _db(db_path) as con:
            con.execute(
                "INSERT INTO comments (video_id, author, content, created_at)"
                " VALUES (?, 'agent', ?, ?)",
                (video_id, text[:_PUBLISH_COMMENT_MAX], _utc_now()))
    except Exception:
        pass


def _publication_row(row) -> dict:
    return {
        "id":                row["id"],
        "video_id":          row["video_id"],
        "platform":          row["platform"],
        "social_account_id": row["social_account_id"],
        "status":            row["status"],
        "post_url":          row["post_url"],
        "error":             row["error"],
        "published_at":      row["published_at"],
        "created_at":        row["created_at"],
        "updated_at":        row["updated_at"],
    }


def _publish_platforms(api_key: str, account_ids: list) -> dict:
    """{account_id: platform} for the targets of one publish.

    Looked up live rather than stored: the allowlist deliberately holds ids
    only, so this is the single place that knows which platform each target
    is, and it is what decides the per-platform content overrides.
    """
    return {a["id"]: a.get("platform", "")
            for a in postforme.list_accounts(api_key) if a["id"] in set(account_ids)}


def publish_text(video) -> tuple:
    """(title, description) a publish starts from.

    What the agent wrote with the script (TMDEV-132), else the video's title
    and topic. The fallback is never stored, so it cannot pass for what an
    agent wrote.
    """
    if video["publish_title"]:
        return video["publish_title"], video["publish_description"]
    return video["title"] or video["topic"], video["topic"] or ""


def start_publish(db_path: str, api_key: str, video_id: str, account_ids: list,
                  title: str, description: str, privacy: dict,
                  schedule=None, slot=None) -> tuple:
    """Publish or schedule one approved video; returns (payload, http_status).

    The whole of POST /videos/<id>/publish after request parsing, at module
    level so Auto Pilot's worker pass (TMDEV-139) runs the identical claim,
    upload and reconciliation rules rather than a second copy of them.

    `schedule` is a human's {"local", "timezone"} and is validated here.
    `slot` is the worker's already-decided (UTC "…Z", zone name, local label);
    it skips resolve_schedule, whose five-minute floor exists to give a human
    a window to cancel in.
    """
    with _db(db_path) as con:
        video = con.execute(
            "SELECT id, project_id, status, title, topic, archived_at"
            " FROM videos WHERE id = ?",
            (video_id,)).fetchone()
        allowed = set(_allowed_account_ids(con))
    if not video:
        return {"error": "Video not found"}, 404
    if video["archived_at"]:
        return {"error": "Video is archived — its rendered file has been deleted."}, 409
    # Advisory only — it exists to say *what* status the video is actually
    # in, which the atomic claim below cannot report. The claim is the real
    # gate; these two cannot disagree in a way that matters, because a race
    # that slips past this read is still stopped there.
    if video["status"] != "VIDEO_APPROVED":
        return {
            "error": f"Video is {video['status']}, not VIDEO_APPROVED — "
                     "only an approved video can be published."
        }, 409

    # Enforced here, not only in the UI: this endpoint is reachable through
    # the dashboard proxy, and the allowlist is what keeps pipeline output
    # off a personal account that happens to be connected to postforme.
    outside = [a for a in account_ids if a not in allowed]
    if outside:
        return {
            "error": f"Not permitted to post to {', '.join(sorted(outside))} — "
                     "enable them on the Socials page first."
        }, 400

    local_path = _output_path(video["project_id"], video_id)
    if not local_path or not local_path.is_file():
        return {"error": "No rendered video file to publish."}, 400

    if not title:
        title = video["title"] or video["topic"]

    # Rejected here rather than at build time, so an unsupported privacy
    # value is a 400 that changes nothing — not a 500 after the claim, and
    # not a silent public post. postforme itself would accept and ignore it.
    try:
        postforme.build_platform_configurations([], title, description, privacy)
    except ValueError as e:
        return {"error": str(e)}, 400

    scheduled_at, scheduled_tz, scheduled_local = slot or ("", "", "")
    if schedule is not None:
        try:
            scheduled_at, scheduled_tz = resolve_schedule(
                schedule, dt.datetime.now(dt.timezone.utc))
        except ValueError as e:
            return {"error": str(e)}, 400
        scheduled_local = schedule["local"].replace("T", " ")

    # Resolved before the claim: it is a read, so failing it changes nothing,
    # and the rows written at the claim below need each target's platform.
    try:
        platforms = _publish_platforms(api_key, account_ids)
    except postforme.PostformeError as e:
        _publish_note(db_path, video_id, f"Publishing failed, nothing was posted: {e}")
        return {"error": str(e)}, 502

    # Claim the video BEFORE anything reaches postforme. Validation above is
    # side-effect-free, so failing it leaves the status alone; from here on
    # there are real side effects, and they must happen at most once.
    #
    # Claiming afterwards looks equivalent and is not: two overlapping
    # requests would both pass the status read above, both create a real
    # post, and only then race on this UPDATE — the loser returning 409
    # while a live post exists with no video_publications rows.
    #
    # The rows are written in the same transaction as the claim, with an
    # empty post id meaning "publish in progress" (TMDEV-97). They used to
    # be inserted only after create_post, so for the whole upload the
    # worker saw PUBLISHING with no rows, read that as a crashed publish,
    # found no post yet, and failed a video that went live moments later.
    now = _utc_now()
    row_ids = [str(uuid.uuid4()) for _ in account_ids]
    with _db(db_path) as con:
        claimed = con.execute(
            "UPDATE videos SET status = 'PUBLISHING', scheduled_at = ?,"
            " scheduled_timezone = ?, updated_at = ?"
            " WHERE id = ? AND status = 'VIDEO_APPROVED' AND archived_at IS NULL",
            (scheduled_at, scheduled_tz, now, video_id)).rowcount
        if claimed:
            for row_id, account_id in zip(row_ids, account_ids):
                con.execute(
                    "INSERT INTO video_publications (id, video_id, platform,"
                    " social_account_id, postforme_post_id, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, '', 'PENDING', ?, ?)",
                    (row_id, video_id, platforms.get(account_id, ""),
                     account_id, now, now))
    if not claimed:
        return {"error": "Video is no longer VIDEO_APPROVED."}, 409

    # Two phases, and the split is the whole point.
    #
    # Everything up to create_post is unambiguous: if it fails, no post
    # exists, so the claim is released and the human can simply try again.
    try:
        slot = postforme.create_upload_url(api_key)
        postforme.upload_media(slot["upload_url"], str(local_path))
    except postforme.PostformeError as e:
        with _db(db_path) as con:
            released = con.execute(
                "UPDATE videos SET status = 'VIDEO_APPROVED', scheduled_at = '',"
                " scheduled_timezone = '', updated_at = ?"
                " WHERE id = ? AND status = 'PUBLISHING'", (_utc_now(), video_id)).rowcount
            # Only with the claim: if the worker already failed the video,
            # its rows are what offers Retry publishing, so they stay.
            if released:
                con.execute(
                    "DELETE FROM video_publications"
                    " WHERE video_id = ? AND postforme_post_id = ''", (video_id,))
        # Already scrubbed by postforme.py — its error bodies carry the
        # connected channel's OAuth tokens, and this table is rendered in
        # the dashboard.
        _publish_note(db_path, video_id, f"Publishing failed, nothing was posted: {e}")
        return {"error": str(e)}, 502

    # create_post is NOT unambiguous. A timeout, a 5xx or a non-JSON body
    # can all arrive after postforme accepted the post, so a failure here
    # does not mean nothing was published. Releasing the claim would invite
    # a retry that publishes the same video twice for real, with no local
    # row for the first one.
    #
    # So the video stays PUBLISHING and the worker reconciles it by
    # external_id (= video_id) on its next pass — finding the post if one
    # exists, and failing the video only if none does.
    #
    # A schedule that has all but arrived during the upload goes out now
    # instead (SCHEDULE_POST_NOW_SECS). The stored scheduled_at stays; at
    # worst the worker parks the video in SCHEDULED for the few seconds
    # left and moves it straight back when it falls due.
    send_at = None
    if scheduled_at:
        due = dt.datetime.strptime(scheduled_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc)
        if (due - dt.datetime.now(dt.timezone.utc)).total_seconds() > SCHEDULE_POST_NOW_SECS:
            send_at = scheduled_at
    try:
        post = postforme.create_post(
            api_key,
            caption=postforme.compose_caption(title, description),
            social_account_ids=account_ids,
            media_url=slot["media_url"],
            platform_configurations=postforme.build_platform_configurations(
                set(platforms.values()), title, description, privacy),
            external_id=video_id,
            scheduled_at=send_at,
        )
    except postforme.PostformeError as e:
        _publish_note(
            db_path, video_id,
            f"Publishing did not complete cleanly and it is unclear whether the post was "
            f"created: {e} The video stays in PUBLISHING while the worker checks postforme "
            f"for a post matching this video, so it is not published twice. "
            f"Do not retry until it settles.")
        return {
            "error": f"{e} — the video is left in PUBLISHING while this is reconciled; "
                     "it may or may not have been posted, so do not retry yet.",
            "reconciling": True,
        }, 502

    # A body with no id leaves the rows in progress, and the worker finds
    # the post by external_id instead.
    post_id = post.get("id", "")
    with _db(db_path) as con:
        if post_id:
            # Only this request's own rows, by id: rows of another attempt
            # at the same video are never touched. Guarded on the post id
            # still being empty, so a worker that already adopted this post
            # by external_id is left alone.
            #
            # created_at is reset because the worker's publish deadline is
            # measured from it: the platforms get their full hour to report
            # from now, not from before the upload.
            #
            # This request cannot outlive that deadline — the upload is
            # capped (postforme.UPLOAD_MAX_SECS) — so the rows are still in
            # flight and the video still PUBLISHING here, never failed by
            # the worker or moved on by Retry.
            ts = _utc_now()
            con.execute(
                "UPDATE video_publications SET postforme_post_id = ?, created_at = ?,"
                " updated_at = ? WHERE id IN (%s) AND postforme_post_id = ''"
                % ",".join("?" * len(row_ids)),
                (post_id, ts, ts, *row_ids))
            # Guarded: a worker that adopted this post first has already
            # moved the video on, and that stands.
            if send_at:
                con.execute(
                    "UPDATE videos SET status = 'SCHEDULED', updated_at = ?"
                    " WHERE id = ? AND status = 'PUBLISHING'", (ts, video_id))
        status = con.execute(
            "SELECT status FROM videos WHERE id = ?", (video_id,)).fetchone()["status"]
        rows = con.execute(
            "SELECT * FROM video_publications WHERE video_id = ? ORDER BY platform, id",
            (video_id,)).fetchall()
    targets = ", ".join(sorted(f"{platforms.get(a) or 'unknown'} ({a})" for a in account_ids))
    if send_at:
        _publish_note(
            db_path, video_id,
            f"Scheduled to post to {len(account_ids)} account(s): {targets}, "
            f"at {scheduled_local} {scheduled_tz} ({scheduled_at} UTC). postforme holds the post "
            f"until then; it can be cancelled until it starts going out.")
    else:
        _publish_note(
            db_path, video_id,
            f"Publishing to {len(account_ids)} account(s): {targets}. "
            f"Awaiting per-platform results.")
    return {"status": status, "postforme_post_id": post_id,
            "scheduled_at": scheduled_at, "scheduled_timezone": scheduled_tz,
            "publications": [_publication_row(r) for r in rows]}, 201


def create_pipeline_blueprint() -> Blueprint:
    bp = Blueprint("pipeline", __name__)

    db_path = os.environ.get("TUBEMATIC_DB", "/data/tubematic.db")
    _init_db(db_path)

    # Adds a file handler; the existing stdout logging is untouched, and a
    # missing or unwritable /logs leaves this a no-op (see tubematic_core).
    tlog.setup_json_logging(
        "api", LOG_DIR,
        retention_days=log_retention_days(db_path),
        secrets=log_secret_provider(db_path),
    )

    # ── request logging ──────────────────────────────────────────────────────
    # On the blueprint, not the app, and that is what excludes /health: it and
    # /render/health are registered directly on the app in server.py, so these
    # hooks never see them. The compose healthcheck runs every 15s, which would
    # otherwise be ~5,760 log lines a day saying nothing.

    @bp.before_request
    def _log_request_start():
        g._req_id = uuid.uuid4().hex[:8]
        g._req_started = time.time()

    @bp.after_request
    def _log_request_end(response):
        started = getattr(g, "_req_started", None)
        duration_ms = round((time.time() - started) * 1000) if started else None
        # A 4xx is the caller's problem and a 5xx is ours, so they are worth
        # different levels — an error-filtered view should show the latter only.
        level = logging.ERROR if response.status_code >= 500 else (
            logging.WARNING if response.status_code >= 400 else logging.INFO)
        log.log(
            level, "%s %s -> %s", request.method, request.path, response.status_code,
            extra={
                "request_id": getattr(g, "_req_id", None),
                "video_id": (request.view_args or {}).get("video_id"),
                "profile_id": (request.view_args or {}).get("profile_id"),
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @bp.errorhandler(Exception)
    def _log_unhandled(exc):
        """Log the traceback, then re-raise so Flask's own handling is unchanged.

        Deliberately not a 500-returning handler: this endpoint set has always
        let Flask turn an unhandled exception into its own 500, and swallowing
        that here would change behaviour under the guise of adding logging.
        """
        log.exception("unhandled error in %s %s", request.method, request.path,
                      extra={"request_id": getattr(g, "_req_id", None)})
        raise exc

    # ── helpers ──────────────────────────────────────────────────────────────

    @contextmanager
    def _conn():
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _parse_video(video: dict) -> dict:
        """Decode the script_segments JSON TEXT column into a list, matching
        the contract established by mcp/server.py's _fetch_video."""
        raw_segments = video.get("script_segments")
        video["script_segments"] = _json.loads(raw_segments) if raw_segments else None
        return video

    def _list_video(video: dict) -> dict:
        """A video as it appears in a LIST payload, with gemini_feedback clipped.

        The review is stored whole (VQA-7 removed every cap on it, so a video
        with many must-fix entries can run long), but `GET /videos` returns
        every row — so shipping full reviews there would grow the list payload
        without bound for content the list never displays. The single-video
        route returns it untruncated; `gemini_feedback_truncated` tells the
        client whether it needs to go and fetch that.
        """
        feedback = video.get("gemini_feedback") or ""
        if len(feedback) > GEMINI_FEEDBACK_LIST_PREVIEW_CHARS:
            video["gemini_feedback"] = feedback[:GEMINI_FEEDBACK_LIST_PREVIEW_CHARS]
            video["gemini_feedback_truncated"] = True
        else:
            video["gemini_feedback_truncated"] = False
        return video

    def _with_voice(video: dict, settings: dict) -> dict:
        video["effective_voice_id"], video["voice_conflicts"] = _voice_state(video, settings)
        return video

    def _video_with_comments(con, video_id: str) -> dict | None:
        row = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not row:
            return None
        settings = _read_all_settings(con)
        video = _with_voice(_parse_video(dict(row)), settings)
        video["voice_info"] = _voice_info(con, video, settings)
        # Never clipped here — this is the route the dashboard's "read more"
        # and every agent-facing read resolve to.
        video["gemini_feedback_truncated"] = False
        comments = con.execute(
            "SELECT * FROM comments WHERE video_id = ? ORDER BY created_at ASC",
            (video_id,)
        ).fetchall()
        video["comments"] = [dict(c) for c in comments]
        return video

    # ── /stats ───────────────────────────────────────────────────────────────

    # Archived rows (TMDEV-84) are left out of every count and list below that
    # feeds the board or the agent: the counts must match the cards the Kanban
    # shows, and a deleted TOPIC_APPROVED/TOPIC_PROPOSED video must neither be
    # worked on by the cron agent nor count towards the research pending cap.
    @bp.get("/stats")
    def stats():
        with _conn() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) as cnt FROM videos"
                " WHERE archived_at IS NULL GROUP BY status"
            ).fetchall()
        return jsonify({r["status"]: r["cnt"] for r in rows})

    # ── /videos ──────────────────────────────────────────────────────────────

    @bp.get("/videos")
    def list_videos():
        clauses, params = [], []
        if status := request.args.get("status"):
            clauses.append("status = ?")
            params.append(status)
        if project_id := request.args.get("project_id"):
            clauses.append("project_id = ?")
            params.append(project_id)
        if strategy := request.args.get("strategy"):
            clauses.append("strategy = ?")
            params.append(strategy)
        # Archived rows are opt-in, so no existing caller silently starts
        # showing them: archived=only is the Archive page, archived=include
        # everything. Anything else is rejected rather than read as the default.
        archived = request.args.get("archived", "")
        if archived == "only":
            clauses.append("archived_at IS NOT NULL")
        elif archived == "":
            clauses.append("archived_at IS NULL")
        elif archived != "include":
            return jsonify({"error": "archived must be 'only' or 'include'"}), 400
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _conn() as con:
            rows = con.execute(
                f"SELECT * FROM videos {where} ORDER BY created_at DESC", params
            ).fetchall()
            settings = _read_all_settings(con)
        return jsonify([_list_video(_with_voice(_parse_video(dict(r)), settings)) for r in rows])

    @bp.get("/videos/actionable")
    def actionable_videos():
        placeholders = ",".join("?" * len(ACTIONABLE_STATUSES))
        with _conn() as con:
            rows = con.execute(
                f"SELECT * FROM videos WHERE status IN ({placeholders})"
                f" AND archived_at IS NULL ORDER BY updated_at ASC",
                list(ACTIONABLE_STATUSES),
            ).fetchall()
            settings = _read_all_settings(con)
        return jsonify([_list_video(_with_voice(_parse_video(dict(r)), settings)) for r in rows])

    # Deliberately not /videos/actionable (above), whose ACTIONABLE_STATUSES is
    # the *human-checkpoint* set and is disjoint from WORKABLE_STATUSES. poll.py
    # needs the agent-workable set, plus each video's agent, model and effort,
    # to start one session per video under the right ones (TMDEV-73, TMDEV-106,
    # TMDEV-129). A video flagged stuck is left out: the poller must not
    # dispatch it until a human acts, and filtering here keeps that rule in one
    # place. Oldest first, which is the order the poller fills its slots in.
    # A separate route rather than an addition to /pipeline/status: that payload
    # is kept in sync with mcp/server.py's get_pipeline_status, and an unbounded
    # array would force a matching MCP change for no MCP benefit.
    @bp.get("/videos/workable")
    def workable_videos():
        placeholders = ",".join("?" * len(WORKABLE_STATUSES))
        with _conn() as con:
            rows = con.execute(
                f"SELECT id, topic, status, agent_model, agent_effort, agent_id, "
                f"updated_at FROM videos "
                f"WHERE status IN ({placeholders}) AND archived_at IS NULL"
                f" AND agent_stuck_at IS NULL"
                f" ORDER BY updated_at ASC",
                list(WORKABLE_STATUSES),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @bp.get("/videos/<video_id>")
    def get_video(video_id: str):
        with _conn() as con:
            video = _video_with_comments(con, video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404
        return jsonify(video)

    @bp.patch("/videos/<video_id>")
    def patch_video(video_id: str):
        body = request.get_json(force=True) or {}
        only_if = body.pop("onlyIfCurrentStatus", None)

        # The four job-path columns are written only by the code that writes
        # the files (generate_voice, write_scene_config, the worker) and are
        # refused here rather than dropped (TMDEV-159/162): a caller relying on
        # one would otherwise get a 200 for a write that never happened. The
        # whole request is refused, status included, so nothing half-applies.
        # Keep in sync with mcp/server.py's update_video.
        sent_paths = sorted(SERVER_OWNED_PATH_FIELDS & body.keys())
        if sent_paths:
            return jsonify({
                "error": f"{', '.join(sent_paths)} cannot be written: the server sets "
                         "the job-file paths itself. Nothing was changed."
            }), 400
        allowed = {
            "status", "title", "script", "video_version", "youtube_url",
            "gemini_feedback", "voice_id", "agent_id", "agent_model", "agent_effort",
            "script_profile_id", "visual_style", "publish_title", "publish_description",
        }
        fields = {k: v for k, v in body.items() if k in allowed}
        # A human may hand a video to another agent at any human checkpoint
        # (TMDEV-110) — checked further down, after the freeze. There is no
        # blank: NULL means "the default at dispatch time", which is only ever
        # the state a video is created in, never one a human picks.
        # Keep in sync with mcp/server.py's update_video.
        if "agent_id" in fields:
            aid = fields["agent_id"]
            if not isinstance(aid, str) or not aid.strip():
                return jsonify({
                    "error": "agent_id must name a live agent (an id from GET /agents); "
                             "it cannot be blank"
                }), 400
            fields["agent_id"] = aid.strip()
        # Shape first: reject what would corrupt poll.py's argv before anything
        # else. Membership in the video's agent's model list is checked further
        # down, after the freeze (TMDEV-90).
        # Keep in sync with mcp/server.py's update_video.
        if "agent_model" in fields:
            am = fields["agent_model"]
            if not isinstance(am, str):
                return jsonify({"error": "agent_model must be a string"}), 400
            am = am.strip()
            if am and (" " in am or am.startswith("-")):
                return jsonify({
                    "error": f"agent_model must be a model alias (sonnet, opus, ...) or full "
                             f"ID with no spaces, or blank for the agent's default model, got {am!r}"
                }), 400
            fields["agent_model"] = am
        # A closed set, so this is a membership check rather than agent_model's
        # shape check — and it is complete: there is no later per-agent check
        # for effort, because every agent takes the same five levels.
        # Keep in sync with mcp/server.py's update_video.
        if "agent_effort" in fields:
            ae = fields["agent_effort"]
            if not isinstance(ae, str):
                return jsonify({"error": "agent_effort must be a string"}), 400
            ae = ae.strip()
            if ae and ae not in AGENT_EFFORTS:
                return jsonify({
                    "error": f"agent_effort must be one of {list(AGENT_EFFORTS)}, or blank for "
                             f"the agent's own effort, got {ae!r}"
                }), 400
            fields["agent_effort"] = ae
        # The display name is capped so Kanban cards stay legible; the full
        # descriptive text lives in topic, which is not writable here.
        # Keep in sync with mcp/server.py's update_video.
        if "title" in fields:
            t = fields["title"]
            if not isinstance(t, str):
                return jsonify({"error": "title must be a string"}), 400
            if len(t) > VIDEO_TITLE_MAX_LEN:
                return jsonify({
                    "error": f"title is {len(t)} characters; the display name must be at most "
                             f"{VIDEO_TITLE_MAX_LEN}. Shorten it — the full text belongs in topic."
                }), 400
        # The publish dialog only reads this pair, so a script is never written
        # without it — the same rule as update_video (TMDEV-132).
        # Keep in sync with mcp/server.py's update_video.
        if "script" in fields:
            missing = [n for n in ("publish_title", "publish_description") if n not in fields]
            if missing:
                return jsonify({
                    "error": f"A script write must also carry {' and '.join(missing)} — "
                             "what the video will be posted with."
                }), 400
        for name, cap in (("publish_title", PUBLISH_TITLE_MAX_LEN),
                          ("publish_description", PUBLISH_DESCRIPTION_MAX_LEN)):
            if name in fields:
                v = fields[name]
                if not isinstance(v, str) or not v.strip():
                    return jsonify({"error": f"{name} must be a non-blank string"}), 400
                v = v.strip()
                if len(v) > cap:
                    return jsonify({"error": f"{name} is {len(v)} characters; at most {cap}."}), 400
                fields[name] = v
        if not fields:
            return jsonify({"error": "No updatable fields provided"}), 400
        if "status" in fields and fields["status"] not in VALID_VIDEO_STATUSES:
            return jsonify({
                "error": f"Invalid status '{fields['status']}'. Must be one of: {sorted(VALID_VIDEO_STATUSES)}"
            }), 400

        fields["updated_at"] = _now()

        with _conn() as con:
            row = con.execute(
                "SELECT status, archived_at FROM videos WHERE id = ?", (video_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "Video not found"}), 404
            # An archived video is frozen (TMDEV-84). Its files are gone, so
            # letting a PATCH move it back into the pipeline — say to VOICING —
            # would spend money on a video the human deleted. The UPDATEs below
            # repeat the check in their WHERE clause, so a DELETE racing this
            # request cannot slip between the read and the write.
            if row["archived_at"]:
                return jsonify({"error": "Video is archived and can no longer be changed"}), 409

            if fields.get("voice_id"):
                roster_ids = {v["voice_id"] for v in _read_all_settings(con)["elevenlabs_voices"]}
                if fields["voice_id"] not in roster_ids:
                    return jsonify({
                        "error": f"voice_id {fields['voice_id']!r} is not in elevenlabs_voices"
                    }), 400

            # The script's markup was written for the model of the voice it
            # was scripted for (TMDEV-121), and a voice on another model may
            # read it aloud or drop it. Refused here, with the reason, rather
            # than at VOICING. Checked on every PATCH carrying a voice, not
            # only on a change: the video's own voice passes by construction
            # (update_video validates and pins it), so the only extra refusal
            # is a voice whose model was edited in Settings after scripting.
            # Keep in sync with mcp/server.py's update_video.
            voice_exempt = False
            if "voice_id" in fields and isinstance(fields["voice_id"], str):
                settings = _read_all_settings(con)
                current = _parse_video(dict(con.execute(
                    "SELECT status, voice_id, script, script_segments FROM videos WHERE id = ?",
                    (video_id,)).fetchone()))
                # TOPIC_PROPOSED waives the check (see _voice_state), so the
                # write is bound to that status below: landing after the video
                # moved on could put a voice under a script it cannot speak.
                voice_exempt = current["status"] == "TOPIC_PROPOSED"
                _, conflicts = _voice_state(current, settings)
                target = fields["voice_id"] or settings["elevenlabs_voice_id"]
                if target in conflicts:
                    return jsonify({
                        "error": f"This script can't be voiced with that voice: "
                                 f"{conflicts[target]} Keep the current voice, or request a "
                                 f"revision so the script is rewritten for the new one.",
                        "voice_conflict": True,
                    }), 409

            # Same shape and same place as the voice_id check above: one
            # connection, and the only_if UPDATE below stays a single atomic
            # statement. "" is always allowed — it means "no profile", the
            # static skill's own generic style.
            if fields.get("script_profile_id"):
                err = _script_profile_error(con, fields["script_profile_id"])
                if err:
                    return jsonify({"error": err}), 400

            # Same shape as the two checks above. resolved_visual_style is
            # deliberately not writable over HTTP at all: it records what the
            # agent settled on at scene-config time, and the dashboard has no
            # business overwriting that.
            if "visual_style" in fields:
                if fields["visual_style"] not in VISUAL_STYLES:
                    return jsonify({
                        "error": f"Invalid visual_style '{fields['visual_style']}'. "
                                 f"Must be one of: {sorted(VISUAL_STYLES)}"
                    }), 400
                if _illustrated_needs_key(con, fields["visual_style"]):
                    return jsonify({"error": ILLUSTRATED_NEEDS_OPENAI_KEY}), 400

            # The per-video choices freeze in two groups, and both are checked
            # against the *current* status — the UPDATE has not run yet — so the
            # PATCH that approves or revises can carry them while a later edit
            # cannot. They are frozen because they are read downstream by a
            # process the dashboard cannot see.
            #
            # The topic group is asked once, at the topic: changing
            # script_profile_id after SCRIPT_READY would leave a script that no
            # longer matches the profile the row claims it was written in.
            topic_locked = [k for k in TOPIC_ONLY_FIELDS if k in fields]
            if topic_locked and row["status"] != "TOPIC_PROPOSED":
                return jsonify({
                    "error": f"{', '.join(sorted(topic_locked))} can only be set while the "
                             f"video is at TOPIC_PROPOSED (this one is {row['status']})"
                }), 409
            # The agent group decides who does the *next* piece of work, so a
            # human may change it at every checkpoint (TMDEV-110). In between,
            # an agent or the renderer holds the video, and switching under it
            # would move it between agents, models or effort levels mid-task.
            agent_locked = [k for k in AGENT_CHECKPOINT_FIELDS if k in fields]
            if agent_locked and row["status"] not in ACTIONABLE_STATUSES:
                return jsonify({
                    "error": f"{', '.join(sorted(agent_locked))} can only be set at a human "
                             f"checkpoint ({', '.join(sorted(ACTIONABLE_STATUSES))}; this one "
                             f"is {row['status']})"
                }), 409

            # After the freeze, so a late edit still reads as "frozen" rather
            # than as an agent or model problem. A separate SELECT rather than
            # widening the one above, whose exact text a race test keys on
            # (TMDEV-90); a second race test keys on this one's (TMDEV-110).
            set_sql = [f"{k} = ?" for k in fields]
            set_params = list(fields.values())
            # Any human status change is a human acting on the video, so it
            # releases a stuck flag and starts the no-progress count afresh
            # (TMDEV-129). Only a status change: renaming a stuck video is not
            # a decision about why the agent could not move it.
            if "status" in fields:
                set_sql += ["agent_no_progress_count = 0", "agent_stuck_at = NULL"]
            where_sql, where_params = "", []
            # Bind the write to the status the freeze was checked against.
            # Without onlyIfCurrentStatus, that check and this UPDATE are two
            # statements, and a status change landing between them would let
            # a frozen field through at a status where it is frozen — after
            # the poller may already have handed the video to its agent.
            frozen_bound = bool(topic_locked or agent_locked or voice_exempt)
            if frozen_bound:
                where_sql, where_params = " AND status = ?", [row["status"]]
            if "agent_id" in fields or fields.get("agent_model"):
                stored = con.execute(
                    "SELECT agent_id FROM videos WHERE id = ?", (video_id,)
                ).fetchone()["agent_id"]
                if "agent_id" in fields:
                    err = _agent_id_error(con, stored, fields["agent_id"])
                    if err:
                        return jsonify({"error": err}), 400
                # A model is checked against the agent the video will have
                # once this request lands, not the one it has now.
                if fields.get("agent_model"):
                    err = _agent_model_error(con, fields.get("agent_id", stored),
                                             fields["agent_model"])
                    if err:
                        return jsonify({"error": err}), 400
                if "agent_id" in fields and "agent_model" not in fields:
                    # A model belongs to one agent's list; kept across a change
                    # it would be rejected by the next PATCH and by the new CLI
                    # on every scheduled run. Cleared back to "the agent's
                    # default". Decided in the UPDATE itself (SET reads the old
                    # row), so no read-then-write race can keep a foreign model.
                    # A NULL agent_id already runs under the default, so naming
                    # the default is not a change.
                    current = _effective_agent(con, stored)
                    set_sql.append(
                        "agent_model = CASE WHEN COALESCE(agent_id, ?) IS ? "
                        "THEN agent_model ELSE '' END")
                    set_params += [current["id"] if current else None, fields["agent_id"]]
                elif "agent_id" not in fields:
                    # The model was validated against `stored`. Bind the write
                    # to it: if another request moved the video to a different
                    # agent meanwhile, match no row rather than pin a model the
                    # new agent does not have.
                    where_sql += " AND agent_id IS ?"
                    where_params.append(stored)
            assignments = ", ".join(set_sql)

            # The only_if precondition is enforced in the UPDATE's own WHERE
            # clause (not a separate SELECT-then-compare) so the check-and-set
            # is atomic — closes the TOCTOU window a double-clicked "Approve"
            # could otherwise race under Flask's threaded=True.
            if only_if:
                cur = con.execute(
                    f"UPDATE videos SET {assignments} WHERE id = ? AND status = ?"
                    f" AND archived_at IS NULL{where_sql}",
                    set_params + [video_id, only_if] + where_params,
                )
            else:
                cur = con.execute(
                    f"UPDATE videos SET {assignments} WHERE id = ? AND archived_at IS NULL"
                    f"{where_sql}",
                    set_params + [video_id] + where_params,
                )
            if cur.rowcount == 0:
                # Re-query rather than reuse `row` — a concurrent request may
                # have changed the row between the SELECT above and this UPDATE
                # (exactly the race these atomic guards exist to catch), and
                # `row` would otherwise report the already-superseded value.
                fresh = con.execute(
                    "SELECT status, archived_at, agent_id FROM videos WHERE id = ?",
                    (video_id,),
                ).fetchone()
                if only_if and (not fresh or fresh["status"] != only_if
                                or fresh["archived_at"]):
                    return jsonify({
                        "error": "Status precondition failed",
                        "current": fresh["status"] if fresh else row["status"],
                        "expected": only_if,
                    }), 409
                if not fresh or fresh["archived_at"]:
                    return jsonify({"error": "Video is archived and can no longer be changed"}), 409
                # The same shape as an onlyIfCurrentStatus miss: the request
                # was validated at a status the video has since left.
                if frozen_bound and fresh["status"] != row["status"]:
                    return jsonify({
                        "error": "Status precondition failed",
                        "current": fresh["status"],
                        "expected": row["status"],
                    }), 409
                return jsonify({
                    "error": "This video's agent changed while the request was in flight — "
                             "reload and pick the model again"
                }), 409
            video = _video_with_comments(con, video_id)

        return jsonify(video)

    # The poller reports every finished session here (TMDEV-129), and this
    # route alone decides whether it was progress: the agent CLIs are
    # unreliable reporters (Claude exits 0 on an unknown model; Codex exits 0
    # with every MCP call refused), so the database is the only witness. A
    # status that differs from the one the session started at is progress,
    # whoever changed it. The count is one atomic UPDATE, so two reports can
    # never lose an increment. updated_at is deliberately untouched: it is the
    # poller's FIFO key and the stalled-VOICING clock. session_key makes a
    # replayed report — a successor finishing a dead supervisor's session — a
    # no-op rather than a second count.
    @bp.post("/videos/<video_id>/agent-outcome")
    def agent_outcome(video_id: str):
        body = request.get_json(force=True, silent=True) or {}
        start_status = body.get("start_status")
        if start_status not in VALID_VIDEO_STATUSES:
            return jsonify({"error": f"start_status must be one of "
                                     f"{sorted(VALID_VIDEO_STATUSES)}"}), 400
        session_key = body.get("session_key")
        if session_key is not None and (not isinstance(session_key, str)
                                        or not 1 <= len(session_key) <= 100):
            return jsonify({"error": "session_key must be a string of 1 to 100 characters"}), 400
        with _conn() as con:
            # IS NOT, so a NULL stored key never matches; a report without a
            # key is counted as it always was.
            cur = con.execute(
                "UPDATE videos SET agent_no_progress_count = CASE WHEN status = ?"
                " THEN agent_no_progress_count + 1 ELSE 0 END,"
                " agent_last_outcome_key = COALESCE(?, agent_last_outcome_key)"
                " WHERE id = ? AND archived_at IS NULL"
                " AND (? IS NULL OR agent_last_outcome_key IS NOT ?)",
                (start_status, session_key, video_id, session_key, session_key))
            row = con.execute(
                "SELECT status, agent_no_progress_count, agent_stuck_at, archived_at,"
                " agent_last_outcome_key FROM videos WHERE id = ?", (video_id,)).fetchone()
            if row is None:
                return jsonify({"error": "Video not found"}), 404
            count = row["agent_no_progress_count"]
            stuck = row["agent_stuck_at"] is not None
            replayed = (bool(session_key) and cur.rowcount == 0 and not row["archived_at"]
                        and row["agent_last_outcome_key"] == session_key)
            if cur.rowcount and not stuck and count >= AGENT_NO_PROGRESS_CAP:
                now = _now()
                # Guarded on IS NULL so a racing report cannot comment twice.
                flagged = con.execute(
                    "UPDATE videos SET agent_stuck_at = ?"
                    " WHERE id = ? AND agent_stuck_at IS NULL", (now, video_id)).rowcount
                if flagged:
                    con.execute(
                        "INSERT INTO comments (video_id, author, content, created_at)"
                        " VALUES (?, 'agent', ?, ?)",
                        (video_id,
                         f"The scheduled agent ran {count} sessions in a row on this video at "
                         f"{row['status']} without moving it forward, so the poller has "
                         f"stopped picking it up. Check poll.log for what the sessions did, "
                         f"then change the video's status or press Retry agent on the "
                         f"dashboard to hand it back.",
                         now))
                stuck = True
        return jsonify({"status": row["status"], "count": count, "stuck": stuck,
                        "replayed": replayed})

    # The dashboard's Retry agent (TMDEV-129): a human hands a stuck video back
    # to the poller without having to change its status.
    @bp.post("/videos/<video_id>/agent-retry")
    def agent_retry(video_id: str):
        with _conn() as con:
            cur = con.execute(
                "UPDATE videos SET agent_no_progress_count = 0, agent_stuck_at = NULL"
                " WHERE id = ? AND archived_at IS NULL", (video_id,))
            if cur.rowcount == 0:
                exists = con.execute(
                    "SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone()
                if not exists:
                    return jsonify({"error": "Video not found"}), 404
                return jsonify({"error": "Video is archived and can no longer be changed"}), 409
            video = _video_with_comments(con, video_id)
        return jsonify(video)

    @bp.post("/videos/<video_id>/comments")
    def add_comment(video_id: str):
        body = request.get_json(force=True) or {}
        author = body.get("author", "human")
        content = body.get("content", "")
        if not content:
            return jsonify({"error": "content is required"}), 400
        if author not in ("human", "agent"):
            return jsonify({"error": "author must be 'human' or 'agent'"}), 400

        with _conn() as con:
            if not con.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone():
                return jsonify({"error": "Video not found"}), 404
            con.execute(
                "INSERT INTO comments (video_id, author, content, created_at) VALUES (?, ?, ?, ?)",
                (video_id, author, content, _now()),
            )
        return jsonify({"ok": True}), 201

    @bp.delete("/videos/<video_id>")
    def delete_video(video_id: str):
        """Delete a video's files, keeping and archiving its record (TMDEV-84).

        The same operation as the worker's retention sweep, so "delete" has one
        meaning in the UI. There is deliberately no hard delete that drops the
        row. Allowed only from DELETABLE_STATUSES — see there for why the
        scene-claim statuses are blocked rather than checked against the claim.
        """
        out = archive_video(db_path, video_id, DELETABLE_STATUSES, "human",
                            "Deleted from the dashboard: the rendered video and its "
                            "working files were removed; this record is kept in the Archive.")
        if out["result"] == "not_found":
            return jsonify({"error": "Video not found"}), 404
        if out["result"] == "conflict":
            if out["archived_at"]:
                return jsonify({"error": "Video is already archived",
                                "archived_at": out["archived_at"]}), 409
            return jsonify({
                "error": f"A video cannot be deleted while it is {out['status']}.",
                "current": out["status"],
            }), 409
        return jsonify({"ok": True, "archived_at": out["archived_at"],
                        "file_errors": out["file_errors"]})

    @bp.get("/retention/backlog")
    def retention_backlog():
        """What unpublished_retention_days would free (TMDEV-134).

        Every non-archived FAILED and TOPIC_REJECTED video, regardless of age or
        of whether the key is on: its job is to make the opt-in discoverable, so
        it has to answer before anyone turns it on. Read-only.
        """
        statuses = sorted(UNPUBLISHED_RETENTION_STATUSES)
        with _conn() as con:
            rows = con.execute(
                "SELECT id, status, project_id FROM videos"
                f" WHERE archived_at IS NULL AND status IN ({','.join('?' * len(statuses))})",
                statuses).fetchall()
        out = {word: {"count": 0, "bytes": 0}
               for word in UNPUBLISHED_RETENTION_STATUSES.values()}
        for row in rows:
            bucket = out[UNPUBLISHED_RETENTION_STATUSES[row["status"]]]
            bucket["count"] += 1
            bucket["bytes"] += (
                _file_bytes(_output_path(row["project_id"], row["id"]))
                + _job_dir_bytes(row["id"]))
        return jsonify(out)

    @bp.post("/videos")
    def create_video():
        body = request.get_json(force=True) or {}
        required = ("topic", "strategy", "producibility_score")
        missing = [k for k in required if k not in body]
        if missing:
            return jsonify({"error": f"Missing fields: {missing}"}), 400

        voice_id = body.get("voice_id", "")
        # Type-check before clipping. _truncate_title takes len() and slices, so
        # an int or bool raises there, and a list or dict slips past it only to
        # fail at the INSERT — either way a 500 for what is a client error.
        # Same rule as patch_video; null/omitted still means "no title".
        raw_title = body.get("title") or ""
        if not isinstance(raw_title, str):
            return jsonify({"error": "title must be a string"}), 400
        title, title_warning = _truncate_title(raw_title)

        # The id names the video's job directory, so a caller-chosen one must
        # be a plain path segment (TMDEV-158). This route only ever creates.
        vid = body.get("id") or str(uuid.uuid4())
        if not tids.check_segment(vid):
            return jsonify({"error": f"id {vid!r} is not a valid id: {tids.SEGMENT_RULE}"}), 400
        now = _now()
        with _conn() as con:
            # Checked here rather than left to the foreign key, which surfaced
            # as an unhandled 500.
            project_id = body.get("project_id")
            if project_id is not None and (not isinstance(project_id, str) or not con.execute(
                    "SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()):
                return jsonify({"error": f"project_id {project_id!r} does not exist"}), 400
            if voice_id:
                roster_ids = {v["voice_id"] for v in _read_all_settings(con)["elevenlabs_voices"]}
                if voice_id not in roster_ids:
                    return jsonify({"error": f"voice_id {voice_id!r} is not in elevenlabs_voices"}), 400
            # A paused or expired domain refuses new videos except a manual
            # one — an explicit human request outranks a pause (TMDEV-115) and
            # the topic cap (TMDEV-153). Reads status alone so a stray paused
            # non-seed refuses too. Keep in sync: mcp/server.py's create_video.
            if body.get("project_id") and body["strategy"] != "manual":
                closed = _closed_domain_error(con, body["project_id"])
                if closed:
                    return jsonify({"error": closed}), 409
            # A project default seeds only its curriculum videos (TMDEV-101):
            # the register reads as a series identity, and curriculum is the
            # one strategy that produces a series. Keep in sync: mcp/server.py's
            # create_video. An explicit visual_style in the body still wins.
            visual_style = (body.get("visual_style") or "").strip()
            if visual_style and visual_style not in VISUAL_STYLES:
                return jsonify({
                    "error": f"Invalid visual_style '{visual_style}'. "
                             f"Must be one of: {sorted(VISUAL_STYLES)}"
                }), 400
            # Only an explicit choice is refused. A seeded default is taken as
            # stored, never rewritten; if the key has gone since the domain's
            # default was set, the approval PATCH (which carries visual_style)
            # refuses it at the topic checkpoint, before any spend.
            if _illustrated_needs_key(con, visual_style):
                return jsonify({"error": ILLUSTRATED_NEEDS_OPENAI_KEY}), 400
            # Unlike visual_style, a project's default voice seeds EVERY video
            # filed into it, whatever the strategy (TMDEV-121) — it is the
            # domain's narrator, not a series identity. An explicit voice wins.
            # Keep in sync: mcp/server.py's create_video.
            if not voice_id:
                voice_id = _project_default_voice(con, body.get("project_id"),
                                                  _read_all_settings(con))
            if not visual_style:
                visual_style = DEFAULT_VISUAL_STYLE
                if body.get("strategy") == "curriculum" and body.get("project_id"):
                    prow = con.execute(
                        "SELECT default_visual_style FROM projects WHERE id = ?",
                        (body["project_id"],)).fetchone()
                    seeded = ((prow["default_visual_style"] if prow else "") or "").strip()
                    if seeded in VISUAL_STYLES:
                        visual_style = seeded
            # The default script profile seeds curriculum videos only, like the
            # visual style (TMDEV-145). A profile no longer READY seeds nothing:
            # the approving PATCH would refuse it. Keep in sync: mcp/server.py's
            # create_video.
            script_profile_id = ""
            if body.get("strategy") == "curriculum" and body.get("project_id"):
                prow = con.execute(
                    "SELECT default_script_profile_id FROM projects WHERE id = ?",
                    (body["project_id"],)).fetchone()
                seeded = (prow["default_script_profile_id"] if prow else "") or ""
                if seeded and not _script_profile_error(con, seeded):
                    script_profile_id = seeded
            # The check above runs outside any transaction, so a pause or another
            # session's topic committed since then would be missed; the INSERT
            # re-checks both itself.
            cur = con.execute(
                f"""INSERT INTO videos
                   (id, project_id, title, topic, strategy, producibility_score,
                    status, video_version, voice_id, agent_id, visual_style,
                    script_profile_id, created_at, updated_at)
                   SELECT ?, ?, ?, ?, ?, ?, 'TOPIC_PROPOSED', 1, ?, ?, ?, ?, ?, ?
                   WHERE {_DOMAIN_OPEN_GUARD}""",
                (vid, body.get("project_id"), title,
                 body["topic"], body["strategy"], body["producibility_score"], voice_id,
                 _pick_agent_id(con), visual_style, script_profile_id, now, now,
                 body["strategy"], body.get("project_id")),
            )
            if cur.rowcount == 0:
                return jsonify({"error": _closed_domain_error(con, body["project_id"])
                                or _paused_domain_error(body["project_id"],
                                                        body["project_id"])}), 409
            video = _video_with_comments(con, vid)
        if title_warning:
            video["warning"] = title_warning
        return jsonify(video), 201

    @bp.post("/videos/manual")
    def create_manual_video():
        """A video submitted by hand from the dashboard's New Video page
        (TMDEV-118), filed into the MANUAL_PROJECT_ID domain.

        Deliberately not POST /videos, whose contract suits a research run
        where failing a create would lose the topic: it clips an over-long
        title and ignores agent_id. A human is present here and picked the
        agent, so an over-long title is refused and a picked agent is kept.
        The video is unscored (0), because submitting it is the approval.

        Everything is validated before anything is written — _conn() commits
        on exit, so a refusal after the domain INSERT would leave an empty
        domain behind.
        """
        body = request.get_json(force=True) or {}

        title = body.get("title")
        if not isinstance(title, str) or not title.strip():
            return jsonify({"error": "title is required"}), 400
        title = title.strip()
        if len(title) > VIDEO_TITLE_MAX_LEN:
            return jsonify({
                "error": f"title is {len(title)} characters; the display name must be at most "
                         f"{VIDEO_TITLE_MAX_LEN}. Shorten it — the full text belongs in topic."
            }), 400
        topic = body.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            return jsonify({"error": "topic is required"}), 400
        topic = topic.strip()

        approve = body.get("approve", True)
        if not isinstance(approve, bool):
            return jsonify({"error": "approve must be true or false"}), 400
        status = "TOPIC_APPROVED" if approve else "TOPIC_PROPOSED"

        # The optional picks are type-checked on the raw value, before blank or
        # default semantics apply: `body.get(k) or ""` would turn a false or 0
        # into "" and accept it as "the default" instead of refusing it. Absent
        # and null both mean the default. A list or dict would otherwise reach
        # a set lookup or a SQL parameter and surface as a 500.
        picks = {}
        for key in ("agent_id", "agent_model", "agent_effort",
                    "visual_style", "voice_id", "script_profile_id"):
            raw = body.get(key)
            if raw is not None and not isinstance(raw, str):
                return jsonify({"error": f"{key} must be a string"}), 400
            picks[key] = (raw or "").strip()

        # The same shape rules as patch_video; membership is checked below,
        # against the agent the video will actually have.
        agent_id = picks["agent_id"] or None
        agent_model = picks["agent_model"]
        if agent_model and (" " in agent_model or agent_model.startswith("-")):
            return jsonify({
                "error": f"agent_model must be a model alias (sonnet, opus, ...) or full ID "
                         f"with no spaces, or blank for the agent's default model, "
                         f"got {agent_model!r}"
            }), 400
        agent_effort = picks["agent_effort"]
        if agent_effort not in ("",) + AGENT_EFFORTS:
            return jsonify({
                "error": f"agent_effort must be one of {list(AGENT_EFFORTS)}, or blank for the "
                         f"agent's own effort, got {agent_effort!r}"
            }), 400

        visual_style = picks["visual_style"] or DEFAULT_VISUAL_STYLE
        if visual_style not in VISUAL_STYLES:
            return jsonify({
                "error": f"Invalid visual_style '{visual_style}'. "
                         f"Must be one of: {sorted(VISUAL_STYLES)}"
            }), 400
        voice_id = picks["voice_id"]
        profile_id = picks["script_profile_id"]

        vid = str(uuid.uuid4())
        now = _now()
        with _conn() as con:
            if voice_id:
                roster_ids = {v["voice_id"] for v in _read_all_settings(con)["elevenlabs_voices"]}
                if voice_id not in roster_ids:
                    return jsonify({"error": f"voice_id {voice_id!r} is not in elevenlabs_voices"}), 400
            if profile_id:
                err = _script_profile_error(con, profile_id)
                if err:
                    return jsonify({"error": err}), 400
            if _illustrated_needs_key(con, visual_style):
                return jsonify({"error": ILLUSTRATED_NEEDS_OPENAI_KEY}), 400
            if agent_id:
                err = _agent_id_error(con, None, agent_id)
                if err:
                    return jsonify({"error": err}), 400
            else:
                # Dealt like every other new video, so the configured weights
                # still hold for a human who leaves the picker on Automatic.
                # Dealing writes the deck — from here on a refusal rolls back.
                agent_id = _pick_agent_id(con)
            if agent_model:
                err = _agent_model_error(con, agent_id, agent_model)
                if err:
                    con.rollback()
                    return jsonify({"error": err}), 400
            con.execute(
                """INSERT OR IGNORE INTO projects
                   (id, name, description, is_curriculum_seed, status, created_at)
                   VALUES (?, ?, ?, 0, 'active', ?)""",
                (MANUAL_PROJECT_ID, MANUAL_PROJECT_NAME, MANUAL_PROJECT_DESCRIPTION, now),
            )
            # "Default" on the New Video page means the manual domain's default
            # voice when it has one (TMDEV-121), else the install default.
            if not voice_id:
                voice_id = _project_default_voice(con, MANUAL_PROJECT_ID,
                                                  _read_all_settings(con))
            con.execute(
                """INSERT INTO videos
                   (id, project_id, title, topic, strategy, producibility_score, status,
                    video_version, voice_id, agent_id, agent_model, agent_effort,
                    script_profile_id, visual_style, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'manual', 0, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (vid, MANUAL_PROJECT_ID, title, topic, status, voice_id, agent_id,
                 agent_model, agent_effort, profile_id, visual_style, now, now),
            )
            video = _video_with_comments(con, vid)
        return jsonify(video), 201

    # ── /projects ─────────────────────────────────────────────────────────────

    @bp.get("/projects")
    def list_projects():
        # topic_count and expired are derived (TMDEV-153), never stored.
        with _conn() as con:
            rows = con.execute(f"{_PROJECT_SELECT} ORDER BY p.created_at DESC").fetchall()
        return jsonify([_project_out(r) for r in rows])

    @bp.post("/projects")
    def create_project():
        body = request.get_json(force=True) or {}
        if "name" not in body:
            return jsonify({"error": "Missing field: name"}), 400
        pid = body.get("id") or f"proj_{uuid.uuid4().hex[:8]}"
        if not isinstance(pid, str):
            return jsonify({"error": "id must be a string"}), 400
        is_seed = int(bool(body.get("is_curriculum_seed", False)))
        status = body.get("status", "active")
        if status not in ("active", "paused"):
            return jsonify({"error": "status must be 'active' or 'paused'"}), 400
        # Only a curriculum seed can be paused (TMDEV-115). This route is a full
        # replace — an omitted status is written as 'active' — so clearing the
        # seed flag reactivates a paused domain without a rule of its own.
        # Keep in sync: mcp/server.py's upsert_project.
        if status == "paused" and not is_seed:
            return jsonify({"error": _non_seed_pause_error(pid)}), 400
        # Absent and null both mean none, which on this full replace is what
        # omission means. Its length is checked below, against the stored row.
        description = body.get("description")
        if description is None:
            description = ""
        if not isinstance(description, str):
            return jsonify({"error": _description_error(description)}), 400
        # "" means the domain has no preference, which is not the same as
        # "auto": auto is a per-video instruction to the agent, this is the
        # absence of a domain-level one. Keep in sync: mcp/server.py's
        # upsert_project.
        default_style = (body.get("default_visual_style") or "").strip()
        if default_style and default_style not in VISUAL_STYLES:
            return jsonify({
                "error": f"Invalid default_visual_style '{default_style}'. Must be one of: "
                         f"{sorted(VISUAL_STYLES)}, or \"\" for no default"
            }), 400
        default_voice = body.get("default_voice_id") or ""
        if not isinstance(default_voice, str):
            return jsonify({"error": "default_voice_id must be a string"}), 400
        default_voice = default_voice.strip()
        # Type-checked on the raw value: `or ""` first would read a false, 0 or
        # [] as "no default" and silently clear the stored one. Absent and null
        # both mean none, which on this full replace is what omission means.
        default_profile = body.get("default_script_profile_id")
        if default_profile is None:
            default_profile = ""
        if not isinstance(default_profile, str):
            return jsonify({"error": "default_script_profile_id must be a string"}), 400
        default_profile = default_profile.strip()
        # Absent and null mean the default, which on this full replace is what
        # omission means. A cap below what the domain already holds is allowed:
        # it expires the domain at once, which is the human's call to make.
        # Keep in sync: mcp/server.py's upsert_project.
        topic_cap = body.get("topic_cap")
        if topic_cap is None:
            topic_cap = TOPIC_CAP_DEFAULT
        cap_error = _topic_cap_error(topic_cap)
        if cap_error:
            return jsonify({"error": cap_error}), 400
        with _conn() as con:
            # A default is a choice made now for videos filed later, so it is
            # refused on the same terms as a per-video one — but only when it
            # CHANGES to illustrated. This route is a full replace, so every
            # edit to a domain re-sends its stored default; refusing that would
            # block unrelated edits once a key is removed. A kept default is
            # harmless: seeding never rewrites, and the approval PATCH refuses.
            prev = con.execute(
                "SELECT description, default_visual_style, default_voice_id, "
                "default_script_profile_id FROM projects WHERE id = ?",
                (pid,)).fetchone()
            # The id names the domain's output directory, so a NEW one must be a
            # plain path segment (TMDEV-158). Only a new one: this is an upsert
            # the dashboard re-sends on every edit, and a domain an agent filed
            # under an odd id (say `node.js-internals`) must stay editable.
            # Keep in sync: mcp/server.py's upsert_project.
            if prev is None and not tids.check_segment(pid):
                return jsonify({"error": f"id {pid!r} is not a valid id: {tids.SEGMENT_RULE}"}), 400
            # The description cap (TMDEV-170) is checked only when the text
            # changes: every edit re-sends it, and one stored longer before the
            # cap existed must not block them. Keep in sync: mcp/server.py's
            # upsert_project.
            if prev is None or (prev["description"] or "") != description:
                err = _description_error(description)
                if err:
                    return jsonify({"error": err}), 400
            unchanged = prev is not None and (prev["default_visual_style"] or "") == default_style
            if not unchanged and _illustrated_needs_key(con, default_style):
                return jsonify({"error": ILLUSTRATED_NEEDS_OPENAI_KEY}), 400
            # The default voice (TMDEV-121) follows the same rule: checked
            # against the roster only when it changes, so a voice removed from
            # the roster later does not block every other edit to the domain.
            # A stale one is harmless — seeding skips a voice not in the roster.
            # Keep in sync: mcp/server.py's upsert_project.
            voice_unchanged = prev is not None and (prev["default_voice_id"] or "") == default_voice
            if default_voice and not voice_unchanged:
                roster_ids = {v["voice_id"] for v in _read_all_settings(con)["elevenlabs_voices"]}
                if default_voice not in roster_ids:
                    return jsonify({
                        "error": f"default_voice_id {default_voice!r} is not in elevenlabs_voices"
                    }), 400
            # The default script profile (TMDEV-145) follows the same rule: a
            # READY, unarchived profile, checked only when it changes. A stored
            # one archived since is harmless — seeding skips it.
            # Keep in sync: mcp/server.py's upsert_project.
            profile_unchanged = (prev is not None
                                 and (prev["default_script_profile_id"] or "") == default_profile)
            if default_profile and not profile_unchanged:
                err = _script_profile_error(con, default_profile)
                if err:
                    return jsonify({"error": err}), 400
            con.execute(
                """INSERT INTO projects (id, name, description, is_curriculum_seed, status,
                                         default_visual_style, default_voice_id,
                                         default_script_profile_id, topic_cap, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     description=excluded.description,
                     is_curriculum_seed=excluded.is_curriculum_seed,
                     status=excluded.status,
                     default_visual_style=excluded.default_visual_style,
                     default_voice_id=excluded.default_voice_id,
                     default_script_profile_id=excluded.default_script_profile_id,
                     topic_cap=excluded.topic_cap""",
                (pid, body["name"], description, is_seed, status,
                 default_style, default_voice, default_profile, topic_cap, _now()),
            )
            row = con.execute(f"{_PROJECT_SELECT} WHERE p.id = ?", (pid,)).fetchone()
        return jsonify(_project_out(row)), 201

    @bp.post("/projects/<project_id>/status")
    def set_project_status(project_id: str):
        body = request.get_json(force=True) or {}
        status = body.get("status")
        if status not in ("active", "paused"):
            return jsonify({"error": "status must be 'active' or 'paused'"}), 400
        with _conn() as con:
            row = con.execute("SELECT is_curriculum_seed FROM projects WHERE id = ?",
                              (project_id,)).fetchone()
            if not row:
                return jsonify({"error": "Project not found"}), 404
            if status == "paused" and not row["is_curriculum_seed"]:
                return jsonify({"error": _non_seed_pause_error(project_id)}), 409
            con.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))
            updated = con.execute(f"{_PROJECT_SELECT} WHERE p.id = ?", (project_id,)).fetchone()
        return jsonify(_project_out(updated))

    @bp.get("/research/strategies")
    def get_research_strategies():
        with _conn() as con:
            return jsonify({"strategies": _active_strategies(con),
                            "mining_available": _mining_available(con)})

    @bp.post("/research/strategies")
    def set_research_strategies():
        body = request.get_json(force=True) or {}
        strategies = body.get("strategies", [])
        valid = {"curriculum", "trending", "mining"}
        invalid = [s for s in strategies if s not in valid]
        if invalid:
            return jsonify({"error": f"Invalid strategies: {invalid}. Valid: {sorted(valid)}"}), 400
        with _conn() as con:
            stored = strategies
            if not _mining_available(con):
                if "mining" in strategies:
                    return jsonify({"error": MINING_NEEDS_GEMINI_KEY}), 400
                # The caller only sees the list with mining filtered out, so a
                # stored mining choice is kept as it was: it comes back on its
                # own once a key is added.
                if "mining" in _stored_strategies(con):
                    stored = strategies + ["mining"]
            value = ",".join(stored)
            con.execute(
                "INSERT INTO settings (key, value) VALUES ('active_strategies', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (value,),
            )
        return jsonify({"strategies": strategies})

    # ── /settings ─────────────────────────────────────────────────────────────

    @bp.get("/settings")
    def get_settings():
        with _conn() as con:
            data = _read_all_settings(con)
        return jsonify(_mask_settings(data))

    @bp.post("/settings")
    def post_settings():
        body = request.get_json(force=True) or {}
        unknown = [k for k in body if k not in SETTINGS_SPEC]
        if unknown:
            return jsonify({
                "error": f"Unknown settings: {unknown}. Valid: {sorted(SETTINGS_SPEC)}"
            }), 400

        with _conn() as con:
            # Read before coercion (TMDEV-73): the secret no-op check below
            # needs the currently stored values to compare masks against.
            current = _read_all_settings(con)

            # GET /settings hands the dashboard a mask, and it round-trips the
            # field back on save. Treat "unchanged mask" as "don't touch this
            # key" — without this, opening Settings and changing anything else
            # would overwrite every stored key with its own mask.
            # Only when something IS stored: a mask-shaped value posted against
            # an empty key is a real (if odd) value, not a no-op.
            body = {
                k: v for k, v in body.items()
                if not (
                    SETTINGS_SPEC[k][0] == "secret"
                    and current.get(k)
                    and v == _mask_secret(current[k])
                )
            }

            coerced = {}
            for key, raw in body.items():
                try:
                    py_val, db_str = _coerce_setting(key, raw)
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400
                coerced[key] = db_str

            # Live check that the webhook still exists (TMDEV-5). A GET on a
            # webhook URL sends no message and needs no auth, so this costs one
            # cheap request and catches a revoked or mistyped URL here rather
            # than as notifications that silently never arrive.
            #
            # Only a *positive* rejection gates the save, mirroring
            # onboard/api_keys.py: "unknown" (timeout, DNS, 5xx, rate limit)
            # stores the URL anyway. Refusing on an unreachable Discord would
            # make Settings un-saveable for reasons that have nothing to do
            # with what was typed.
            webhook = coerced.get("discord_webhook_url")
            if webhook:
                verdict, detail = discord_notify.verify_webhook(webhook)
                if verdict == "invalid":
                    return jsonify({
                        "error": f"Discord rejected that webhook URL: {detail}"
                    }), 400

            for key, db_str in coerced.items():
                con.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, db_str),
                )
            data = _read_all_settings(con)
        # Masked like GET: this response is what the dashboard stores as its
        # local state, so returning raw keys here would leak them on every save.
        return jsonify(_mask_settings(data))

    # ── /voices/<voice_id>/preview ──────────────────────────────────────────────
    # Generate-if-missing, idempotent audio preview for a roster voice (TMDEV-51
    # follow-up). Deliberately its own endpoint, not part of POST /settings — a
    # settings save must stay a cheap DB write, not up to 10 paid, slow, fallible
    # ElevenLabs calls. The credits a generated preview spends are recorded in
    # the usage ledger with no video (TMDEV-107) and returned to the caller; a
    # cached preview makes no call and records nothing.

    @bp.post("/voices/<voice_id>/preview")
    def voice_preview(voice_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", voice_id):
            return jsonify({"error": "voice_id must match [A-Za-z0-9_-]+"}), 400

        with _conn() as con:
            settings = _read_all_settings(con)
        voice = next((v for v in settings["elevenlabs_voices"] if v["voice_id"] == voice_id), None)
        if voice is None:
            return jsonify({
                "error": f"voice_id {voice_id!r} is not in elevenlabs_voices"
            }), 400
        # The preview speaks with the voice's own model (TMDEV-121). The body
        # may name another one so the Settings page can preview a model change
        # before it is saved; the cache key includes the model, so a changed
        # model always produces a fresh sample. silent=True, not force=True:
        # the dashboard proxy sends every preview with an empty body.
        body = request.get_json(silent=True)
        model_id = (body.get("model_id") if isinstance(body, dict) else None) or voice["model_id"]
        if not isinstance(model_id, str) or model_id not in DICTIONARY_COMPATIBLE_MODELS:
            return jsonify({
                "error": f"model_id must be one of {sorted(DICTIONARY_COMPATIBLE_MODELS)}, "
                         f"got {model_id!r}"
            }), 400

        api_key = _secret(settings, "elevenlabs_api_key", "ELEVENLABS_API_KEY")
        if not api_key:
            return jsonify({
                "error": "ElevenLabs API key not configured — previews require ElevenLabs "
                         "access. Add it on the Settings page."
            }), 503

        cache_key = hashlib.sha256(
            f"{voice_id}|{model_id}|{VOICE_PREVIEW_SAMPLE_TEXT}".encode()
        ).hexdigest()[:16]
        preview_dir = OUTPUT_DIR / "voice-previews"
        preview_path = preview_dir / f"{cache_key}.mp3"
        container_path = f"/output_videos/voice-previews/{cache_key}.mp3"

        if preview_path.exists():
            return jsonify({"path": container_path, "cached": True, "credits": 0})

        import httpx as _httpx
        payload = {
            "text": VOICE_PREVIEW_SAMPLE_TEXT,
            "model_id": model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            "output_format": "mp3_44100_128",
        }
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        try:
            with _httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    json=payload,
                    headers=headers,
                )
        except Exception as e:
            return jsonify({"error": f"ElevenLabs request failed: {e}"}), 502
        if resp.status_code != 200:
            return jsonify({"error": f"ElevenLabs {resp.status_code}: {resp.text[:400]}"}), 502
        credits, estimated = _elevenlabs_credits(resp, VOICE_PREVIEW_SAMPLE_TEXT)
        tusage.record_usage(db_path, service="elevenlabs", model=model_id,
                            operation="voice_preview", units={"credits": credits},
                            request_id=resp.headers.get("request-id"), estimated=estimated)

        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(resp.content)
        return jsonify({"path": container_path, "cached": False, "credits": credits})

    # ── /pipeline/pause ───────────────────────────────────────────────────────

    @bp.post("/pipeline/pause")
    def pipeline_pause():
        body = request.get_json(force=True) or {}
        paused = body.get("paused")
        if not isinstance(paused, bool):
            return jsonify({"error": "'paused' must be a boolean"}), 400
        _, db_str = _coerce_setting("pipeline_paused", paused)
        with _conn() as con:
            con.execute(
                "INSERT INTO settings (key, value) VALUES ('pipeline_paused', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (db_str,),
            )
        return jsonify({"paused": paused})

    # ── /research/mining-sources ──────────────────────────────────────────────

    @bp.get("/research/mining-sources")
    def get_mining_sources():
        with _conn() as con:
            row = con.execute(
                "SELECT value FROM settings WHERE key = 'mining_youtube_urls'"
            ).fetchone()
        urls = _json.loads(row["value"]) if row else []
        return jsonify({"youtube_urls": urls})

    @bp.post("/research/mining-sources")
    def set_mining_sources():
        body = request.get_json(force=True) or {}
        # Each URL becomes Gemini's file_uri on a paid mining call, so the list
        # is refused whole if any entry is not a YouTube video URL, and stored
        # canonical and deduplicated. Keep in sync: mcp/server.py's
        # set_mining_sources (both call the one rule in tubematic_core).
        urls, error = tyoutube.check_mining_sources(body.get("youtube_urls"))
        if error:
            return jsonify({"error": error}), 400
        value = _json.dumps(urls)
        with _conn() as con:
            con.execute(
                "INSERT INTO settings (key, value) VALUES ('mining_youtube_urls', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (value,),
            )
        return jsonify({"youtube_urls": urls})

    # ── /research/record-run ─────────────────────────────────────────────────
    # Called by poll.py right before it invokes a research agent session, so
    # research_runs_today reflects attempts, not completions -- a crashed or
    # forgotten mark_research_done() must not leave the cap stuck at 0 forever.
    # No atomic claim needed: poll.py holds an exclusive flock for its entire
    # run, so at most one process ever reaches this read-prune-append-write.

    # ── /usage/agent-session ─────────────────────────────────────────────────
    # How an agent CLI run's usage reaches the ledger (TMDEV-107). poll.py has
    # no database access by design, so it parses the CLI's JSON output and
    # posts the events here, tagged with the videos the session was for.
    # Idempotent per (session_id, event position): resending a payload whose
    # first attempt timed out after committing records nothing twice.

    @bp.post("/usage/agent-session")
    def record_agent_session():
        body = request.get_json(silent=True) or {}
        operation = body.get("operation")
        if operation not in tusage.AGENT_OPERATIONS:
            return jsonify({"error": f"operation must be one of "
                                     f"{', '.join(tusage.AGENT_OPERATIONS)}"}), 400
        events = body.get("events")
        if not isinstance(events, list) or not events or len(events) > 50:
            return jsonify({"error": "events must be a non-empty list (at most 50)"}), 400
        videos = [v for v in body.get("videos") or []
                  if isinstance(v, dict) and isinstance(v.get("video_id"), str)]
        session_id = str(body.get("session_id") or "")[:100]
        if not session_id:
            return jsonify({"error": "session_id is required — it is what makes a resent "
                                     "report idempotent"}), 400
        recorded = 0
        for index, ev in enumerate(events):
            if not isinstance(ev, dict) or not isinstance(ev.get("service"), str):
                continue
            units = ev.get("units") if isinstance(ev.get("units"), dict) else {}
            reported = ev.get("reported_cost_usd")
            if tusage.record_usage(
                    db_path, service=ev["service"][:40], model=str(ev.get("model") or "")[:200],
                    operation=operation,
                    units={k: v for k, v in units.items()
                           if isinstance(v, (int, float)) and not isinstance(v, bool)},
                    raw=ev.get("raw"), videos=videos, session_id=session_id,
                    reported_cost_usd=float(reported) if isinstance(reported, (int, float))
                    else None,
                    estimated=bool(ev.get("estimated")),
                    # Same session id + position on a resend → same key, so a
                    # replayed payload never doubles the session's spend.
                    event_key=f"agent:{session_id}:{index}") is not None:
                recorded += 1
        return jsonify({"recorded": recorded, "events": len(events)})

    @bp.post("/research/record-run")
    def record_research_run():
        with _conn() as con:
            pruned, _ = _research_run_window(con)
            pruned.append(_now())
            _write_research_run_window(con, pruned)
            cap = _read_all_settings(con)["max_research_runs_per_day"]
        return jsonify({"research_runs_today": len(pruned), "max_research_runs_per_day": cap})

    # ── /publishing ───────────────────────────────────────────────────────────
    # Publishing to social platforms via postforme.dev (TMDEV-83). Every route
    # here is human-driven from the dashboard; no MCP tool touches any of it,
    # deliberately — the cron agent must never be able to post to a real
    # account. The one unattended path is Auto Pilot (TMDEV-139), which runs in
    # the worker and calls start_publish directly, never these routes. The
    # postforme key is read from the settings table by both processes.

    def _publishing_context():
        """(settings, api_key) once publishing is usable, else a 503 response.

        Both gates are checked before any outbound call so a misconfigured
        install gets an actionable message rather than a postforme error.
        """
        with _conn() as con:
            settings = _read_all_settings(con)
        if not settings.get("publishing_enabled"):
            return None, None, (jsonify({
                "error": "Publishing is disabled — turn it on in Settings first."
            }), 503)
        api_key = _secret(settings, "postforme_api_key", "POSTFORME_API_KEY")
        if not api_key:
            return None, None, (jsonify({
                "error": "postforme.dev API key not configured — publishing requires it. "
                         "Add it on the Settings page."
            }), 503)
        return settings, api_key, None

    # ── /autopilot ────────────────────────────────────────────────────────────
    # Auto Pilot (TMDEV-139): for the projects selected here the worker approves
    # every human checkpoint and schedules the post itself. The whole
    # configuration is read and written as one document, so the dashboard can
    # never save a switch that is on over a project list that failed to save.

    AUTO_PILOT_WAITING = ("TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY", "VIDEO_APPROVED")

    def _auto_pilot_payload(con) -> dict:
        settings = _read_all_settings(con)
        config = _auto_pilot_config(con)
        # What switching a project on would act on at once. The dashboard shows
        # it in the confirmation, because approving a backlog spends money the
        # moment the switch is saved.
        waiting: dict = {}
        for row in con.execute(
                "SELECT project_id, status, COUNT(*) AS cnt FROM videos"
                " WHERE archived_at IS NULL AND project_id IS NOT NULL AND status IN (%s)"
                " GROUP BY project_id, status" % ",".join("?" * len(AUTO_PILOT_WAITING)),
                AUTO_PILOT_WAITING):
            waiting.setdefault(row["project_id"], {})[row["status"]] = row["cnt"]
        return {
            "enabled": settings["auto_pilot_enabled"],
            "gap_mins": settings["auto_pilot_gap_mins"],
            "max_in_flight": settings["auto_pilot_max_in_flight"],
            # What the limit is held to, so the panel can say why Auto Pilot
            # has stopped starting videos when it is full.
            "in_flight": in_flight_count(con, config["projects"]),
            "projects": config["projects"],
            "account_limits": config["account_limits"],
            "default_daily_limit": AUTO_PILOT_DEFAULT_DAILY,
            "waiting": waiting,
        }

    @bp.get("/autopilot")
    def get_auto_pilot():
        """The Auto Pilot configuration. Not gated on publishing: Auto Pilot
        approves checkpoints with publishing off, and stops at VIDEO_APPROVED."""
        with _conn() as con:
            return jsonify(_auto_pilot_payload(con))

    @bp.post("/autopilot")
    def set_auto_pilot():
        """Replace the Auto Pilot configuration. Validated whole, written whole."""
        body = request.get_json(force=True) or {}
        try:
            _, enabled = _coerce_setting("auto_pilot_enabled", body.get("enabled"))
            _, gap = _coerce_setting("auto_pilot_gap_mins", body.get("gap_mins"))
            # Optional: a dashboard tab opened before the limit existed (or
            # before its rename) sends none, and saving from it must not reset
            # the stored one.
            ceiling = None
            if "max_in_flight" in body:
                _, ceiling = _coerce_setting("auto_pilot_max_in_flight",
                                             body["max_in_flight"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        projects, limits = body.get("projects"), body.get("account_limits")
        if not isinstance(projects, dict) or not all(
                isinstance(ids, list) and all(isinstance(a, str) for a in ids)
                for ids in projects.values()):
            return jsonify({"error": "projects must map a project id to a list of "
                                     "account ids"}), 400
        if not isinstance(limits, dict) or not all(
                isinstance(n, int) and not isinstance(n, bool)
                and 0 <= n <= MAX_AUTO_PILOT_DAILY for n in limits.values()):
            return jsonify({"error": "account_limits must map an account id to a whole "
                                     f"number between 0 and {MAX_AUTO_PILOT_DAILY}"}), 400

        with _conn() as con:
            known = {r["id"] for r in con.execute("SELECT id FROM projects")}
            unknown = sorted(set(projects) - known)
            if unknown:
                return jsonify({"error": f"Unknown project(s): {', '.join(unknown)}"}), 400
            # The same allowlist a human publish is held to. Auto Pilot must
            # never be a way to post to an account the Socials page has off.
            #
            # An id already stored for the same project is let through: it was
            # allowed when it was added, and refusing it now would refuse every
            # later save, turning Auto Pilot off included. It cannot be posted
            # to either way, because the worker re-checks the allowlist.
            allowed = set(_allowed_account_ids(con))
            stored = _auto_pilot_config(con)["projects"]
            outside = sorted({a for pid, ids in projects.items() for a in ids
                              if a not in allowed and a not in stored.get(pid, [])})
            if outside:
                return jsonify({
                    "error": f"Not permitted to post to {', '.join(outside)} — "
                             "enable them on the Socials page first."
                }), 400
            config = {
                "projects": {pid: sorted(set(ids)) for pid, ids in projects.items()},
                "account_limits": limits,
            }
            writes = [("auto_pilot_enabled", enabled),
                      ("auto_pilot_gap_mins", gap),
                      ("auto_pilot_config", _json.dumps(config))]
            if ceiling is not None:
                writes.append(("auto_pilot_max_in_flight", ceiling))
            for key, value in writes:
                con.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value))
            return jsonify(_auto_pilot_payload(con))

    @bp.get("/publishing/accounts")
    def get_publishing_accounts():
        """Live accounts from postforme, reconciled against the allowlist.

        Reconciled rather than mirrored: an account the user disconnected
        upstream is reported `available: false` here, so the Socials page can
        say so — otherwise the first sign of it would be a failed publish.
        """
        # `?feeds=0` skips the probe below: the Analytics page only wants
        # names for its account filter, and a probe per load spends the 5/s
        # limit on a question it does not ask.
        probe_feeds = request.args.get("feeds") != "0"
        _settings, api_key, err = _publishing_context()
        if err:
            return err
        try:
            live = postforme.list_accounts(api_key)
        except postforme.PostformeError as e:
            return jsonify({"error": str(e)}), 502

        with _conn() as con:
            allowed = set(_allowed_account_ids(con))

        # Projected through postforme.public_account, which is an allowlist of
        # fields. postforme returns the channel's live OAuth access_token and a
        # refresh_token with no expiry, and this payload crosses the Next proxy
        # into a browser — a blocklist would leak whatever credential field
        # postforme adds next.
        accounts = []
        seen = set()
        for account in live:
            data = postforme.public_account(account)
            data["allowed"] = data["id"] in allowed
            data["available"] = True
            # `feeds` is opt-in at connect time — postforme defaults an account
            # to post-only — so an allowlisted account can publish perfectly
            # while producing no metrics at all, silently and forever. Probed
            # only for allowlisted accounts: they are the few that matter, and
            # the limit is 5 requests/second.
            data["analytics"] = (_feeds_available(api_key, data["id"])
                                 if data["allowed"] and probe_feeds else None)
            seen.add(data["id"])
            accounts.append(data)

        # Allowlisted but no longer connected upstream.
        for missing in sorted(allowed - seen):
            accounts.append({"id": missing, "platform": "", "username": "",
                             "profile_photo_url": "", "status": "disconnected",
                             "allowed": True, "available": False})
        return jsonify(accounts)

    @bp.post("/publishing/accounts")
    def set_publishing_accounts():
        """Replace the allowlist. Ids only — display data is hydrated live on
        every load, so storing a username would be a second copy going stale."""
        _settings, _api_key, err = _publishing_context()
        if err:
            return err
        body = request.get_json(force=True) or {}
        account_ids = body.get("account_ids")
        if not isinstance(account_ids, list) or not all(isinstance(a, str) for a in account_ids):
            return jsonify({"error": "account_ids must be a list of strings"}), 400
        with _conn() as con:
            con.execute(
                "INSERT INTO settings (key, value) VALUES ('publishing_accounts', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_json.dumps(account_ids),))
        return jsonify({"account_ids": account_ids})

    @bp.post("/publishing/accounts/connect")
    def connect_publishing_account():
        """Mint a postforme consent URL that connects a new account.

        The permissions are fixed here, never taken from the body: postforme's
        default is `posts` alone, and an account connected that way publishes
        while silently never reporting a metric (see _feeds_available). Minted
        per click because the URL's `state` is single-use, and never logged for
        the same reason. Nothing is stored — the account appears in the list
        above once the consent finishes on postforme.dev.
        """
        _settings, api_key, err = _publishing_context()
        if err:
            return err
        platform = (request.get_json(silent=True) or {}).get("platform")
        if platform not in postforme.SUPPORTED_PLATFORMS:
            return jsonify({
                "error": f"platform must be one of {', '.join(postforme.SUPPORTED_PLATFORMS)}"
            }), 400
        try:
            minted = postforme.create_auth_url(
                api_key, platform=platform, permissions=postforme.CONNECT_PERMISSIONS)
        except postforme.PostformeError as e:
            # Carries postforme's own message, which for a platform not enabled
            # on the postforme project says where to enable it.
            return jsonify({"error": str(e)}), 502
        url = minted.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            return jsonify({"error": "postforme returned no consent URL"}), 502
        return jsonify({"platform": platform, "url": url})

    # Comments are the pipeline's durable record of what happened to a video —
    # the worker already writes one on every AI-review outcome so a result is
    # visible without grepping container logs. A publish is a human-initiated
    # action against real accounts, so it earns the same treatment: without it a
    # failure lives only in a dialog that closes.

    def _publish_comment(video_id: str, text: str) -> None:
        _publish_note(db_path, video_id, text)

    def _feeds_available(api_key: str, account_id: str):
        """Whether this account will actually yield metrics. None = unknown.

        A one-entry probe, not a real fetch. Answers the question the Socials
        page otherwise cannot: publishing and analytics are separate grants, and
        nothing else ever reports the difference.

        Only a *durable* rejection counts as False. A 429 is entirely plausible
        here — the limit is 5 requests/second and this probes each allowlisted
        account — and a 5xx or a timeout says nothing about permissions at all.
        Reporting those as False would tell the user to reconnect an account
        that is perfectly fine.

        **A missing `feeds` grant is not always a rejection, so this probe does
        not always catch one** (TMDEV-104, probed live — don't re-derive, it
        costs API calls). On Instagram the feed request *succeeds*: HTTP 200,
        the complete post list, and an empty `metrics` object on every entry.
        Nothing 4xxs, so this returns True and the Socials page shows no badge,
        for exactly the case the badge exists to catch. Measured across every
        post on two accounts, including a two-week-old one, so it is not a
        freshness effect; a YouTube account holding `feeds` returns real metrics
        from the same call.

        Left as-is deliberately (user decision). Inferring the grant from empty
        metrics would mean calling an account dead on evidence that is also what
        a brand-new account with no posts, or a platform that has not computed
        insights yet, looks like — and the failure mode is telling someone to
        reconnect an account that is fine. postforme exposes no permission list
        on the account record, so there is nothing authoritative to ask. The
        gap is closed at source instead: the Socials page's Connect buttons
        always request `feeds` (connect_publishing_account), and
        docs/developer/14-publishing.md "Connecting accounts" plus the page's help text
        cover an account connected directly on postforme.dev.

        So: a non-transient 4xx is the answer where there is one, everything
        else is None, and None shows nothing rather than a guess.
        """
        try:
            postforme.get_account_feed(api_key, social_account_id=account_id, limit=1)
            return True
        except postforme.PostformeError as e:
            status = getattr(e, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                return False
            return None
        except Exception:
            return None

    @bp.get("/videos/<video_id>/publications")
    def get_video_publications(video_id):
        """Where a video actually went. Replaces videos.youtube_url as the read
        path — one TEXT column cannot hold four platform URLs."""
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM video_publications WHERE video_id = ? ORDER BY platform, id",
                (video_id,)).fetchall()
        return jsonify([_publication_row(r) for r in rows])

    @bp.post("/videos/<video_id>/publish-prefill")
    def publish_prefill(video_id):
        """Starting title and description for the publish dialog.

        A read: the agent writes publish_title/publish_description with the
        script (TMDEV-132), so opening the dialog calls no model and waits on
        nobody. It used to ask Gemini here, which put a paid, slow, fallible
        call in front of the one irreversible human action.

        Always answers 200. A video with nothing written (scripted before the
        agent wrote these) falls back to its title and topic, because a dialog
        that will not open is a far worse outcome than a plain prefill. The
        fallback is never stored, so it cannot pass for what an agent wrote.
        """
        with _conn() as con:
            video = con.execute(
                "SELECT topic, title, publish_title, publish_description"
                " FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Returned alongside the prefill because the dialog already makes this
        # call — a separate endpoint for one number would be a second round
        # trip for the same dialog open.
        duration = _video_duration_secs(video_id)
        shorts = {
            "duration_secs": duration,
            "youtube_short": None if duration is None else duration <= YOUTUBE_SHORTS_MAX_SECS,
            "youtube_shorts_max_secs": YOUTUBE_SHORTS_MAX_SECS,
        }

        title, description = publish_text(video)
        return jsonify({"title": title, "description": description, **shorts})

    @bp.post("/videos/<video_id>/publish")
    def publish_video(video_id):
        """Upload the mp4 and create one postforme post across every target —
        now, or at a scheduled time when the body carries `schedule`.

        Runs inline rather than on the worker: the worker renders one video at
        a time for ~20 minutes, and a human-clicked publish queued behind a
        render would look broken. Measured live, the upload alone is ~50s for a
        153MB render, so this request is slow by design.

        The video is claimed (PUBLISHING, with one in-progress row per target)
        before anything reaches postforme. A failure before create_post undoes
        both, so the human can simply press the button again; a failure of
        create_post itself is ambiguous and is left for the worker to reconcile.

        A scheduled publish runs exactly the same way — the upload happens now,
        under the same PUBLISHING claim — and only its last step differs: once
        postforme holds the post, the video moves to SCHEDULED to wait. The
        worker moves it back to PUBLISHING when it falls due (TMDEV-133).
        """
        _settings, api_key, err = _publishing_context()
        if err:
            return err

        body = request.get_json(force=True) or {}
        account_ids = body.get("account_ids")
        if not isinstance(account_ids, list) or not account_ids:
            return jsonify({"error": "account_ids must be a non-empty list"}), 400
        title = (body.get("title") or "").strip()
        description = (body.get("description") or "").strip()
        privacy = body.get("privacy") or {}
        if not isinstance(privacy, dict):
            return jsonify({"error": "privacy must be an object keyed by platform"}), 400

        payload, code = start_publish(
            db_path, api_key, video_id, account_ids, title, description, privacy,
            schedule=body.get("schedule"))
        return jsonify(payload), code

    @bp.post("/videos/<video_id>/publish/retry")
    def retry_publish(video_id):
        """Recover a video that failed while publishing, without posting twice.

        postforme is asked first, by external_id: a FAILED video can be live —
        that is how TMDEV-97 was found. If a live post exists it is adopted and
        the video goes back to PUBLISHING for the worker to settle; nothing is
        re-posted. Only when no live post exists does the video return to
        VIDEO_APPROVED, for the human to publish again through the normal
        dialog — the original account and privacy choices are not stored.

        "Failed while publishing" is "FAILED with publication rows". Flask
        writes the rows at the claim, so every publish failure has them, and a
        render failure never does.

        The lookup runs before the claim because it is only a read: two
        overlapping retries may both look, but the claim lets one act.
        """
        _settings, api_key, err = _publishing_context()
        if err:
            return err

        with _conn() as con:
            video = con.execute(
                "SELECT status, archived_at FROM videos WHERE id = ?", (video_id,)).fetchone()
            pubs = con.execute(
                "SELECT social_account_id, platform, error FROM video_publications"
                " WHERE video_id = ? ORDER BY platform, id", (video_id,)).fetchall()
        if not video:
            return jsonify({"error": "Video not found"}), 404
        if video["archived_at"]:
            return jsonify({"error": "Video is archived — its rendered file has been deleted."}), 409
        if video["status"] != "FAILED" or not pubs:
            return jsonify({
                "error": "Only a video that failed while publishing can be retried."
            }), 409

        try:
            post = postforme.find_post_by_external_id(api_key, external_id=video_id)
        except postforme.PostformeError as e:
            return jsonify({"error": f"Could not check postforme for an existing post: {e}"}), 502

        live = post if post and post.get("live") else None
        now = _now()
        with _conn() as con:
            if live:
                claimed = con.execute(
                    "UPDATE videos SET status = 'PUBLISHING', updated_at = ?"
                    " WHERE id = ? AND status = 'FAILED' AND archived_at IS NULL",
                    (now, video_id)).rowcount
                if claimed:
                    # Rebuilt from the post, which is the truth about where it
                    # went; the local rows are only what we hoped for. A fresh
                    # created_at restarts the worker's publish deadline.
                    targets = (postforme.publication_targets(live)
                               or [(p["social_account_id"], p["platform"]) for p in pubs])
                    con.execute("DELETE FROM video_publications WHERE video_id = ?", (video_id,))
                    for account_id, platform in targets:
                        con.execute(
                            "INSERT INTO video_publications (id, video_id, platform,"
                            " social_account_id, postforme_post_id, status, created_at,"
                            " updated_at) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)",
                            (str(uuid.uuid4()), video_id, platform, account_id,
                             live["id"], now, now))
            else:
                claimed = con.execute(
                    "UPDATE videos SET status = 'VIDEO_APPROVED', scheduled_at = '',"
                    " scheduled_timezone = '', updated_at = ?"
                    " WHERE id = ? AND status = 'FAILED' AND archived_at IS NULL",
                    (now, video_id)).rowcount
                if claimed:
                    con.execute("DELETE FROM video_publications WHERE video_id = ?", (video_id,))
        if not claimed:
            return jsonify({"error": "Video is no longer FAILED."}), 409

        if live:
            _publish_comment(
                video_id,
                f"Retry publishing: postforme already has a live post for this video "
                f"({live['id']}), so it was not posted again. Publishing results will "
                f"update as each platform reports.")
            return jsonify({"outcome": "reconciling", "status": "PUBLISHING"}), 200

        # The rows are gone now, so their errors survive only in this comment.
        errors = "; ".join(
            f"{p['platform'] or 'unknown'} ({p['social_account_id']}): {p['error'] or 'no error recorded'}"
            for p in pubs)
        _publish_comment(
            video_id,
            f"Retry publishing: postforme has no live post for this video, so it is back at "
            f"VIDEO_APPROVED to publish again. The previous attempt: {errors}")
        return jsonify({"outcome": "republish", "status": "VIDEO_APPROVED"}), 200

    @bp.post("/videos/<video_id>/schedule/cancel")
    def cancel_schedule(video_id):
        """Cancel a scheduled post and return the video to VIDEO_APPROVED.

        postforme is asked first and the local state follows it: a post it
        still holds must never be left without the rows that settle it. There
        is no reschedule — postforme's update is a full-replace PUT that posts
        immediately when scheduled_at is missing — so a new time means cancel,
        then schedule again.

        The release matches PUBLISHING as well as SCHEDULED. The worker moves a
        video to PUBLISHING when it falls due, which can happen while this
        request is talking to postforme; if postforme still deleted the post,
        nothing will go out, whichever status the worker left.
        """
        _settings, api_key, err = _publishing_context()
        if err:
            return err

        with _conn() as con:
            video = con.execute(
                "SELECT status FROM videos WHERE id = ?", (video_id,)).fetchone()
            pub = con.execute(
                "SELECT postforme_post_id FROM video_publications"
                " WHERE video_id = ? AND postforme_post_id != '' LIMIT 1",
                (video_id,)).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404
        if video["status"] != "SCHEDULED" or not pub:
            return jsonify({
                "error": f"Video is {video['status']}, not SCHEDULED — only a scheduled "
                         "post can be cancelled."
            }), 409
        post_id = pub["postforme_post_id"]

        try:
            postforme.delete_post(api_key, post_id=post_id)
        except postforme.PostformeError as e:
            if e.status_code == 400:
                return jsonify({
                    "error": "postforme has already started sending this post, so it can no "
                             "longer be cancelled. It will settle as published or failed."
                }), 409
            if e.status_code != 404:
                return jsonify({"error": f"Cancelling failed: {e} The post is still "
                                         "scheduled; try again."}), 502
            # 404 is what a repeated cancel gets after a first one that deleted
            # the post but answered badly — and also what postforme answers
            # when its own lookup fails. Only the first may release the video.
            try:
                found = postforme.find_post_by_external_id(api_key, external_id=video_id)
            except postforme.PostformeError as e2:
                return jsonify({"error": f"Cancelling failed: {e2} The post may still be "
                                         "scheduled; try again."}), 502
            if found and found.get("id") == post_id:
                return jsonify({"error": "postforme could not find the post to cancel, but "
                                         "still lists it. Try again."}), 502

        with _conn() as con:
            released = con.execute(
                # auto_pilot_hold: without it Auto Pilot would schedule the
                # video again on the worker's next tick, and no cancel in an
                # Auto Pilot project could ever stick (TMDEV-139).
                "UPDATE videos SET status = 'VIDEO_APPROVED', scheduled_at = '',"
                " scheduled_timezone = '', auto_pilot_hold = 1, updated_at = ?"
                " WHERE id = ? AND status IN ('SCHEDULED', 'PUBLISHING')",
                (_now(), video_id)).rowcount
            if released:
                con.execute("DELETE FROM video_publications WHERE video_id = ?", (video_id,))
        if not released:
            return jsonify({"error": "The post was cancelled, but the video changed status "
                                     "meanwhile; reload it."}), 409
        _publish_comment(video_id, "Scheduled post cancelled; nothing was posted. The video "
                                   "is back at VIDEO_APPROVED and can be published or "
                                   "scheduled again.")
        return jsonify({"status": "VIDEO_APPROVED"}), 200

    # Latest snapshot per publication. Each video_metrics row is a cumulative
    # reading, so the series is read with a max-fetched_at pick rather than a
    # SUM — adding two snapshots of the same post would double-count it.
    _LATEST_METRIC_JOIN = """
        FROM video_publications vp
        JOIN videos v ON v.id = vp.video_id
        LEFT JOIN video_metrics m ON m.id = (
            SELECT id FROM video_metrics WHERE publication_id = vp.id
            ORDER BY fetched_at DESC, id DESC LIMIT 1)
        WHERE vp.status = 'PUBLISHED'
    """

    @bp.get("/analytics")
    def get_analytics():
        """Cross-platform overview, served entirely from the local snapshots.

        Never reaches postforme: the worker polls and caches, because rendering
        this page over N accounts x M videos against a live API would hit a
        rate limit immediately.

        Aggregating `views` across platforms is defensible and is all that is
        summed here. Platform-specific metrics are deliberately not summed —
        they live in video_metrics.raw_json and mean different things.
        """
        platform = request.args.get("platform", "").strip()
        account_id = request.args.get("social_account_id", "").strip()

        sql = "SELECT vp.*, v.title, v.topic, m.views, m.likes, m.comments, m.shares," \
              " m.fetched_at" + _LATEST_METRIC_JOIN
        params = []
        if platform:
            sql += " AND vp.platform = ?"
            params.append(platform)
        if account_id:
            sql += " AND vp.social_account_id = ?"
            params.append(account_id)
        sql += " ORDER BY vp.published_at DESC, vp.id"

        with _conn() as con:
            rows = con.execute(sql, params).fetchall()

        publications, totals, by_platform = [], {}, {}
        for row in rows:
            entry = _publication_row(row)
            entry["title"] = row["title"] or row["topic"]
            for column in ("views", "likes", "comments", "shares"):
                entry[column] = row[column]
                # None means "not reported" and stays None on the row, but
                # contributes nothing to a total rather than breaking it.
                totals[column] = totals.get(column, 0) + (row[column] or 0)
                bucket = by_platform.setdefault(row["platform"], {})
                bucket[column] = bucket.get(column, 0) + (row[column] or 0)
            entry["fetched_at"] = row["fetched_at"]
            publications.append(entry)

        for column in ("views", "likes", "comments", "shares"):
            totals.setdefault(column, 0)
        totals["publications"] = len(publications)
        totals["videos"] = len({p["video_id"] for p in publications})
        by_month, zone_name = _views_gained_by_month(platform, account_id)
        return jsonify({"totals": totals, "by_platform": by_platform,
                        "publications": publications, "by_month": by_month,
                        "timezone": zone_name})

    ANALYTICS_MONTHS = 12

    def _views_gained_by_month(platform: str, account_id: str):
        """([{month, views}], zone name): views gained in each of the last
        ANALYTICS_MONTHS host-zone months, oldest first (TMDEV-113).

        Snapshots are cumulative, so a month's gain is the sum of every post's
        latest reading before the month ended minus the same before it began —
        about one indexed lookup per post per boundary, never a walk of the
        hourly history. Nothing is known before a post's first reading, so the
        views it already had count in that reading's month. Months before any
        reading are left out rather than shown as 0, and a month where views
        fell (a platform recount) keeps its negative figure.
        """
        zone_name, zone = _host_zone()
        today = dt.datetime.now(zone).date()
        this_month = today.replace(day=1)
        firsts = [this_month]
        for _ in range(ANALYTICS_MONTHS - 1):
            firsts.insert(0, (firsts[0] - dt.timedelta(days=1)).replace(day=1))
        # ...and the start of next month, which closes this one.
        firsts.append((this_month + dt.timedelta(days=32)).replace(day=1))
        boundaries = [_day_range(d, d, zone)[0] for d in firsts]

        where, params = "vp.status = 'PUBLISHED'", []
        if platform:
            where += " AND vp.platform = ?"
            params.append(platform)
        if account_id:
            where += " AND vp.social_account_id = ?"
            params.append(account_id)
        sql = ("SELECT COALESCE(SUM(x), 0) AS total, COUNT(x) AS known FROM ("
               " SELECT (SELECT views FROM video_metrics WHERE publication_id = vp.id"
               "  AND views IS NOT NULL AND fetched_at < ?"
               "  ORDER BY fetched_at DESC, id DESC LIMIT 1) AS x"
               f" FROM video_publications vp WHERE {where})")
        with _conn() as con:
            cumulative = [con.execute(sql, [b, *params]).fetchone() for b in boundaries]

        months = []
        for i, first in enumerate(firsts[:-1]):
            # `known` only grows with the boundary, so skipping zeros drops
            # exactly the leading months.
            if cumulative[i + 1]["known"] == 0:
                continue
            months.append({"month": first.strftime("%Y-%m"),
                           "views": cumulative[i + 1]["total"] - cumulative[i]["total"]})
        return months, zone_name

    # ── Costs (TMDEV-107) ────────────────────────────────────────────────────
    # Read side of the usage ledger, and the price table behind it. Every
    # dollar figure is an API list price; ElevenLabs is plan credits.

    @bp.get("/videos/<video_id>/costs")
    def video_costs(video_id: str):
        with _conn() as con:
            return jsonify(tusage.video_costs(con, video_id))

    def _host_zone():
        """(name, tzinfo) for the host's zone, or UTC when it cannot be named
        or loaded. Falling back beats a 500: the page still works, and the
        response says which zone the days were cut in."""
        name = hosttz.host_timezone()["timezone"]
        if name:
            try:
                return name, zoneinfo.ZoneInfo(name)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                pass
        return "UTC", dt.timezone.utc

    def _day_range(start: dt.date, end: dt.date, zone):
        """Inclusive local days -> the UTC [since, until) that covers them, or
        None when either end falls outside what a datetime can hold (the day
        after 9999-12-31, or year-1 midnight east of UTC).

        Each boundary is a local midnight converted on its own, so a range
        across a DST switch is not off by an hour at one end. isoformat pads
        the year to four digits, which strftime does not for years below 1000."""
        def utc_midnight(day):
            local = dt.datetime.combine(day, dt.time(), tzinfo=zone)
            utc = local.astimezone(dt.timezone.utc).replace(tzinfo=None)
            return utc.isoformat(timespec="seconds") + "Z"

        try:
            return utc_midnight(start), utc_midnight(end + dt.timedelta(days=1))
        except OverflowError:
            return None

    @bp.get("/usage/summary")
    def usage_summary():
        """Spend for the Analytics page's Spend tab, plus the ElevenLabs credit
        pool when the key can read it. `user_read` is an optional permission,
        so a key without it simply omits the pool rather than failing the tab.

        One of:
        - `preset` (today, week, month) — resolved here, in the host zone.
          The dashboard learns that zone asynchronously and falls back to UTC,
          so a "today" it worked out itself could name the wrong day.
        - `from`/`to` — inclusive YYYY-MM-DD days in the host zone.
        - `since` — open-ended (default: the start of this UTC month), for
          other callers.
        """
        preset = request.args.get("preset")
        first, last = request.args.get("from"), request.args.get("to")
        since, until, days = request.args.get("since"), None, None
        ways = (preset is not None) + (first is not None or last is not None) + (since is not None)
        if ways > 1:
            return jsonify({"error": "send one of preset, from/to or since"}), 400
        if preset is not None or first is not None or last is not None:
            zone_name, zone = _host_zone()
            if preset is not None:
                if preset not in SPEND_PRESETS:
                    return jsonify({"error": f"preset must be one of {', '.join(SPEND_PRESETS)}"}), 400
                end = dt.datetime.now(zone).date()
                start = _preset_first_day(preset, end)
            else:
                date_re = r"\d{4}-\d{2}-\d{2}"
                if not (first and last and re.fullmatch(date_re, first)
                        and re.fullmatch(date_re, last)):
                    return jsonify({"error": "from and to must both be dates like 2026-09-01"}), 400
                try:
                    start, end = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
                except ValueError:
                    start = end = None
                if start is None or start > end:
                    return jsonify({"error": "from and to must be real dates, from on or before to"}), 400
            span = _day_range(start, end, zone)
            if span is None:
                return jsonify({"error": "that range is outside the dates that can be represented"}), 400
            since, until = span
            days = {"from": start.isoformat(), "to": end.isoformat(), "timezone": zone_name}
        since = since or time.strftime("%Y-%m-01T00:00:00Z", time.gmtime())
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", since):
            return jsonify({"error": "since must be an ISO timestamp like 2026-09-01T00:00:00Z"}), 400
        with _conn() as con:
            summary = tusage.spend_summary(con, since, until)
            settings = _read_all_settings(con)
        if days:
            summary.update(days)
        summary["elevenlabs_pool"] = _elevenlabs_pool(
            _secret(settings, "elevenlabs_api_key", "ELEVENLABS_API_KEY"))
        return jsonify(summary)

    @bp.get("/prices")
    def list_prices():
        """Every model in use with the rates that would price it now and where
        they come from, the models with unpriced calls, and the sync state."""
        with _conn() as con:
            pairs = tprices.models_in_use(con) | {
                (r["service"], r["model"]) for r in con.execute(
                    "SELECT DISTINCT service, model FROM model_prices")}
            models = []
            for service, model in sorted(pairs):
                price = tprices.lookup_rates(con, service, model)
                row = con.execute(
                    "SELECT MAX(effective_from) AS since FROM model_prices "
                    "WHERE service = ? AND model = ?", (service, model)).fetchone()
                models.append({"service": service, "model": model,
                               "source": price["source"] if price else None,
                               "rates": price["rates"] if price else {},
                               "tiered": bool(price and price["tiered"]),
                               "effective_from": row["since"] if row else None})
            unpriced = [dict(r) for r in con.execute(
                "SELECT service, model, COUNT(*) AS calls FROM usage_events "
                "WHERE cost_basis = 'unpriced' GROUP BY service, model ORDER BY calls DESC")]
            state = {r["key"]: r["value"] for r in con.execute(
                "SELECT key, value FROM settings WHERE key IN ('last_price_sync_at', "
                "'last_price_sync_ok_at', 'last_price_sync_error')")}
        return jsonify({"models": models, "unpriced": unpriced,
                        "unit_kinds": list(tprices.UNIT_KINDS),
                        "last_sync_attempt_at": state.get("last_price_sync_at") or None,
                        "last_sync_ok_at": state.get("last_price_sync_ok_at") or None,
                        "last_sync_error": state.get("last_price_sync_error") or None})

    @bp.post("/prices/sync")
    def sync_prices_now():
        with _conn() as con:
            return jsonify(tprices.sync_prices(con))

    @bp.post("/prices/override")
    def set_price_override():
        """Body {service, model, rates: {unit_kind: usd_per_token}}. A manual
        rate is never touched by a sync, and adding one prices that model's
        unpriced calls; calls already priced keep the price they were charged."""
        body = request.get_json(silent=True) or {}
        service, model = body.get("service"), body.get("model")
        if not isinstance(service, str) or not service or not isinstance(model, str) or not model:
            return jsonify({"error": "service and model are required"}), 400
        if service == "elevenlabs":
            return jsonify({"error": "ElevenLabs is recorded in plan credits and never priced"}), 400
        try:
            with _conn() as con:
                repriced = tprices.set_manual_rates(con, service, model, body.get("rates"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "repriced": repriced})

    @bp.delete("/prices/override")
    def clear_price_override():
        service, model = request.args.get("service"), request.args.get("model")
        if not service or not model:
            return jsonify({"error": "service and model are required"}), 400
        with _conn() as con:
            tprices.clear_manual_rates(con, service, model)
        return jsonify({"ok": True})

    @bp.post("/analytics/refresh")
    def refresh_analytics():
        """Capture a snapshot now instead of waiting for the worker's hourly pass.

        Bounded by the per-account walk: one feed per account regardless of how
        many videos have been published. Returns counts rather than the payload
        — the page re-fetches /analytics itself, so this stays one job.
        """
        _settings, api_key, err = _publishing_context()
        if err:
            return err
        return jsonify(metrics_poll.poll(db_path, api_key))

    # ── /script-profiles ──────────────────────────────────────────────────────
    # A script profile is corpus-derived *style* stored as markdown (TMDEV-81),
    # picked per video. Creation fetches transcripts here and parks the row at
    # PENDING; the next cron tick has the agent turn them into markdown over
    # MCP. The transcripts are dropped at that point — profiles are immutable
    # once READY, so nothing needs them again.

    def _profile_row(row, *, full: bool = False) -> dict:
        data = {
            "id":            row["id"],
            "name":          row["name"],
            "status":        row["status"],
            "source_urls":   _json.loads(row["source_urls"] or "[]"),
            "error":         row["error"],
            "attempt_count": row["attempt_count"],
            # Always 0 in the list payload (it filters archived out), but the
            # by-id route deliberately serves archived rows so a video that
            # picked one still resolves — and the dashboard needs to say the
            # profile was deleted rather than show a name nobody can pick.
            "archived":      bool(row["archived"]),
            "created_at":    row["created_at"],
            "updated_at":    row["updated_at"],
        }
        if full:
            data["markdown"] = row["markdown"]
            data["corpus_summary"] = row["corpus_summary"]
        return data

    @bp.get("/script-profiles")
    def list_script_profiles():
        # markdown is deliberately not in the list payload — it is a whole
        # skill's worth of prose per row, and the picker only needs identity.
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM script_profiles WHERE archived = 0 ORDER BY created_at DESC"
            ).fetchall()
        return jsonify([_profile_row(r) for r in rows])

    @bp.get("/script-profiles/pending")
    def pending_script_profiles():
        # GENERATING is included on purpose: a crashed agent session leaves the
        # row there, and it must be retried rather than stranded. The attempt
        # cap (record-attempt below) is what stops that repeating forever.
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM script_profiles "
                "WHERE archived = 0 AND status IN ('PENDING','GENERATING') "
                "ORDER BY created_at ASC"
            ).fetchall()
        return jsonify([_profile_row(r) for r in rows])

    @bp.get("/script-profiles/<profile_id>")
    def get_script_profile(profile_id: str):
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM script_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        if not row:
            return jsonify({"error": "Script profile not found"}), 404
        return jsonify(_profile_row(row, full=True))

    @bp.post("/script-profiles")
    def create_script_profile():
        body = request.get_json(force=True) or {}
        name = (body.get("name") or "").strip()
        urls = body.get("urls", [])
        if not name:
            return jsonify({"error": "name is required"}), 400
        if not isinstance(urls, list) or not urls:
            return jsonify({"error": "urls must be a non-empty list"}), 400
        if len(urls) > MAX_PROFILE_URLS:
            return jsonify({
                "error": f"at most {MAX_PROFILE_URLS} URLs per profile, got {len(urls)}"
            }), 400

        # Checked before any fetch, and reported as its own message: an unset
        # key is a setup gap the user can fix on the Settings page, not a
        # transcript that happened to be unavailable.
        with _conn() as con:
            api_key = _secret(_read_all_settings(con),
                              "youtube_transcript_api_key", "YOUTUBE_TRANSCRIPT_API_KEY")
        if not api_key:
            return jsonify({
                "error": "youtube-transcript.io API key not configured — script profiles are "
                         "built from transcripts. Add it on the Settings page."
            }), 503

        fetched, failures = [], []
        for url in urls:
            youtube_id = transcripts.extract_video_id(url)
            if not youtube_id:
                failures.append({"url": url, "error": "could not extract a YouTube video ID"})
                continue
            try:
                text = transcripts.fetch_transcript(youtube_id, api_key)
            except Exception as exc:
                failures.append({"url": url, "error": str(exc)})
                continue
            if not text:
                failures.append({"url": url, "error": "no transcript available"})
                continue
            fetched.append({"url": url, "youtube_id": youtube_id, "text": text})

        if not fetched:
            return jsonify({
                "error": "No transcripts could be fetched — no profile was created.",
                "failures": failures,
            }), 400

        pid = str(uuid.uuid4())
        now = _now()
        with _conn() as con:
            con.execute(
                """INSERT INTO script_profiles
                   (id, name, status, source_urls, created_at, updated_at)
                   VALUES (?, ?, 'PENDING', ?, ?, ?)""",
                (pid, name, _json.dumps([f["url"] for f in fetched]), now, now),
            )
            con.executemany(
                """INSERT INTO script_profile_transcripts
                   (profile_id, source_url, youtube_id, text, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                [(pid, f["url"], f["youtube_id"], f["text"], now) for f in fetched],
            )
            row = con.execute(
                "SELECT * FROM script_profiles WHERE id = ?", (pid,)
            ).fetchone()
        payload = _profile_row(row, full=True)
        payload["transcripts_fetched"] = len(fetched)
        payload["failures"] = failures
        return jsonify(payload), 201

    @bp.delete("/script-profiles/<profile_id>")
    def delete_script_profile(profile_id: str):
        # Archive, never DELETE: a video that already picked this profile keeps
        # a resolvable script_profile_id, it just stops being offered.
        #
        # The transcripts do go, though. complete_script_profile is the only
        # other place that drops them, so archiving a profile that never got
        # there (PENDING, GENERATING, or FAILED) would strand its transcripts in
        # the table forever — both list endpoints exclude archived rows, so
        # nothing would ever surface the id again, and the ON DELETE CASCADE
        # cannot fire because the profile row itself is never deleted.
        # Unconditional rather than gated on status: a READY profile's
        # transcripts are already gone, so this is a no-op there.
        with _conn() as con:
            cur = con.execute(
                "UPDATE script_profiles SET archived = 1, updated_at = ? WHERE id = ?",
                (_now(), profile_id),
            )
            if cur.rowcount == 0:
                return jsonify({"error": "Script profile not found"}), 404
            con.execute(
                "DELETE FROM script_profile_transcripts WHERE profile_id = ?", (profile_id,)
            )
        return jsonify({"ok": True, "archived": True})

    @bp.post("/script-profiles/<profile_id>/record-attempt")
    def record_script_profile_attempt(profile_id: str):
        """Called by poll.py right before it invokes a profile-building agent.

        Attempts are recorded before the invoke, not after, for the same reason
        research runs are (TMDEV-44): an agent that crashes leaves no completion
        to count, so a completion-counted cap fails open exactly when it matters
        and re-fires every tick forever.

        The cap gates *before* incrementing, so MAX_PROFILE_ATTEMPTS is the
        number of agent sessions that ever run — incrementing first and then
        comparing would allow one more than it says.
        """
        now = _now()
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM script_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "Script profile not found"}), 404
            if row["status"] in ("READY", "FAILED"):
                return jsonify({
                    "id": profile_id, "status": row["status"],
                    "attempt_count": row["attempt_count"],
                }), 409
            if row["attempt_count"] >= MAX_PROFILE_ATTEMPTS:
                error = (f"Profile generation did not complete after "
                         f"{MAX_PROFILE_ATTEMPTS} agent session(s). Delete this profile and "
                         f"create a new one.")
                con.execute(
                    "UPDATE script_profiles SET status = 'FAILED', error = ?, updated_at = ? "
                    "WHERE id = ?",
                    (error, now, profile_id),
                )
                return jsonify({
                    "id": profile_id, "status": "FAILED",
                    "attempt_count": row["attempt_count"], "error": error,
                })
            con.execute(
                "UPDATE script_profiles SET status = 'GENERATING', "
                "attempt_count = attempt_count + 1, updated_at = ? WHERE id = ?",
                (now, profile_id),
            )
        return jsonify({
            "id": profile_id, "status": "GENERATING",
            "attempt_count": row["attempt_count"] + 1,
        })

    # ── /agents ───────────────────────────────────────────────────────────────
    # Installed coding agents (TMDEV-90). Read-mostly: rows are created,
    # uninstalled (archived_at set, never deleted, so every video pinned to an
    # agent keeps resolving it), and their binary/models/workspace changed only
    # by the host-side installer, which validates them against the real CLI.
    # Over HTTP a human may only pick the default agent, set each agent's
    # random-pick weight, pick which of its installed models is its default,
    # and pick its default effort level.

    AGENT_PATCHABLE = {"is_default", "weight", "default_model", "effort"}

    @bp.get("/agents")
    def list_agents():
        # Archived rows included: the dashboard needs them to label a video
        # still pinned to one.
        with _conn() as con:
            rows = con.execute("SELECT * FROM agents ORDER BY created_at, id").fetchall()
        return jsonify([_agent_dict(r) for r in rows])

    @bp.patch("/agents/<agent_id>")
    def patch_agent(agent_id: str):
        # silent=True: a malformed body is the caller's 400, not an exception
        # for the blueprint's error handler to re-raise as a 500.
        body = request.get_json(force=True, silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Body must be a JSON object"}), 400
        disallowed = sorted(k for k in body if k not in AGENT_PATCHABLE)
        if disallowed:
            return jsonify({
                "error": f"{', '.join(disallowed)} cannot be changed here. An agent's name, "
                         f"binary, workspace and models are installed and changed only by "
                         f"`python onboard.py --install-agent <name>` on the host, which "
                         f"validates them. Only is_default, weight, default_model and effort "
                         f"are editable."
            }), 400
        if not body:
            return jsonify({
                "error": "No updatable fields provided (is_default, weight, default_model, "
                         "effort)"
            }), 400
        if "is_default" in body and body["is_default"] is not True:
            if body["is_default"] is False:
                return jsonify({
                    "error": "is_default cannot be cleared — make another agent the default "
                             "instead"
                }), 400
            return jsonify({"error": "is_default must be true"}), 400
        if "weight" in body:
            w = body["weight"]
            # bool first: isinstance(True, int) is True in Python.
            if isinstance(w, bool) or not isinstance(w, int) or not 0 <= w <= 100:
                return jsonify({"error": f"weight must be an integer from 0 to 100, got {w!r}"}), 400
        if "default_model" in body and not isinstance(body["default_model"], str):
            return jsonify({"error": "default_model must be a string"}), 400
        # Unlike default_model, this needs no row read: the levels are the same
        # five for every agent, so membership is the whole check. Blank is
        # refused here (it is meaningful on a *video*, where it means "follow
        # the agent"; on the agent itself there is nothing to follow).
        if "effort" in body:
            e = body["effort"]
            if not isinstance(e, str) or e not in AGENT_EFFORTS:
                return jsonify({
                    "error": f"effort must be one of {list(AGENT_EFFORTS)}, got {e!r}"
                }), 400

        now = _now()
        fields = {k: (1 if k == "is_default" else v) for k, v in body.items()
                  if k != "default_model"}
        fields["updated_at"] = now
        with _conn() as con:
            # The default model is models[0] everywhere (poll.py, MCP, the
            # dashboard), so picking one reorders the list rather than adding a
            # column. Membership only: the set itself stays installer-owned.
            if "default_model" in body:
                row = con.execute("SELECT models, archived_at FROM agents WHERE id = ?",
                                  (agent_id,)).fetchone()
                if row and not row["archived_at"]:
                    models = _agent_models(row["models"])
                    choice = body["default_model"]
                    if choice not in models:
                        return jsonify({
                            "error": f"default_model {choice!r} is not one of agent "
                                     f"{agent_id!r}'s installed models: {models}. Add it with "
                                     f"`python onboard.py --install-agent {agent_id}`."
                        }), 400
                    fields["models"] = _json.dumps([choice] + [m for m in models if m != choice])
            assignments = ", ".join(f"{k} = ?" for k in fields)
            # The target first, guarded in its own WHERE, so an archived or
            # missing agent fails before any other row is touched.
            cur = con.execute(
                f"UPDATE agents SET {assignments} WHERE id = ? AND archived_at IS NULL",
                list(fields.values()) + [agent_id],
            )
            if cur.rowcount == 0:
                row = con.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone()
                if not row:
                    return jsonify({"error": "Agent not found"}), 404
                return jsonify({
                    "error": "Agent is uninstalled and can no longer be changed — re-install it "
                             f"with `python onboard.py --install-agent {agent_id}`"
                }), 409
            # Exactly one default: same transaction as the write above.
            if "is_default" in body:
                con.execute(
                    "UPDATE agents SET is_default = 0, updated_at = ? "
                    "WHERE id != ? AND is_default != 0",
                    (now, agent_id),
                )
            row = con.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return jsonify(_agent_dict(row))

    # ── /pipeline/status ──────────────────────────────────────────────────────
    # Used by poll.py to decide whether to invoke the agent — no DB imports needed.
    # Response shape keep in sync with mcp/server.py get_pipeline_status().
    # The two already diverge deliberately — MCP adds pronunciation state and the
    # scene claims, this one adds the host timezone — and `pending_script_profiles`
    # (TMDEV-81) is another such case, not drift: poll.py is its only consumer, and
    # the agent has list_script_profiles() for the same information in a usable
    # shape. Don't mirror it into the MCP tool just because this comment is here.
    # `version` (TMDEV-100) is the same: the dashboard top bar is its only consumer
    # and the agent has no use for it. It rides here rather than on /stats because
    # /stats is a bare status->count map that callers iterate, so a non-count key
    # there would break its shape; this payload is already named keys, and the
    # dashboard already fetches it once on mount for the timezone.
    # `github_repo` (TMDEV-114) rides along for the dashboard's update check:
    # its image cannot import tubematic_core, and the repo is spelled only there.

    @bp.get("/pipeline/status")
    def pipeline_status():
        with _conn() as con:
            # Archived rows excluded: proposed_count is the research pending
            # cap's input. Keep in sync with mcp/server.py's get_pipeline_status.
            count_rows = con.execute(
                "SELECT status, COUNT(*) as cnt FROM videos"
                " WHERE archived_at IS NULL GROUP BY status"
            ).fetchall()
            video_counts = {r["status"]: r["cnt"] for r in count_rows}

            paused_row = con.execute(
                "SELECT value FROM settings WHERE key = 'pipeline_paused'"
            ).fetchone()
            paused = paused_row["value"].lower() == "true" if paused_row else False

            cap_row = con.execute(
                "SELECT value FROM settings WHERE key = 'research_pending_cap'"
            ).fetchone()
            try:
                research_pending_cap = int(cap_row["value"]) if cap_row else 15
            except (ValueError, TypeError):
                research_pending_cap = 15

            research_row = con.execute(
                "SELECT value FROM settings WHERE key = 'last_research_at'"
            ).fetchone()
            last_research_at = research_row["value"] if research_row else None

            strategies = _active_strategies(con)
            mining_available = _mining_available(con)

            max_runs_row = con.execute(
                "SELECT value FROM settings WHERE key = 'max_research_runs_per_day'"
            ).fetchone()
            try:
                max_research_runs_per_day = int(max_runs_row["value"]) if max_runs_row else 8
            except (ValueError, TypeError):
                max_research_runs_per_day = 8

            research_runs, research_window_resets_at = _research_run_window(con)

            profile_row = con.execute(
                "SELECT COUNT(*) AS cnt FROM script_profiles "
                "WHERE archived = 0 AND status IN ('PENDING','GENERATING')"
            ).fetchone()
            pending_script_profiles = profile_row["cnt"] if profile_row else 0

        proposed_count = video_counts.get("TOPIC_PROPOSED", 0)
        workable_count = sum(video_counts.get(s, 0) for s in WORKABLE_STATUSES)

        tz = hosttz.host_timezone()
        return jsonify({
            "paused": paused,
            "workable_count": workable_count,
            "proposed_count": proposed_count,
            "video_counts": video_counts,
            "last_research_at": last_research_at,
            "active_strategies": strategies,
            "mining_available": mining_available,
            "research_pending_cap": research_pending_cap,
            "research_runs_today": len(research_runs),
            "max_research_runs_per_day": max_research_runs_per_day,
            "research_window_resets_at": research_window_resets_at,
            "pending_script_profiles": pending_script_profiles,
            "timezone": tz["timezone"],
            "timezone_label": tz["timezone_label"],
            "version": tversion.version(),
            "github_repo": tversion.GITHUB_REPO,
        })

    # ── /logs ────────────────────────────────────────────────────────────────

    @bp.get("/logs")
    def get_logs():
        """Structured log records, newest first.

        The dashboard's only route to the logs, and deliberately the only one
        there is: it holds no log mount and no Docker socket, so this endpoint
        is the whole of its access.

        `service` is optional. Omitted, it reads all of them — which is what a
        video-scoped query needs, since one video's trail spans the renderer
        that rendered it, the MCP tools that voiced and staged it, and the API
        calls that moved it between statuses. Supplied, it is checked against
        the allowlist before anything touches the filesystem; a filename is
        always built from a known service name, never from request input.
        """
        service = request.args.get("service", "").strip()
        if service and service not in tlog.SERVICES:
            return jsonify({"error": f"Unknown service: {service!r}"}), 400

        level = request.args.get("level", "").strip().lower()
        if level and level not in tlog.LEVELS:
            return jsonify({"error": f"Unknown level: {level!r}"}), 400

        raw_limit = request.args.get("limit", "").strip()
        if raw_limit:
            try:
                limit = int(raw_limit)
            except ValueError:
                return jsonify({"error": f"Expected an integer limit, got {raw_limit!r}"}), 400
            if not (1 <= limit <= MAX_LOG_LIMIT):
                return jsonify({"error": f"limit must be between 1 and {MAX_LOG_LIMIT}"}), 400
        else:
            limit = DEFAULT_LOG_LIMIT

        records = tlog.read_logs(
            LOG_DIR,
            services=[service] if service else None,
            min_level=level or None,
            video_id=request.args.get("video_id", "").strip() or None,
            profile_id=request.args.get("profile_id", "").strip() or None,
            search=request.args.get("q", "").strip() or None,
            limit=limit,
        )
        response = jsonify({
            "records": records,
            "count": len(records),
            "limit": limit,
            # Echoed so the dashboard's filter list is not a second copy of the
            # allowlist that could drift from this one.
            "services": list(tlog.SERVICES),
            "levels": list(tlog.LEVELS),
        })
        # The dashboard proxy already sends no-store, so this covers the direct
        # host-side caller (curl, a script) rather than the browser path.
        response.headers["Cache-Control"] = "no-store"
        return response

    return bp
