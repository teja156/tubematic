"""Unit tests for onboard/prompt.py's pure logic — the parts that don't
require a real terminal. Actual questionary interaction (ask_field's
.ask() calls) is exercised via a real pty in manual verification, not here;
mocking prompt_toolkit's I/O for a full interactive test is more machinery
than this module's small amount of logic warrants."""
import json

import pytest

from onboard.config import OnboardConfig, agent_workspace_exists
from onboard.prompt import _adapt_validator, prompt_fields, prompt_step
from onboard.steps import STEP_BY_KEY


def test_adapt_validator_none_passes_through():
    assert _adapt_validator(None) is None


def test_adapt_validator_wraps_valid_and_invalid():
    fn = lambda v: None if v == "ok" else "bad value"
    validate = _adapt_validator(fn)
    assert validate("ok") is True
    assert validate("no") == "bad value"


def test_prompt_step_skips_entirely_for_prompt_free_steps(monkeypatch):
    calls = []
    monkeypatch.setattr("onboard.prompt.ask_field", lambda *a, **k: calls.append(a) or "x")
    cfg = OnboardConfig(values={})
    prompt_step(STEP_BY_KEY["directories"], cfg)
    assert calls == []


def test_before_field_runs_only_for_the_fields_actually_asked(monkeypatch):
    """--install-agent previews an existing workspace through this hook; it
    must never fire for a question whose condition skipped it."""
    from onboard.config import Field
    monkeypatch.setattr("onboard.prompt.ask_field", lambda f, current, values, opts=None: current)
    seen = []
    asked = Field("A", "a", help="h")
    skipped = Field("B", "b", help="h", condition=lambda v: False)
    prompt_fields([asked, skipped], OnboardConfig(values={}),
                  before_field=lambda f: seen.append(f.key))
    assert seen == ["A"]


def test_prompt_step_writes_answers_into_cfg_values(monkeypatch):
    monkeypatch.setattr("onboard.prompt.ask_field", lambda f, current, values, opts=None: f"answer-{f.key}")
    cfg = OnboardConfig(values={})
    prompt_step(STEP_BY_KEY["cron"], cfg)
    assert cfg.values["POLL_INTERVAL_MINS"] == "answer-POLL_INTERVAL_MINS"


# ── Minimal vs full questionnaire (TMDEV-74) ───────────────────────────────

def _asked(step_key, monkeypatch, *, full=False, values=None):
    """Every field key prompt_step would actually ask for."""
    asked = []
    monkeypatch.setattr("onboard.prompt.ask_field",
                        lambda f, current, all_values, opts=None: asked.append(f.key) or current)
    cfg = OnboardConfig(values=dict(values or {}))
    prompt_step(STEP_BY_KEY[step_key], cfg, full=full)
    return asked, cfg


def test_prompt_step_skips_advanced_fields_by_default(monkeypatch):
    asked, _ = _asked("pipeline_settings", monkeypatch)
    assert asked == ["elevenlabs_voices", "elevenlabs_voice_id", "image_model"]


def test_prompt_step_asks_advanced_fields_under_full(monkeypatch):
    asked, _ = _asked("pipeline_settings", monkeypatch, full=True)
    assert "render_timeout_mins" in asked
    assert "ai_review_max_loops" in asked
    # Advanced, so absent from the minimal questionnaire asserted above and
    # present here — the pair is what pins the flag rather than the field.
    assert "log_retention_days" in asked
    assert "retention_days" in asked
    assert "auto_pilot_enabled" in asked
    assert len(asked) == 15


def test_a_skipped_advanced_field_keeps_its_prefilled_value(monkeypatch):
    """The whole reason no apply-side plumbing was needed: cfg.values already
    holds the answer, so not asking is the same as answering with it."""
    asked, cfg = _asked("pipeline_settings", monkeypatch,
                        values={"render_timeout_mins": "55"})
    assert "render_timeout_mins" not in asked
    assert cfg.values["render_timeout_mins"] == "55"


