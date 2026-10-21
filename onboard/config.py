"""Declarative field/section specs for the interactive prompt flow, plus
loaders that pre-fill every field from the settings table.

This is the single source of truth for "what does onboard ask" — each
Section maps to exactly one step via SECTION_TO_STEP (see fields_for_step),
so a step's questions are exactly that section's fields, asked once, right
before that step's action runs (see onboard/prompt.py).

The settings table is the only source of truth for configuration (TMDEV-73);
.env no longer exists. Field "sources" now describe *which* table lookup a
field's pre-fill uses, not which file:
  - "env"      — historical name, kept because renaming it would churn every
                 field spec. These are the fields that used to live in .env
                 and now map to a settings row via ENV_FIELD_TO_SETTING. Their
                 keys stay uppercase because they are form identifiers.
  - "settings" — read from the settings table under the field's own key
                 (trending sources, per-run topic caps, the ElevenLabs voice
                 roster and default, image/review settings).
  - "ephemeral" — never pre-filled from disk (e.g. a one-shot yes/no that must
                 be re-answered every run); loaded value is always "".
"""
import json
import sqlite3
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Callable, Optional

from tubematic_core import voice_models as _voice_models
from onboard.api_keys import (
    KeyCheck,
    check_elevenlabs,
    check_gemini,
    check_openai,
    check_postforme,
    check_youtube_transcript,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Host-side data root — fixed, not configurable (TMDEV-76).
# The pipeline database (which holds the API keys) and the rendered video
# library are machine state, not properties of a git checkout: under the old
# repo-relative `mounted/` a `rm -rf` + re-clone destroyed both silently.
# Keep in sync with docker-compose.yml's volume devices, onboard/config.py,
# scripts/config.py, mcp/server.py and uninstall.py.
DATA_ROOT = Path.home() / ".tubematic-data"

DB_PATH = DATA_ROOT / "data" / "tubematic.db"

# The subdirectories the directories step creates under DATA_ROOT, one per
# bind-mounted volume. checks.py probes the same list for host-user write
# access (TMDEV-94), so the two cannot disagree about what exists.
DATA_SUBDIRS = ("jobs", "data", "output_videos", "scenes/generated", "logs", "backups")

# Where poll.py writes poll.log, and where cron's own output goes. Fixed: the
# cron line names no agent (TMDEV-90), and poll.py starts logging before it can
# ask the API anything. Agent workspaces are its siblings, never its parents
# (agent_install.default_run_path / workspace_conflict). Keep in sync with
# scripts/config.py POLL_LOG_DIR.
POLL_LOG_DIR = Path.home() / ".tubematic-agent" / "logs"

# Source checkout vs. release tarball (TMDEV-91 Phase 2). The tarball ships no
# source trees to build from — the compose file is named identically
# (docker-compose.yml) in both, so a missing renderer/Dockerfile is exactly
# what a release install looks like, and a git checkout always has it.
INSTALL_MODES = ("dev", "release")


def detect_install_mode(repo_root: Path = REPO_ROOT) -> str:
    return "dev" if (repo_root / "renderer" / "Dockerfile").exists() else "release"


def resolve_install_mode(explicit: str | None = None, *, recorded: str | None = None,
                          repo_root: Path = REPO_ROOT) -> str:
    """Precedence: an explicit --install-mode flag, then the mode recorded in
    .onboard-state.json from a prior run, then live detection.

    Without `recorded`, a checkout-relative re-run (e.g. `onboard.py --step
    renderer` with no flag) would re-detect from the checkout layout on every
    invocation — always "dev" inside this repo, no matter which mode the
    original install actually used. Recording the answer once and reusing it
    is what lets a later --step call agree with the run that came before it.
    """
    if explicit:
        return explicit
    if recorded:
        return recorded
    return detect_install_mode(repo_root)

# Trending sources the cron agent can reliably scan via WebFetch/WebSearch
# (public pages, no auth or captcha required). Keep in sync with:
#   dashboard/app/settings/page.tsx  SUPPORTED_TRENDING_SOURCES
#   agent_files/skills/tubematic-topic-research/SKILL.md
SUPPORTED_TRENDING_SOURCES = ["GitHub Trending", "Hacker News", "Lobsters", "Dev.to"]
DEFAULT_TRENDING_SOURCES = ["GitHub Trending", "Hacker News"]

# The ElevenLabs model sets live in tubematic_core.voice_models (TMDEV-121),
# shared with the MCP server and the API. Ordered here for the model prompt:
# the default first, the rest alphabetically.
PRONUNCIATION_PHONEME_MODELS = sorted(_voice_models.PHONEME_COMPATIBLE_MODELS)
DEFAULT_DICTIONARY_MODEL = _voice_models.DEFAULT_MODEL_ID
DICTIONARY_COMPATIBLE_MODELS = [DEFAULT_DICTIONARY_MODEL] + sorted(
    _voice_models.DICTIONARY_COMPATIBLE_MODELS - {DEFAULT_DICTIONARY_MODEL})

# The image-model catalog; OpenAI is the only image provider (TMDEV-165).
# Keep in sync with: renderer/api/pipeline.py, mcp/server.py,
# dashboard/app/settings/page.tsx. Every model must support transparent
# backgrounds: the character_model setting is allowlisted against this list
# too (TMDEV-148).
OPENAI_IMAGE_MODELS = ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]
DEFAULT_IMAGE_MODEL = OPENAI_IMAGE_MODELS[0]

