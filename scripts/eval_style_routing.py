#!/usr/bin/env python3
"""Check Auto's style routing against the fixed topic set (TMDEV-203).

Sends every topic in tubematic_core/tests/fixtures/style_routing_cases.json
through the same instructions the agent follows (the tubematic-style-routing
skill) and the same candidate list it reads (get_video's
style_routing.candidates, here with every style available), using the Claude
Code CLI. Then, for a main style that takes inserts, it asks the
tubematic-insert-routing skill which insert styles the script may use, a
second short call per topic (TMDEV-224; --no-inserts skips it). It scores the
pick against the topic's expected styles and the inserts against its
inserts_expect, and writes a Markdown report.

Run it by hand before and after a style pack lands, and compare the reports.
It needs no Tubematic install and no database; it needs `claude` on PATH,
logged in. It makes one short model call per topic (no tools), on your
Claude subscription or API key, whichever the CLI uses. With --openrouter it
calls that OpenRouter model instead (the cheaper models live agents often run
through OpenCode), with the key in OPENROUTER_API_KEY.

    python3 scripts/eval_style_routing.py                  # sonnet, every topic
    python3 scripts/eval_style_routing.py --model opus --only "DNS"
    python3 scripts/eval_style_routing.py --openrouter deepseek/deepseek-v4.1-flash
    python3 scripts/eval_style_routing.py --out /tmp/routing-report.md

Never run in CI: routing is a model's judgement, so the result varies from run
to run. CI checks the topic set itself (tubematic_core/tests/test_style_routing.py).
"""
import argparse
import datetime
import http.client
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tubematic_core import inserts as tinserts  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

SKILL = REPO / "agent_files" / "skills" / "tubematic-style-routing" / "SKILL.md"
INSERT_SKILL = REPO / "agent_files" / "skills" / "tubematic-insert-routing" / "SKILL.md"
CASES = REPO / "tubematic_core" / "tests" / "fixtures" / "style_routing_cases.json"
DEFAULT_OUT_DIR = REPO / "docs_private" / "reports" / "style-routing"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

INSTRUCTION = """\
You are the Tubematic agent running the tubematic-style-routing skill below for one video.
You have no tools in this run. Do every step of the skill in your head, then, instead of
calling choose_visual_style and add_comment, answer with ONLY one JSON object and nothing else:

{"style": "<candidate id>", "runner_up": "<candidate id or empty>", "reason": "<one sentence>",
 "description": "<your Step 1 description, one line>", "scores": {"<candidate id>": <points>, ...}}

The skill:

"""


INSERT_INSTRUCTION = """\
You are the Tubematic agent running the tubematic-insert-routing skill below for one video. Its
main style is already decided. You have no tools in this run. Do every step of the skill in your
head, then, instead of calling choose_inserts and add_comment, answer with ONLY one JSON object and
nothing else:

{"inserts": ["<insert style id>", ...], "reason": "<one sentence>", "beats": "<your beat list, one line>"}

The skill:

"""


def build_insert_prompt(case: dict, style: str, candidates: list[dict],
                        insert_candidates: list[dict]) -> str:
    """The insert step's question (TMDEV-224): the video as get_video returns
    it once the main style is decided, with its insert_routing."""
    visual_style = tvs.AUTO if style == tvs.SCENES else style
    host = tvs.hosts_inserts(visual_style)
    video = {
        "video_id": "vid_eval",
        "status": "TOPIC_APPROVED",
        "visual_style": visual_style,
        "title": case["title"],
        "topic": case["brief"],
        "comments": [],
        "style_routing": {"decided": True, "pick": style, "candidates": candidates},
        "insert_mode": "auto",
        "insert_styles": None,
        "insert_routing": {
            "decided": False, "mode": "auto", "styles": None, "reason": "",
            "host": host["host"], "transition": host.get("transition", ""),
            "max_styles": tinserts.MAX_STYLES_PER_VIDEO,
            "limits": {"target_seconds": tinserts.TARGET_SECONDS, "max_seconds": tinserts.MAX_SECONDS,
                       "max_share": round(tinserts.MAX_SHARE, 3),
                       "min_main_gap_seconds": tinserts.MIN_MAIN_GAP_SECONDS},
            "candidates": insert_candidates,
        },
    }
    return (f"get_video(\"vid_eval\") returned:\n\n```json\n{json.dumps(video, indent=2)}\n```\n\n"
            "Decide this video's inserts.")