def test_the_wipe_question_is_asked_only_for_an_existing_workspace(monkeypatch, tmp_path):
    from onboard.agent_install import RUN_PATH_FIELD, WIPE_FIELD
    existing = tmp_path / "ws"
    existing.mkdir()
    for path, expected in ((tmp_path / "gone", ["AGENT_RUN_PATH"]),
                           (existing, ["AGENT_RUN_PATH", "WIPE_AGENT_WORKSPACE"])):
        asked = []
        monkeypatch.setattr("onboard.prompt.ask_field",
                            lambda f, current, values, opts=None: asked.append(f.key) or current)
        prompt_fields([RUN_PATH_FIELD, WIPE_FIELD],
                      OnboardConfig(values={"AGENT_RUN_PATH": str(path)}))
        assert asked == expected


def test_agent_workspace_exists_rejects_a_blank_path(tmp_path):
    """Path("").expanduser() is Path("."), which is always a directory — without
    the guard the wipe question would show on every fresh install."""
    assert agent_workspace_exists({}) is False
    assert agent_workspace_exists({"AGENT_RUN_PATH": ""}) is False
    assert agent_workspace_exists({"AGENT_RUN_PATH": "   "}) is False
    assert agent_workspace_exists({"AGENT_RUN_PATH": str(tmp_path)}) is True
    assert agent_workspace_exists({"AGENT_RUN_PATH": str(tmp_path / "nope")}) is False


# ── Required settings (TMDEV-80) ───────────────────────────────────────────

from onboard.config import FIELDS_BY_KEY          # noqa: E402
from onboard.prompt import PromptOptions, ask_field, _skipped_check  # noqa: E402
from onboard import api_keys                       # noqa: E402


def _secret_answers(monkeypatch, field, answers, opts):
    """Drive ask_field's secret branch with a scripted sequence of pastes."""
    seq = list(answers)
    monkeypatch.setattr("onboard.prompt.questionary.password",
                        lambda *a, **k: type("P", (), {"ask": lambda _s: seq.pop(0)})())
    monkeypatch.setattr("onboard.prompt.rail", lambda *a, **k: None)
    return ask_field(field, "", {}, opts), seq


def test_a_required_key_is_re_asked_until_supplied(monkeypatch):
    """Blank never reaches the network (resolve_secret returns it untouched),
    so blankness has to be caught by the outer required loop."""
    field = FIELDS_BY_KEY["OPENAI_API_KEY"]
    monkeypatch.setattr(field, "key_check", lambda k: api_keys.KeyCheck(api_keys.VALID))
    val, left = _secret_answers(monkeypatch, field, ["", "", "sk-real"],
                                PromptOptions(verify_keys=False))
    assert val == "sk-real"
    assert left == []


def test_allow_skipping_accepts_a_blank_required_key(monkeypatch):
    field = FIELDS_BY_KEY["OPENAI_API_KEY"]
    val, _ = _secret_answers(monkeypatch, field, [""],
                             PromptOptions(allow_skipping=True, verify_keys=False))
    assert val == ""


def test_an_optional_key_still_accepts_blank(monkeypatch):
    """GEMINI_API_KEY is deliberately not required — mining and AI review are
    simply off without it."""
    field = FIELDS_BY_KEY["GEMINI_API_KEY"]
    assert not field.required
    val, _ = _secret_answers(monkeypatch, field, [""], PromptOptions(verify_keys=False))
    assert val == ""


def test_disable_verification_never_calls_the_provider(monkeypatch):
    called = []
    field = FIELDS_BY_KEY["ELEVENLABS_API_KEY"]
    monkeypatch.setattr(field, "key_check", lambda k: called.append(k) or api_keys.KeyCheck(api_keys.VALID))
    val, _ = _secret_answers(monkeypatch, field, ["sk-whatever"],
                             PromptOptions(verify_keys=False))
    assert val == "sk-whatever"
    assert called == [], "provider must not be probed under --disable-verification"


def test_disable_verification_still_rejects_a_malformed_paste(monkeypatch):
    """The local guard protects what gets *stored*; it is not a network check,
    so --disable-verification must not switch it off."""
    field = FIELDS_BY_KEY["ELEVENLABS_API_KEY"]
    monkeypatch.setattr(field, "key_check", lambda k: api_keys.KeyCheck(api_keys.VALID))
    val, left = _secret_answers(monkeypatch, field, ["bad\tkey", "sk-clean"],
                                PromptOptions(verify_keys=False))
    assert val == "sk-clean"
    assert left == []


