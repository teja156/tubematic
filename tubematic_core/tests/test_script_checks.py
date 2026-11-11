"""The script warnings (TMDEV-211): each check fires on the script it is for
and stays quiet on a clean one.

The quiet half matters as much as the firing half. The warnings are shown to
a person at Script Ready and handed to the agent to act on, so a check that
fires on a sound script teaches both to ignore the list.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import script_checks as sc  # noqa: E402

FORMULA = "broken-expectation"  # 130 to 200 words
TITLE = "Why Git Loses a File You Renamed"
HOOK = "You renamed one file and rewrote half of it in the same commit."

CLEAN = (
    f"{HOOK} Now the history shows a deleted file and a brand new one, and the log stops "
    "dead at today. So you blame the rename and do it again with the move command. Same two "
    "lines, one red and one green. Then the log must be wrong. But every diff tells the same "
    "story. Nothing is broken. The rename was never written down. Each commit stores a list "
    "of names, and each name points at a blob of content. So a rename is one name vanishing "
    "and another appearing. When you ask for history, the tool pairs a deleted name with an "
    "added one and compares what is inside. Change nothing, and the two match completely. "
    "But rewrite half the lines and the match drops below the fifty percent the tool needs. "
    "It stops calling it a rename. The file was never lost. The guess just failed, and a "
    "lower similarity threshold on the log command brings the whole history back."
)


def ids(script=CLEAN, **kw):
    kw.setdefault("publish_title", TITLE)
    kw.setdefault("formula_id", FORMULA)
    kw.setdefault("kept_hook", HOOK)
    return [w["id"] for w in sc.check(script, **kw)]


def swap_end(ending: str) -> str:
    """CLEAN with its last sentence replaced."""
    return " ".join(sc.sentences(CLEAN)[:-1] + [ending])


def test_the_clean_script_raises_nothing():
    assert sc.word_count(CLEAN) in range(130, 201)
    assert sc.check(CLEAN, publish_title=TITLE, formula_id=FORMULA, kept_hook=HOOK,
                    recent_scripts=["Some other script. It ends on a different note entirely."]) == []


def test_an_empty_script_raises_nothing():
    assert sc.check("") == [] and sc.check("   ") == []


def test_every_warning_has_an_id_and_a_message():
    out = sc.check("Hey everyone, welcome back. Follow for more.", publish_title="x")
    assert out and all(set(w) == {"id", "message"} and w["message"].strip() for w in out)


# --- sentences ---------------------------------------------------------

def test_an_ellipsis_inside_a_sentence_does_not_end_it():
    assert sc.sentences("The catch... it never checks. Then it fails.") == [
        "The catch... it never checks.", "Then it fails."]


def test_a_closing_quote_stays_with_its_sentence():
    assert sc.sentences('He said "it should be safe." Then he pressed enter.') == [
        'He said "it should be safe."', "Then he pressed enter."]


def test_a_sentence_starting_with_a_number_is_a_new_sentence():
    assert len(sc.sentences("It dropped to zero. 75 gigabytes were gone.")) == 2


# --- the closing ---------------------------------------------------------

@pytest.mark.parametrize("ending", [
    "Follow for more Git internals.",
    "Follow along for more like this.",
    "Subscribe so you never miss one.",
    "Like and share if this helped.",
    "Thanks for watching.",
    "See you in the next one.",
    "Send this to the friend who rewrites history on Fridays.",
    "Let me know what broke for you.",
    "Tell us in the comments.",
])
def test_a_closing_ask_is_flagged(ending):
    assert "closing_ask" in ids(swap_end(ending))


@pytest.mark.parametrize("ending", [
    "The packets follow the shortest path home.",
    "It has stayed that way for more than a decade.",
    "Nobody likes the answer, and it is still the answer.",
])
def test_an_ending_that_only_uses_the_words_is_not_a_closing_ask(ending):
    assert "closing_ask" not in ids(swap_end(ending))


def test_an_ask_in_the_middle_is_not_a_closing_ask():
    sents = sc.sentences(CLEAN)
    script = " ".join(sents[:3] + ["Follow for more of these."] + sents[3:])
    assert "closing_ask" not in ids(script)


@pytest.mark.parametrize("ending", [
    "Next time the log stops early, you will know why.",
    "So remember, a rename is only a guess.",
    "And that's why the history stops.",
    "So that’s how a rename really works.",
    "In short, the tool guesses.",
    "Now you know what a rename is.",
])
def test_a_recap_ending_is_flagged(ending):
    assert "recap_ending" in ids(swap_end(ending))


def test_a_callback_that_explains_the_title_is_not_a_recap():
    assert "recap_ending" not in ids(swap_end("That is why the history stopped at today."))


def test_a_recap_in_the_second_to_last_sentence_is_flagged():
    sents = sc.sentences(CLEAN)
    script = " ".join(sents[:-1] + ["So remember this.", "The file was never lost."])
    assert "recap_ending" in ids(script)


def test_a_closing_that_opens_like_the_domains_recent_scripts_is_flagged():
    recent = ["A script. The file was never truly gone.", "Another. It ends its own way here."]
    script = swap_end("The file was never where the log looked.")
    out = sc.check(script, publish_title=TITLE, formula_id=FORMULA, kept_hook=HOOK,
                   recent_scripts=recent)
    assert [w["id"] for w in out] == ["closing_repeat"]
    assert "the file was" in out[0]["message"] and "1 of" in out[0]["message"]


def test_only_the_newest_thirty_scripts_are_compared():
    script = swap_end("The file was never where the log looked.")
    old = ["Start here. The file was never gone."]
    filler = [f"Start here. Ending number {i} goes here." for i in range(sc.RECENT_SCRIPTS)]
    assert "closing_repeat" not in ids(script, recent_scripts=filler + old)
    assert "closing_repeat" in ids(script, recent_scripts=filler[:-1] + old)


def test_a_two_word_closing_is_never_a_repeat():
    assert "closing_repeat" not in ids(swap_end("It guessed."), recent_scripts=["Start here. It guessed."])


# --- the opening ---------------------------------------------------------

@pytest.mark.parametrize("opening", [
    "Hey everyone, welcome back.",
    "Welcome to another one.",
    "In this video we look at renames.",
    "Today we're going to look at renames.",
    "Today, let’s look at renames.",
    "Let me show you something about renames.",
    "What's up, it is rename time.",
])
def test_a_greeting_or_agenda_opener_is_flagged(opening):
    assert "greeting_opener" in ids(f"{opening} {CLEAN}", kept_hook="")


def test_a_greeting_word_later_in_the_script_is_not_an_opener():
    sents = sc.sentences(CLEAN)
    script = " ".join(sents[:5] + ["Welcome to the part nobody reads."] + sents[5:])
    assert "greeting_opener" not in ids(script)


def test_a_first_sentence_that_reads_the_title_back_is_flagged():
    script = "Here is why Git loses a file you renamed. " + CLEAN
    assert "title_repeat" in ids(script, kept_hook="")


def test_a_first_sentence_that_shares_a_few_title_words_is_not():
    # "renamed" and "file" are in both; that is continuing the title.
    assert "title_repeat" not in ids()


def test_a_short_title_cannot_be_repeated():
    assert "title_repeat" not in ids("Git renames. " + CLEAN, publish_title="Git Renames",
                                     kept_hook="")


def test_the_kept_hook_must_open_the_script():
    assert "hook_mismatch" in ids(kept_hook="Why does the log stop at today?")
    assert "hook_mismatch" not in ids(kept_hook=HOOK.upper().rstrip("."))
    assert "hook_mismatch" not in ids(kept_hook="")


# --- the middle ---------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "Here's the thing.", "Here’s the catch.", "Here's the trick.",
    "Here's where it gets strange.", "Here's the clever part.",
])
def test_a_staged_run_up_is_flagged(phrase):
    sents = sc.sentences(CLEAN)
    assert "staged_runup" in ids(" ".join(sents[:6] + [phrase] + sents[6:]))


def test_heres_followed_by_the_fact_itself_is_not_a_run_up():
    sents = sc.sentences(CLEAN)
    assert "staged_runup" not in ids(" ".join(sents[:6] + ["Here's the commit."] + sents[6:]))


def test_a_script_with_no_turn_in_the_middle_is_flagged():
    flat = CLEAN.replace("But rewrite half", "Rewrite half").replace("But every", "Every")
    assert "no_turn" in ids(flat)


def test_a_turn_only_at_the_very_start_or_end_does_not_count():
    flat = CLEAN.replace("But rewrite half", "Rewrite half").replace("But every", "Every")
    assert "no_turn" in ids("But first. " + flat + " But not today.", kept_hook="")


def test_a_very_short_script_is_not_asked_for_a_turn():
    assert "no_turn" not in ids("One fact about a file. It was renamed.", formula_id="",
                                kept_hook="")


# --- length ---------------------------------------------------------

def _of(n: int) -> str:
    return " ".join(["word"] * (n - 1)) + " but."


@pytest.mark.parametrize("n, expected", [
    (123, True),    # below 130 less the slack (123.5)
    (124, False),
    (130, False),
    (200, False),
    (210, False),   # 200 plus the slack
    (211, True),
])
def test_the_band_warning_allows_the_slack_and_no_more(n, expected):
    assert ("length_band" in ids(_of(n), kept_hook="", publish_title="")) is expected


def test_the_band_message_names_the_count_the_formula_and_its_band():
    out = sc.check(_of(260), formula_id=FORMULA)
    msg = next(w["message"] for w in out if w["id"] == "length_band")
    assert "260" in msg and "Broken Expectation" in msg and "130 to 200" in msg


def test_no_formula_means_no_band_and_says_so():
    out = ids(_of(260), formula_id="", kept_hook="", publish_title="")
    assert "length_band" not in out and "no_formula" in out


def test_a_formula_this_version_does_not_know_is_not_judged():
    out = ids(_of(260), formula_id="retired-formula", kept_hook="", publish_title="")
    assert "length_band" not in out and "no_formula" not in out


def test_past_the_ceiling_is_one_warning_not_two():
    out = ids(_of(451), kept_hook="", publish_title="")
    assert "over_ceiling" in out and "length_band" not in out
    assert "over_ceiling" not in ids(_of(450), formula_id="anomaly-file", kept_hook="",
                                     publish_title="")
    assert "over_ceiling" in ids(_of(451), formula_id="", kept_hook="", publish_title="")


def test_word_count_counts_what_the_voice_speaks():
    assert sc.word_count("the catch... it never verifies") == 5
    assert sc.word_count("") == 0


# --- found in review ---------------------------------------------------------

def test_remember_with_a_comma_is_a_recap():
    assert "recap_ending" in ids(swap_end("Remember, the file was never lost."))


def test_a_long_run_of_dots_is_read_in_linear_time():
    import time
    started = time.monotonic()
    sc.check("One fact" + "." * 20000 + " Then another fact. " + CLEAN)
    assert time.monotonic() - started < 1.0


def test_a_title_or_an_initial_does_not_end_a_sentence():
    assert sc.sentences("Dr. Brown joined the U.S. Navy. Then he left.") == [
        "Dr. Brown joined the U.S. Navy.", "Then he left."]
    assert sc.sentences("He said no. Then he left.") == ["He said no.", "Then he left."]


@pytest.mark.parametrize("ending", [
    "So what does that tell us about the moon?",
    "That is what a black hole looks like and why nothing escapes it.",
])
def test_ordinary_endings_found_in_review_are_not_closing_asks(ending):
    assert "closing_ask" not in ids(swap_end(ending))


def test_today_as_an_ordinary_word_is_not_an_agenda_line():
    assert "greeting_opener" not in ids("Today we are still using a cable laid in 1988. " + CLEAN,
                                        kept_hook="")
    assert "greeting_opener" in ids("Today we're going to look at renames. " + CLEAN, kept_hook="")


def test_a_closing_line_the_preferences_asked_for_is_not_a_repeat():
    # The follow line recurs because the operator asked for it. What is
    # compared is the sentence before it, the script's own ending.
    script = CLEAN + " Follow for more Git internals."
    recent = ["Start here. It ended its own way. Follow for more Git internals."]
    out = ids(script, recent_scripts=recent)
    assert "closing_ask" in out and "closing_repeat" not in out
    same_payoff = ["Start here. The guess just went wrong. Follow for more Git internals."]
    assert "closing_repeat" in ids(script, recent_scripts=same_payoff)


@pytest.mark.parametrize("position", [0.26, 0.5, 0.79])
def test_a_turn_anywhere_in_the_wide_middle_counts(position):
    tokens = ["word"] * 200
    tokens[int(200 * position)] = "but"
    assert "no_turn" not in ids(" ".join(tokens) + ".", formula_id="", kept_hook="",
                                publish_title="")


@pytest.mark.parametrize("position", [0.1, 0.9])
def test_a_turn_near_either_end_does_not(position):
    tokens = ["word"] * 200
    tokens[int(200 * position)] = "but"
    assert "no_turn" in ids(" ".join(tokens) + ".", formula_id="", kept_hook="",
                            publish_title="")
