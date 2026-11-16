"""Advisory checks on a script's words (TMDEV-211, TMDEV-213).

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
# Share of the publish title's content words found in the first sentence (or
# of the first sentence's in the title) at which the two count as repeating.
TITLE_OVERLAP = 0.8
# A title (or a sentence) with fewer content words than this cannot be
# "repeated" meaningfully.
TITLE_MIN_WORDS = 3
# How many of the domain's earlier scripts the closing sentence is compared with.
RECENT_SCRIPTS = 30
# How many opening words of the closing sentence make it "the same closing".
CLOSING_WORDS = 3
# How many opening words of the first sentence make it "the same opening".
OPENING_WORDS = 3

_A = r"(?:'|’)"  # an apostrophe, straight or curly

# Where an ask can begin: the start of the sentence, after a comma or a
# joining word, or after "don't forget to" and its kin. "Clients subscribe to
# the topic" and "two servers share this with every client" use the same
# words in the middle of a statement and are not asks.
_LEAD = (rf"(?:^|[,;:]\s+|\b(?:and|so|then|please|now)\s+"
         rf"|\b(?:don{_A}?t forget to|make sure (?:to|you)|be sure to|remember to)\s+)")
# "Follow this packet" and "subscribe to the topic" are instructions about the
# subject. "Follow the channel" is the ask.
_FOLLOW = (r"follow\b(?! (?:the|this|that|a|an|it|its|each|every|one|your|these|those|them"
           r"|him|her)\b(?! (?:channel|page|account)))")
_SUBSCRIBE = r"subscribe\b(?! to (?:the|a|an|this|that|each|every)\b(?! (?:channel|page)))"
_CLOSING_ASK = re.compile(
    r"\bfollow\b[^.?!]{0,40}\bfor more\b"
    rf"|{_LEAD}(?:(?:hit|tap|smash) |drop (?:a|us a) |give (?:this|us|me) a )?(?:{_FOLLOW}|{_SUBSCRIBE})"
    r"|\blike and (?:subscribe|share|follow|comment)\b"
    r"|\b(?:share|comment) and (?:subscribe|like|follow)\b"
    r"|\b(?:smash|hit|tap) (?:the|that) (?:like|bell|follow|subscribe)\b"
    r"|\bthanks for watching\b"
    r"|\bsee you (?:next|in the next|soon)\b"
    r"|\bstay tuned\b"
    rf"|{_LEAD}(?:share|send) this (?:with|to)\b"
    r"|\b(?:comment below|in the comments)\b"
    rf"|{_LEAD}(?:let (?:me|us) know|tell (?:me|us) (?:in|below|what you|your))\b",
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
    r"|let me (?:show|tell) you)\b"
    rf"|\btoday,? (?:we{_A}?re|we are|i{_A}?m|i am|we will|we{_A}?ll|i will|i{_A}?ll|let{_A}?s) "
    r"(?:going to |gonna )?(?:look|talk|div(?:e|ing)|explor(?:e|ing)|cover|break|learn|discuss"
    r"|explain|walk|show)",
    re.I)
_RUNUP = re.compile(
    rf"\bhere{_A}?s the (?:\w+ )?(?:thing|catch|trick|part|kicker|twist|problem|deal|truth)\b"
    rf"|\bhere{_A}?s where it gets\b"
    rf"|\blet{_A}?s (?:dive|break (?:it|this|that) down|explore)\b"
    r"|\bwithout further ado\b"
    r"|\bthe thing is,"
    rf"|\blet{_A}?s be honest\b"
    rf"|\bhere{_A}?s what (?:you need to know|happens)\b",
    re.I)
# A contrast that sets up a point by denying one nobody made: "not just X, but
# Y", "it's not X, it's Y" (in one sentence or across two), "this doesn't mean
# X. It means Y", "a feature, not a bug". Where the first half corrects a
# belief the viewer holds, the contrast is the point and the warning may stand.
_NOT_BUT = re.compile(
    r"\bnot (?:just|only|merely|simply)\b[^.?!]{0,80}\bbut\b"
    rf"|\b(?:\w+(?:{_A}s|{_A}re) not|\w+ (?:is|are|was|were) not"
    rf"|\w+ (?:isn{_A}t|aren{_A}t|wasn{_A}t|weren{_A}t))\b[^.?!]{{0,60}}[.,;]\s+"
    rf"(?:it|this|that|they|these|those)(?:{_A}s|{_A}re| is| are| was| were)\b"
    rf"|\b(?:this|that) (?:doesn{_A}t|does not|don{_A}t|do not) mean\b[^.?!]{{0,80}}[.?!]\s+"
    r"(?:it|that|this) means\b"
    r"|\b(?:a|an|the) \w+(?: \w+)?, not (?:a|an|the) \w+",
    re.I)
# Sayings and stock words that dress an ordinary point as a deep one. Only
# phrases with no plain use are listed: "key", "landscape", "unlock", "the
# architecture of" or "the language of" can be literal, so they are left to the
# skill's slop-patterns.md, where a writer can judge them.
_STOCK = re.compile(
    r"\bat its core\b|\bthe real question\b|\bstands? as a testament\b"
    r"|\bplays? an? (?:key|crucial|pivotal|vital) role\b|\blet that sink in\b"
    r"|\bread that again\b|\bmake no mistake\b|\bdelv(?:e|es|ed|ing)\b"
    r"|\b(?:a|the) (?:rich )?tapestry of\b|\bgame[- ]changer\b"
    rf"|\bin today{_A}?s fast[- ]paced\b"
    r"|\bunlock(?:s|ing)? the (?:secret|power|potential|mystery)\b",
    re.I)
# A row of this many sentences, each this short or shorter, reads as a drumroll
# ("No map. No plan. No way back.") and not as a sentence with a claim. Three
# short sentences that each carry a fact ("He ran. She followed. The door
# closed.") are narration, so a row of three counts only when two of its
# sentences start with the same word; a row of FRAGMENT_LONG_ROW counts always.
FRAGMENT_ROW = 3
FRAGMENT_LONG_ROW = 4
FRAGMENT_WORDS = 3
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
# sentence: a title or a short form that comes before a name. Single letters
# and dotted runs are left alone: "written in C." and "at 3 a.m." end
# sentences as often as "U.S." does not.
_ABBREVIATION = re.compile(r"\b(?:dr|mr|mrs|prof|st|vs|jr|sr|lt|sgt)\.$", re.I)
_ABBREVIATION_REACH = 6  # the longest short form above, with its stop
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
        # Only the word before the stop is read, so a long text stays linear.
        stop = match.start() + 1
        if _ABBREVIATION.search(text[max(start, stop - _ABBREVIATION_REACH):stop]):
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


def opening_words(text: str) -> tuple:
    """The first words of a script's first sentence, or () when that sentence
    has fewer than OPENING_WORDS words."""
    sents = sentences(text)
    head = words(sents[0])[:OPENING_WORDS] if sents else []
    return tuple(head) if len(head) == OPENING_WORDS else ()


def _fragment_row(sents: list[str]) -> list[str]:
    """The first drumroll: FRAGMENT_ROW or more consecutive sentences of at most
    FRAGMENT_WORDS words, of which two start with the same word (or
    FRAGMENT_LONG_ROW or more, whatever they start with). [] when there is none."""
    run: list[str] = []
    for sent in sents + [""]:
        if sent and word_count(sent) <= FRAGMENT_WORDS:
            run.append(sent)
            continue
        starts = [(words(r) or [""])[0] for r in run]
        if len(run) >= FRAGMENT_LONG_ROW or (
                len(run) >= FRAGMENT_ROW and len(set(starts)) < len(starts)):
            return run
        run = []
    return []


def _warn(warn_id: str, message: str) -> dict:
    return {"id": warn_id, "message": message}


def check(script: str, *, publish_title: str = "", formula_id: str = "", kept_hook: str = "",
          recent_scripts=(), hook_type: str = "", recent_hook_types=(),
          beats=()) -> list[dict]:
    """Warnings for one script, as [{"id", "message"}], in a fixed order.

    script: the spoken text, markup already removed.
    publish_title: what the video will be posted under.
    formula_id: the formula recorded with the script, or "" for none.
    kept_hook: the text of the opening the writer kept, markup removed, or "".
    recent_scripts: spoken texts of the same domain's earlier scripts, newest
        first; only the first RECENT_SCRIPTS are read.
    hook_type: the type of the opening the writer kept, or "".
    recent_hook_types: the kept opening types of the domain's previous videos,
        newest first; only the first tformulas.ROTATION_WINDOW are read.
    beats: each segment's beat label, in order ("" for none).
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
    names = {tformulas.beat_key(n) for n in tformulas.beat_names(formula_id)}
    unknown = sorted({b for b in beats or () if isinstance(b, str) and b.strip()
                      and tformulas.beat_key(b) not in names}) if names else []
    if unknown:
        out.append(_warn("beat_unknown",
                         "These segment beats are not beats of the formula: "
                         + ", ".join(f'"{b}"' for b in unknown)
                         + ". Label each segment with a beat name from the formula's reference "
                           "file, or the scene author cannot tell where the picture must change."))
    if _GREETING.search(first_two):
        out.append(_warn("greeting_opener",
                         "The script opens on a greeting or an agenda line. Open on the act, "
                         "the anomaly or the paradox itself."))
    # Either way round: the sentence reads the title back, or the title copies
    # a short opening sentence. Both leave the viewer reading the same words twice.
    title = [w for w in words(publish_title) if w not in _STOPWORDS]
    opening = [w for w in words(sents[0]) if w not in _STOPWORDS]
    title_set, opening_set = set(title), set(opening)
    if ((len(title) >= TITLE_MIN_WORDS
         and sum(w in opening_set for w in title) / len(title) >= TITLE_OVERLAP)
            or (len(opening) >= TITLE_MIN_WORDS
                and sum(w in title_set for w in opening) / len(opening) >= TITLE_OVERLAP)):
        out.append(_warn("title_repeat",
                         "The first sentence repeats the publish title. The title and the opening "
                         "are a pair: the title states the question or the stake, and the first "
                         "sentence continues from where it stops."))
    start = opening_words(script)
    if start:
        same = sum(opening_words(s) == start for s in list(recent_scripts)[:RECENT_SCRIPTS])
        if same:
            out.append(_warn("opening_repeat",
                             f"The script opens with \"{' '.join(start)}\", like {same} of this "
                             "domain's recent scripts."))
    if hook_type and hook_type in list(recent_hook_types)[:tformulas.ROTATION_WINDOW]:
        out.append(_warn("hook_type_repeat",
                         f"The opening is a {tformulas.HOOK_TYPES.get(hook_type, hook_type)} "
                         "opening, like one of this domain's previous "
                         f"{tformulas.ROTATION_WINDOW} videos. Vary the type of opening from "
                         "video to video where another type fits the topic honestly."))
    if _RUNUP.search(script):
        out.append(_warn("staged_runup",
                         "A staged run-up (\"Here's the thing\", \"Let's dive in\") announces "
                         "what is coming instead of saying it. State it itself."))
    contrasts = [m.group(0) for m in _NOT_BUT.finditer(script)]
    if contrasts:
        out.append(_warn("contrast_staging",
                         f"{len(contrasts)} staged contrast(s), such as \"{contrasts[0]}\": a "
                         "denial nobody made, set up so the real point sounds bigger. State the "
                         "point directly. Keep a contrast only where it corrects something the "
                         "viewer believes."))
    stock = list(dict.fromkeys(m.group(0).lower() for m in _STOCK.finditer(script)))
    if stock:
        out.append(_warn("stock_phrase",
                         "Stock phrases that sound deep and add no fact: "
                         + ", ".join(f'"{p}"' for p in stock[:3])
                         + ". Replace each with the specific claim."))
    row = _fragment_row(sents)
    if row:
        out.append(_warn("fragment_row",
                         f"A row of {len(row)} very short sentences (\"{' '.join(row)}\") reads "
                         "as a drumroll. Join them into one sentence that carries the claim."))
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