def test_skipped_check_reports_unknown_not_valid():
    """UNKNOWN, so nothing downstream can mistake an unchecked key for a
    verified one."""
    result = _skipped_check("anything")
    assert result.status == api_keys.UNKNOWN
    assert "disable-verification" in result.detail


def _drive_voices(monkeypatch, answers, opts, current="[]", models=None):
    """answers feed the text prompts (name, ID, ...); models feed the per-voice
    model select, and the default it was offered is recorded — an unset
    models list answers with whatever default the prompt offered."""
    seq = list(answers)
    model_seq = list(models or [])
    offered = []
    monkeypatch.setattr("onboard.prompt.questionary.text",
                        lambda *a, **k: type("P", (), {"ask": lambda _s: seq.pop(0)})())

    def _select(*a, **k):
        offered.append(k["default"])
        return type("P", (), {"ask": lambda _s: model_seq.pop(0) if model_seq
                              else k["default"]})()
    monkeypatch.setattr("onboard.prompt.questionary.select", _select)
    monkeypatch.setattr("onboard.prompt.rail", lambda *a, **k: None)
    val = ask_field(FIELDS_BY_KEY["elevenlabs_voices"], current, {}, opts)
    _drive_voices.offered = offered
    return val, seq


def test_voice_roster_is_re_asked_until_one_is_entered(monkeypatch):
    """An empty roster also forces elevenlabs_voice_id blank, and generate_voice
    then fails on the first video anyone tries to voice."""
    val, left = _drive_voices(monkeypatch, ["", "Rachel", "21m00Tcm", ""], PromptOptions())
    assert json.loads(val) == [{"name": "Rachel", "voice_id": "21m00Tcm",
                                "model_id": "eleven_multilingual_v2"}]
    assert left == []


def test_each_voice_is_asked_for_its_model_defaulting_to_the_previous_one(monkeypatch):
    """The model follows the voice (TMDEV-121). A roster on one model is a
    string of Enters: the second voice is offered the first one's model."""
    val, _ = _drive_voices(monkeypatch, ["A", "a", "B", "b", ""], PromptOptions(),
                           models=["eleven_v3"])
    assert [v["model_id"] for v in json.loads(val)] == ["eleven_v3", "eleven_v3"]
    assert _drive_voices.offered == ["eleven_multilingual_v2", "eleven_v3"]


def test_a_re_entered_voice_is_offered_the_model_it_already_had(monkeypatch):
    existing = json.dumps([{"name": "A", "voice_id": "a", "model_id": "eleven_flash_v2"}])
    _drive_voices(monkeypatch, ["A", "a", ""], PromptOptions(), current=existing)
    assert _drive_voices.offered == ["eleven_flash_v2"]


def test_allow_skipping_accepts_an_empty_roster(monkeypatch):
    val, _ = _drive_voices(monkeypatch, [""], PromptOptions(allow_skipping=True))
    assert val == "[]"


def test_a_blank_first_answer_still_keeps_an_existing_roster(monkeypatch):
    """Required must not mean "retype the roster on every re-run" — an existing
    list satisfies it."""
    existing = json.dumps([{"name": "Rachel", "voice_id": "21m00Tcm",
                            "model_id": "eleven_multilingual_v2"}])
    val, _ = _drive_voices(monkeypatch, [""], PromptOptions(), current=existing)
    assert val == existing


# ── Every kind reaches a prompt (regression: TMDEV-80) ─────────────────────
#
# Extracting a helper out of ask_field once stranded the `textarea` and
# `text`/`int` branches inside it as dead code after a `return`. ask_field then
# fell off the end and returned None for those kinds, which surfaced as
# "expected str, bytes or os.PathLike object, not NoneType" in apply_install_config
# — several steps after the prompt that actually caused it. Nothing caught it:
# the prompt tests monkeypatch ask_field wholesale, and the unit tests below
# only covered `secret` and `voices`. These walk every kind through the real
# ask_field so a missing branch fails here instead.

def _stub_questionary(monkeypatch, answer):
    """Every questionary constructor returns a prompt yielding `answer`."""
    made = []

    def factory(*a, **k):
        made.append(k)
        return type("P", (), {"ask": lambda _s: answer})()

    for name in ("text", "password", "select", "checkbox", "autocomplete"):
        monkeypatch.setattr(f"onboard.prompt.questionary.{name}", factory)
    monkeypatch.setattr("onboard.prompt.rail", lambda *a, **k: None)
    return made


