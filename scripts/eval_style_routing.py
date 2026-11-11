#!/usr/bin/env python3
"""Check Auto's style routing against the fixed topic set (TMDEV-203).

Sends every topic in tubematic_core/tests/fixtures/style_routing_cases.json
through the same instructions the agent follows (the tubematic-style-routing
skill) and the same candidate list it reads (get_video's
style_routing.candidates, here with every style available), using the Claude
Code CLI. Then it scores each pick against the topic's expected styles and
writes a Markdown report.

Run it by hand before and after a style pack lands, and compare the reports.
It needs no Tubematic install and no database; it needs `claude` on PATH,
logged in. It makes one short model call per topic (no tools), on your
Claude subscription or API key, whichever the CLI uses.

    python3 scripts/eval_style_routing.py                  # sonnet, every topic
    python3 scripts/eval_style_routing.py --model opus --only "DNS"
    python3 scripts/eval_style_routing.py --out /tmp/routing-report.md

Never run in CI: routing is a model's judgement, so the result varies from run
to run. CI checks the topic set itself (tubematic_core/tests/test_style_routing.py).
"""
import argparse
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

from tubematic_core import visual_styles as tvs  # noqa: E402

SKILL = REPO / "agent_files" / "skills" / "tubematic-style-routing" / "SKILL.md"
CASES = REPO / "tubematic_core" / "tests" / "fixtures" / "style_routing_cases.json"
DEFAULT_OUT_DIR = REPO / "docs_private" / "reports" / "style-routing"

INSTRUCTION = """\
You are the Tubematic agent running the tubematic-style-routing skill below for one video.
You have no tools in this run. Do every step of the skill in your head, then, instead of
calling choose_visual_style and add_comment, answer with ONLY one JSON object and nothing else:

{"style": "<candidate id>", "runner_up": "<candidate id or empty>", "reason": "<one sentence>",
 "description": "<your Step 1 description, one line>", "scores": {"<candidate id>": <points>, ...}}

The skill:

"""


def build_prompt(case: dict, candidates: list[dict]) -> str:
    video = {
        "video_id": "vid_eval",
        "status": "TOPIC_APPROVED",
        "visual_style": "auto",
        "title": case["title"],
        "topic": case["brief"],
        "mascot": None,
        "comments": [],
        "style_routing": {
            "decided": False, "pick": "", "runner_up": "", "reason": "",
            "candidates": candidates,
            "domain": {"name": case.get("domain", ""), "description": case.get("domain_description", "")},
        },
    }
    return (f"get_video(\"vid_eval\") returned:\n\n```json\n{json.dumps(video, indent=2)}\n```\n\n"
            "Pick this video's style.")


def parse_answer(text: str) -> dict | None:
    """The last JSON object in the model's answer that names a style, or None."""
    decoder = json.JSONDecoder()
    found = None
    for m in re.finditer(r"\{", text):
        try:
            out, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(out, dict) and "style" in out:
            found = out
    return found


def ask(prompt: str, system: str, model: str, timeout: int) -> tuple[dict | None, str]:
    with tempfile.TemporaryDirectory() as cwd:  # no project CLAUDE.md, no skills folder
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", model, "--tools", "",
             "--strict-mcp-config", "--no-session-persistence", "--system-prompt", system,
             prompt],
            cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()[-500:]
    try:
        result = json.loads(proc.stdout).get("result", "")
    except ValueError:
        result = proc.stdout
    answer = parse_answer(result)
    return answer, "" if answer else f"no JSON answer: {result[-300:]}"


def verdict(case: dict, style: str) -> str:
    if style == case["expect"][0]:
        return "best"
    if style in case["expect"] or style in case["ok"]:
        return "ok"
    return "wrong"


def render_report(rows: list[dict], model: str, started: str) -> str:
    n = len(rows)
    best = sum(r["verdict"] == "best" for r in rows)
    ok = sum(r["verdict"] in ("best", "ok") for r in rows)
    failed = sum(r["verdict"] == "error" for r in rows)
    lines = [
        "# Style routing eval",
        "",
        f"- Run: {started}, model `{model}`, {n} topics",
        f"- Styles: {', '.join(tvs.ROUTE_CHOICES)}",
        f"- Best pick: {best}/{n} ({best * 100 // max(n, 1)}%)",
        f"- Best or acceptable: {ok}/{n} ({ok * 100 // max(n, 1)}%)",
        f"- Errors: {failed}",
        "",
        "| Topic | Expected | Also OK | Picked | Runner-up | Verdict | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        c = r["case"]
        reason = (r.get("reason") or r.get("error") or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {c['title']} | {', '.join(c['expect'])} | {', '.join(c['ok']) or '-'} | "
                     f"{r.get('style') or '-'} | {r.get('runner_up') or '-'} | {r['verdict']} | {reason} |")
    wrong = [r for r in rows if r["verdict"] == "wrong"]
    if wrong:
        lines += ["", "## Wrong picks", ""]
        for r in wrong:
            lines += [f"### {r['case']['title']}", "",
                      f"- Expected {r['case']['expect'][0]}, picked {r['style']}",
                      f"- Description: {r.get('description', '')}",
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
    cases = [c for c in json.loads(CASES.read_text())["cases"] if args.only in c["title"]]
    if not cases:
        print(f"No topic title contains {args.only!r}.", file=sys.stderr)
        return 2
    candidates = tvs.routing_candidates(openai_key_set=True, gpu_status="working", has_mascot=False)
    system = INSTRUCTION + SKILL.read_text()
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def run(case):
        try:
            answer, err = ask(build_prompt(case, candidates), system, args.model, args.timeout)
        except subprocess.TimeoutExpired:
            answer, err = None, f"timed out after {args.timeout} s"
        if not answer:
            return {"case": case, "verdict": "error", "error": err}
        style = str(answer.get("style", "")).strip()
        row = {"case": case, "style": style, "runner_up": str(answer.get("runner_up", "")),
               "reason": str(answer.get("reason", "")), "description": str(answer.get("description", "")),
               "scores": answer.get("scores", {})}
        row["verdict"] = verdict(case, style) if style in tvs.ROUTE_CHOICES else "wrong"
        print(f"  {row['verdict']:5}  {case['title']}  -> {style}", flush=True)
        return row

    print(f"Routing {len(cases)} topics with {args.model}...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(run, cases))

    report = render_report(rows, args.model, started)
    out = pathlib.Path(args.out) if args.out else (
        DEFAULT_OUT_DIR / f"{datetime.datetime.now():%Y%m%d-%H%M}-{args.model}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print("\n" + "\n".join(report.splitlines()[2:7]))
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
