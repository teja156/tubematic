"""The script formula is picked before the script (TMDEV-213):
choose_script_formula, get_video's formula_routing, the rotation rule, a
person's own choice, and what gives a pick back.

What matters most here:

  * The pick is what the script must follow, so every condition
    choose_script_formula checks (the status, the style decided, no pick yet,
    the person's choice) must also hold in the UPDATE itself, or a write racing
    it lands on a video that moved on.
  * A person's choice wins: it becomes the pick whatever the agent prefers,
    is never replaced by the agent, and survives a return to the topic.
  * Rotation is enforced here and not left to the skill: a formula the domain
    just used is refused unless the call says why nothing else fits.
  * An experimental formula is off for Auto until the setting allows it.

Run from repo root: pytest mcp/tests/
"""
from datetime import datetime, timezone

import pytest

import server
from sample_angle import ANGLE
from tubematic_core import formulas as tf

REASON = "A request moves through fixed stages, each handing on to the next."


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, created_at) VALUES ('dom', 'A domain', ?)",
                    (_now(),))
    return tmp_path / "test.db"


def _video(vid="vid_1", status="TOPIC_APPROVED", style="system_flow", style_pick="",
           choice="", pick="", formula_id="", hook_type="", project="dom",
           created="2026-06-01T00:00:00Z"):
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, visual_style, style_pick, "
            "formula_choice, formula_pick, formula_id, hook_type, created_at, updated_at) "
            "VALUES (?, ?, 'a topic', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, project, status, style, style_pick, choice, pick, formula_id, hook_type,
             created, _now()))
    return vid


def _row(vid="vid_1"):
    with server._conn() as con:
        return dict(con.execute(
            "SELECT status, formula_choice, formula_pick, formula_runner_up, formula_reason "
            "FROM videos WHERE id = ?", (vid,)).fetchone())


def _allow_experimental(on=True):
    with server._conn() as con:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES "
                    "('auto_experimental_formulas', ?)", ("true" if on else "false",))


# ── the pick ─────────────────────────────────────────────────────────────────

def test_autos_pick_is_recorded_with_its_runner_up_and_reason(db):
    _video()
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON,
                                       runner_up="paradox-mechanism-reframe")
    assert out["formula_pick"] == "follow-the-flow" and out["chosen_by"] == "auto"
    assert out["label"] == "Follow the Flow" and out["words"] == [90, 260]
    assert out["reference"] == "formulas/follow-the-flow.md"
    assert _row() == {"status": "TOPIC_APPROVED", "formula_choice": "",
                      "formula_pick": "follow-the-flow",
                      "formula_runner_up": "paradox-mechanism-reframe", "formula_reason": REASON}
    routing = server.get_video("vid_1")["formula_routing"]
    assert routing["decided"] and routing["pick"] == "follow-the-flow"
    assert routing["runner_up"] == "paradox-mechanism-reframe" and routing["reason"] == REASON


def test_a_pick_needs_no_runner_up(db):
    _video()
    assert "error" not in server.choose_script_formula("vid_1", "scene-story", REASON)
    assert _row()["formula_runner_up"] == ""


def test_the_reason_is_stored_on_one_line(db):
    _video()
    server.choose_script_formula("vid_1", "scene-story", "  One person,\n one   moment. ")
    assert _row()["formula_reason"] == "One person, one moment."


@pytest.mark.parametrize("kw, message", [
    ({"formula": "no-such-formula"}, "Invalid formula"),
    ({"runner_up": "no-such-formula"}, "Invalid runner_up"),
    ({"runner_up": "follow-the-flow"}, "different formula"),
    ({"reason": "   "}, "reason is required"),
    ({"reason": "x" * 301}, "reason is 301 characters"),
    ({"repeat_reason": "x" * 301}, "repeat_reason is 301 characters"),
])
def test_a_malformed_pick_is_refused_and_nothing_is_written(db, kw, message):
    _video()
    args = {"formula": "follow-the-flow", "reason": REASON, **kw}
    assert message in server.choose_script_formula("vid_1", **args)["error"]
    assert _row()["formula_pick"] == ""


