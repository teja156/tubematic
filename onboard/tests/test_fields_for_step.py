"""Every section maps to exactly one step (SECTION_TO_STEP), and
fields_for_step is what drives the actual per-step prompting — this is the
mechanism that guarantees a field like GEMINI_REVIEW_ENABLED (shared across
install_config/pipeline_settings in steps.py's descriptive `consumes` lists) is
only ever *asked* once, by its owning section's step."""
from onboard.config import SECTIONS, SECTION_TO_STEP, fields_for_step, FIELDS_BY_KEY
from onboard.steps import STEP_DEFS, VALID_KEYS


def test_every_section_maps_to_a_valid_step():
    for section in SECTIONS:
        assert section.key in SECTION_TO_STEP, f"{section.key} has no owning step"
        assert SECTION_TO_STEP[section.key] in VALID_KEYS


def test_fields_for_step_install_config_matches_the_services_section():
    services = next(s for s in SECTIONS if s.key == "services")
    expected = [f.key for f in services.fields]
    assert [f.key for f in fields_for_step("install_config", full=True)] == expected


def test_fields_for_step_empty_for_prompt_free_steps():
    for key in ("prerequisites", "python_deps", "directories", "database"):
        assert fields_for_step(key) == []


def test_every_field_key_is_unique_across_sections():
    keys = [f.key for s in SECTIONS for f in s.fields]
    assert len(keys) == len(set(keys))


def test_the_main_flow_asks_nothing_about_an_agent():
    """Agents are installed separately, by --install-agent (TMDEV-90): the main
    flow sets up the project only."""
    agent_keys = {"INSTALL_SCOPE", "AGENT_RUN_PATH", "TUBEMATIC_AGENT",
                  "TUBEMATIC_AGENT_MODEL", "WIPE_AGENT_WORKSPACE", "AGENT_MODELS"}
    for step in STEP_DEFS:
        asked = {f.key for f in fields_for_step(step.key, full=True)}
        assert not asked & agent_keys, step.key


# ── Minimal vs full questionnaire (TMDEV-74) ───────────────────────────────

MINIMAL_BY_STEP = {
    "install_config": [
        # The four unconditional credentials lead, contiguous (TMDEV-79).
        "ELEVENLABS_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "YOUTUBE_TRANSCRIPT_API_KEY",
        # Then the publishing gate and the credential it gates (TMDEV-83).
        # fields_for_step with no values does not evaluate conditions, so the
        # key appears here even though a real run may skip it.
        "PUBLISHING_ENABLED", "POSTFORME_API_KEY",
        "GEMINI_REVIEW_ENABLED",
    ],
    # The voice roster and default voice are advanced since a fresh install
    # starts with the pre-loaded voices (TMDEV-172).
    "pipeline_settings": ["image_model"],
    "cron": ["POLL_INTERVAL_MINS"],
}


def test_minimal_questionnaire_is_the_default_and_asks_exactly_this_set():
    """Pinned explicitly rather than derived from the `advanced` flags, so
    flipping a flag has to be a deliberate edit here too — the whole point of
    TMDEV-74 is that this list stays short."""
    for step_key, expected in MINIMAL_BY_STEP.items():
        assert [f.key for f in fields_for_step(step_key)] == expected, step_key


def test_api_key_questions_are_contiguous():
    """The unconditional credential prompts run back-to-back and lead the
    section (TMDEV-79) — easy for a later edit to undo by dropping a new field
    in between.

    POSTFORME_API_KEY is the one exception (TMDEV-83) and is not a violation:
    it is gated on PUBLISHING_ENABLED, so it *must* come after that answer.
    It still sits immediately after its gate rather than drifting elsewhere.
    """
    services = next(s for s in SECTIONS if s.key == "services")
    keys = [f.key for f in services.fields]
    kinds = [f.kind for f in services.fields]
    unconditional_secrets = [i for i, f in enumerate(services.fields)
                             if f.kind == "secret" and f.condition is None]
    assert unconditional_secrets == list(range(len(unconditional_secrets))), \
        "unconditional secret fields must lead the section"
    assert [keys[i] for i in unconditional_secrets] == [
        "ELEVENLABS_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "YOUTUBE_TRANSCRIPT_API_KEY",
    ]
    # The gated key follows its gate directly.
    assert keys[keys.index("PUBLISHING_ENABLED") + 1] == "POSTFORME_API_KEY"
    assert kinds[keys.index("POSTFORME_API_KEY")] == "secret"
    # ...and no credential is left stranded in another section.
    for section in SECTIONS:
        if section.key != "services":
            assert not any(f.kind == "secret" for f in section.fields), section.key


