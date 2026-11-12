# Formula routing

A video's script formula is picked before its script is written
([How a formula is picked](../08-scripting-and-voice.md#how-a-formula-is-picked)). The pick is a
model's judgement, made by the `tubematic-formula-routing` skill, so no unit test can run it. Two
checks cover it: a fixed topic set that CI keeps honest, and an eval you run by hand.

## The topic set

`tubematic_core/tests/fixtures/formula_routing_cases.json` holds topics that no install owns. Each
case is:

| Field | Holds |
|---|---|
| `title`, `brief` | The topic as the agent sees it at `TOPIC_APPROVED`. The brief carries the facts a formula needs |
| `expect` | The right formula, best first |
| `ok` | Formulas that are acceptable but not the best |
| `style` | Optional. The video's visual style, a style pack id. Without it the video is on mixed scenes |
| `experimental` | Optional. `true` routes the case with `auto_experimental_formulas` on, and lets it expect an experimental formula |
| `note` | Why the expectation is what it is, when that is not obvious |

`tubematic_core/tests/test_formula_routing.py` checks it in CI: every id is a real formula or
style, every formula that is not experimental is the first expectation of at least three cases
routed with the setting off, and every experimental formula has a case.

A change that adds a formula adds its topics: three for a formula that is not experimental, one for
an experimental one. CI fails until it does.

## The eval

`scripts/eval_formula_routing.py` sends every topic through the routing skill's text and the
candidate list `routing_candidates` builds for the case, using the Claude Code CLI with no tools,
and scores each pick:

- **best**: the first expectation
- **ok**: another expectation, or an `ok` formula
- **wrong**: anything else

```bash
python3 scripts/eval_formula_routing.py                               # sonnet, every topic
python3 scripts/eval_formula_routing.py --model opus --only password  # one model, matching topics
```

It needs `claude` on the PATH and logged in, and nothing else: no install, no database. It makes one
short call per topic. The report is Markdown: the totals, a table of best and acceptable picks per
formula, a table of every pick, and a section per wrong pick giving the agent's description of the
topic and its scores. It goes to `docs_private/reports/formula-routing/` unless `--out` names a
file.

Run it before and after a change to a formula's routing fields, the routing skill or the topic set,
and compare the two reports. Results vary between runs of the same model, so read a change of one
or two picks as noise and a change across several topics as a real effect.

The eval routes each topic with no history, so it does not measure rotation. The MCP suite covers
the rotation rule, which the tool enforces (`mcp/tests/test_choose_script_formula.py`).

`scripts/tests/test_eval_formula_routing.py` covers the eval's prompt, parsing and scoring without
calling a model.
