"""Format Packs (TMDEV-240): the checks a Format Packs insert must pass before
the scene-config is written.

Format Packs is an insert style only. An insert is one entry of the config's
`inserts`; its `props.formatPacks` is one phone-native format timed on the
video's frames: a chat thread, a short numbered list, a quiz board or a news
strap. The renderer's side of this contract is
renderer/remotion/src/scenes/installed/formatPacks/contract.ts.

The user's line on impersonation (TMDEV-240): nothing may pass for a real app
or a real screenshot. The component draws generic chrome and an EXAMPLE tag on
every made-up thread or headline; these checks refuse what data could add on
top: a phone number outside the ranges set aside for fiction, a verified tick,
and the name of a messaging or social app in a header. A brand named inside a
message cannot be caught by a list; the authoring skill and the AI review
(the pack's insert.review) cover it.

Keep in sync: FORMATS, LIMITS, TIMING, WRAP, ONE_LINE, BAND, LAYOUT, TICKS,
APPS and wrap_lines mirror contract.ts; the widths come from text_fit.py; both sides run the shared cases in
tests/fixtures/format_packs_contract.json. The style pack's insert.block is
BAND.

Free of the database and of I/O.
"""
from __future__ import annotations

import re

import text_fit

SCENE_SRC = "FormatPacks"
PROPS_KEY = "formatPacks"
STYLE_ID = "format_packs"

FORMATS = ("chat", "list", "quiz", "strap")
LIMITS = {
    "minMessages": 2, "maxMessages": 5, "messageChars": 90, "contactChars": 24, "titleChars": 40, "titleLines": 2,
    "maxMarks": 3, "markLabelChars": 16, "markChars": 22, "minItems": 2, "maxItems": 4, "leadChars": 24, "itemChars": 64,
    "itemLines": 2, "questionChars": 80, "questionLines": 3, "minOptions": 2, "maxOptions": 4, "optionChars": 30,
    "kickerChars": 20, "headlineChars": 70, "headlineLines": 3, "dateChars": 24, "sourceChars": 40,
    "flapChars": 10, "flapLabelChars": 20, "maxStrapMarks": 2, "minGap": 18, "markLead": 8, "endHold": 30,
    "maxStillSeconds": 3,
}
TIMING = {"bubbleIn": 7, "dots": 14, "rowIn": 14, "optionIn": 10, "lock": 10, "mark": 14, "headlineIn": 12,
          "flip": 8, "flipPerTile": 3}
# Each wrapped text's font size, the width of its box and whether it is set in
# capitals, as the components draw it: a bubble 44 px in 640 less its padding,
# a list title 56 px capitals, an item 36 px beside its number, the question
# 52 px in the quiz card, the headline 60 px beside the strap's bar.
WRAP = {"bubble": (44, 580, False), "title": (56, 796, True), "item": (36, 686, False),
        "question": (52, 768, False), "headline": (60, 756, False)}
# One-line texts that shrink to fit their box (fitText.ts), down to a smallest
# size the validator holds them to: the chat title (capitals, spacing 1) and a
# quiz option.
ONE_LINE = {"chatTitle": (36, 620, 1, True), "option": (30, 680, 0, False)}
# Texts that must fit one line at their own size: a list item's lead (44 px in
# the row beside its number) and the contact name (40 px beside the avatar).
LEAD_BOX = (44, 686)
CONTACT_BOX = (40, 640)
BAND = (200, 1330)
LAYOUT = {"threadBudget": 760, "bubbleLine": 54, "bubblePadY": 22, "bubbleGap": 22, "listBudget": 1100,
          "titleLine": 64, "itemLine": 46, "rowBase": 104, "rowGap": 20}
TICKS = ("✓", "✔", "☑", "✅", "\U0001F5F8", "☑️", "✔️")
APPS = ("WhatsApp", "iMessage", "Messenger", "Instagram", "TikTok", "X", "Twitter", "Facebook", "Telegram",
        "Signal", "Snapchat")
# A step's `at` may sit this many frames from a word's start.
WORD_SNAP_FRAMES = 2
MAX_ERRORS = 12

