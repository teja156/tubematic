# Style routing

Auto picks a video's style from the style packs before its script is written
([How Auto picks a style](../10-scene-authoring.md#how-auto-picks-a-style)). The pick is a model's
judgement, made by the `tubematic-style-routing` skill, so no unit test can run it. Two checks cover
it instead: a fixed topic set that CI keeps honest, and an eval you run by hand.

## The topic set

`tubematic_core/tests/fixtures/style_routing_cases.json` holds topics a channel would get.
Each case is:

| Field | Holds |
|---|---|
| `title`, `brief` | The topic as the agent sees it at `TOPIC_APPROVED` |
| `expect` | The right outcome, best first: a pack id or `scenes` |
| `ok` | Outcomes that are acceptable but not the best |
| `future` | A coming style expected to take the topic over once its pack ships, or `""` |
| `note` | Why the expectation is what it is, when that is not obvious |

`tubematic_core/tests/test_style_routing.py` checks it in CI: every id is a real outcome, and every
pack and `scenes` is the first expectation of at least three topics.

A ticket that adds a pack adds at least three topics that expect it, and moves the topics whose
`future` names it to `expect`. CI fails until it does.

## The eval

`scripts/eval_style_routing.py` sends every topic through the routing skill's text and the candidate
list `routing_candidates` builds (every style available), using the Claude Code CLI with no tools,
and scores each pick:

- **best**: the first expectation
- **ok**: another expectation, or an `ok` outcome
- **wrong**: anything else

```bash
python3 scripts/eval_style_routing.py                          # sonnet, every topic
python3 scripts/eval_style_routing.py --model opus --only DNS  # one model, matching topics
```

It needs `claude` on the PATH and logged in, and nothing else: no install, no database. It makes one
short call per topic. The report is Markdown, with a table of every pick and a section per wrong
pick giving the agent's description of the topic and its scores. It goes to
`docs_private/reports/style-routing/` unless `--out` names a file.

Run it before and after a change to a pack's `routing` block, the routing skill or the topic set,
and compare the two reports. Results vary between runs of the same model, so read a change of one
or two picks as noise and a change across several topics as a real effect.

`scripts/tests/test_eval_style_routing.py` covers the eval's prompt, parsing and scoring without
calling a model.
