#!/usr/bin/env python3
"""Check formula routing against the fixed topic set.

Sends every topic in tubematic_core/tests/fixtures/formula_routing_cases.json
through the same instructions the agent follows (the tubematic-formula-routing
skill) and the same candidate list it reads (get_video's
formula_routing.candidates), using the Claude Code CLI. Then it scores each
pick against the topic's expected formulas and writes a Markdown report.

A topic with an angle is routed with it, as get_video returns it (angle,
angle_kind and the derived angle_formula); a topic without one is routed
from the topic alone. A topic marked experimental is routed with the setting
auto_experimental_formulas on; every other topic with it off, as a fresh
install runs. A topic with a style is routed as a video in that style; one
without as a video Auto gave the mixed scene system.

Run it by hand before and after a formula or the skill changes, and compare
the reports. It needs no Tubematic install and no database; it needs `claude`
on PATH, logged in. It makes one short model call per topic (no tools), on
your Claude subscription or API key, whichever the CLI uses.

    python3 scripts/eval_formula_routing.py                  # sonnet, every topic
    python3 scripts/eval_formula_routing.py --model opus --only "password"
    python3 scripts/eval_formula_routing.py --out /tmp/formula-routing.md

Never run in CI: routing is a model's judgement, so the result varies from run
to run. CI checks the topic set itself
(tubematic_core/tests/test_formula_routing.py).
"""
import argparse
import datetime
import json
import pathlib
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from eval_style_routing import ask, verdict  # noqa: E402
from tubematic_core import angles as tangles  # noqa: E402
from tubematic_core import formulas as tformulas  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

SKILL = REPO / "agent_files" / "skills" / "tubematic-formula-routing" / "SKILL.md"
CASES = REPO / "tubematic_core" / "tests" / "fixtures" / "formula_routing_cases.json"
DEFAULT_OUT_DIR = REPO / "docs_private" / "reports" / "formula-routing"

INSTRUCTION = """\
You are the Tubematic agent running the tubematic-formula-routing skill below for one video.
You have no tools in this run. Do every step of the skill in your head, then, instead of
calling choose_script_formula and add_comment, answer with ONLY one JSON object and nothing
else:

{"formula": "<candidate id>", "runner_up": "<candidate id or empty>", "reason": "<one sentence>",
 "repeat_reason": "<one sentence, or empty>", "shape": "<your Step 1 shape, one line>",
 "scores": {"<candidate id>": <points>, ...}}

The skill:

"""


def build_prompt(case: dict) -> str:
    """get_video as the skill reads it: a video at TOPIC_APPROVED whose style
    is decided and whose formula is not."""
    style = case.get("style", "")
    video = {
        "video_id": "vid_eval",
        "status": "TOPIC_APPROVED",
        "title": case["title"],
        "topic": case["brief"],
        "comments": [],
        # As get_video returns it: all three empty for a topic with no angle.
        "angle": case.get("angle", ""),
        "angle_kind": case.get("angle_kind", ""),
        "angle_formula": tangles.formula_for(case.get("angle_kind", "")),
        "visual_style": style or tvs.AUTO,
        "style": tvs.agent_view(style),
        "style_routing": {"decided": True, "pick": style or tvs.SCENES},
        "formula_routing": {
            "decided": False, "pick": "", "runner_up": "", "reason": "", "choice": "",
            "candidates": tformulas.routing_candidates(
                style, bool(case.get("experimental")), case.get("recent", [])),
            "recent": {"formulas": list(case.get("recent", [])), "hook_types": []},
        },
    }
    return (f"get_video(\"vid_eval\") returned:\n\n```json\n{json.dumps(video, indent=2)}\n```\n\n"
            "Pick this video's script formula.")


def by_formula(rows: list[dict]) -> list[tuple]:
    """(formula, topics expecting it first, best picks, best-or-acceptable
    picks) for every formula some topic expects first, in formula order."""
    out = []
    for fid in tformulas.FORMULAS:
        mine = [r for r in rows if r["case"]["expect"][0] == fid]
        if mine:
            out.append((fid, len(mine), sum(r["verdict"] == "best" for r in mine),
                        sum(r["verdict"] in ("best", "ok") for r in mine)))
    return out


