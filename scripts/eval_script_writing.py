#!/usr/bin/env python3
"""Compare scripts written with an older script-writing skill and with the current one.

For every topic in scripts/eval_script_topics.json this has a model write the
script twice, once following the skill as it was at a git ref (the "old"
side, default the v2.1.1 tag) and once following the skill in this checkout
(the "new" side, with its formula files), using the Claude Code CLI with no
tools. It then runs the script checks (tubematic_core.script_checks) over
both and saves the scripts side by side with a summary.

Run it by hand before and after a change to the script-writing skill, the
formula files or the checks, and compare the two reports. It needs no
Tubematic install and no database; it needs `claude` on PATH, logged in, and
git for the old side. It makes two model calls per topic, on your Claude
subscription or API key, whichever the CLI uses, and prints what the CLI
reports as their cost.

    python3 scripts/eval_script_writing.py                     # sonnet, every topic, both sides
    python3 scripts/eval_script_writing.py --model opus --only "pudding"
    python3 scripts/eval_script_writing.py --sides new --out /tmp/scripts

Never run in CI: a script is a model's writing, so the result varies from run
to run. CI checks this file's plumbing (scripts/tests/test_eval_script_writing.py).
"""
import argparse
import collections
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tubematic_core import formulas as tformulas  # noqa: E402
from tubematic_core import script_checks as tchecks  # noqa: E402

SKILL_REL = "agent_files/skills/tubematic-script-writing-skill"
SKILL_DIR = REPO / SKILL_REL
TOPICS = REPO / "scripts" / "eval_script_topics.json"
DEFAULT_OUT_DIR = REPO / "docs_private" / "reports" / "script-baseline"
DEFAULT_OLD_REF = "v2.1.1"
SIDES = ("old", "new")

INSTRUCTION = """\
You are the Tubematic agent running the tubematic-script-writing-skill below for one video.
You have no tools in this run. The results of the calls the skill makes first are given to
you in the prompt. Do every step of the skill in your head, then, instead of calling
update_video, answer with ONLY one JSON object and nothing else, holding the arguments the
skill tells you to pass to update_video:

{"script_segments": [{"id": "seg-1", "voice": "...", "visual": "..."}, ...],
 "publish_title": "...", "publish_description": "..."}

If the skill tells you to pass other arguments to update_video with the script, add them to
the same object under the names the skill uses.

The skill:

"""

REFERENCES_NOTE = """

---

The skill tells you to read one file from its `formulas/` folder. You have no tools, so every
file in that folder follows. Use only the one for this video's formula.

"""

# Markup a script's `voice` may carry, removed to get the words as spoken: a
# tag is reduced to what it wraps, a pause tag to nothing.
_TAG = re.compile(r"<[^>]+>")
_PAUSE = re.compile(r"\[(?:short |long )?pause\]")


def old_skill(ref: str) -> str:
    """The skill's SKILL.md as it was at a git ref."""
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{SKILL_REL}/SKILL.md"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"cannot read the skill at {ref!r}: {proc.stderr.strip()}")
    return proc.stdout


