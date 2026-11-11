"""Topic angles: what a topic gives its opening, recorded with the topic.

An angle is one sentence saying what the hook will use (the paradox, the
failure, the belief, the incident), plus its kind from a closed list and a
score for how strong it is. Research files a topic only when it has one; a
person's own topic may come without. The script writer starts from the
formula the angle's kind is the first choice for.

A kind is about the topic. It is a different list from
formulas.HOOK_TYPES, which says how one opening line is worded.

The MCP server and the Flask API both validate through angle_error, the
research skill's reference block and the mining prompt are rendered from this
module (scripts/gen_angle_reference.py; a test keeps the skill equal), and the
dashboard reads the kinds through GET /angle-kinds.

Free of Flask and of I/O beyond what importing formulas does.
"""
from . import formulas as tformulas

# The longest an angle sentence may be: one sentence a person reads beside
# the topic. The same limit as a style pick's reason.
ANGLE_MAX_CHARS = 300
ANGLE_SCORE_MAX = 10
# A research proposal whose angle scores under this is not filed. The same
# floor as the producibility score's.
ANGLE_MIN_SCORE = 5

# id -> label, what the topic must hold for an angle of this kind to be
# honest, and the formula the kind is the first choice for. Each `means` is
# written from that formula's best_for and avoid_for.
ANGLE_KINDS = {
    "paradox": {
        "label": "Paradox",
        "means": "Something the viewer owns or uses works in a way that seems impossible, or a "
                 "system does something that looks like a loss and is not. The viewer has felt "
                 "the contradiction; a definition with a 'but' added does not count.",
        "formula": "paradox-mechanism-reframe",
    },
    "broken_expectation": {
        "label": "Broken expectation",
        "means": "A tool did something that looks wrong, and the viewer has met it or can "
                 "reproduce it. There is a visible symptom.",
        "formula": "broken-expectation",
    },
    "process": {
        "label": "Process",
        "means": "A process with a natural order that the viewer starts without seeing the rest "
                 "of: a request, a boot, a login, a payment. One thing can be followed from start "
                 "to finish, and the end is something the viewer does not already know.",
        "formula": "follow-the-flow",
    },
    "myth": {
        "label": "Myth",
        "means": "A belief most people hold is wrong, and a real mechanism, study or figure "
                 "shows it. Not a trivia correction, and not a myth already debunked everywhere.",
        "formula": "myth-break-model",
    },
    "design_question": {
        "label": "Design question",
        "means": "A design decision that looks stupid from outside, or a question newcomers keep "
                 "asking, answered by a real rule or constraint that has a source.",
        "formula": "why-dont-they-just",
    },
    "incident": {
        "label": "Incident",
        "means": "A real outage, loss, bug or breach with a timeline: a public account gives "
                 "times, numbers and a decision a person made.",
        "formula": "incident-file",
    },
    "scheme": {
        "label": "Scheme",
        "means": "A scam, a fraud, a loophole or an exploit that works as a loop of four steps "
                 "or fewer, run by someone who meant it.",
        "formula": "scheme-machine",
    },
    "anomaly": {
        "label": "Anomaly",
        "means": "Evidence that looked wrong: every reading normal during a failure, a record "
                 "that should not exist. The anomaly is real and its answer is not common "
                 "knowledge.",
        "formula": "anomaly-file",
    },
    "scene": {
        "label": "Scene",
        "means": "One person inside one moment: a near miss, a strange true incident, an "
                 "ordinary life in a big event. The moment comes from a real account, or from "
                 "the story's own canon when the subject is a story. Not a biography, and "
                 "testimony is never invented.",
        "formula": "scene-story",
    },
    "measure": {
        "label": "Measure",
        "means": "Something with a natural measure the video can climb: size, cost, speed, time "
                 "to break, risk. The numbers are real and each has something to compare it to.",
        "formula": "escalating-ladder",
    },
}

# The angle score's signals as (points, signal). Summed and clamped to
# 0..ANGLE_SCORE_MAX. The positive signals add up to the maximum.
ANGLE_RUBRIC = (
    (3, "The angle names one thing the viewer waits for: an outcome, a cause, a number or a "
        "name the video can hold back and then give"),
    (2, "The viewer has met it: they own the thing, have seen the failure or hold the belief"),
    (2, "The material you read gives real specifics for it: a named incident, a date, a figure, "
        "a pair of numbers"),
    (2, "It carries a stake or a contrast: a loss, a before and after, a number against a "
        "benchmark, one actor who meant it"),
    (1, "The answer is not common knowledge"),
    (-3, "The angle is a definition, an overview or a list label (\"what X is\", \"five things "
         "about X\")"),
    (-3, "It needs facts the material does not give: an invented incident, person or number"),
    (-2, "The answer is already told everywhere"),
)

