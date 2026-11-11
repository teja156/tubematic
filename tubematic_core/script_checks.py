"""Advisory checks on a script's words (TMDEV-211).

`check` reads a script as plain spoken text and returns a list of warnings.
A warning never refuses a write and never changes a status: the script write
returns the list to the agent, stores it on the video, and the dashboard shows
it at Script Ready. Nothing here goes near the AI review, whose findings send
a video to revision and a paid re-voice.

Every pattern and threshold the checks use is in this file, so that one test
file covers them and no other module has a copy to drift.

The checks are counts and regular expressions. They catch a script that fell
back to a stock shape (a closing ask, a recap, a greeting); they do not judge
whether a script is good.
"""
import re

from . import formulas as tformulas

# Share of a formula's band a script may miss it by before the length warning
# fires. A model counts words loosely, and 203 words against a 200-word band
# is not worth a rewrite.
BAND_SLACK = 0.05
# The middle of a script, as shares of its words, where a turn belongs.
TURN_WINDOW = (0.25, 0.80)
# Scripts shorter than this have no middle to turn in.
TURN_MIN_WORDS = 60
# Share of the publish title's content words found in the first sentence at
# which the sentence counts as reading the title back.
TITLE_OVERLAP = 0.8
# A title with fewer content words than this cannot be "repeated" meaningfully.
TITLE_MIN_WORDS = 3
# How many of the domain's earlier scripts the closing sentence is compared with.
RECENT_SCRIPTS = 30
# How many opening words of the closing sentence make it "the same closing".
CLOSING_WORDS = 3

_A = r"(?:'|’)"  # an apostrophe, straight or curly

_CLOSING_ASK = re.compile(
    r"\bfollow\b[^.?!]{0,40}\bfor more\b"
    r"|\bfollow (?:me|us|along|this|the (?:channel|page|account))\b"
    r"|\bsubscribe\b"
    r"|\blike and (?:subscribe|share|follow|comment)\b"
    r"|\b(?:share|comment) and (?:subscribe|like|follow)\b"
    r"|\b(?:smash|hit) (?:the|that) (?:like|bell|follow|subscribe)\b"
    r"|\bthanks for watching\b"
    r"|\bsee you (?:next|in the next|soon)\b"
    r"|\bstay tuned\b"
    r"|\b(?:share|send) this (?:with|to)\b"
    r"|\b(?:comment below|in the comments|let (?:me|us) know"
    r"|tell (?:me|us) (?:in|below|what you|your))\b",
    re.I)
_RECAP = re.compile(
    r"\b(?:next time|so remember|the (?:lesson|takeaway|moral)"
    r"|in (?:short|summary|conclusion)|to sum up|to recap|now you know"
    rf"|(?:and|so),? that{_A}?s (?:why|how))\b"
    r"|\bremember,",
    re.I)
_GREETING = re.compile(
    r"\b(?:welcome (?:back )?to|(?:hey|hi|hello) (?:guys|everyone|there|folks|and welcome)"
    rf"|what{_A}?s up|in (?:this|today{_A}?s) (?:video|short|episode)"
    rf"|today,? (?:we{_A}?re|we are|i{_A}?m|i am|we will|we{_A}?ll|i will|i{_A}?ll|let{_A}?s) "
    r"(?:going to |gonna )?(?:look|talk|dive|explor|cover|break|learn|discuss|explain|walk|go)"
    r"|let me (?:show|tell) you)",
    re.I)
_RUNUP = re.compile(
    rf"\bhere{_A}?s the (?:\w+ )?(?:thing|catch|trick|part|kicker|twist|problem|deal|truth)\b"
    rf"|\bhere{_A}?s where it gets\b",
    re.I)
_TURN = re.compile(r"\b(?:but|however|yet|until|instead|except|though|in fact|turns out)\b",
                   re.I)
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
# A sentence ends at . ! or ? (and any closing quote), when what follows does
# not start in lower case: an ellipsis inside a sentence ("the catch... it
# never checks") is a pause, not an ending. The lookbehind makes a run of
# punctuation match once, from its first character; without it a long run of
# dots is rescanned from every dot.
_SENTENCE_END = re.compile(r"(?<![.!?])[.!?]+[\"'”’)\]]*\s+(?=[^a-z\s])")
# A full stop after one of these is part of the word, not the end of a
# sentence: a title or a short form before a name, or a single initial.
_ABBREVIATION = re.compile(r"(?:\b(?:dr|mr|mrs|ms|st|vs|prof|gen|col|lt|sgt|jr|sr|inc|ltd)"
                           r"|\b[a-z])\.$", re.I)
_STOPWORDS = frozenset(
    "a an the and or but of to in on at for with from by as is are was were be been it its this "
    "that these those how why what when where who which do does did your you".split())


def words(text: str) -> list[str]:
    """Lower-case words of a text, punctuation dropped."""
    return _WORD.findall((text or "").lower().replace("’", "'"))