def insert_verdict(case: dict, chosen: list[str]) -> str:
    """"right" when the chosen insert styles are the expected ones (plus any
    in inserts_ok), "wrong" otherwise, "-" when the topic expects nothing in
    particular ("any", or no inserts_expect)."""
    expect = case.get("inserts_expect", "any")
    if expect == "any":
        return "-"
    allowed = set(expect) | set(case.get("inserts_ok", []))
    return "right" if set(expect) <= set(chosen) <= allowed else "wrong"


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


def parse_answer(text: str, key: str = "style") -> dict | None:
    """The last JSON object in the model's answer that holds `key`, or None."""
    decoder = json.JSONDecoder()
    found = None
    for m in re.finditer(r"\{", text):
        try:
            out, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(out, dict) and key in out:
            found = out
    return found


def ask(prompt: str, system: str, model: str, timeout: int,
        key: str = "style") -> tuple[dict | None, str]:
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
    answer = parse_answer(result, key)
    return answer, "" if answer else f"no JSON answer: {result[-300:]}"


def ask_openrouter(prompt: str, system: str, model: str, timeout: int,
                   key: str, answer_key: str = "style") -> tuple[dict | None, str, float]:
    """The same question through OpenRouter's chat completions. Returns the
    answer, an error and the call's cost in dollars (0 when not reported)."""
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    # OpenRouter keeps a slow request open by sending whitespace, so the socket
    # timeout alone never fires: the whole call gets one deadline.
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            chunks = []
            while chunk := resp.read1(65536):  # read() would wait for the whole 64 KB
                chunks.append(chunk)
                if time.monotonic() > deadline:
                    try:  # the chunk that ran past the deadline may have completed the reply
                        json.loads(b"".join(chunks))
                        break
                    except ValueError:
                        return None, f"timed out after {timeout} s", 0.0
            data = json.loads(b"".join(chunks))
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode(errors='replace')[-300:]}", 0.0
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
        return None, f"request failed: {e!r}"[-300:], 0.0
    if not isinstance(data, dict):
        return None, f"no answer: {json.dumps(data)[-300:]}", 0.0
    try:
        cost = float((data.get("usage") or {}).get("cost") or 0)
    except (TypeError, ValueError):
        cost = 0.0
    try:
        result = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return None, f"no answer: {json.dumps(data)[-300:]}", cost
    answer = parse_answer(result, answer_key)
    return answer, "" if answer else f"no JSON answer: {result[-300:]}", cost


def verdict(case: dict, style: str) -> str:
    if style == case["expect"][0]:
        return "best"
    if style in case["expect"] or style in case["ok"]:
        return "ok"
    return "wrong"