def test_an_unknown_or_archived_video_is_refused(db):
    assert "not found" in server.choose_script_formula("nope", "scene-story", REASON)["error"]
    _video()
    with server._conn() as con:
        con.execute("UPDATE videos SET archived_at = ? WHERE id = 'vid_1'", (_now(),))
    assert "error" in server.choose_script_formula("vid_1", "scene-story", REASON)
    assert _row()["formula_pick"] == ""


def test_the_style_is_decided_first(db):
    _video(style="auto")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert "Pick the style first" in out["error"] and _row()["formula_pick"] == ""


def test_autos_mixed_scenes_counts_as_a_decided_style(db):
    _video(style="auto", style_pick="scenes")
    assert "error" not in server.choose_script_formula("vid_1", "follow-the-flow", REASON)


def test_the_pick_is_made_once(db):
    _video(pick="scene-story")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert "made once" in out["error"] and _row()["formula_pick"] == "scene-story"


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "SCRIPT_READY", "VOICE_READY",
                                    "VIDEO_READY", "PUBLISHED"])
def test_a_pick_is_refused_outside_its_two_statuses(db, status):
    _video(status=status)
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert "TOPIC_APPROVED" in out["error"] and _row()["formula_pick"] == ""


def test_a_video_that_moved_on_after_the_read_is_not_written(db, monkeypatch):
    _video()
    real = server._person_formula_choice

    def and_it_is_approved_meanwhile(row):
        # Runs between the tool's read and its write transaction: another
        # writer moves the video on. The UPDATE's WHERE names the status the
        # tool read, so it finds nothing to write.
        with server._conn() as con:
            con.execute("UPDATE videos SET status = 'SCRIPT_READY' WHERE id = 'vid_1'")
        return real(row)

    monkeypatch.setattr(server, "_person_formula_choice", and_it_is_approved_meanwhile)
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert "changed while the call was in flight" in out["error"]
    assert _row()["formula_pick"] == ""


def test_nothing_can_change_the_row_between_the_check_and_the_write(db, monkeypatch):
    import sqlite3
    _video()
    real = server._recent_domain_formulas
    seen = {"locked": False}

    def and_a_person_tries_to_choose(project_id, video_id):
        # Runs inside the tool's write transaction. A second writer cannot
        # get in, so the setting and the history the tool just read still
        # hold when it writes.
        other = sqlite3.connect(server.DB_FILE, timeout=0.1)
        try:
            other.execute("UPDATE videos SET formula_choice = 'scene-story' WHERE id = 'vid_1'")
            other.commit()
        except sqlite3.OperationalError:
            seen["locked"] = True
        finally:
            other.close()
        return real(project_id, video_id)

    monkeypatch.setattr(server, "_recent_domain_formulas", and_a_person_tries_to_choose)
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert seen["locked"] and out["formula_pick"] == "follow-the-flow"


# ── experimental formulas ────────────────────────────────────────────────────

def test_an_experimental_formula_is_refused_while_the_setting_is_off(db):
    _video()
    out = server.choose_script_formula("vid_1", "stake-first-list", REASON)
    assert "auto_experimental_formulas" in out["error"] and _row()["formula_pick"] == ""
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON,
                                       runner_up="stake-first-list")
    assert "runner_up" in out["error"] and _row()["formula_pick"] == ""


def test_an_experimental_formula_can_be_picked_once_the_setting_is_on(db):
    _video()
    _allow_experimental()
    out = server.choose_script_formula("vid_1", "stake-first-list", REASON, runner_up="test-case")
    assert out["formula_pick"] == "stake-first-list" and _row()["formula_runner_up"] == "test-case"


def test_the_candidates_show_which_formulas_auto_may_pick(db):
    _video()
    cands = {c["id"]: c for c in server.get_video("vid_1")["formula_routing"]["candidates"]}
    assert list(cands) == list(tf.FORMULAS)
    assert not cands["news-take"]["available"] and cands["scene-story"]["available"]
    _allow_experimental()
    cands = {c["id"]: c for c in server.get_video("vid_1")["formula_routing"]["candidates"]}
    assert cands["news-take"]["available"]


def test_the_candidates_are_marked_for_the_videos_style(db):
    _video(style="terminal_doc")
    cands = {c["id"]: c for c in server.get_video("vid_1")["formula_routing"]["candidates"]}
    assert cands["broken-expectation"]["suits_style"] and not cands["scene-story"]["suits_style"]