# Gemini models usable for the AI review (VQA-7) — video-understanding text
# models, distinct from the image catalogs above. Keep in sync with
# renderer/api/pipeline.py and dashboard/app/settings/page.tsx.
AI_REVIEW_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]
DEFAULT_AI_REVIEW_MODEL = AI_REVIEW_MODELS[0]
# Gemini's documented valid range for videoMetadata.fps.
MAX_AI_REVIEW_FPS = 24
# VQA-7: "default AI review loop to 1 and max to 2".
MAX_AI_REVIEW_LOOPS = 2
# Keep in sync with renderer/api/pipeline.py's MIN/MAX_LOG_RETENTION_DAYS.
MIN_LOG_RETENTION_DAYS = 1
MAX_LOG_RETENTION_DAYS = 365
# Keep in sync with renderer/api/pipeline.py's MIN/MAX_RETENTION_DAYS. 0 is a
# real value here — it disables the video retention sweep.
MIN_RETENTION_DAYS = 0
MAX_RETENTION_DAYS = 365

# "Teja (eleven_v4) and Adam (eleven_v3)" — the pre-loaded roster, for help text.
_DEFAULT_VOICE_NAMES = " and ".join(
    f"{v['name']} ({v['model_id']})" for v in _voice_models.DEFAULT_VOICES)

# Max named voices in the roster (TMDEV-51). Keep in sync with
# renderer/api/pipeline.py, mcp/server.py and dashboard/app/settings/page.tsx.
MAX_VOICES = 10


# ── Validators ─────────────────────────────────────────────────────────────
# Each returns an error string, or None if valid.

def _positive_int(val: str) -> Optional[str]:
    try:
        if int(val) >= 1:
            return None
    except ValueError:
        pass
    return "Enter a positive integer."


def _nonneg_int(val: str) -> Optional[str]:
    try:
        if int(val) >= 0:
            return None
    except ValueError:
        pass
    return "Enter an integer >= 0."


def _render_timeout_mins(val: str) -> Optional[str]:
    # Floor of 1 minute matches renderer/api/pipeline.py's 60s hard floor on
    # the underlying render_timeout_secs setting — below it a render can never
    # finish before timing out, so every attempt would guarantee-fail (TMDEV-57).
    try:
        if int(val) >= 1:
            return None
    except ValueError:
        pass
    return "Enter an integer >= 1 (minutes) — lower guarantees every render times out."


def _ai_review_fps(val: str) -> Optional[str]:
    # Mirrors renderer/api/pipeline.py's coercion bound. Out of range is a 400
    # at Gemini, and the review fails open — so a bad value here would ship
    # every video unreviewed without surfacing an error anywhere (VQA-7).
    try:
        if 1 <= int(val) <= MAX_AI_REVIEW_FPS:
            return None
    except ValueError:
        pass
    return f"Enter an integer between 1 and {MAX_AI_REVIEW_FPS} (Gemini's valid sampling range)."


def _log_retention_days(val: str) -> Optional[str]:
    # Mirrors renderer/api/pipeline.py's coercion bound. Seeding a value the
    # settings API rejects would leave the dashboard 400ing on the next save of
    # an unrelated field, since POST /settings coerces the whole payload.
    try:
        if MIN_LOG_RETENTION_DAYS <= int(val) <= MAX_LOG_RETENTION_DAYS:
            return None
    except ValueError:
        pass
    return (f"Enter an integer between {MIN_LOG_RETENTION_DAYS} and "
            f"{MAX_LOG_RETENTION_DAYS} (days of logs to keep).")


def _retention_days(val: str) -> Optional[str]:
    # Mirrors renderer/api/pipeline.py's coercion bound, for the same reason as
    # _log_retention_days above.
    try:
        if MIN_RETENTION_DAYS <= int(val) <= MAX_RETENTION_DAYS:
            return None
    except ValueError:
        pass
    return (f"Enter an integer between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS} "
            f"(0 keeps published videos forever).")