def test_full_questionnaire_is_a_superset_of_the_minimal_one():
    for step in STEP_DEFS:
        minimal = [f.key for f in fields_for_step(step.key)]
        full = [f.key for f in fields_for_step(step.key, full=True)]
        assert set(minimal) <= set(full)
        # Order is section-then-field in both; skipping must not reorder.
        assert minimal == [k for k in full if k in set(minimal)]


def test_every_advanced_default_is_one_the_wizard_would_have_accepted():
    """A skipped question seeds its default without ever passing through the
    prompt's validation, so an invalid default would be written silently —
    the one failure mode this feature actually introduces."""
    for field in FIELDS_BY_KEY.values():
        if not field.advanced:
            continue
        if field.validator is not None:
            assert field.validator(field.default) is None, field.key
        if field.kind == "select" and field.choices:
            assert field.default in field.choices, field.key
        if field.kind == "checkbox":
            import json
            assert set(json.loads(field.default)) <= set(field.choices), field.key


def test_no_dynamic_choices_field_is_split_from_its_driver():
    """prompt_step passes cfg.values as all_values while iterating, so a
    dynamic_choices field whose driver was skipped would resolve its choices
    against a stale value. Keeping both halves on the same side of the
    minimal/advanced line is what prevents that."""
    drivers = {
        "elevenlabs_voice_id": "elevenlabs_voices",
    }
    for dependent, driver in drivers.items():
        assert FIELDS_BY_KEY[dependent].dynamic_choices is not None
        assert FIELDS_BY_KEY[dependent].advanced == FIELDS_BY_KEY[driver].advanced, dependent


def test_conditional_fields_are_listed_when_no_values_are_supplied():
    """--steps has no running config; passing values=None must show every
    conditional field rather than silently dropping it."""
    assert "POSTFORME_API_KEY" in [f.key for f in fields_for_step("install_config")]
    assert "POSTFORME_API_KEY" not in [
        f.key for f in fields_for_step("install_config", values={"PUBLISHING_ENABLED": "false"})]


def test_every_field_has_help_text():
    """The redesigned prompt renders each field's help as the panel above it
    (TMDEV-79). A field without help degrades to a bare progress line with no
    explanation — the exact thing the redesign set out to remove."""
    missing = [k for k, f in FIELDS_BY_KEY.items() if not f.help.strip()]
    assert missing == [], f"fields with no help text: {missing}"


def test_help_text_carries_no_ticket_ids():
    """Help is now rendered in a panel the user reads while answering; a
    tracker reference means nothing to them. Rationale belongs in a `#`
    comment beside the field instead."""
    import re
    leaky = [k for k, f in FIELDS_BY_KEY.items() if re.search(r"\b(TMDEV|VQA)-\d+", f.help)]
    assert leaky == [], f"ticket IDs in user-facing help: {leaky}"


def test_only_pipeline_critical_settings_are_required():
    """Pinned as an explicit list: `required` decides whether someone can
    finish onboarding at all, so widening it must be a deliberate edit here
    too (TMDEV-80)."""
    required = sorted(k for k, f in FIELDS_BY_KEY.items() if f.required)
    assert required == ["ELEVENLABS_API_KEY", "OPENAI_API_KEY"]


def test_the_optional_keys_stay_optional():
    """Gemini only powers mining and AI review, both off without it (TMDEV-165);
    the transcript key feeds the on-demand Script Profiles. Requiring either
    would block onboarding on an account the user may not have."""
    assert not FIELDS_BY_KEY["GEMINI_API_KEY"].required
    assert not FIELDS_BY_KEY["YOUTUBE_TRANSCRIPT_API_KEY"].required