def test_a_revision_whose_pick_is_a_persons_choice_gets_no_candidates(db):
    # The tool would refuse a re-pick there, so the list is not sent.
    _video(status="REVISION_REQUESTED", choice="scene-story", pick="scene-story")
    assert server.get_video("vid_1")["formula_routing"]["candidates"] == []


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "SCRIPT_READY", "VOICE_READY", "VIDEO_READY"])
def test_a_video_with_no_pick_that_cannot_pick_now_gets_no_candidates(db, status):
    _video(status=status)
    assert server.get_video("vid_1")["formula_routing"]["candidates"] == []


def test_the_candidates_are_left_out_once_the_pick_cannot_change(db):
    _video(pick="scene-story", status="SCRIPT_READY")
    assert server.get_video("vid_1")["formula_routing"]["candidates"] == []
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = 'vid_1'")
    assert len(server.get_video("vid_1")["formula_routing"]["candidates"]) == len(tf.FORMULAS)


# ── rotation ─────────────────────────────────────────────────────────────────

def _history(db):
    # Newest first by created_at: v_new, v_mid, v_old. Only the two newest count.
    _video("v_old", status="PUBLISHED", formula_id="incident-file", hook_type="number",
           created="2026-01-01T00:00:00Z")
    _video("v_mid", status="PUBLISHED", formula_id="scene-story", hook_type="scene",
           created="2026-02-01T00:00:00Z")
    _video("v_new", status="SCRIPT_READY", pick="myth-break-model", hook_type="",
           created="2026-03-01T00:00:00Z")


def test_recent_is_the_domains_previous_two_videos_newest_first(db):
    _history(db)
    _video()
    routing = server.get_video("vid_1")["formula_routing"]
    # A video with a pick and no script yet counts by its pick.
    assert routing["recent"] == {"formulas": ["myth-break-model", "scene-story"],
                                 "hook_types": ["scene", "number"]}
    cands = {c["id"]: c for c in routing["candidates"]}
    assert {fid for fid, c in cands.items() if c["recent"]} == {"myth-break-model", "scene-story"}


def test_a_formula_the_domain_just_used_is_refused_without_a_repeat_reason(db):
    _history(db)
    _video()
    out = server.choose_script_formula("vid_1", "scene-story", REASON)
    assert "repeat_reason" in out["error"] and _row()["formula_pick"] == ""
    # The third video back is outside the window.
    assert "error" not in server.choose_script_formula("vid_1", "incident-file", REASON)


def test_a_repeat_with_its_reason_is_accepted_and_the_reason_is_kept(db):
    _history(db)
    _video()
    out = server.choose_script_formula("vid_1", "scene-story", REASON,
                                       repeat_reason="The topic is one person in one moment.")
    assert out["formula_pick"] == "scene-story"
    assert _row()["formula_reason"] == (
        f"{REASON} Repeats a recent formula: The topic is one person in one moment.")


def test_another_domains_videos_do_not_count(db):
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, created_at) VALUES ('other', 'Other', ?)",
                    (_now(),))
    _video("v_other", status="PUBLISHED", formula_id="scene-story", project="other")
    _video()
    assert "error" not in server.choose_script_formula("vid_1", "scene-story", REASON)


def test_a_video_with_no_domain_has_no_history(db):
    _video(project=None)
    assert server.get_video("vid_1")["formula_routing"]["recent"] == {"formulas": [],
                                                                     "hook_types": []}
    assert "error" not in server.choose_script_formula("vid_1", "scene-story", REASON)


# ── a person's choice ────────────────────────────────────────────────────────

def test_a_persons_choice_is_the_pick_and_autos_formula_is_the_runner_up(db):
    _video(choice="scene-story")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON,
                                       runner_up="incident-file")
    assert out["formula_pick"] == "scene-story" and out["chosen_by"] == "person"
    assert out["reference"] == "formulas/scene-story.md"
    assert _row() == {"status": "TOPIC_APPROVED", "formula_choice": "scene-story",
                      "formula_pick": "scene-story", "formula_runner_up": "follow-the-flow",
                      "formula_reason": f"Auto would have picked Follow the Flow: {REASON}"}