_NO_ANGLE = ("A subject with no honest angle is not proposed: leave it out and name it in your "
             "run summary. Do not invent an angle to get past this check.")


def clean(angle):
    """An angle sentence with its whitespace collapsed; any other type is
    returned as it came, for angle_error to refuse."""
    return " ".join(angle.split()) if isinstance(angle, str) else angle


def formula_for(kind) -> str:
    """The formula an angle kind is the first choice for, or '' for no kind
    or an unknown one."""
    spec = ANGLE_KINDS.get(kind) if isinstance(kind, str) else None
    return spec["formula"] if spec else ""


def angle_error(angle, kind, score=0, *, required: bool = False) -> str | None:
    """Why this angle cannot be stored, or None.

    angle is the sentence (already through clean), kind an id from
    ANGLE_KINDS, score a whole number from 0 to ANGLE_SCORE_MAX where 0 means
    unscored. The sentence and the kind are stored together or not at all.
    required is for a research proposal: it must carry an angle that scores
    ANGLE_MIN_SCORE or more.
    """
    for name, value in (("angle", angle), ("angle_kind", kind)):
        if not isinstance(value, str):
            return f"{name} must be a string"
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= ANGLE_SCORE_MAX:
        return (f"angle_score must be a whole number from 0 to {ANGLE_SCORE_MAX} "
                f"(0 = unscored), got {score!r}")
    if not angle and not kind:
        if required:
            return ("A research proposal needs an angle and an angle_kind: one sentence saying "
                    "what the opening will use, and its kind (one of: "
                    f"{', '.join(ANGLE_KINDS)}). {_NO_ANGLE}")
        if score:
            return "angle_score describes an angle: pass it with angle and angle_kind"
        return None
    if not angle or not kind:
        return ("angle and angle_kind are written together: pass the sentence and its kind, or "
                "leave both empty")
    if kind not in ANGLE_KINDS:
        return f"angle_kind {kind!r} is not a kind. Must be one of: {', '.join(ANGLE_KINDS)}"
    if len(angle) > ANGLE_MAX_CHARS:
        return (f"angle is {len(angle)} characters; the limit is {ANGLE_MAX_CHARS} "
                "(one sentence)")
    if required and score < ANGLE_MIN_SCORE:
        return (f"angle_score {score} is below {ANGLE_MIN_SCORE}: this angle is too weak to "
                f"propose. {_NO_ANGLE}")
    return None


def public_list() -> list:
    """What GET /angle-kinds serves: the kinds in order, for labels and pickers."""
    return [{"id": kind, "label": spec["label"], "means": spec["means"]}
            for kind, spec in ANGLE_KINDS.items()]


def _points(points: int) -> str:
    return f"+{points}" if points > 0 else f"−{-points}"


def reference_markdown() -> str:
    """The block the topic-research skill carries: the kinds and the score."""
    out = ["| Kind (`angle_kind`) | The topic has | The script will start from |",
           "|---|---|---|"]
    for kind, spec in ANGLE_KINDS.items():
        out.append(f"| **{spec['label']}** (`{kind}`) | {spec['means']} | "
                   f"{tformulas.label(spec['formula'])} |")
    out += ["",
            f"**Angle score.** Sum the signals and clamp to 0–{ANGLE_SCORE_MAX}. "
            f"A research candidate needs {ANGLE_MIN_SCORE} or more.",
            "",
            "| Signal | Points |", "|---|---|"]
    out += [f"| {signal} | {_points(points)} |" for points, signal in ANGLE_RUBRIC]
    return "\n".join(out) + "\n"


def prompt_text() -> str:
    """The same kinds and score as plain text, for the mining prompt."""
    kinds = "\n".join(f"- {kind}: {spec['means']}" for kind, spec in ANGLE_KINDS.items())
    signals = "; ".join(f"{signal} {_points(points)}" for points, signal in ANGLE_RUBRIC)
    return (
        "Each candidate needs an angle: one sentence, at most "
        f"{ANGLE_MAX_CHARS} characters, saying what the video's opening will use, taken from "
        "what this video says. The angle has a kind, one of:\n"
        f"{kinds}\n"
        "A concept with no honest angle of any kind is left out. Never invent an incident, a "
        "person or a number to make one.\n"
        f"Score the angle: sum these signals and clamp to 0-{ANGLE_SCORE_MAX}. {signals}. "
        f"Under {ANGLE_MIN_SCORE} = skip."
    )