def sentences(text: str) -> list[str]:
    """A spoken text cut into sentences, in order."""
    text = " ".join((text or "").split())
    out, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        if _ABBREVIATION.search(text[start:match.end()].rstrip()):
            continue
        out.append(text[start:match.end()].strip())
        start = match.end()
    if text[start:].strip():
        out.append(text[start:].strip())
    return out


def word_count(text: str) -> int:
    """Words as the voice speaks them: runs of non-space characters."""
    return len((text or "").split())


def closing_opening(text: str) -> tuple:
    """The first words of the sentence a script closes on, or () when that
    sentence has fewer than CLOSING_WORDS words.

    A closing ask (a follow line the operator's preferences asked for) is
    stepped over: it is meant to recur, so the sentence compared is the one
    before it, the script's own ending.
    """
    sents = sentences(text)
    if len(sents) > 1 and _CLOSING_ASK.search(sents[-1]):
        sents = sents[:-1]
    head = words(sents[-1])[:CLOSING_WORDS] if sents else []
    return tuple(head) if len(head) == CLOSING_WORDS else ()


def _warn(warn_id: str, message: str) -> dict:
    return {"id": warn_id, "message": message}


def check(script: str, *, publish_title: str = "", formula_id: str = "", kept_hook: str = "",
          recent_scripts=()) -> list[dict]:
    """Warnings for one script, as [{"id", "message"}], in a fixed order.

    script: the spoken text, markup already removed.
    publish_title: what the video will be posted under.
    formula_id: the formula recorded with the script, or "" for none.
    kept_hook: the text of the opening the writer kept, markup removed, or "".
    recent_scripts: spoken texts of the same domain's earlier scripts, newest
        first; only the first RECENT_SCRIPTS are read.
    """
    sents = sentences(script)
    out = []
    if not sents:
        return out
    count = word_count(script)
    first_two = " ".join(sents[:2])
    last, last_two = sents[-1], " ".join(sents[-2:])

    if not formula_id:
        out.append(_warn("no_formula",
                         "No formula is on record for this script, so its structure and "
                         "length were not checked against one."))
    if kept_hook and words(script)[:len(words(kept_hook))] != words(kept_hook):
        out.append(_warn("hook_mismatch",
                         "The opening marked as used is not how the script begins: the first "
                         "segment starts with other words."))
    if _GREETING.search(first_two):
        out.append(_warn("greeting_opener",
                         "The script opens on a greeting or an agenda line. Open on the act, "
                         "the anomaly or the paradox itself."))
    title = [w for w in words(publish_title) if w not in _STOPWORDS]
    if len(title) >= TITLE_MIN_WORDS:
        first = set(words(sents[0]))
        if sum(w in first for w in title) / len(title) >= TITLE_OVERLAP:
            out.append(_warn("title_repeat",
                             "The first sentence repeats the publish title. The title asks; "
                             "the first sentence should continue from where it stops."))
    if _RUNUP.search(script):
        out.append(_warn("staged_runup",
                         "A staged run-up (\"Here's the thing\", \"Here's the catch\") announces "
                         "a turn. State the turn itself."))
    if count >= TURN_MIN_WORDS:
        tokens = script.split()
        middle = " ".join(tokens[int(count * TURN_WINDOW[0]):int(count * TURN_WINDOW[1])])
        if not _TURN.search(middle):
            out.append(_warn("no_turn",
                             "No turn word (but, however, yet, until, instead, except, though) "
                             "in the middle of the script. A script holds better when one short "
                             "sentence there changes direction."))
    band = tformulas.word_band(formula_id)
    if count > tformulas.WORD_CEILING:
        out.append(_warn("over_ceiling",
                         f"The script is {count} words; the ceiling for any script is "
                         f"{tformulas.WORD_CEILING} (three minutes)."))
    elif band and not (band[0] * (1 - BAND_SLACK) <= count <= band[1] * (1 + BAND_SLACK)):
        out.append(_warn("length_band",
                         f"The script is {count} words; {tformulas.label(formula_id)} runs "
                         f"{band[0]} to {band[1]}."))
    if _RECAP.search(last_two):
        out.append(_warn("recap_ending",
                         "The script ends on a recap (\"next time\", \"so remember\", \"and "
                         "that's why\"). End on the payoff, with nothing after it."))
    if _CLOSING_ASK.search(last):
        out.append(_warn("closing_ask",
                         "The last sentence asks the viewer to follow, subscribe, share or "
                         "comment. A script ends on its payoff unless the preferences ask for "
                         "a closing line."))
    opening = closing_opening(script)
    if opening:
        same = sum(closing_opening(s) == opening for s in list(recent_scripts)[:RECENT_SCRIPTS])
        if same:
            out.append(_warn("closing_repeat",
                             f"The script closes on a sentence that opens with "
                             f"\"{' '.join(opening)}\", like {same} of this domain's recent "
                             "scripts."))
    return out