def test_when_auto_agrees_with_the_person_the_runner_up_is_autos_own(db):
    _video(choice="scene-story")
    server.choose_script_formula("vid_1", "scene-story", REASON, runner_up="incident-file")
    row = _row()
    assert (row["formula_pick"], row["formula_runner_up"], row["formula_reason"]) == \
        ("scene-story", "incident-file", REASON)


def test_a_persons_experimental_choice_holds_while_the_setting_is_off(db):
    _video(choice="stake-first-list")
    out = server.choose_script_formula("vid_1", "myth-break-model", REASON)
    assert out["formula_pick"] == "stake-first-list" and out["label"] == "Stake-First List"
    assert _row()["formula_runner_up"] == "myth-break-model"


def test_a_persons_experimental_choice_is_an_available_candidate(db):
    _video(choice="stake-first-list")
    cands = {c["id"]: c for c in server.get_video("vid_1")["formula_routing"]["candidates"]}
    assert cands["stake-first-list"]["available"] and not cands["news-take"]["available"]


def test_a_persons_choice_is_exempt_from_rotation(db):
    _history(db)
    _video(choice="scene-story")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert out["formula_pick"] == "scene-story"


def test_the_agent_agreeing_with_a_recent_choice_is_not_refused(db):
    # A domain default makes every video's choice the same formula, so it is
    # always recent; the agent naming it too is not a repeat Auto made.
    _history(db)
    _video(choice="scene-story")
    out = server.choose_script_formula("vid_1", "scene-story", REASON)
    assert out["formula_pick"] == "scene-story"
    assert _row()["formula_reason"] == REASON      # no "Repeats a recent formula" beside a person's choice


def test_a_recent_runner_up_beside_a_choice_is_not_refused(db):
    _history(db)
    _video(choice="incident-file")
    out = server.choose_script_formula("vid_1", "myth-break-model", REASON)
    assert out["formula_pick"] == "incident-file" and out["formula_runner_up"] == "myth-break-model"


def test_a_choice_of_a_formula_that_no_longer_exists_is_auto(db):
    _video(choice="retired-formula")
    assert server.get_video("vid_1")["formula_routing"]["choice"] == ""
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert out["formula_pick"] == "follow-the-flow" and out["chosen_by"] == "auto"


# ── a revision ───────────────────────────────────────────────────────────────

def test_auto_may_pick_again_in_a_revision(db):
    _video(status="REVISION_REQUESTED", pick="follow-the-flow")
    out = server.choose_script_formula("vid_1", "scene-story", "The person asked for a story.",
                                       runner_up="follow-the-flow")
    assert out["formula_pick"] == "scene-story"
    assert _row()["formula_runner_up"] == "follow-the-flow"


def test_a_persons_choice_is_not_replaced_in_a_revision(db):
    _video(status="REVISION_REQUESTED", choice="scene-story", pick="scene-story")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert "A person chose" in out["error"] and _row()["formula_pick"] == "scene-story"


def test_a_video_scripted_before_picks_gets_one_in_a_revision_whatever_its_style(db):
    # A 2.1.x video: on "auto" with no style pick, no formula pick, no record.
    # The style check is for TOPIC_APPROVED only, or such a video could never
    # be given a formula.
    _video(status="REVISION_REQUESTED", style="auto")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert out["formula_pick"] == "follow-the-flow"


def test_a_choice_with_no_pick_yet_is_written_in_a_revision(db):
    _video(status="REVISION_REQUESTED", choice="scene-story")
    out = server.choose_script_formula("vid_1", "follow-the-flow", REASON)
    assert out["formula_pick"] == "scene-story" and out["chosen_by"] == "person"


# ── what gives a pick back ───────────────────────────────────────────────────

