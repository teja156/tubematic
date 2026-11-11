"""Script formulas: the structures a script can follow, one data file per formula.

A formula is a JSON file in `formulas/`, named for the formula's id. It says
which topics it suits, how long the script runs, the beats in order with each
beat's share of the script, the shapes its opening can take, what holds the
viewer, how it ends, and a fill-in template. A formula is structure only: how
a line sounds belongs to the script profile, and what a segment shows belongs
to the visual style.

The script-writing skill's `formulas/<id>.md` files and its decision table are
rendered from this data (scripts/gen_formula_references.py; a test keeps them
equal), the MCP server checks a script's recorded formula and hook types
against it, and the dashboard reads the labels through GET /script-formulas.

Free of Flask and of I/O beyond reading the files once at import. A malformed
file raises at import, so a bad file stops the process at start-up rather than
at the first script that names it.
"""
import json
import pathlib

FORMULAS_DIR = pathlib.Path(__file__).resolve().parent / "formulas"

# The hard length limit of every script, whatever its formula: three minutes
# at the measured speaking rate, past which a video is no longer a Short.
WORD_CEILING = 450
# No formula's band may start below this: a script shorter than about fifteen
# seconds has no room for a turn.
WORD_FLOOR = 40

# What an opening can be, as one closed list shared by every formula, so
# openings can be compared across formulas. A formula's hook shapes each carry
# one of these, and a script records the type of the opening it kept.
HOOK_TYPES = {
    "paradox": "Paradox",
    "problem": "The viewer's problem",
    "question": "Question",
    "myth": "Belief, then break",
    "claim": "Flat claim",
    "number": "Number",
    "scene": "Scene in motion",
    "result": "Result first",
    "anomaly": "Anomaly",
    "quote": "Spoken line",
    "what_if": "What if",
    "frame": "Both ends named",
}

FAMILIES = ("explain", "story", "ladder")

# The longest a beat's name may be. A script segment carries its beat's name
# as a label, and the script write refuses a longer one.
BEAT_NAME_MAX_LEN = 60

# The SQL that empties a video's script record (migration 0023): the formula,
# the kept opening's type, the drafted openings and the stored warnings. For a
# write that replaces the script with words the record does not describe.
RECORD_CLEAR_SET = ("formula_id = '', hook_type = '', hook_alternatives = '', "
                    "script_warnings = ''")

_TEXT_KEYS = ("label", "line", "holds", "ending", "template")
_LIST_KEYS = ("best_for", "also_for", "avoid_for", "pitfalls")
_KEYS = {"id", "order", "family", "words", "beats", "hooks", *_TEXT_KEYS, *_LIST_KEYS}
MIN_HOOK_SHAPES = 3


class FormulaError(ValueError):
    """A formula file that does not match the schema below."""


def _check_formula(path: pathlib.Path, data) -> dict:
    """Validate one formula; returns it unchanged. Every rule here is one a
    caller relies on: the skill's reference file is rendered from these fields
    and the script write checks against them."""
    where = path.name

    def fail(msg):
        raise FormulaError(f"formula {where}: {msg}")

    def is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    if not isinstance(data, dict):
        fail("must be a JSON object")
    if set(data) != _KEYS:
        fail(f"must have exactly the keys {sorted(_KEYS)}")
    if data["id"] != path.stem:
        fail(f"id {data['id']!r} must equal the file name {path.stem!r}")
    if not is_int(data["order"]):
        fail("order must be a whole number")
    if data["family"] not in FAMILIES:
        fail(f"family must be one of {FAMILIES}")
    for key in _TEXT_KEYS:
        if not isinstance(data[key], str) or not data[key].strip():
            fail(f"{key} must be a non-empty string")

    def one_line(value, where_):
        # Every text is rendered into a Markdown table cell or a list item.
        if "|" in value or "\n" in value:
            fail(f"{where_} must be one line with no | character")

    for key in _TEXT_KEYS:
        one_line(data[key], key)
    for key in _LIST_KEYS:
        val = data[key]
        if not isinstance(val, list) or not all(isinstance(s, str) and s.strip() for s in val):
            fail(f"{key} must be a list of non-empty strings")
        for item in val:
            one_line(item, key)
    if not data["best_for"]:
        fail("best_for must name at least one kind of topic")
    words = data["words"]
    if not (isinstance(words, list) and len(words) == 2 and all(is_int(w) for w in words)
            and WORD_FLOOR <= words[0] < words[1] <= WORD_CEILING):
        fail(f"words must be [min, max] with {WORD_FLOOR} <= min < max <= {WORD_CEILING}")
    beats = data["beats"]
    if not isinstance(beats, list) or len(beats) < 3:
        fail("beats must be a list of at least three beats")
    at = 0
    for i, beat in enumerate(beats):
        if not isinstance(beat, dict) or set(beat) != {"name", "from", "to", "job"}:
            fail(f"beats[{i}] must have exactly the keys name, from, to, job")
        if not all(isinstance(beat[k], str) and beat[k].strip() for k in ("name", "job")):
            fail(f"beats[{i}] name and job must be non-empty strings")
        one_line(beat["name"], f"beats[{i}].name")
        one_line(beat["job"], f"beats[{i}].job")
        if len(beat["name"]) > BEAT_NAME_MAX_LEN:
            fail(f"beats[{i}].name must be at most {BEAT_NAME_MAX_LEN} characters")
        if not (is_int(beat["from"]) and is_int(beat["to"])) or beat["from"] != at \
                or beat["to"] <= beat["from"]:
            fail(f"beats[{i}] must start at {at} percent, where the beat before it ends, "
                 "and end later")
        at = beat["to"]
    if at != 100:
        fail("the last beat must end at 100 percent")
    names = [b["name"] for b in beats]
    if len(set(names)) != len(names):
        fail("two beats share a name")
    hooks = data["hooks"]
    if not isinstance(hooks, list):
        fail("hooks must be a list")
    for i, hook in enumerate(hooks):
        if not isinstance(hook, dict) or set(hook) != {"type", "shape"}:
            fail(f"hooks[{i}] must have exactly the keys type, shape")
        if hook["type"] not in HOOK_TYPES:
            fail(f"hooks[{i}].type must be one of {sorted(HOOK_TYPES)}")
        if not isinstance(hook["shape"], str) or not hook["shape"].strip():
            fail(f"hooks[{i}].shape must be a non-empty string")
        one_line(hook["shape"], f"hooks[{i}].shape")
    types = [h["type"] for h in hooks]
    # The writer drafts three openings of different types for the formula it
    # chose, so every formula has to offer three.
    if len(set(types)) != len(types) or len(types) < MIN_HOOK_SHAPES:
        fail(f"hooks must offer at least {MIN_HOOK_SHAPES} shapes, each of a different type")
    return data