_KEYS = {
    "chat": {"format", "title", "contact", "messages", "marks"},
    "list": {"format", "title", "items"},
    "quiz": {"format", "question", "options", "answer", "lockAt"},
    "strap": {"format", "kicker", "headline", "date", "source", "marks", "flap"},
}
_UK = re.compile(r"^(?:\+44|0044|0)7700900\d{3}$")
_US = re.compile(r"^(?:\+?1)?(?:\d{3})?55501\d{2}$")
# A run that reads as a phone number: digits joined by the characters a written
# number uses. Amounts with commas are not one; a price or a date with dots or
# slashes has too few digits (real_looking_numbers counts them).
_PHONE_RUN = re.compile(r"\+?\(?\d[\d\s().\-/\u2010-\u2015]{5,}\d")
# The fewest digits a phone number has.
MIN_PHONE_DIGITS = 7
# Digit groups in the shape of a written phone number (867.5309, 212 867 5309,
# 020 7946 0000, 07911 123456); a date (12-03-2026) or a grouped count
# (1-000-000) has another shape.
PHONE_SHAPES = {(3, 4), (3, 3, 4), (1, 3, 3, 4), (4, 3, 4), (3, 4, 4), (2, 4, 4), (5, 6), (4, 6)}
_APP_WORDS = [re.compile(r"\bX\b") if a == "X" else re.compile(rf"\b{re.escape(a)}\b", re.I) for a in APPS]


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def wrap_lines(text: str, kind: str) -> int:
    """Lines `text` takes in the box of a WRAP kind, by the shared width
    estimate (contract.ts wrapLines, text_fit.wrap_count). The estimate is on
    the wide side, so the browser wraps it in at most as many lines."""
    size, box, upper = WRAP[kind]
    return text_fit.wrap_count(text.upper() if upper else text, size, box)


def flap_frames(old: str, new: str) -> int:
    """Frames the board takes to show `new`: the tiles flip one after another,
    and a tile whose character does not change is already in place
    (strap.tsx Flap pads both values on the left to one length)."""
    n = max(len(old), len(new))
    a, b = old.rjust(n), new.rjust(n)
    changed = [i for i in range(n) if a[i] != b[i]]
    return changed[-1] * TIMING["flipPerTile"] + TIMING["flip"] if changed else 0


def one_line_fits(text: str, kind: str) -> bool:
    """Whether a one-line text fits its box at the smallest size the scene
    shrinks it to (fitText.ts fitFontSize)."""
    smallest, box, spacing, upper = ONE_LINE[kind]
    return text_fit.fits_at(text.upper() if upper else text, box, smallest, spacing)


def bubble_height(text: str) -> int:
    return wrap_lines(text, "bubble") * LAYOUT["bubbleLine"] + 2 * LAYOUT["bubblePadY"]


def thread_height(texts: list[str]) -> int:
    return sum(bubble_height(t) for t in texts) + max(0, len(texts) - 1) * LAYOUT["bubbleGap"]


def list_height(title: str, items: list[dict]) -> int:
    t = (wrap_lines(title, "title") if title else 0) * LAYOUT["titleLine"] + 40
    rows = sum(LAYOUT["rowBase"] + wrap_lines(it.get("text", ""), "item") * LAYOUT["itemLine"] for it in items)
    return t + rows + max(0, len(items) - 1) * LAYOUT["rowGap"]


# What joins the digits of a written phone number: spaces, hyphens and dashes,
# dots, slashes and brackets.
_JOINERS = r"\s().\-/\u2010-\u2015"


def is_fiction_number(raw: str) -> bool:
    n = re.sub(rf"[{_JOINERS}]", "", raw)
    return bool(_UK.match(n) or _US.match(n))


def real_looking_numbers(text: str) -> list[str]:
    """Phone-number-like runs in `text` outside the fiction ranges: a run with a
    plus sign or brackets, one whose digit groups have a phone number's shape
    (867.5309, 020 7946 0000), or one of ten or more digits. A date, a price, a
    grouped count (1-000-000) or a bare short count is not one."""
    out = []
    for m in _PHONE_RUN.finditer(text):
        run = m.group(0).strip()
        digits = re.sub(r"\D", "", run)
        if len(digits) > 15 or len(digits) < MIN_PHONE_DIGITS or is_fiction_number(run):
            continue
        groups = tuple(len(g) for g in re.findall(r"\d+", run))
        if re.search(r"[+()]", run) or groups in PHONE_SHAPES or len(digits) >= 10:
            out.append(run)
    return out