def test_a_return_to_the_topic_drops_the_pick_and_keeps_the_persons_choice(db):
    _video(status="SCRIPT_READY", choice="scene-story", pick="scene-story")
    with server._conn() as con:
        con.execute("UPDATE videos SET formula_runner_up = 'incident-file', "
                    "formula_reason = 'why' WHERE id = 'vid_1'")
    assert "error" not in server.set_video_status("vid_1", "REVISION_REQUESTED")
    assert _row()["formula_pick"] == "scene-story"  # a script revision keeps it
    assert "error" not in server.set_video_status("vid_1", "TOPIC_PROPOSED")
    assert _row() == {"status": "TOPIC_PROPOSED", "formula_choice": "scene-story",
                      "formula_pick": "", "formula_runner_up": "", "formula_reason": ""}


def test_a_guarded_return_to_the_topic_drops_the_pick_too(db):
    _video(status="REVISION_REQUESTED", pick="follow-the-flow")
    out = server.set_video_status("vid_1", "TOPIC_PROPOSED",
                                  only_if_current_status="REVISION_REQUESTED")
    assert "error" not in out and _row()["formula_pick"] == ""


# ── seeding and the domain default ───────────────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining", "manual"])
def test_the_domains_default_formula_seeds_every_new_video(db, strategy):
    out = server.upsert_project("dom", "A domain", default_formula_id="scene-story")
    assert out["default_formula_id"] == "scene-story"
    made = server.create_video("dom", "a topic", strategy, 7, **ANGLE)
    assert made["formula_choice"] == "scene-story"
    assert _row(made["video_id"])["formula_choice"] == "scene-story"


def test_a_domain_on_auto_seeds_nothing(db):
    made = server.create_video("dom", "a topic", "trending", 7, **ANGLE)
    assert made["formula_choice"] == "" and _row(made["video_id"])["formula_choice"] == ""


def test_a_default_that_is_no_formula_any_more_seeds_nothing(db):
    with server._conn() as con:
        con.execute("UPDATE projects SET default_formula_id = 'retired-formula' WHERE id = 'dom'")
    assert server.create_video("dom", "a topic", "trending", 7, **ANGLE)["formula_choice"] == ""


def test_a_default_formula_must_be_a_formula(db):
    out = server.upsert_project("dom", "A domain", default_formula_id="no-such-formula")
    assert "is not a formula" in out["error"]
    # An experimental one is a person's choice and is allowed with the setting off.
    out = server.upsert_project("dom", "A domain", default_formula_id="news-take")
    assert out["default_formula_id"] == "news-take"


def test_omitting_the_default_leaves_it_and_blank_clears_it(db):
    server.upsert_project("dom", "A domain", default_formula_id="scene-story")
    assert server.upsert_project("dom", "Renamed")["default_formula_id"] == "scene-story"
    assert server.upsert_project("dom", "Renamed", default_formula_id="")["default_formula_id"] == ""


def test_a_stored_default_that_was_dropped_does_not_block_another_edit(db):
    with server._conn() as con:
        con.execute("UPDATE projects SET default_formula_id = 'retired-formula' WHERE id = 'dom'")
    out = server.upsert_project("dom", "Renamed", default_formula_id="retired-formula")
    assert "error" not in out and out["name"] == "Renamed"


def test_rows_filed_in_the_same_second_are_ordered_by_insertion(db):
    for vid, formula in (("v_a", "incident-file"), ("v_b", "scene-story"), ("v_c", "anomaly-file")):
        _video(vid, status="PUBLISHED", formula_id=formula, created="2026-06-01T00:00:00Z")
    _video()
    # vid_1 shares the second too; the two newest other rows are the last two inserted.
    assert server.get_video("vid_1")["formula_routing"]["recent"]["formulas"] == ["anomaly-file", "scene-story"]


# ── no Script Ready over a script in another formula ─────────────────────────

def test_a_switched_video_cannot_reach_script_ready_before_its_rewrite(db):
    _video(formula_id="follow-the-flow", pick="scene-story")
    out = server.set_video_status("vid_1", "SCRIPT_READY", only_if_current_status="TOPIC_APPROVED")
    assert "Rewrite the script" in out["error"] and _row()["status"] == "TOPIC_APPROVED"
    out = server.set_video_status("vid_1", "SCRIPT_READY")
    assert "Rewrite the script" in out["error"] and _row()["status"] == "TOPIC_APPROVED"