def _ai_review_max_loops(val: str) -> Optional[str]:
    # 0 is rejected rather than meaning "review once": the routing boundary is
    # `count > cap`, so 0 would force acceptance before any revision round.
    try:
        if 1 <= int(val) <= MAX_AI_REVIEW_LOOPS:
            return None
    except ValueError:
        pass
    return f"Enter 1 or {MAX_AI_REVIEW_LOOPS}."


def _agent_model(val: str) -> Optional[str]:
    # Shape only: claude's --model takes an alias (sonnet, opus, ...) *or* a
    # full model ID, and the catalog changes faster than this repo does, so an
    # allowlist (like the ElevenLabs voice models') would go stale and reject valid
    # new models. Only reject shapes that can't be a model name and would
    # corrupt the argv (TMDEV-63). Whether the agent actually accepts a name is
    # probed live at --install-agent time (TMDEV-90), not decided here.
    if val == "" or (val == val.strip() and " " not in val and not val.startswith("-")):
        return None
    return "Enter a model alias (sonnet, opus, ...) or full ID — no spaces, or leave blank."


def _parse_voices(raw: str | None) -> list:
    """Parse a JSON-encoded {name, voice_id, model_id} list, degrading to []
    on any corrupt/invalid value — same corrupt-value-falls-back philosophy as
    renderer/api/pipeline.py's _read_all_settings and mcp/server.py's
    _get_voices (three independent readers of the same shape, not a shared
    module). A legacy {name, voice_id} roster is stamped with a model before
    it gets here — see _stamp_legacy_voices."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list) or len(parsed) > MAX_VOICES:
        return []
    for entry in parsed:
        if not isinstance(entry, dict) or set(entry) != {"name", "voice_id", "model_id"}:
            return []
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            return []
        if not isinstance(entry["voice_id"], str) or not entry["voice_id"].strip():
            return []
        if entry["model_id"] not in DICTIONARY_COMPATIBLE_MODELS:
            return []
    return parsed


def _stamp_legacy_voices(raw: str | None, legacy_model: str | None) -> str | None:
    """Give every voice of a pre-TMDEV-121 {name, voice_id} roster the model
    the install was using (legacy_model: the old elevenlabs_model_id row).

    Needed because onboarding reads the stored values BEFORE its database step
    migrates: on a re-run against an older install it would otherwise see a
    roster the strict _parse_voices reads as empty, and apply an empty roster
    over the real one. Same rule as migration 0006 — a blank or retired model
    falls back to the default — so the two can never stamp a voice differently.
    Anything that is not a list of dicts is returned unchanged.
    """
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return raw
    if not isinstance(parsed, list) or not all(isinstance(e, dict) for e in parsed):
        return raw
    model = legacy_model if legacy_model in DICTIONARY_COMPATIBLE_MODELS \
        else DEFAULT_DICTIONARY_MODEL
    if all(e.get("model_id") in DICTIONARY_COMPATIBLE_MODELS for e in parsed):
        return raw
    return json.dumps([{**e, "model_id": e.get("model_id")
                        if e.get("model_id") in DICTIONARY_COMPATIBLE_MODELS else model}
                       for e in parsed])


def writable_parent(val: str) -> Optional[str]:
    """Parent-directory-writable validator. Moves what used to be an
    immediate mkdir-at-prompt-time failure (setup_env used to mkdir
    OUTPUT_VIDEOS_PATH right when asked) back to the point of entry, since
    two-phase would otherwise only surface it minutes later at Apply."""
    if not val:
        return None
    import os

    def _exists(path: Path) -> bool:
        try:
            return path.exists()
        except PermissionError:
            # Can't even stat it — treat as "doesn't exist" so the walk-up
            # keeps climbing toward an ancestor we *can* inspect.
            return False

    p = Path(val).expanduser()
    parent = p if _exists(p) else p.parent
    # Walk up to the nearest existing (and stat-able) ancestor.
    while not _exists(parent) and parent != parent.parent:
        parent = parent.parent
    if not _exists(parent):
        return f"No existing ancestor directory for {val}"
    try:
        writable = os.access(parent, os.W_OK)
    except PermissionError:
        writable = False
    if not writable:
        return f"{parent} is not writable"
    return None


def agent_workspace_exists(values: dict) -> bool:
    """Whether AGENT_RUN_PATH already points at a directory from a prior
    install. Gates the "wipe it?" question (TMDEV-74) — asking that on a fresh
    machine, where there is nothing to wipe, is pure noise.

    The empty-string guard is load-bearing: Path("").expanduser() is Path("."),
    which is always a directory, so a blank AGENT_RUN_PATH would make the
    question always appear. onboard/prompt.py's read-only workspace preview
    calls this same predicate rather than repeating the existence check, so
    the preview and the question can never disagree about what exists.
    """
    raw = (values.get("AGENT_RUN_PATH") or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).expanduser().is_dir()
    except OSError:
        return False


# ── Field / Section model ───────────────────────────────────────────────────

@dataclass
class Field:
    key: str
    label: str
    help: str = ""
    kind: str = "text"          # text | secret | int | select | checkbox | voices | models
    source: str = "env"         # env | settings | ephemeral
    default: str = ""
    choices: list = dc_field(default_factory=list)
    validator: Optional[Callable[[str], Optional[str]]] = None
    # For fields whose valid choices depend on another field's current value
    # in the same form (elevenlabs_voice_id depends on elevenlabs_voices).
    dynamic_choices: Optional[Callable[[dict], list]] = None
    # Blank is not an acceptable answer: the pipeline cannot run without it,
    # so the prompt re-asks instead of storing "" (TMDEV-80). Onboarding exists
    # to hand back a working install, and every one of these has no fallback
    # and no default that could stand in. `--allow-skipping` relaxes it for
    # someone who genuinely cannot supply the value yet.
    required: bool = False
    # Skipped by the default (minimal) questionnaire, which asks only the
    # questions a first install genuinely has to answer; everything marked
    # here is seeded from `default` (or, on a re-run, whatever is already
    # stored) and is editable afterwards on the Settings dashboard (TMDEV-74).
    # `--full-questionnaire` asks these too. Skipping needs no apply-side
    # plumbing: load_current_values() has already put the right value in
    # cfg.values before any question is asked.
    advanced: bool = False
    # Ask this field only when the predicate holds for the current answer set.
    # A separate axis from `advanced` — a conditional field is conditional in
    # both the minimal and the full questionnaire.
    condition: Optional[Callable[[dict], bool]] = None
    # Live credential check for kind="secret" fields (TMDEV-52) — a network
    # round trip, so it stays separate from `validator`, which is pure and
    # runs on every answer of every other kind. Hung off the Field rather than
    # kept in a registry elsewhere so this module remains the single source of
    # truth for what onboard asks *and* what it accepts. Every kind="secret"
    # field must have one; test_config.py pins that, so a future provider
    # can't be added with its key silently unchecked.
    key_check: Optional[Callable[[str], KeyCheck]] = None


@dataclass
class Section:
    key: str
    title: str
    fields: list


SECTIONS = [
    Section("services", "Services & API keys", [
        Field("ELEVENLABS_API_KEY", "ElevenLabs API key", kind="secret",
              key_check=check_elevenlabs, required=True,
              help="Voices every script. Required — there is no fallback provider, so without "
                   "it no video can get past the voicing stage. Billed per character, which is "
                   "why script approval is a human checkpoint."),
        # Optional since TMDEV-165: Gemini no longer draws images, and its two
        # remaining uses — the mining strategy and AI review — are both off
        # without it rather than broken.
        Field("GEMINI_API_KEY", "Gemini API key", kind="secret", key_check=check_gemini,
              help="Optional. Powers the mining research strategy and AI video review. "
                   "Leave it blank and both are simply off; add it later on the Settings "
                   "dashboard to turn them on."),
        # Required (TMDEV-165): OpenAI is the only image provider.
        Field("OPENAI_API_KEY", "OpenAI API key", kind="secret", key_check=check_openai,
              required=True,
              help="Required. Draws every scene image, and the Illustrated style's characters "
                   "(transparent cut-outs). OpenAI grants model access per project, so the "
                   "key's project needs access to the image model you pick later — a key "
                   "without it is refused when the first image is generated, not here."),
        Field("YOUTUBE_TRANSCRIPT_API_KEY", "youtube-transcript.io API key", kind="secret",
              key_check=check_youtube_transcript,
              help="Used by Script Profiles, which you build on the dashboard from transcripts "
                   "of videos whose scripting style you want to borrow. Nothing else needs it: "
                   "the Mining research strategy hands YouTube URLs straight to Gemini and never "
                   "fetches a transcript. Leave blank to set later."),
        # Publishing (TMDEV-83). The toggle is asked FIRST and the key is gated
        # on it: an install that will never publish is never asked for a
        # credential it has no use for.
        #
        # This works only because prompt_step evaluates each field's condition
        # as it reaches it, rather than filtering the whole step up front — see
        # the comment there. Filtering up front would read the pre-filled
        # "false" and drop the key question before the answer existed, so
        # enabling publishing would silently never prompt for a key.
        #
        # Deliberately NOT `required`: a publish is never needed to produce a
        # video, and requiring a postforme account would block onboarding on a
        # service the user may not hold.
        Field("PUBLISHING_ENABLED", "Enable publishing to social platforms?",
              kind="select", choices=["false", "true"], default="false",
              help="Lets you publish approved videos to YouTube, Instagram, TikTok and Facebook "
                   "from the dashboard, via postforme.dev. Every publish is something you click "
                   "and confirm, unless you later put a project on Auto Pilot. Leave off to keep "
                   "downloading videos and posting them yourself; you can turn it on later in "
                   "Settings."),
        # Not `advanced`: conditional AND advanced would collect nothing in the
        # default questionnaire, so answering yes above would still never ask
        # for a key (the trap TMDEV-79 hit with NEW_TRANSCRIPT_URLS).
        Field("POSTFORME_API_KEY", "postforme.dev API key", kind="secret",
              key_check=check_postforme,
              condition=lambda v: v.get("PUBLISHING_ENABLED") == "true",
              help="Found on your postforme.dev dashboard. This is the most powerful credential "
                   "in the install — it can post to every social account connected to that "
                   "postforme project — so connect only accounts you are happy for Tubematic to "
                   "reach, then pick which of them it may use on the Socials page."),
        # Off by default (TMDEV-165). "false" leads `choices` because a select
        # falls back to choices[0]. Keep in sync: the two fallbacks in
        # actions.py, renderer/api/pipeline.py SETTINGS_SPEC, and worker.py.
        Field("GEMINI_REVIEW_ENABLED", "Enable Gemini defect review? (Experimental)",
              kind="select", choices=["false", "true"], default="false",
              help="Off by default. After each render, sends the finished video to Gemini to "
                   "look for visual defects, and sends it back for revision if it finds any. "
                   "Experimental: it needs the Gemini key, costs a Gemini call per render and "
                   "can flag a non-defect. If the review itself fails, the video goes to your "
                   "review as if it had passed. Off, renders go straight to your review."),
        # Caps RENDER retries only (crash, timeout, worker-restart
        # reconciliation). It used to double as the AI-review loop cap; VQA-7
        # split those apart, and the review's own cap is asked in the
        # "AI review" section of the pipeline_settings step.
        Field("MAX_RENDER_RETRIES", "Max render retries", kind="int",
              default="1", validator=_nonneg_int, advanced=True,
              help="How many times a crashed or timed-out render is retried before the video is "
                   "marked FAILED. This is not the AI-review loop — that is asked separately, in "
                   "the AI review step."),
        Field("MCP_PORT", "MCP server port", help="published by the tubematic-mcp container",
              kind="int", default="4100", validator=_positive_int, advanced=True),
        Field("RESEARCH_PENDING_CAP", "Max pending topics before research is skipped",
              kind="int", default="15", validator=_nonneg_int, advanced=True,
              help="A cost guard. Once this many topics are waiting for your approval, scheduled "
                   "research stops running entirely — no agent invocation, no tokens. The cap "
                   "clears itself as you approve or reject topics."),
    ]),
    # The agent's own questions (install scope, workspace, wipe, models) are
    # not here: agents are installed separately, by `onboard.py --install-agent
    # <name>`, whose fields live in onboard/agent_install.py (TMDEV-90).
    Section("scheduling", "Scheduling", [
        Field("POLL_INTERVAL_MINS", "Cron poll interval (minutes)", kind="int",
              default="30", validator=_positive_int,
              help="How often cron checks for work when the pipeline is idle. While there is "
                   "work, the scheduled poller keeps running and starts each next stage as soon "
                   "as the last one finishes, so this is not how often videos advance. This is "
                   "baked into the crontab line, so "
                   "changing it later means re-running this step — editing the stored value "
                   "alone does nothing."),
    ]),
    Section("research_caps", "Per-run topic caps", [
        Field("max_curriculum_per_run", "Max curriculum topics per run", source="settings",
              kind="int", default="2", validator=_nonneg_int, advanced=True,
              help="How many topics one research run may propose per active seed domain."),
        Field("max_trending_per_run", "Max trending topics per run", source="settings",
              kind="int", default="2", validator=_nonneg_int, advanced=True,
              help="How many topics one research run may propose from the trending sources."),
        Field("max_mining_per_run", "Max mining topics per run", source="settings",
              kind="int", default="2", validator=_nonneg_int, advanced=True,
              help="How many spin-off topics one research run may propose from your mining "
                   "YouTube URLs."),
        Field("trending_sources", "Active trending sources", source="settings",
              kind="checkbox", choices=SUPPORTED_TRENDING_SOURCES, advanced=True,
              default=json.dumps(DEFAULT_TRENDING_SOURCES),
              help="Which public pages the trending strategy scans for producible angles. All "
                   "four are fetched over the open web — no account or API key needed."),
        Field("max_research_runs_per_day", "Max research runs per 24h (rolling window)",
              source="settings", kind="int", default="8", validator=_nonneg_int, advanced=True,
              help="Research runs once each time the scheduled poller starts, when the "
                   "pending-topic queue has room; this bounds how many research agent sessions "
                   "can fire in any trailing 24h, independent of that queue check."),
    ]),
    Section("voices", "ElevenLabs voices", [
        # Must precede elevenlabs_voice_id in this section: prompt_step writes
        # each answer into cfg.values as it iterates and passes cfg.values as
        # all_values, so elevenlabs_voice_id's dynamic_choices only sees the
        # roster if it was asked first.
        # Advanced (TMDEV-172): a fresh install starts with
        # voice_models.DEFAULT_VOICES and its first voice as the default,
        # seeded through these fields' defaults — load_current_values only
        # falls back to a default when no row is stored, so a re-run keeps the
        # stored roster, even an emptied one. That default is also why the
        # roster is no longer required (it was since TMDEV-80: an empty roster
        # fails the first voicing with "No default voice set").
        # Each voice carries its own model (TMDEV-121), asked right after its
        # ID. Pronunciation is not a separate choice: the lexicon and inline
        # <respell> tags work on every model, and a model in
        # PRONUNCIATION_PHONEME_MODELS additionally gets <phoneme> tags, and
        # the IPA models <ipa> tags, detected automatically from the voice's model.
        Field("elevenlabs_voices", f"Named voices (up to {MAX_VOICES})", source="settings",
              kind="voices", default=json.dumps(list(_voice_models.DEFAULT_VOICES)),
              advanced=True,
              help="Give each ElevenLabs voice ID a short name and pick the model it speaks "
                   "with — find the IDs in your ElevenLabs voice library. A new install starts "
                   f"with {_DEFAULT_VOICE_NAMES}. Pronunciation control (the term "
                   "lexicon and inline <respell> tags) works on every model; "
                   f"{', '.join(PRONUNCIATION_PHONEME_MODELS)} also take exact <phoneme> tags "
                   f"and {', '.join(sorted(_voice_models.IPA_COMPATIBLE_MODELS))} exact IPA. "
                   "Enter on the first prompt keeps the roster you already have."),
        Field("elevenlabs_voice_id", "Default voice", source="settings", kind="select",
              default=_voice_models.DEFAULT_VOICE_ID, advanced=True,
              help="Used whenever a video doesn't have its own voice picked.",
              dynamic_choices=lambda values: [
                  v["voice_id"] for v in _parse_voices(values.get("elevenlabs_voices"))
              ]),
    ]),
    Section("image_generation", "Image generation", [
        Field("image_model", "Image generation model", source="settings", kind="select",
              choices=OPENAI_IMAGE_MODELS, default=DEFAULT_IMAGE_MODEL,
              help="The OpenAI model that draws scene images. Image generation needs billing "
                   "enabled on the OpenAI project your key belongs to."),
    ]),
    Section("rendering", "Rendering", [
        # Asked in minutes for readability; stored as render_timeout_secs (seconds)
        # in the settings table, which is what renderer/api/pipeline.py and
        # worker.py actually read. The minutes<->seconds conversion happens at
        # the load boundary (load_current_values, below) and the write boundary
        # (onboard/actions.py's apply_pipeline_settings) — this field's own key
        # is never itself a settings-table key.
        Field("render_timeout_mins", "Render timeout (minutes)", source="settings",
              kind="int", default="40", validator=_render_timeout_mins, advanced=True,
              help="How long the render worker waits for a single video before giving up and "
                   "auto-retrying. Videos that use generated images render markedly slower than "
                   "pure-animation ones — raise this if renders are timing out."),
    ]),
    Section("logs", "Logs", [
        Field("log_retention_days", "Keep logs for (days)", source="settings",
              kind="int", default="14", validator=_log_retention_days, advanced=True,
              help="How long the structured JSONL logs under ~/.tubematic-data/logs are "
                   "kept before being deleted. Each service prunes its own files at "
                   "startup and once a day after that, so a change here takes effect at "
                   "the next pass rather than immediately."),
    ]),
    Section("retention", "Video retention", [
        Field("retention_days", "Delete published videos after (days)", source="settings",
              kind="int", default="7", validator=_retention_days, advanced=True,
              help="How many days after a video is published before its rendered mp4 and "
                   "working files (audio, images) are deleted to free disk. The record, its "
                   "publication links and analytics are kept, in the dashboard's Archive. "
                   "Only published videos are ever deleted this way. 0 keeps them forever."),
    ]),
    Section("auto_pilot", "Auto Pilot", [
        # A select, not a checkbox, and off by default: this is the one switch
        # that removes every human checkpoint, so it is never a keypress away.
        # Turning it on here does nothing by itself — projects are chosen on
        # the dashboard, which is also where the confirmation lives.
        Field("auto_pilot_enabled", "Turn on Auto Pilot?", source="settings",
              kind="select", choices=["false", "true"], default="false", advanced=True,
              help="Auto Pilot approves topics, scripts and finished videos with no human "
                   "review and posts them, for the projects you select on the dashboard's "
                   "Settings, Auto Pilot tab. It spends ElevenLabs credits, image generation "
                   "and agent sessions on every topic research files, and it posts publicly "
                   "to real accounts, including videos the AI review flagged or could not "
                   "check. A published post cannot be taken back. Leave it off unless you "
                   "want that. Nothing is approved until a project is selected."),
    ]),
    Section("ai_review", "AI review", [
        # Per-option annotations aren't supported — prompt.py passes bare
        # strings to questionary.select — so the cost comparison lives in one
        # help blob.
        Field("ai_review_model", "AI review model", source="settings", kind="select",
              choices=AI_REVIEW_MODELS, default=DEFAULT_AI_REVIEW_MODEL, advanced=True,
              help="Which Gemini model reviews each rendered video. gemini-2.5-flash is the "
                   "default and the cheapest. The 3.x flash models cost only about 1.4x as much "
                   "per video reviewed, not the 5x their headline token price suggests — they "
                   "tokenise video roughly 3.7x more cheaply (measured: 71 vs 263 tokens per "
                   "frame). Of the two, gemini-3.6-flash is strictly better value than "
                   "gemini-3.5-flash: same input price, cheaper output."),
        Field("ai_review_fps", "Review sampling rate (frames/sec)", source="settings",
              kind="int", default="10", validator=_ai_review_fps, advanced=True,
              help="Gemini samples an uploaded video at 1 frame per second unless told "
                   "otherwise, which is too coarse to see motion defects in a 30fps render. "
                   "10 is the highest rate that fits a ~6 minute video in gemini-2.5-flash's "
                   "context window; the 3.x models afford the full 24. Cost scales linearly "
                   "with this (a 4-minute video costs roughly 2 cents at 1, 20 cents at 10 on "
                   "gemini-2.5-flash). Videos too long for the chosen rate are sampled lower "
                   "automatically rather than failing."),
        Field("ai_review_max_loops", "Max AI review rounds", source="settings",
              kind="int", default="1", validator=_ai_review_max_loops, advanced=True,
              help="How many times the review can send a video back for revision before it is "
                   "accepted regardless of findings (1 or 2). Separate from the render retry "
                   "cap asked in the Services step."),
    ]),
]

FIELDS_BY_KEY = {f.key: f for s in SECTIONS for f in s.fields}

# Which step's prompt-and-run turn asks a given section's fields. Every
# section maps to exactly one step; a step with no section mapped to it
# (directories, database, renderer, dashboard) has no prompts
# of its own, and the actions.py step docstrings on steps.py's STEP_DEFS
# describe what those fields are used for (e.g. "claude" also reads
# MCP_PORT, but doesn't prompt for it — that's asked once, by "env").
SECTION_TO_STEP = {
    "services": "install_config",
    "scheduling": "cron",
    "research_caps": "pipeline_settings",
    "voices": "pipeline_settings",
    "image_generation": "pipeline_settings",
    "rendering": "pipeline_settings",
    "logs": "pipeline_settings",
    "retention": "pipeline_settings",
    "auto_pilot": "pipeline_settings",
    "ai_review": "pipeline_settings",
}


def fields_for_step(step_key: str, *, full: bool = False,
                    values: Optional[dict] = None) -> list:
    """Every field a step should prompt for, in section-then-field order.

    `full=False` (the default) is the minimal questionnaire: fields marked
    `advanced` are dropped and keep whatever load_current_values() pre-filled
    for them — their stored value, or the field's own default on a fresh
    install (TMDEV-74). `--full-questionnaire` passes full=True.

    `values` is the current answer set, used to evaluate each field's
    `condition`. Passing None means "don't evaluate conditions at all" rather
    than "no answers yet": --steps lists what a step *can* ask without a
    running config, and must show conditional fields rather than silently
    omitting them.
    """
    fields = [f for s in SECTIONS if SECTION_TO_STEP.get(s.key) == step_key for f in s.fields]
    if not full:
        fields = [f for f in fields if not f.advanced]
    if values is not None:
        fields = [f for f in fields if f.condition is None or f.condition(values)]
    return fields


# Form-field key → settings-table row (TMDEV-73). The fields that used to be
# written to .env keep their uppercase keys — those are form identifiers, and
# renaming them would churn every prompt, test and help string for no gain —
# while the rows they now land in are lowercase like every other settings key.
# One table so the reader (load_current_values) and the writer
# (actions.apply_install_config) can never disagree about the mapping.
ENV_FIELD_TO_SETTING = {
    # Credentials — SETTINGS_SPEC "secret" keys, masked over HTTP.
    "ELEVENLABS_API_KEY":         "elevenlabs_api_key",
    "GEMINI_API_KEY":             "gemini_api_key",
    "OPENAI_API_KEY":             "openai_api_key",
    "YOUTUBE_TRANSCRIPT_API_KEY": "youtube_transcript_api_key",
    "POSTFORME_API_KEY":          "postforme_api_key",
    # Dashboard-editable (Tier A).
    "GEMINI_REVIEW_ENABLED":      "gemini_review_enabled",
    "PUBLISHING_ENABLED":         "publishing_enabled",
    "MAX_RENDER_RETRIES":         "max_render_retries",
    "RESEARCH_PENDING_CAP":       "research_pending_cap",
    # Tier B — stored for visibility and for onboard's own re-runs, but a
    # dashboard edit would be a silent no-op until onboard regenerates the
    # derived artifact (the cron line), so these
    # are deliberately outside SETTINGS_SPEC. The agent's binary, workspace and
    # install scope used to be here too; they are columns of its agents row
    # now (TMDEV-90), written by --install-agent.
    "MCP_PORT":                   "mcp_port",
    "POLL_INTERVAL_MINS":         "poll_interval_mins",
}


# ── Loaders ──────────────────────────────────────────────────────────────

def read_settings(db_path: Path = DB_PATH) -> dict:
    if not db_path.exists():
        return {}
    try:
        con = sqlite3.connect(str(db_path))
        rows = con.execute("SELECT key, value FROM settings").fetchall()
        con.close()
        return dict(rows)
    except Exception:
        return {}


def read_agents(db_path: Path = DB_PATH) -> list:
    """Every agents row, archived included, with `models` parsed — [] when
    there is no database or no agents table yet (TMDEV-90)."""
    if not db_path.exists():
        return []
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM agents ORDER BY created_at, id").fetchall()]
        finally:
            con.close()
    except sqlite3.Error:
        return []
    for row in rows:
        try:
            models = json.loads(row.get("models") or "[]")
        except json.JSONDecodeError:
            models = []
        row["models"] = [m for m in models if isinstance(m, str)] if isinstance(models, list) else []
    return rows


def load_current_values(repo_root: Path = REPO_ROOT, db_path: Path = DB_PATH) -> dict:
    """The stored value for every field — the prompt flow's pre-fill/default
    for each question. `repo_root` is vestigial; nothing on disk is read any
    more, only the settings table."""
    settings = read_settings(db_path)
    values = {}
    for f in FIELDS_BY_KEY.values():
        if f.source == "env":
            # Historical source name; the value lives in the settings table
            # under its mapped row (TMDEV-73). `or` rather than a plain
            # .get default: onboarding seeds "" for every credential it did
            # not ask about, and an empty row should still offer the default.
            row = ENV_FIELD_TO_SETTING.get(f.key)
            stored = settings.get(row, "") if row else ""
            values[f.key] = stored or f.default
        elif f.source == "settings":
            values[f.key] = settings.get(f.key, f.default)
            if f.key == "elevenlabs_voices":
                values[f.key] = _stamp_legacy_voices(values[f.key],
                                                     settings.get("elevenlabs_model_id"))
        else:  # ephemeral — never read from disk; the field's own default
               # (e.g. "false" for a wipe confirm) is the pre-fill instead.
            values[f.key] = f.default

    # render_timeout_mins has no settings-table row of its own — it's a
    # minutes-readable view over render_timeout_secs (TMDEV-57). Override the
    # generic settings.get(f.key, ...) miss above (there is no "render_timeout_mins"
    # row) with the real seconds value converted to whole minutes, so onboard
    # re-runs reflect whatever was actually set (dashboard, MCP, or a prior run)
    # instead of always showing the field's static default.
    raw_secs = settings.get("render_timeout_secs")
    if raw_secs is not None:
        try:
            values["render_timeout_mins"] = str(max(1, int(raw_secs) // 60))
        except (TypeError, ValueError):
            pass
    return values


@dataclass
class OnboardConfig:
    """A running answer set. There is no separate "loaded" baseline to diff
    against — a step's questions are only ever asked when that step is
    about to run (fresh install, or explicitly targeted via --step/--force),
    so there's no window where an edited answer could be silently discarded
    the way a collect-everything-then-apply-later design would risk."""
    values: dict

    @classmethod
    def load(cls, repo_root: Path = REPO_ROOT, db_path: Path = DB_PATH) -> "OnboardConfig":
        return cls(values=load_current_values(repo_root, db_path))