def test_the_openai_help_says_it_draws_every_scene_image():
    """OpenAI is the only image provider, so the old "optional — leave it blank"
    advice would now produce an install that cannot draw a single scene."""
    help_text = FIELDS_BY_KEY["OPENAI_API_KEY"].help
    assert help_text.startswith("Required.")
    assert "every scene image" in help_text and "Illustrated" in help_text
    assert "leave it blank" not in help_text
    # The one failure onboarding cannot pre-flight: access is per project.
    assert "per project" in help_text


def test_the_gemini_help_says_what_is_off_without_it():
    help_text = FIELDS_BY_KEY["GEMINI_API_KEY"].help
    assert help_text.startswith("Optional.")
    assert "mining" in help_text and "review" in help_text
    assert "image" not in help_text.lower()


def test_every_required_field_is_in_the_minimal_questionnaire():
    """A required field marked `advanced` would be unreachable without
    --full-questionnaire, so the wizard would demand something it never asks."""
    for key, f in FIELDS_BY_KEY.items():
        if f.required:
            assert not f.advanced, key
            assert f.condition is None, key


# ── TMDEV-83: publishing ────────────────────────────────────────────────────

def test_the_postforme_key_is_gated_on_enabling_publishing():
    """An install that will never publish is never asked for a credential it
    has no use for.

    This works only because prompt_step evaluates conditions per field as it
    reaches them. Filtering the whole step up front — which it used to do —
    would read the pre-filled "false" and drop this question before the answer
    existed, so enabling publishing would silently never prompt for a key.
    test_prompt.py covers that end of it.
    """
    field = FIELDS_BY_KEY["POSTFORME_API_KEY"]
    assert field.condition is not None
    assert field.condition({"PUBLISHING_ENABLED": "true"}) is True
    assert field.condition({"PUBLISHING_ENABLED": "false"}) is False
    assert field.condition({}) is False


def test_the_publishing_fields_are_asked_in_the_minimal_questionnaire():
    """Marking either `advanced` would seed publishing_enabled from the default
    and never ask for the key, which is the same silent outcome as the
    condition trap above."""
    assert not FIELDS_BY_KEY["PUBLISHING_ENABLED"].advanced
    assert not FIELDS_BY_KEY["POSTFORME_API_KEY"].advanced
    asked = [f.key for f in fields_for_step("install_config")]
    assert "POSTFORME_API_KEY" in asked
    assert "PUBLISHING_ENABLED" in asked


def test_publishing_does_not_widen_the_required_set():
    """A publish is never needed to produce a video, and requiring a postforme
    account would block onboarding on a service the user may not hold."""
    assert not FIELDS_BY_KEY["POSTFORME_API_KEY"].required
    assert not FIELDS_BY_KEY["PUBLISHING_ENABLED"].required


def test_the_toggle_is_asked_before_the_key_it_gates():
    """Order is load-bearing, not cosmetic: the condition reads an answer given
    earlier in the same step, so the gate has to come first."""
    asked = [f.key for f in fields_for_step("install_config")]
    assert asked.index("PUBLISHING_ENABLED") < asked.index("POSTFORME_API_KEY")


# ── TMDEV-172: pre-loaded voices ────────────────────────────────────────────

def test_the_skipped_voice_questions_seed_the_pre_loaded_roster():
    """The voice fields are skipped by default, so their defaults are what a
    fresh install gets — written without passing the prompt's checks. The
    roster must survive _parse_voices (anything invalid drops the whole list
    to []) and the default voice must be on it, or apply_pipeline_settings
    quietly picks another."""
    import json
    from onboard.config import _parse_voices
    from tubematic_core import voice_models
    roster = _parse_voices(FIELDS_BY_KEY["elevenlabs_voices"].default)
    assert roster == list(voice_models.DEFAULT_VOICES)
    assert json.loads(FIELDS_BY_KEY["elevenlabs_voices"].default) == roster
    default = FIELDS_BY_KEY["elevenlabs_voice_id"].default
    assert default == voice_models.DEFAULT_VOICE_ID
    assert default in FIELDS_BY_KEY["elevenlabs_voice_id"].dynamic_choices(
        {"elevenlabs_voices": FIELDS_BY_KEY["elevenlabs_voices"].default})