def _install_agent_fields() -> dict:
    """--install-agent's questions, which live outside FIELDS_BY_KEY. The models
    field gets a probe that always passes, so nothing runs a real agent."""
    from onboard import agent_install
    probe = lambda model: api_keys.KeyCheck(api_keys.VALID)
    fields = (agent_install.SCOPE_FIELD, agent_install.RUN_PATH_FIELD, agent_install.WIPE_FIELD,
              agent_install.models_field(agent_install.ADAPTERS["claude"], [], probe))
    return {f.key: f for f in fields}


@pytest.mark.parametrize("key,answer,expected", [
    ("AGENT_RUN_PATH", "/tmp/ws", "/tmp/ws"),          # text
    ("MCP_PORT", "4200", "4200"),                      # int
    ("POLL_INTERVAL_MINS", "15", "15"),                # int
    ("INSTALL_SCOPE", "project", "project"),           # select
])
def test_every_scalar_kind_returns_the_answer(monkeypatch, key, answer, expected):
    _stub_questionary(monkeypatch, answer)
    field = {**FIELDS_BY_KEY, **_install_agent_fields()}[key]
    assert ask_field(field, field.default, {}, PromptOptions()) == expected


def test_no_kind_falls_through_to_none(monkeypatch):
    """The actual failure shape: a kind with no branch returns None silently.
    Runs the REAL ask_field over every field, --install-agent's included."""
    for key, field in {**FIELDS_BY_KEY, **_install_agent_fields()}.items():
        if field.kind in ("voices", "checkbox"):
            continue  # repeat-until-blank / list kinds, covered separately
        if field.kind == "models":
            # Repeat-until-blank: one entry, then Enter to finish.
            seq = ["opus", ""]
            factory = lambda *a, **k: type("P", (), {"ask": lambda _s: seq.pop(0)})()
            monkeypatch.setattr("onboard.prompt.questionary.autocomplete", factory)
            monkeypatch.setattr("onboard.prompt.questionary.text", factory)
            monkeypatch.setattr("onboard.prompt.rail", lambda *a, **k: None)
        else:
            _stub_questionary(monkeypatch, "x")
        # verify_keys=False: the secret fields would otherwise probe their real
        # providers over the network from a unit test, and the models field its
        # agent CLI.
        result = ask_field(field, field.default, {"elevenlabs_voices": "[]"},
                           PromptOptions(verify_keys=False))
        assert result is not None, f"{key} ({field.kind}) fell through to None"


def test_checkbox_returns_json_and_does_not_clobber_the_options(monkeypatch):
    """The checkbox branch used to bind its choice list to `opts`, the same
    name as the PromptOptions parameter."""
    monkeypatch.setattr("onboard.prompt.questionary.checkbox",
                        lambda *a, **k: type("P", (), {"ask": lambda _s: ["Lobsters"]})())
    monkeypatch.setattr("onboard.prompt.rail", lambda *a, **k: None)
    field = FIELDS_BY_KEY["trending_sources"]
    assert json.loads(ask_field(field, field.default, {}, PromptOptions())) == ["Lobsters"]


# ── Same-step conditions (TMDEV-83) ─────────────────────────────────────────
#
# fields_for_step used to be evaluated ONCE, before prompt_step asked anything,
# so a field gated on an answer given in the SAME step was filtered out before
# that answer existed. Conditions are now evaluated as each field is reached,
# which is what makes "ask for the key only if publishing was enabled" work.


def _record_answers(monkeypatch, answers: dict):
    """Drive prompt_step with scripted answers; return the keys it asked."""
    asked = []

    def fake_ask(f, current, values, opts=None):
        asked.append(f.key)
        return answers.get(f.key, current)

    monkeypatch.setattr("onboard.prompt.ask_field", fake_ask)
    return asked


def test_the_postforme_key_is_asked_only_after_enabling_publishing(monkeypatch):
    asked = _record_answers(monkeypatch, {"PUBLISHING_ENABLED": "true"})
    cfg = OnboardConfig(values={"PUBLISHING_ENABLED": "false"})
    prompt_step(STEP_BY_KEY["install_config"], cfg)

    assert "POSTFORME_API_KEY" in asked
    # ...and only after the toggle, never before it.
    assert asked.index("PUBLISHING_ENABLED") < asked.index("POSTFORME_API_KEY")