def _overlaps(text: str, match: str, earlier: list) -> bool:
    """Whether `match`'s first place in `text` overlaps an earlier mark's (the
    renderer draws a mark at its match's first place and skips an overlapping
    one, parts.tsx MarkedText)."""
    i = text.find(match)
    for m in earlier:
        j = text.find(m) if isinstance(m, str) and m else -1
        if i >= 0 and j >= 0 and i < j + len(m) and j < i + len(match):
            return True
    return False


def app_names(text: str) -> list[str]:
    return [a for a, rx in zip(APPS, _APP_WORDS) if rx.search(text)]


def has_tick(text: str) -> bool:
    return any(t in text for t in TICKS)


def change_frames(data: dict, start: int) -> list[int]:
    """Every frame something new happens (contract.ts changeFrames)."""
    at = [start]
    fmt = data.get("format")

    def take(seq, key="at"):
        for x in seq if isinstance(seq, list) else []:
            if isinstance(x, dict) and _int(x.get(key)):
                at.append(x[key])

    if fmt == "chat":
        take(data.get("messages"))
        take(data.get("marks"))
    elif fmt == "list":
        take(data.get("items"))
    elif fmt == "quiz":
        take(data.get("options"))
        if _int(data.get("lockAt")):
            at.append(data["lockAt"])
    elif fmt == "strap":
        take(data.get("marks"))
        flap = data.get("flap")
        if isinstance(flap, dict) and _int(flap.get("at")):
            at.append(flap["at"])
    return sorted(set(at))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def check_insert(entry: dict, fps: int, word_starts: list[int], words: list[str]) -> list[str]:
    """Every problem with one Format Packs insert, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. The window itself is checked by
    mcp/inserts.py."""
    start, dur = entry.get("startFrame"), entry.get("durationInFrames")
    if not (_int(start) and _int(dur) and dur > 0):
        return ["The insert needs whole-number startFrame and durationInFrames."]
    props = entry.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    if not isinstance(data, dict):
        return [f"The insert's props must hold {PROPS_KEY!r}: one format and its text."]
    end = start + dur
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    fmt = data.get("format")
    if fmt not in FORMATS:
        return [f"formatPacks.format must be one of {', '.join(FORMATS)}."]
    extra = set(data) - _KEYS[fmt]
    if extra:
        err(f"A {fmt} holds {', '.join(sorted(_KEYS[fmt]))}; remove {sorted(extra)}.")

    # The impersonation line, over every string in the data.
    for s in _strings(data):
        if has_tick(s):
            err("No tick or verified mark anywhere: it reads as a verified account. Remove it.")
            break
    odd = [c for x in _strings(data) for c in text_fit.unsupported_chars(x)]
    if odd and not any(has_tick(x) for x in _strings(data)):
        err(f"{odd[0]!r} is not a character the format's fonts draw (they draw Latin letters, digits, punctuation, "
            "currency signs and arrows): no emoji, other scripts or invisible characters. Rewrite it in plain text.")
    # Every string, the strap's date and flap included: the rule tells a date,
    # a price or a count from a phone number by its shape.
    found = [n for x in _strings(data) for n in real_looking_numbers(x)]
    if found:
        err(f"{found[0]!r} looks like a real phone number. Use one from the ranges kept for fiction: UK 07700 "
            "900000 to 900999, or 555-0100 to 555-0199 in North America.")

    def text(value, key: str, cap: int, required: bool = True) -> str:
        if value is None and not required:
            return ""
        if not isinstance(value, str) or not value.strip() or len(value) > cap:
            err(f"{key} must be text of 1 to {cap} characters.")
            return ""
        return value

    def header(value, key: str) -> None:
        names = app_names(value) if isinstance(value, str) else []
        if names:
            err(f"{key} names {names[0]}: never name a messaging or social app. Use a generic label "
                "(\"Unknown number\", \"Bank?\", \"Delivery\").")

    def timed(seq, key: str, lo: int, hi: int) -> list[dict]:
        if not isinstance(seq, list) or not lo <= len(seq) <= hi or not all(isinstance(x, dict) for x in seq):
            err(f"{key} lists {lo} to {hi} entries.")
            return []
        return seq

    snaps = sorted(set(word_starts))

    def on_word(at: int, where: str) -> None:
        if snaps and min(abs(at - w) for w in snaps) > WORD_SNAP_FRAMES:
            nearest = min(snaps, key=lambda w: abs(at - w))
            err(f"{where} arrives at frame {at}, which is not on a word; put it on the word that reads it (the "
                f"nearest word starts at {nearest}).")

    def arrivals(seq: list[dict], name: str, first_at_start: bool = True) -> None:
        prev = None
        for i, x in enumerate(seq):
            at = x.get("at")
            where = f"{name} {i + 1}"
            if not _int(at):
                err(f"{where} needs a whole-number at (a frame of the video).")
                continue
            if not start <= at <= end - LIMITS["endHold"]:
                err(f"{where} arrives at frame {at}, outside the insert ({start} to {end - LIMITS['endHold']}, "
                    f"the last {LIMITS['endHold']} frames held).")
            if i == 0 and first_at_start and at != start:
                err(f"{where} arrives at frame {at}; the first one is on screen with the insert, at its startFrame "
                    f"{start}.")
            elif at != start:
                on_word(at, where)
            if prev is not None and at - prev < LIMITS["minGap"]:
                err(f"{where} arrives {at - prev} frames after the one before; keep at least {LIMITS['minGap']} "
                    "frames between them.")
            prev = at

    if fmt == "chat":
        title = data.get("title")
        if title is not None:
            title = text(title, "chat title", LIMITS["titleChars"])
            header(title, "The title")
            if title and not one_line_fits(title, "chatTitle"):
                err("The chat title does not fit one line above the phone; shorten it (about 22 characters, fewer "
                    "with wide letters).")
        contact = data.get("contact")
        if not isinstance(contact, dict) or not set(contact) <= {"name", "number"}:
            err("contact is {name, number}: a generic label and, if any, a number from the fiction ranges.")
        else:
            name = text(contact.get("name"), "contact.name", LIMITS["contactChars"])
            header(name, "The contact")
            if name and not text_fit.fits_at(name, CONTACT_BOX[1], CONTACT_BOX[0]):
                err("contact.name does not fit the phone's header beside the avatar; shorten it.")
            number = contact.get("number")
            if number is not None and (not isinstance(number, str) or not is_fiction_number(number)):
                err("contact.number must come from the ranges kept for fiction: UK 07700 900000 to 900999, or "
                    "555-0100 to 555-0199 in North America. Or leave it out.")
        messages = timed(data.get("messages"), "messages", LIMITS["minMessages"], LIMITS["maxMessages"])
        for i, m in enumerate(messages):
            if m.get("from") not in ("them", "me") or not set(m) <= {"at", "from", "text"}:
                err(f"Message {i + 1} is {{at, from, text}} with from \"them\" or \"me\".")
            text(m.get("text"), f"Message {i + 1} text", LIMITS["messageChars"])
        arrivals(messages, "Message")
        texts = [m["text"] for m in messages if isinstance(m.get("text"), str)]
        if len(texts) == len(messages) and texts and thread_height(texts) > LAYOUT["threadBudget"]:
            err("The messages do not fit on the phone together; shorten them or show fewer.")
        marks = data.get("marks", [])
        if not isinstance(marks, list) or len(marks) > LIMITS["maxMarks"] \
                or not all(isinstance(k, dict) for k in marks):
            err(f"marks lists at most {LIMITS['maxMarks']} marks.")
            marks = []
        for i, k in enumerate(marks):
            where = f"Mark {i + 1}"
            if not set(k) <= {"at", "message", "match", "kind", "label"} or k.get("kind") not in ("underline", "ring"):
                err(f"{where} is {{at, message, match, kind, label}} with kind \"underline\" or \"ring\".")
                continue
            mi = k.get("message")
            if not _int(mi) or not 0 <= mi < len(messages):
                err(f"{where}: message is the index (from 0) of a message in the thread.")
                continue
            msg = messages[mi].get("text") if isinstance(messages[mi].get("text"), str) else ""
            if not isinstance(k.get("match"), str) or not k["match"] or k["match"] not in msg:
                err(f"{where}: match must be words in message {mi} as written.")
            elif len(k["match"]) > LIMITS["markChars"]:
                err(f"{where}: match is at most {LIMITS['markChars']} characters; mark the few words that give it away.")
            elif not text_fit.fits_at(k["match"], WRAP["bubble"][1], WRAP["bubble"][0]):
                err(f"{where}: the marked words are wider than a bubble line; mark fewer words.")
            elif _overlaps(msg, k["match"], [o.get("match") for o in marks[:i]
                                            if isinstance(o, dict) and o.get("message") == mi]):
                err(f"{where}: its words overlap another mark on message {mi}; mark different words.")
            if k.get("label") is not None:
                text(k.get("label"), f"{where} label", LIMITS["markLabelChars"])
                if any(o is not k and o.get("message") == mi and o.get("label") is not None
                       for o in marks[:i] if isinstance(o, dict)):
                    err(f"{where}: message {mi} already has a labelled mark; a message carries one label.")
            at = k.get("at")
            m_at = messages[mi].get("at")
            if not _int(at):
                err(f"{where} needs a whole-number at.")
            else:
                if _int(m_at) and at < m_at + LIMITS["markLead"]:
                    err(f"{where} lands at frame {at}, before its message is on screen; mark it at least "
                        f"{LIMITS['markLead']} frames after the message arrives ({m_at}).")
                if at > end - LIMITS["endHold"]:
                    err(f"{where} lands at frame {at}, too close to the insert's end.")
                on_word(at, where)
    elif fmt == "list":
        title = text(data.get("title"), "list title", LIMITS["titleChars"])
        header(title, "The title")
        if title and wrap_lines(title, "title") > LIMITS["titleLines"]:
            err(f"The list title takes more than {LIMITS['titleLines']} lines; shorten it.")
        items = timed(data.get("items"), "items", LIMITS["minItems"], LIMITS["maxItems"])
        for i, it in enumerate(items):
            if not set(it) <= {"at", "lead", "text"}:
                err(f"Item {i + 1} is {{at, lead, text}}.")
            lead = text(it.get("lead"), f"Item {i + 1} lead", LIMITS["leadChars"])
            if lead and not text_fit.fits_at(lead, LEAD_BOX[1], LEAD_BOX[0]):
                err(f"Item {i + 1} lead does not fit one line of its row; shorten it.")
            body = text(it.get("text"), f"Item {i + 1} text", LIMITS["itemChars"])
            if body and wrap_lines(body, "item") > LIMITS["itemLines"]:
                err(f"Item {i + 1} text takes more than {LIMITS['itemLines']} lines; shorten it.")
        arrivals(items, "Item")
        if items and all(isinstance(it.get("text"), str) for it in items) \
                and list_height(title, items) > LAYOUT["listBudget"]:
            err("The list does not fit in the frame; shorten the rows or show fewer.")
    elif fmt == "quiz":
        q = text(data.get("question"), "question", LIMITS["questionChars"])
        if q and wrap_lines(q, "question") > LIMITS["questionLines"]:
            err(f"The question takes more than {LIMITS['questionLines']} lines; shorten it.")
        options = timed(data.get("options"), "options", LIMITS["minOptions"], LIMITS["maxOptions"])
        for i, o in enumerate(options):
            if not set(o) <= {"at", "text"}:
                err(f"Option {i + 1} is {{at, text}}.")
            opt = text(o.get("text"), f"Option {i + 1} text", LIMITS["optionChars"])
            if opt and not one_line_fits(opt, "option"):
                err(f"Option {i + 1} does not fit its row; shorten it (wide letters take more room).")
        arrivals(options, "Option", first_at_start=False)
        answer, lock = data.get("answer"), data.get("lockAt")
        if not _int(answer) or not 0 <= answer < max(1, len(options)):
            err("answer is the index (from 0) of the right option.")
        if not _int(lock):
            err("lockAt is the frame the answer locks in.")
        else:
            last = max([o["at"] for o in options if _int(o.get("at"))] or [start])
            if lock < last + LIMITS["minGap"]:
                err(f"The answer locks at frame {lock}, before every option has been read; lock it at least "
                    f"{LIMITS['minGap']} frames after the last option ({last}).")
            if lock > end - LIMITS["endHold"]:
                err(f"The answer locks at frame {lock}, too close to the insert's end.")
            on_word(lock, "The answer")
    else:  # strap
        kicker = text(data.get("kicker"), "kicker", LIMITS["kickerChars"])
        header(kicker, "The kicker")
        head = text(data.get("headline"), "headline", LIMITS["headlineChars"])
        if head and wrap_lines(head, "headline") > LIMITS["headlineLines"]:
            err(f"The headline takes more than {LIMITS['headlineLines']} lines; shorten it.")
        text(data.get("date"), "date", LIMITS["dateChars"])
        if data.get("source") is not None:
            text(data.get("source"), "source", LIMITS["sourceChars"])
        marks = data.get("marks", [])
        if not isinstance(marks, list) or len(marks) > LIMITS["maxStrapMarks"] \
                or not all(isinstance(k, dict) and set(k) <= {"at", "match"} for k in marks):
            err(f"marks lists at most {LIMITS['maxStrapMarks']} marks {{at, match}} on the headline.")
            marks = []
        for i, k in enumerate(marks):
            if not isinstance(k.get("match"), str) or not k["match"] or k["match"] not in head:
                err(f"Mark {i + 1}: match must be words in the headline as written.")
            elif len(k["match"]) > LIMITS["markChars"]:
                err(f"Mark {i + 1}: match is at most {LIMITS['markChars']} characters.")
            elif not text_fit.fits_at(k["match"], WRAP["headline"][1], WRAP["headline"][0]):
                err(f"Mark {i + 1}: the marked words are wider than a headline line; mark fewer words.")
            elif _overlaps(head, k["match"], [o.get("match") for o in marks[:i]]):
                err(f"Mark {i + 1}: its words overlap another mark on the headline; mark different words.")
            at = k.get("at")
            if not _int(at) or not start + LIMITS["markLead"] <= at <= end - LIMITS["endHold"]:
                err(f"Mark {i + 1} needs an at inside the insert, after the headline is on screen.")
            else:
                on_word(at, f"Mark {i + 1}")
        flap = data.get("flap")
        if flap is not None:
            if not isinstance(flap, dict) or set(flap) != {"label", "from", "to", "at"}:
                err("flap is {label, from, to, at}: a value changing on a split-flap board.")
            else:
                text(flap.get("label"), "flap.label", LIMITS["flapLabelChars"])
                a = text(flap.get("from"), "flap.from", LIMITS["flapChars"])
                b = text(flap.get("to"), "flap.to", LIMITS["flapChars"])
                if a and a == b:
                    err("flap.from and flap.to are the same; the board flips from one value to another.")
                at = flap.get("at")
                flipping = flap_frames(a or "", b or "")
                if not _int(at) or not start + LIMITS["markLead"] <= at <= end - LIMITS["endHold"]:
                    err("flap.at must be inside the insert, after the headline is on screen.")
                elif at + flipping > end - LIMITS["endHold"]:
                    err(f"The flap takes {flipping} frames to flip its changing tiles and would still be flipping "
                        f"at the insert's end; start it by frame {end - LIMITS['endHold'] - flipping}.")
                else:
                    on_word(at, "The flap")

    # Nothing may hold still for long.
    still = round(LIMITS["maxStillSeconds"] * fps)
    frames = change_frames(data, start)
    for a, b in zip(frames, frames[1:]):
        if b - a > still:
            err(f"Nothing changes for {(b - a) / fps:.1f} s from frame {a}; the longest still stretch is "
                f"{LIMITS['maxStillSeconds']} s. Add a message, a row, a mark or end the insert sooner.")
            break
    if end - frames[-1] > still + LIMITS["endHold"]:
        err(f"Nothing changes for the last {(end - frames[-1]) / fps:.1f} s of the insert; add a change or end the "
            "insert sooner.")
    return errors


def insert_unit_windows(entry: dict) -> list[tuple[int, int]]:
    """(start, end) between every change of one Format Packs insert, for the text audit."""
    props = entry.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    s, d = entry.get("startFrame"), entry.get("durationInFrames")
    if not isinstance(data, dict) or not (_int(s) and _int(d)):
        return []
    frames = [f for f in change_frames(data, s) if s <= f < s + d]
    return [(a, b) for a, b in zip(frames, frames[1:] + [s + d]) if b > a]


def is_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(scenes: list) -> str:
    """FormatPacks is never one of a video's scenes: it is an insert style."""
    if any(is_scene(s) for s in scenes or []):
        return ("FormatPacks is never one of a video's scenes: Format Packs is an insert style. Put the thread, list, "
                "quiz or strap in the config's \"inserts\" list, over a segment the script marks as a format_packs "
                "insert, and build the scenes in the video's own style.")
    return ""