def new_skill() -> str:
    """This checkout's SKILL.md with every formula file after it."""
    parts = [(SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"), REFERENCES_NOTE]
    for path in sorted((SKILL_DIR / "formulas").glob("*.md")):
        parts.append(f"=== formulas/{path.name} ===\n\n{path.read_text(encoding='utf-8')}\n")
    return "".join(parts)


def build_prompt(topic: dict) -> str:
    """What the skill's first calls would return for this topic: a video at
    TOPIC_APPROVED with no script profile, on the default voice model."""
    video = {
        "video_id": "vid_eval", "status": "TOPIC_APPROVED", "title": topic["title"],
        "topic": topic["brief"], "comments": [], "script_profile_id": "",
        "script": None, "script_segments": None, "formula_id": "", "hook_alternatives": [],
        "script_warnings": [], "visual_style": "auto",
        "style": {"id": "auto", "label": "Auto", "script": ""},
        # The formula is picked before the script. The current skill writes in
        # this pick; a skill from before picks existed ignores it and chooses.
        "formula_routing": {"decided": True, "pick": topic["formula"], "runner_up": "",
                            "reason": "", "choice": "", "candidates": [],
                            "recent": {"formulas": [], "hook_types": []}},
        "elevenlabs_model_id": "eleven_multilingual_v2", "pronunciation_mode": "respell",
    }
    status = {"pronunciation_lexicon": [], "user_preferences": ""}
    return (f"get_video(\"vid_eval\") returned:\n\n```json\n{json.dumps(video, indent=2)}\n```\n\n"
            f"get_pipeline_status() returned (the parts this skill reads):\n\n"
            f"```json\n{json.dumps(status, indent=2)}\n```\n\nWrite this video's script.")


def parse_answer(text: str) -> dict | None:
    """The last JSON object in the model's answer that holds a script, or None."""
    decoder = json.JSONDecoder()
    found = None
    for m in re.finditer(r"\{", text):
        try:
            out, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(out, dict) and isinstance(out.get("script_segments"), list):
            found = out
    return found


def spoken(text: str) -> str:
    """A `voice` text as it is spoken: markup removed, whitespace collapsed."""
    return " ".join(_PAUSE.sub(" ", _TAG.sub("", text or "")).split())


def score(answer: dict) -> dict:
    """The script's words, its record and the checks' findings."""
    segments = [s for s in answer.get("script_segments", []) if isinstance(s, dict)]
    script = " ".join(spoken(str(s.get("voice", ""))) for s in segments)
    formula_id = str(answer.get("formula_id") or "")
    hooks = [h for h in answer.get("hooks") or [] if isinstance(h, dict)]
    kept = next((h for h in hooks if h.get("kept")), {})
    warnings = tchecks.check(
        script, publish_title=str(answer.get("publish_title") or ""),
        formula_id=formula_id if formula_id in tformulas.FORMULAS else "",
        kept_hook=spoken(str(kept.get("text", ""))))
    return {"script": script, "words": tchecks.word_count(script), "segments": segments,
            "formula_id": formula_id, "hook_type": str(kept.get("type", "")), "hooks": hooks,
            "publish_title": str(answer.get("publish_title") or ""),
            "warnings": warnings}


def ask(prompt: str, system: str, model: str, timeout: int) -> tuple[dict | None, str, float]:
    """(answer, error, reported cost in dollars) for one model call."""
    with tempfile.TemporaryDirectory() as cwd:  # no project CLAUDE.md, no skills folder
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", model, "--tools", "",
             "--strict-mcp-config", "--no-session-persistence", "--system-prompt", system,
             prompt],
            cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()[-500:], 0.0
    try:
        data = json.loads(proc.stdout)
        result, cost = data.get("result", ""), float(data.get("total_cost_usd") or 0.0)
    except ValueError:
        result, cost = proc.stdout, 0.0
    answer = parse_answer(result)
    return answer, "" if answer else f"no JSON answer: {result[-300:]}", cost


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]


def render_topic(topic: dict, results: dict) -> str:
    """One topic's scripts, one side after the other, with their findings."""
    out = [f"# {topic['title']}", "", f"Topic shape: {topic['shape']}", "", topic["brief"], ""]
    for side in SIDES:
        row = results.get(side)
        if row is None:
            continue
        out += [f"## {side.capitalize()} skill", ""]
        if "error" in row:
            out += [f"No script: {row['error']}", ""]
            continue
        record = f", formula `{row['formula_id']}`, opening `{row['hook_type']}`" \
            if row["formula_id"] else ""
        out += [f"{row['words']} words, {len(row['segments'])} segments{record}. "
                f"Publish title: {row['publish_title']}", ""]
        for seg in row["segments"]:
            beat = f" ({seg['beat']})" if seg.get("beat") else ""
            out += [f"**{seg.get('id', '')}**{beat}: {spoken(str(seg.get('voice', '')))}", "",
                    f"> {seg.get('visual', '')}", ""]
        if row["hooks"]:
            out += ["Openings drafted:", ""]
            out += [f"- `{h.get('type', '')}`{' (used)' if h.get('kept') else ''}: "
                    f"{h.get('text', '')}" + (f" ({h['note']})" if h.get("note") else "")
                    for h in row["hooks"]]
            out.append("")
        out += ["Warnings: " + (", ".join(w["id"] for w in row["warnings"]) or "none"), ""]
    return "\n".join(out)


