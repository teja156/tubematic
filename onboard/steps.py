"""The 10 apply-phase steps of a default run, in order.

Agents are not a step (TMDEV-90): the project is set up here, and each agent is
installed afterwards by `onboard.py --install-agent <name>` — see
onboard/agent_install.py.

This is the single source of truth for "what each step contains" — `--steps`
renders straight from here. Actual apply logic lives in onboard/actions.py;
the actual *prompts* for a step come from onboard/config.py's
`fields_for_step()` (one section maps to each step). `consumes` here is
descriptive metadata only — e.g. "pipeline_settings" reading
GEMINI_REVIEW_ENABLED, which "install_config" prompts for — used for `--steps`
output, not for any prompting/gating logic.

Build/container-start steps (`renderer`, `dashboard`) are last, per TMDEV-6's
"build steps at the END" ask. `directories` and `database` must precede them:
Docker creates missing bind-mount targets as root, so if either ran after
container start the mount points (or the DB file) would come out root-owned.
Since prompting happens step-by-step in this same order and only
"install_config" through "cron" have any prompts at all, by the time execution
reaches "renderer" every question has already been asked — builds run last with
nothing interleaved, without needing a separate collect-everything phase.

`database` additionally precedes `install_config` (TMDEV-73): configuration is
now seeded into the settings table rather than written to .env, so there has to
be a database to write it into. That is the one ordering constraint the .env
era did not have.

"""
from dataclasses import dataclass, field


@dataclass
class Step:
    key: str
    label: str
    description: str
    consumes: list = field(default_factory=list)
    builds_or_starts: bool = False


STEP_DEFS = [
    Step(
        "prerequisites", "Prerequisites",
        "Checks Docker running, docker compose v2, Python 3.11+, Node.js/npx. "
        "No prompts — read-only.",
    ),
    Step(
        "python_deps", "Python dependencies",
        "pip install -r scripts/requirements.txt. Previewed, not executed, under --dry-run.",
    ),
    Step(
        "directories", "Directories",
        "Creates mounted/jobs, mounted/data, mounted/output_videos, mounted/scenes/generated. "
        "Must precede container start.",
    ),
    Step(
        "database", "Database",
        "Initialises mounted/data/tubematic.db with the canonical schema. Must precede container "
        "start for the same root-ownership reason as directories.",
    ),
    Step(
        "auth", "Dashboard password and service tokens",
        "Creates the three service tokens in ~/.tubematic-data/secrets/ (kept when they "
        "already exist) and asks for the dashboard password when none is set — twice, hidden, "
        "at least 12 characters. Change it later with --set-password. Must precede container "
        "start: Compose refuses to start a service whose token file is missing.",
    ),
    Step(
        "install_config", "Install configuration",
        "Seeds the settings table with API keys, publishing, per-run research cap, transcript "
        "API key. Every API key is verified against "
        "its provider as it is entered, and a rejected one is re-asked. Requires the OpenAI key, "
        "which draws every scene image. Runs after `database` because it "
        "writes rows, not a file. The MCP port, render retry budget and pending-topic "
        "cap are only asked under --full-questionnaire.",
        consumes=[
            "ELEVENLABS_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
            "GEMINI_REVIEW_ENABLED", "MAX_RENDER_RETRIES", "MCP_PORT",
            "RESEARCH_PENDING_CAP", "YOUTUBE_TRANSCRIPT_API_KEY",
        ],
    ),
    Step(
        "pipeline_settings", "Pipeline settings",
        "Seeds the rest of the dashboard-editable settings table: per-run topic caps, "
        "trending sources, the "
        "ElevenLabs voice roster (each voice with its own model; pronunciation mode is "
        "auto-detected from the model, not asked) and default voice, the image-generation model, the render timeout, and the AI "
        "review model/sampling rate/loop cap, all asked fresh. Only the image model is asked by "
        "default; the rest need --full-questionnaire. A new install's voice roster starts with "
        "the pre-loaded voices.",
        consumes=[
            "GEMINI_REVIEW_ENABLED", "MAX_RENDER_RETRIES", "RESEARCH_PENDING_CAP",
            "max_curriculum_per_run", "max_trending_per_run",
            "max_mining_per_run", "trending_sources", "elevenlabs_voices", "elevenlabs_voice_id",
            "max_research_runs_per_day", "image_model",
            "render_timeout_mins",
            "ai_review_model", "ai_review_fps", "ai_review_max_loops",
        ],
    ),
    Step(
        "cron", "Cron jobs",
        "Writes the poll cron entry (advances the pipeline and runs topic research) to your "
        "user crontab. The entry names no agent — each tick asks the API which agent each video "
        "belongs to — so it does nothing until one is installed with --install-agent.",
        consumes=["POLL_INTERVAL_MINS"],
    ),
    Step(
        "renderer", "API, MCP + render worker containers",
        "docker compose build tubematic-api (shared image) + up tubematic-api tubematic-mcp "
        "tubematic-renderer. Waits for the API and MCP health checks.",
        builds_or_starts=True,
    ),
    Step(
        "dashboard", "Dashboard container",
        "docker compose build + up tubematic-dashboard.",
        builds_or_starts=True,
    ),
]

STEP_BY_KEY = {s.key: s for s in STEP_DEFS}
VALID_KEYS = set(STEP_BY_KEY)