def render_report(rows: list[dict], model: str, started: str) -> str:
    n = len(rows)
    best = sum(r["verdict"] == "best" for r in rows)
    ok = sum(r["verdict"] in ("best", "ok") for r in rows)
    failed = sum(r["verdict"] == "error" for r in rows)
    lines = [
        "# Formula routing eval",
        "",
        f"- Run: {started}, model `{model}`, {n} topics",
        f"- Best pick: {best}/{n} ({best * 100 // max(n, 1)}%)",
        f"- Best or acceptable: {ok}/{n} ({ok * 100 // max(n, 1)}%)",
        f"- Errors: {failed}",
        "",
        "## By formula",
        "",
        "| Formula | Topics expecting it | Best | Best or acceptable |",
        "|---|---|---|---|",
    ]
    lines += [f"| {fid} | {total} | {b} | {o} |" for fid, total, b, o in by_formula(rows)]
    lines += ["", "## By topic", "",
              "| Topic | Style | Expected | Also OK | Picked | Runner-up | Verdict | Reason |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r["case"]
        reason = (r.get("reason") or r.get("error") or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {c['title']} | {c.get('style') or '-'} | {', '.join(c['expect'])} | "
                     f"{', '.join(c['ok']) or '-'} | {r.get('formula') or '-'} | "
                     f"{r.get('runner_up') or '-'} | {r['verdict']} | {reason} |")
    wrong = [r for r in rows if r["verdict"] == "wrong"]
    if wrong:
        lines += ["", "## Wrong picks", ""]
        for r in wrong:
            lines += [f"### {r['case']['title']}", "",
                      f"- Expected {r['case']['expect'][0]}, picked {r['formula']}",
                      f"- Shape: {r.get('shape', '')}",
                      f"- Scores: {json.dumps(r.get('scores', {}))}", ""]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="sonnet", help="model alias or id for the claude CLI (default: sonnet)")
    ap.add_argument("--only", default="", help="only topics whose title contains this text")
    ap.add_argument("--jobs", type=int, default=3, help="topics routed at once (default: 3)")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per topic (default: 300)")
    ap.add_argument("--out", default="", help=f"report path (default: {DEFAULT_OUT_DIR}/<time>-<model>.md)")
    args = ap.parse_args(argv)

    if not shutil.which("claude"):
        print("claude is not on PATH: install Claude Code and log in first.", file=sys.stderr)
        return 2
    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]
             if args.only in c["title"]]
    if not cases:
        print(f"No topic title contains {args.only!r}.", file=sys.stderr)
        return 2
    system = INSTRUCTION + SKILL.read_text(encoding="utf-8")
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def run(case):
        try:
            answer, err = ask(build_prompt(case), system, args.model, args.timeout, key="formula")
        except subprocess.TimeoutExpired:
            answer, err = None, f"timed out after {args.timeout} s"
        if not answer:
            return {"case": case, "verdict": "error", "error": err}
        formula = str(answer.get("formula", "")).strip()
        row = {"case": case, "formula": formula, "runner_up": str(answer.get("runner_up", "")),
               "reason": str(answer.get("reason", "")), "shape": str(answer.get("shape", "")),
               "scores": answer.get("scores", {})}
        row["verdict"] = verdict(case, formula) if formula in tformulas.FORMULAS else "wrong"
        print(f"  {row['verdict']:5}  {case['title']}  -> {formula}", flush=True)
        return row

    print(f"Routing {len(cases)} topics with {args.model}...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(run, cases))

    report = render_report(rows, args.model, started)
    out = pathlib.Path(args.out) if args.out else (
        DEFAULT_OUT_DIR / f"{datetime.datetime.now():%Y%m%d-%H%M}-{args.model}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("\n" + "\n".join(report.splitlines()[2:6]))
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
