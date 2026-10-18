"""Unit tests for poll.py build_research_prompt."""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch

import pytest
import json

# Import the functions under test
from poll import build_research_prompt, build_pipeline_prompt, _fetch_settings, _now_iso


def test_build_research_prompt_embeds_configured_caps():
    """Prompt includes per-run caps from settings."""
    settings_data = {
        "max_curriculum_per_run": 3,
        "max_trending_per_run": 2,
        "max_mining_per_run": 4,
        "trending_sources": ["Lobsters"],
    }
    with patch("poll._fetch_settings", return_value=settings_data), \
         patch("poll._fetch_mining_urls", return_value=[]):
        prompt = build_research_prompt(["curriculum", "trending", "mining"])
    assert "up to 3" in prompt
    assert "up to 2" in prompt
    assert "up to 4" in prompt
    assert "Lobsters" in prompt


def test_no_mining_target_without_mining():
    """The API drops mining while no Gemini key is stored (TMDEV-165); a
    mining target left in the prompt would invite a call that cannot work."""
    with patch("poll._fetch_settings", return_value={"max_mining_per_run": 4}), \
         patch("poll._fetch_mining_urls", return_value=[]):
        prompt = build_research_prompt(["curriculum", "trending"])
    assert "mine_youtube_topics" not in prompt
    assert "mining:" not in prompt
    with patch("poll._fetch_settings", return_value={"max_mining_per_run": 4}), \
         patch("poll._fetch_mining_urls", return_value=[]):
        prompt = build_research_prompt(["curriculum", "mining"])
    assert "mining:     up to 4" in prompt


def test_build_research_prompt_uses_defaults_when_settings_unavailable():
    """Prompt uses default caps if settings fetch fails."""
    with patch("poll._fetch_settings", return_value={}), \
         patch("poll._fetch_mining_urls", return_value=[]):
        prompt = build_research_prompt(["curriculum"])
    assert "up to 2" in prompt  # default curriculum cap


def test_build_research_prompt_dedups_against_the_whole_domain_history():
    """list_videos hides archived videos, so deduplicating with it re-proposed
    deleted and retention-swept topics (TMDEV-153). The prompt must name the
    tool that lists them, and skip an expired domain like a paused one."""
    with patch("poll._fetch_settings", return_value={}), \
         patch("poll._fetch_mining_urls", return_value=[]):
        prompt = build_research_prompt(["curriculum", "trending"])
    assert "list_project_topics()" in prompt
    assert "archived" in prompt
    assert "expired is false" in prompt
    assert "paused or expired, SKIP" in prompt


def test_fetch_settings_returns_empty_on_error():
    """_fetch_settings returns {} on network error."""
    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        result = _fetch_settings()
    assert result == {}


def test_build_research_prompt_trending_sources_shown_only_when_trending_active():
    """Trending sources block only appears when trending strategy is active."""
    settings_data = {"trending_sources": ["SomeSource"]}
    with patch("poll._fetch_settings", return_value=settings_data), \
         patch("poll._fetch_mining_urls", return_value=[]):
        prompt_with_trending = build_research_prompt(["trending"])
        prompt_without_trending = build_research_prompt(["curriculum"])
    assert "SomeSource" in prompt_with_trending
    assert "SomeSource" not in prompt_without_trending


def test_build_research_prompt_mining_urls_embedded():
    """Mining URLs from _fetch_mining_urls are included in the prompt."""
    with patch("poll._fetch_settings", return_value={}), \
         patch("poll._fetch_mining_urls", return_value=["https://youtube.com/watch?v=abc"]):
        prompt = build_research_prompt(["mining"])
    assert "https://youtube.com/watch?v=abc" in prompt


def test_now_iso_carries_a_utc_offset_not_a_bare_z():
    """_now_iso() switched from UTC-with-Z to host-local-with-offset (TMDEV-35).
    A bare 'Z' would mean the value is still forced UTC."""
    ts = _now_iso()
    assert "Z" not in ts
    assert re.search(r"[+-]\d{4}", ts)


def test_pipeline_prompt_header_carries_local_offset():
    """The [TUBEMATIC POLL — ts] header the agent reads its 'now' from is
    host-local with an explicit offset, not the old forced-UTC format."""
    prompt = build_pipeline_prompt("vid_a", "VOICING")
    header = prompt.splitlines()[0]
    assert re.search(r"\[TUBEMATIC POLL — \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} \(.+\)\]", header)


# ── User preferences block (TMDEV-117) ───────────────────────────────────────

from poll import build_script_profile_prompt, _preferences_block  # noqa: E402

PREFS = "Research: favour Linux internals.\nScripts: no jokes, calm tone."
FOOTER = "IMPORTANT: Skip the operator skill setup checks"


def _all_prompts(preferences):
    with patch("poll._fetch_settings", return_value={}), \
         patch("poll._fetch_mining_urls", return_value=[]):
        return {
            "pipeline": build_pipeline_prompt("vid_a", "VOICE_READY", preferences=preferences),
            "research": build_research_prompt(["curriculum"], preferences=preferences),
            "profile": build_script_profile_prompt("prof-1", "A", preferences=preferences),
        }


def test_empty_preferences_produce_no_block():
    assert _preferences_block("", "topic research") == []
    assert _preferences_block("  \n\t ", "topic research") == []