def test_a_rewritten_or_pre_pick_script_reaches_script_ready(db):
    _video(formula_id="scene-story", pick="scene-story")
    assert "error" not in server.set_video_status("vid_1", "SCRIPT_READY")
    _video("vid_2", formula_id="scene-story")          # scripted before picks existed
    assert "error" not in server.set_video_status("vid_2", "SCRIPT_READY")
    _video("vid_3")                                    # no pick, no record
    assert "error" not in server.set_video_status("vid_3", "SCRIPT_READY")


def test_a_pick_with_no_record_is_not_settled(db):
    # What an opening switch leaves (it clears the record), and what a script
    # written with no record would leave: neither may be handed back.
    _video(pick="scene-story")
    assert "Rewrite the script" in server.set_video_status("vid_1", "SCRIPT_READY")["error"]


def test_a_re_pick_in_a_revision_cannot_go_on_to_scenes_unrewritten(db):
    _video(status="REVISION_REQUESTED", formula_id="follow-the-flow", pick="scene-story")
    out = server.set_video_status("vid_1", "VOICE_READY",
                                  only_if_current_status="REVISION_REQUESTED")
    assert "cannot go to VOICE_READY" in out["error"] and _row()["status"] == "REVISION_REQUESTED"


def test_a_repeat_reason_is_not_stored_for_a_formula_that_is_not_recent(db):
    _video()
    server.choose_script_formula("vid_1", "scene-story", REASON, repeat_reason="Nothing else fits.")
    assert _row()["formula_reason"] == REASON


def test_recent_counts_the_pick_ahead_of_a_switched_scripts_record(db):
    # A switched video's old script is about to be replaced; its pick is the
    # formula the domain will see.
    _video("v_old", status="TOPIC_APPROVED", formula_id="incident-file", pick="scene-story",
           created="2026-05-01T00:00:00Z")
    _video()
    assert server.get_video("vid_1")["formula_routing"]["recent"]["formulas"] == ["scene-story"]


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "TOPIC_REJECTED"])
def test_a_topic_sent_back_or_rejected_does_not_count_as_recent(db, status):
    _video("v_old", status=status, formula_id="incident-file", hook_type="number",
           created="2026-05-01T00:00:00Z")
    _video()
    assert server.get_video("vid_1")["formula_routing"]["recent"] == {"formulas": [],
                                                                     "hook_types": []}



# ── a formula a later version dropped ────────────────────────────────────────

def test_a_pick_of_a_dropped_formula_is_picked_again(db):
    # Bound to a formula no tool accepts, the video could never be scripted.
    _video(pick="retired-formula")
    routing = server.get_video("vid_1")["formula_routing"]
    assert routing["decided"] is False and routing["pick"] == ""
    assert len(routing["candidates"]) == len(tf.FORMULAS)
    out = server.choose_script_formula("vid_1", "scene-story", REASON)
    assert out["formula_pick"] == "scene-story"


def test_a_pick_of_a_dropped_formula_does_not_bind_the_script_or_block_script_ready(db):
    # Both the write and the move on: a guard that read the raw pick would
    # tell the agent to record a formula no tool accepts, forever.
    _video(status="REVISION_REQUESTED", pick="retired-formula", formula_id="retired-formula")
    out = server.update_video(
        "vid_1", script_segments=[{"id": "seg-1", "voice": "One. Two.", "visual": "x"}],
        publish_title="t", publish_description="d")
    assert "error" not in out
    assert "error" not in server.set_video_status("vid_1", "SCRIPT_READY")


# ── voicing and scenes need a settled script ─────────────────────────────────

def test_a_re_pick_in_a_revision_cannot_be_voiced_unrewritten(db):
    _video(status="REVISION_REQUESTED", formula_id="follow-the-flow", pick="scene-story")
    out = server.set_video_status("vid_1", "VOICING", only_if_current_status="REVISION_REQUESTED")
    assert "cannot go to VOICING" in out["error"] and "SCRIPT_READY" in out["error"]
    assert _row()["status"] == "REVISION_REQUESTED"


def test_the_voice_ready_refusal_sends_a_new_script_to_a_person(db):
    _video(status="REVISION_REQUESTED", formula_id="follow-the-flow", pick="scene-story")
    out = server.set_video_status("vid_1", "VOICE_READY")
    assert "move the video to SCRIPT_READY for a person to approve" in out["error"]