def render_report(rows: list[dict], model: str, started: str, cost: float = 0.0) -> str:
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
        *([f"- Cost: ${cost:.4f}"] if cost else []),
    ]
    scored = [r for r in rows if r.get("insert_verdict") in ("right", "wrong")]
    if scored:
        right = sum(r["insert_verdict"] == "right" for r in scored)
        lines.append(f"- Inserts as expected: {right}/{len(scored)} ({right * 100 // len(scored)}%)")
    lines += [
        "",
        "| Topic | Expected | Also OK | Picked | Runner-up | Verdict | Inserts expected | Inserts | Inserts verdict | Reason |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        c = r["case"]
        reason = (r.get("reason") or r.get("error") or "").replace("|", "/").replace("\n", " ")
        expect = c.get("inserts_expect", "any")
        expect = "any" if expect == "any" else (", ".join(expect) or "none")
        chosen = r.get("inserts")
        chosen = "-" if chosen is None else (", ".join(chosen) or "none")
        lines.append(f"| {c['title']} | {', '.join(c['expect'])} | {', '.join(c['ok']) or '-'} | "
                     f"{r.get('style') or '-'} | {r.get('runner_up') or '-'} | {r['verdict']} | "
                     f"{expect} | {chosen} | {r.get('insert_verdict', '-')} | {reason} |")
    wrong = [r for r in rows if r["verdict"] == "wrong"]
    if wrong:
        lines += ["", "## Wrong picks", ""]
        for r in wrong:
            lines += [f"### {r['case']['title']}", "",
                      f"- Expected {r['case']['expect'][0]}, picked {r['style']}",
                      f"- Description: {r.get('description', '')}",
                      f"- Scores: {json.dumps(r.get('scores', {}))}", ""]
    wrong_inserts = [r for r in rows if r.get("insert_verdict") == "wrong"]
    if wrong_inserts:
        lines += ["", "## Wrong inserts", ""]
        for r in wrong_inserts:
            lines += [f"### {r['case']['title']}", "",
                      f"- Main style {r.get('style')}; expected inserts "
                      f"{r['case'].get('inserts_expect')}, chose {r.get('inserts')}",
                      f"- Beats: {r.get('beats', '')}",
                      f"- Reason: {r.get('insert_reason', '')}", ""]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="sonnet", help="model alias or id for the claude CLI (default: sonnet)")
    ap.add_argument("--openrouter", default="", metavar="MODEL",
                    help="route with this OpenRouter model id instead of the claude CLI "
                         "(key in OPENROUTER_API_KEY)")
    ap.add_argument("--only", default="", help="only topics whose title contains this text")
    ap.add_argument("--jobs", type=int, default=3, help="topics routed at once (default: 3)")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per topic (default: 300)")
    ap.add_argument("--out", default="", help=f"report path (default: {DEFAULT_OUT_DIR}/<time>-<model>.md)")
    ap.add_argument("--no-inserts", action="store_true",
                    help="skip the insert step (one call per topic instead of two)")
    args = ap.parse_args(argv)

    key = ""
    if args.openrouter:
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
            return 2
    elif not shutil.which("claude"):
        print("claude is not on PATH: install Claude Code and log in first.", file=sys.stderr)
        return 2
    model = f"openrouter:{args.openrouter}" if args.openrouter else args.model
    cases = [c for c in json.loads(CASES.read_text())["cases"] if args.only in c["title"]]
    if not cases:
        print(f"No topic title contains {args.only!r}.", file=sys.stderr)
        return 2
    candidates = tvs.routing_candidates(openai_key_set=True, gpu_status="working", has_mascot=False)
    system = INSTRUCTION + SKILL.read_text()
    insert_system = INSERT_INSTRUCTION + INSERT_SKILL.read_text()
    insert_candidates = tvs.insert_candidates(openai_key_set=True, gpu_status="working")
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def run(case):
        cost = 0.0
        try:
            if args.openrouter:
                answer, err, cost = ask_openrouter(build_prompt(case, candidates), system,
                                                   args.openrouter, args.timeout, key)
            else:
                answer, err = ask(build_prompt(case, candidates), system, args.model, args.timeout)
        except subprocess.TimeoutExpired:
            answer, err = None, f"timed out after {args.timeout} s"
        if not answer:
            return {"case": case, "verdict": "error", "error": err, "cost": cost}
        style = str(answer.get("style", "")).strip()
        row = {"case": case, "style": style, "runner_up": str(answer.get("runner_up", "")),
               "reason": str(answer.get("reason", "")), "description": str(answer.get("description", "")),
               "scores": answer.get("scores", {}), "cost": cost}
        row["verdict"] = verdict(case, style) if style in tvs.ROUTE_CHOICES else "wrong"
        if not args.no_inserts and style in tvs.ROUTE_CHOICES:
            row.update(route_inserts(case, style))
            cost += row.pop("insert_cost", 0.0)
            row["cost"] = cost
        print(f"  {row['verdict']:5}  {case['title']}  -> {style}"
              f"  inserts {row.get('inserts')} ({row.get('insert_verdict', '-')})", flush=True)
        return row

    def route_inserts(case, style):
        """The insert step for one topic, after its main pick."""
        visual_style = tvs.AUTO if style == tvs.SCENES else style
        if not tvs.hosts_inserts(visual_style)["host"]:
            return {"inserts": [], "insert_reason": "the main style takes no inserts",
                    "insert_verdict": insert_verdict(case, [])}
        prompt = build_insert_prompt(case, style, candidates, insert_candidates)
        cost = 0.0
        try:
            if args.openrouter:
                answer, err, cost = ask_openrouter(prompt, insert_system, args.openrouter, args.timeout,
                                                   key, answer_key="inserts")
            else:
                answer, err = ask(prompt, insert_system, args.model, args.timeout, key="inserts")
        except subprocess.TimeoutExpired:
            answer, err = None, f"timed out after {args.timeout} s"
        if not answer or not isinstance(answer.get("inserts"), list):
            return {"inserts": None, "insert_reason": err or "no inserts list", "insert_verdict": "error",
                    "insert_cost": cost}
        chosen = [str(i).strip() for i in answer["inserts"]]
        return {"inserts": chosen, "insert_reason": str(answer.get("reason", "")),
                "beats": str(answer.get("beats", "")), "insert_verdict": insert_verdict(case, chosen),
                "insert_cost": cost}

    print(f"Routing {len(cases)} topics with {model}...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(run, cases))

    report = render_report(rows, model, started, sum(r.get("cost", 0.0) for r in rows))
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model)
    out = pathlib.Path(args.out) if args.out else (
        DEFAULT_OUT_DIR / f"{datetime.datetime.now():%Y%m%d-%H%M}-{slug}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print("\n" + "\n".join(line for line in report.splitlines()[2:9] if line.startswith("- ")))
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