def test_no_preferences_leave_every_prompt_exactly_as_before():
    """An install that never sets preferences must send the agent the same
    bytes it always did — the default argument and "" are identical."""
    with patch("poll._fetch_settings", return_value={}), \
         patch("poll._fetch_mining_urls", return_value=[]):
        with patch("poll._now_iso", return_value="T"):
            before = {
                "pipeline": build_pipeline_prompt("vid_a", "VOICE_READY"),
                "research": build_research_prompt(["curriculum"]),
                "profile": build_script_profile_prompt("prof-1", "A"),
            }
            after = {
                "pipeline": build_pipeline_prompt("vid_a", "VOICE_READY", preferences="   "),
                "research": build_research_prompt(["curriculum"], preferences=""),
                "profile": build_script_profile_prompt("prof-1", "A", preferences=""),
            }
    assert before == after
    assert all("USER PREFERENCES" not in p for p in before.values())


def test_every_prompt_carries_the_preferences_verbatim_in_a_fenced_block():
    for name, prompt in _all_prompts(PREFS).items():
        assert "=== USER PREFERENCES" in prompt, name
        assert "=== END USER PREFERENCES ===" in prompt, name
        start = prompt.index("=== USER PREFERENCES")
        end = prompt.index("=== END USER PREFERENCES ===")
        assert PREFS in prompt[start:end], name


def test_the_block_names_the_stage_of_each_run():
    prompts = _all_prompts(PREFS)
    assert "This run's stage: advancing one video (scene work)" in prompts["pipeline"]
    assert "This run's stage: topic research" in prompts["research"]
    assert "This run's stage: building a script style profile" in prompts["profile"]


def test_the_block_scopes_itself_to_the_stage_and_never_overrides_the_rules():
    """The text mixes stages, so the agent is told to take only what fits; and
    a preference like "just approve scripts" must not read as permission to
    cross a human checkpoint."""
    block = "\n".join(_preferences_block(PREFS, "topic research"))
    assert "Apply ONLY the instructions relevant to this stage" in block
    assert "never override" in block
    assert "human checkpoints" in block


def test_the_block_sits_after_the_task_and_before_the_footer():
    for name, prompt in _all_prompts(PREFS).items():
        assert prompt.index("=== END USER PREFERENCES ===") < prompt.index(FOOTER), name


# ── One video, one stage per session (TMDEV-129) ─────────────────────────────

@pytest.mark.parametrize("status,stops", [
    ("TOPIC_APPROVED", ["SCRIPT_READY"]),
    ("VOICING", ["VOICE_READY"]),
    ("VOICE_READY", ["RENDER_QUEUED"]),
    ("REVISION_REQUESTED", ["TOPIC_PROPOSED", "SCRIPT_READY", "VOICING", "RENDER_QUEUED"]),
])
def test_the_pipeline_prompt_names_one_video_and_where_its_stage_ends(status, stops):
    prompt = build_pipeline_prompt("vid_a", status)
    assert "scoped to video vid_a, currently at " + status in prompt
    assert 'get_video("vid_a")' in prompt
    stop_line = next(line for line in prompt.splitlines() if line.startswith("Stop as soon as"))
    for stop in stops:
        assert stop in stop_line


def test_the_pipeline_prompt_forbids_looking_for_other_work():
    """Other sessions are advancing other videos at the same time; a session
    that went looking for more work would collide with them."""
    prompt = build_pipeline_prompt("vid_a", "VOICE_READY")
    assert "Work only on this video" in prompt
    assert "do not go looking for more work with list_videos or get_pipeline_status" in prompt


def test_the_pipeline_prompt_does_not_ban_reading_settings():
    """The skills read the pronunciation lexicon and the voice roster from
    get_pipeline_status. A flat "do not call" made sessions skip what the
    skill required: seen live, illustrated videos came out with no generated
    characters because the key check lived behind the banned tool."""
    prompt = build_pipeline_prompt("vid_a", "VOICE_READY")
    assert "do not call get_pipeline_status" not in prompt
    assert "Reading install settings from get_pipeline_status is fine" in prompt


def test_a_pronunciation_revision_is_told_to_end_at_voicing():
    """Seen live: with only the stop list to go on, a revision session set
    VOICING, re-voiced and redid the scenes in one go, recording all of it as
    the revision's cost — the operator skill's pronunciation row says to carry
    on, so the prompt has to say plainly that a scheduled run does not."""
    prompt = build_pipeline_prompt("vid_a", "REVISION_REQUESTED")
    assert "A pronunciation revision ends at VOICING" in prompt
    assert "Do NOT call generate_voice here" in prompt
    assert "A pronunciation revision ends at VOICING" not in build_pipeline_prompt("vid_a", "VOICING")


def test_the_operator_skill_ends_a_scheduled_pronunciation_revision_at_voicing():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    skill = open(os.path.join(root, "agent_files", "skills", "tubematic-operator",
                              "SKILL.md")).read()
    row = next(line for line in skill.splitlines()
               if line.startswith("|") and "| **Pronunciation revision** |" in line)
    assert "In a scheduled run scoped to one video and one stage, end the session here" in row


def test_a_revision_is_told_not_to_stop_at_voice_ready():
    """The scene-work claim spans REVISION_REQUESTED → VOICE_READY and is keyed
    to the session: stopping there would hand the second half to a session the
    claim refuses."""
    assert "Do NOT stop at VOICE_READY" in build_pipeline_prompt("vid_a", "REVISION_REQUESTED")
    assert "Do NOT stop at VOICE_READY" not in build_pipeline_prompt("vid_a", "VOICING")


def test_every_workable_status_has_a_stage():
    """A workable status with no stage would be skipped forever."""
    import poll
    pipeline_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "renderer", "api", "pipeline.py")).read()
    block = pipeline_src.split("WORKABLE_STATUSES = [", 1)[1].split("]", 1)[0]
    workable = set(re.findall(r'"([A-Z_]+)"', block))
    assert workable == set(poll.STAGES)