def render_summary(rows: list, model: str, old_ref: str, started: str, cost: float) -> str:
    """The run's summary: one line per topic, then each warning's count per side."""
    out = ["# Script writing: old skill against new", "",
           f"Model `{model}`, {len(rows)} topics, old skill from `{old_ref}`, started {started}. "
           f"Cost reported by the CLI: ${cost:.2f}.", "",
           "| Topic | Old words | Old warnings | New words | New warnings | Formula | Opening |",
           "|---|---|---|---|---|---|---|"]

    def cell(row, key):
        if row is None:
            return "-"
        if "error" in row:
            return "error"
        return str(row["words"]) if key == "words" else \
            (", ".join(w["id"] for w in row["warnings"]) or "none")

    counts = {side: collections.Counter() for side in SIDES}
    words = {side: [] for side in SIDES}
    for item in rows:
        old, new = item["results"].get("old"), item["results"].get("new")
        ok_new = new if new and "error" not in new else {}
        out.append(f"| {item['topic']['title']} | {cell(old, 'words')} | {cell(old, 'warn')} | "
                   f"{cell(new, 'words')} | {cell(new, 'warn')} | "
                   f"{ok_new.get('formula_id') or '-'} | {ok_new.get('hook_type') or '-'} |")
        for side in SIDES:
            row = item["results"].get(side)
            if row and "error" not in row:
                words[side].append(row["words"])
                counts[side].update(w["id"] for w in row["warnings"])
    out += ["", "## Warnings by check", "", "| Check | Old | New |", "|---|---|---|"]
    for check in sorted(set(counts["old"]) | set(counts["new"])):
        out.append(f"| `{check}` | {counts['old'][check]} | {counts['new'][check]} |")
    out += ["", "## Length", ""]
    for side in SIDES:
        if words[side]:
            ws = sorted(words[side])
            out.append(f"- {side.capitalize()}: {len(ws)} scripts, {ws[0]} to {ws[-1]} words, "
                       f"median {ws[len(ws) // 2]}.")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="sonnet", help="model alias or id for the claude CLI (default: sonnet)")
    ap.add_argument("--old-ref", default=DEFAULT_OLD_REF,
                    help=f"git ref the old skill is read from (default: {DEFAULT_OLD_REF})")
    ap.add_argument("--sides", default="old,new", help="which sides to write: old, new or old,new")
    ap.add_argument("--only", default="", help="only topics whose title contains this text")
    ap.add_argument("--jobs", type=int, default=3, help="model calls at once (default: 3)")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per script (default: 600)")
    ap.add_argument("--out", default="", help=f"report folder (default: {DEFAULT_OUT_DIR}/<time>-<model>)")
    args = ap.parse_args(argv)

    sides = [s.strip() for s in args.sides.split(",") if s.strip()]
    if not sides or any(s not in SIDES for s in sides):
        print(f"--sides must be drawn from {SIDES}.", file=sys.stderr)
        return 2
    if not shutil.which("claude"):
        print("claude is not on PATH: install Claude Code and log in first.", file=sys.stderr)
        return 2
    topics = [t for t in json.loads(TOPICS.read_text())["topics"]
              if args.only.lower() in t["title"].lower()]
    if not topics:
        print(f"No topic title contains {args.only!r}.", file=sys.stderr)
        return 2
    systems = {}
    if "old" in sides:
        systems["old"] = INSTRUCTION + old_skill(args.old_ref)
    if "new" in sides:
        systems["new"] = INSTRUCTION + new_skill()
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def run(job):
        topic, side = job
        try:
            answer, err, cost = ask(build_prompt(topic), systems[side], args.model, args.timeout)
        except subprocess.TimeoutExpired:
            answer, err, cost = None, f"timed out after {args.timeout} s", 0.0
        row = score(answer) if answer else {"error": err}
        note = f"{row['words']} words, {len(row['warnings'])} warnings" if answer else "error"
        print(f"  {side:3}  {topic['title']}: {note}", flush=True)
        return topic["title"], side, row, cost

    jobs = [(t, s) for t in topics for s in sides]
    print(f"Writing {len(jobs)} scripts with {args.model}...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        done = list(pool.map(run, jobs))

    rows = [{"topic": t, "results": {side: row for title, side, row, _ in done if title == t["title"]}}
            for t in topics]
    total = sum(cost for *_, cost in done)
    out = pathlib.Path(args.out) if args.out else (
        DEFAULT_OUT_DIR / f"{datetime.datetime.now():%Y%m%d-%H%M}-{args.model}")
    out.mkdir(parents=True, exist_ok=True)
    for item in rows:
        (out / f"{slug(item['topic']['title'])}.md").write_text(
            render_topic(item["topic"], item["results"]))
    summary = render_summary(rows, args.model, args.old_ref, started, total)
    (out / "summary.md").write_text(summary)
    (out / "results.json").write_text(json.dumps(rows, indent=1))
    print("\n" + summary)
    print(f"Report folder: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