def _load() -> dict:
    formulas = {}
    for path in sorted(FORMULAS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise FormulaError(f"formula {path.name}: not valid JSON ({exc})") from exc
        formulas[path.stem] = _check_formula(path, data)
    if not formulas:
        raise FormulaError(f"no formulas found in {FORMULAS_DIR}")
    for key in ("order", "label"):
        values = [f[key] for f in formulas.values()]
        if len(set(values)) != len(values):
            raise FormulaError(f"two formulas share a {key} value")
    return dict(sorted(formulas.items(), key=lambda kv: kv[1]["order"]))


FORMULAS = _load()


def word_band(formula_id: str):
    """(min, max) words for a formula, or None for no formula or an unknown one."""
    formula = FORMULAS.get(formula_id or "")
    return tuple(formula["words"]) if formula else None


def hook_types(formula_id: str) -> tuple:
    """The hook types a formula's opening shapes offer, in file order."""
    formula = FORMULAS.get(formula_id or "")
    return tuple(h["type"] for h in formula["hooks"]) if formula else ()


def label(formula_id: str) -> str:
    """A formula's display name; the id itself when it is not a known formula
    (a video written under a formula a later version dropped)."""
    formula = FORMULAS.get(formula_id or "")
    return formula["label"] if formula else (formula_id or "")


def public_list() -> dict:
    """What GET /script-formulas serves: enough to label a video's record."""
    return {
        "formulas": [{"id": f["id"], "label": f["label"], "family": f["family"],
                      "line": f["line"], "words": list(f["words"])}
                     for f in FORMULAS.values()],
        "hook_types": [{"id": k, "label": v} for k, v in HOOK_TYPES.items()],
    }


def _cell(items: list) -> str:
    return "; ".join(items) if items else "-"


def decision_table_markdown() -> str:
    """The script-writing skill's table for choosing a formula from the shape
    of a topic. One row per formula, in formula order."""
    lines = ["| Formula (`formula_id`) | First choice when the topic is | Also fits | Not for | Words |",
             "|---|---|---|---|---|"]
    for f in FORMULAS.values():
        lines.append(f"| **{f['label']}** (`{f['id']}`) | {_cell(f['best_for'])} | "
                     f"{_cell(f['also_for'])} | {_cell(f['avoid_for'])} | "
                     f"{f['words'][0]} to {f['words'][1]} |")
    return "\n".join(lines) + "\n"


def reference_markdown(formula: dict) -> str:
    """One formula's reference file for the script-writing skill."""
    lo, hi = formula["words"]
    out = [f"# {formula['label']}", "",
           f"`formula_id`: `{formula['id']}`", "",
           formula["line"], "",
           "## Length", "",
           f"{lo} to {hi} words across every segment's `voice`. Stay inside the band: the beats "
           "below are sized for it.", "",
           "## Beats", "",
           "In this order. A share is the part of the script's words the beat covers; hold each "
           "within a few points.", "",
           "| Beat | Share of the script | Its job |", "|---|---|---|"]
    out += [f"| {b['name']} | {b['from']} to {b['to']}% | {b['job']} |" for b in formula["beats"]]
    out += ["", "## Openings", "",
            "Draft one opening from each of three shapes. The type goes in `hooks[].type`.", "",
            "| Type (`type`) | Shape |", "|---|---|"]
    out += [f"| {HOOK_TYPES[h['type']]} (`{h['type']}`) | {h['shape']} |" for h in formula["hooks"]]
    out += ["", "## What holds the viewer", "", formula["holds"], "",
            "## Ending", "", formula["ending"], "",
            "## Pitfalls", ""]
    out += [f"- {p}" for p in formula["pitfalls"]]
    out += ["", "## Template", "",
            "The shape of the whole script with the facts left out. Fill it with this topic's "
            "facts; never keep its wording.", "",
            f"> {formula['template']}", ""]
    return "\n".join(out)