def test_the_postforme_key_is_not_asked_when_publishing_stays_disabled(monkeypatch):
    asked = _record_answers(monkeypatch, {"PUBLISHING_ENABLED": "false"})
    cfg = OnboardConfig(values={"PUBLISHING_ENABLED": "false"})
    prompt_step(STEP_BY_KEY["install_config"], cfg)

    assert "PUBLISHING_ENABLED" in asked
    assert "POSTFORME_API_KEY" not in asked


def test_a_condition_reads_the_answer_given_in_this_step_not_the_prefill(monkeypatch):
    """The whole point. The pre-filled value says false; the answer says true.
    Reading the pre-fill would silently never ask for the key."""
    asked = _record_answers(monkeypatch, {"PUBLISHING_ENABLED": "true"})
    cfg = OnboardConfig(values={"PUBLISHING_ENABLED": "false"})
    prompt_step(STEP_BY_KEY["install_config"], cfg)
    assert "POSTFORME_API_KEY" in asked


def test_turning_publishing_off_on_a_re_run_stops_asking_for_the_key(monkeypatch):
    """A stored "true" from a previous install must not pin the question open."""
    asked = _record_answers(monkeypatch, {"PUBLISHING_ENABLED": "false"})
    cfg = OnboardConfig(values={"PUBLISHING_ENABLED": "true",
                                "POSTFORME_API_KEY": "pfm-old"})
    prompt_step(STEP_BY_KEY["install_config"], cfg)
    assert "POSTFORME_API_KEY" not in asked


def test_the_wipe_condition_reads_the_workspace_answer_not_the_prefill(monkeypatch, tmp_path):
    """--install-agent asks the workspace and the wipe question in one pass, so
    the condition must see the path just typed — the pre-fill points at a
    directory that does not exist."""
    from onboard.agent_install import RUN_PATH_FIELD, WIPE_FIELD
    workspace = tmp_path / "ws"
    workspace.mkdir()
    asked = _record_answers(monkeypatch, {"AGENT_RUN_PATH": str(workspace)})
    prompt_fields([RUN_PATH_FIELD, WIPE_FIELD],
                  OnboardConfig(values={"AGENT_RUN_PATH": str(tmp_path / "missing")}))
    assert "WIPE_AGENT_WORKSPACE" in asked


def test_the_end_of_step_summary_omits_a_question_that_was_never_asked(monkeypatch):
    """It prints to scrollback — listing a skipped field would claim an answer
    the user never gave."""
    summarised = []
    monkeypatch.setattr("onboard.prompt.render_step_summary",
                        lambda fields, values: summarised.extend(f.key for f in fields))
    _record_answers(monkeypatch, {"PUBLISHING_ENABLED": "false"})
    prompt_step(STEP_BY_KEY["install_config"],
                OnboardConfig(values={"PUBLISHING_ENABLED": "false"}))
    assert "PUBLISHING_ENABLED" in summarised
    assert "POSTFORME_API_KEY" not in summarised


def test_the_progress_count_never_exceeds_the_questions_actually_asked(monkeypatch):
    """A skipped field must not leave a gap like "5/9" on a step that asks 8."""
    frames = []
    monkeypatch.setattr("onboard.prompt.open_field_frame",
                        lambda f, number, total: frames.append((number, total)))
    monkeypatch.setattr("onboard.prompt.close_field_frame", lambda: None)
    _record_answers(monkeypatch, {"PUBLISHING_ENABLED": "false"})
    prompt_step(STEP_BY_KEY["install_config"],
                OnboardConfig(values={"PUBLISHING_ENABLED": "false"}))

    numbers = [n for n, _ in frames]
    assert numbers == list(range(1, len(frames) + 1))
    assert all(n <= total for n, total in frames)
    assert frames[-1][0] == frames[-1][1]


# ── An agent's model list (--install-agent) ─────────────────────────────────
#
# Every entry is probed before it is kept. The probe is stubbed throughout —
# a real one runs the agent CLI, and for a valid model that is a billed call.

def _drive_models(monkeypatch, answers, *, current="[]", probe=None, choices=True,
                  opts=None):
    """ask_field on the models field with scripted entries. Returns
    (result, kinds of prompt used, models probed)."""
    import contextlib
    import dataclasses
    from onboard import agent_install
    seq, used, probed = list(answers), [], []

    def make(kind):
        def factory(*a, **k):
            used.append(kind)
            return type("P", (), {"ask": lambda _s: seq.pop(0)})()
        return factory

    monkeypatch.setattr("onboard.prompt.questionary.autocomplete", make("autocomplete"))
    monkeypatch.setattr("onboard.prompt.questionary.text", make("text"))
    monkeypatch.setattr("onboard.prompt.rail", lambda *a, **k: None)
    monkeypatch.setattr("onboard.prompt.console.status",
                        lambda *a, **k: contextlib.nullcontext())

    def recording(model):
        probed.append(model)
        return (probe or (lambda m: api_keys.KeyCheck(api_keys.VALID)))(model)

    field = agent_install.models_field(agent_install.ADAPTERS["claude"], [], recording)
    if not choices:
        field = dataclasses.replace(field, dynamic_choices=None)
    result = ask_field(field, current, {}, opts or PromptOptions())
    return result, used, probed


def test_models_are_kept_in_order_first_is_the_default(monkeypatch):
    result, _, _ = _drive_models(monkeypatch, ["sonnet", "claude-opus-5", ""])
    assert json.loads(result) == ["sonnet", "claude-opus-5"]


def test_a_rejected_model_is_dropped_and_the_prompt_continues(monkeypatch):
    rejecting = lambda m: api_keys.KeyCheck(
        api_keys.INVALID if m == "sonnett" else api_keys.VALID, "nope")
    result, _, probed = _drive_models(monkeypatch, ["sonnett", "sonnet", ""], probe=rejecting)
    assert json.loads(result) == ["sonnet"]
    assert probed == ["sonnett", "sonnet"]


def test_an_unverifiable_model_is_kept(monkeypatch):
    """Only a positive rejection drops a model — the resolve_secret rule."""
    unknown = lambda m: api_keys.KeyCheck(api_keys.UNKNOWN, "timed out")
    result, _, _ = _drive_models(monkeypatch, ["opus", ""], probe=unknown)
    assert json.loads(result) == ["opus"]


def test_a_malformed_name_is_refused_before_any_probe(monkeypatch):
    result, _, probed = _drive_models(monkeypatch, ["two words", "--model", "opus", ""])
    assert json.loads(result) == ["opus"]
    assert probed == ["opus"]


def test_a_duplicate_is_ignored_not_probed_twice(monkeypatch):
    result, _, probed = _drive_models(monkeypatch, ["opus", "opus", ""])
    assert json.loads(result) == ["opus"]
    assert probed == ["opus"]


def test_at_least_one_model_is_required(monkeypatch):
    result, _, _ = _drive_models(monkeypatch, ["", "opus", ""])
    assert json.loads(result) == ["opus"]


def test_allow_skipping_accepts_no_models(monkeypatch):
    result, _, _ = _drive_models(monkeypatch, [""], opts=PromptOptions(allow_skipping=True))
    assert result == "[]"


def test_keeping_the_stored_list_re_checks_it(monkeypatch):
    """Validation is point-in-time; a re-run after a CLI upgrade is how a model
    the CLI has since retired gets dropped instead of carried forward."""
    retired = lambda m: api_keys.KeyCheck(
        api_keys.INVALID if m == "claude-old-1" else api_keys.VALID, "retired")
    result, _, probed = _drive_models(monkeypatch, [""], probe=retired,
                                      current=json.dumps(["opus", "claude-old-1"]))
    assert json.loads(result) == ["opus"]
    assert probed == ["opus", "claude-old-1"]


def test_disable_verification_never_probes(monkeypatch):
    result, _, probed = _drive_models(monkeypatch, ["opus", ""],
                                      opts=PromptOptions(verify_keys=False))
    assert json.loads(result) == ["opus"]
    assert probed == []


def test_suggestions_use_autocomplete_and_none_fall_back_to_free_text(monkeypatch):
    """Suggestions help; they never gate what can be typed."""
    _, used, _ = _drive_models(monkeypatch, ["opus", ""])
    assert set(used) == {"autocomplete"}
    _, used, _ = _drive_models(monkeypatch, ["opus", ""], choices=False)
    assert set(used) == {"text"}
