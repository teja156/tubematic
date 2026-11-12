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
| `inserts_expect` | The insert styles the insert step should choose for the picked main style, `[]` for none, or `"any"` (also when absent) |
| `inserts_ok` | Insert styles that are also acceptable |

`tubematic_core/tests/test_style_routing.py` checks it in CI: every id is a real outcome, and every
main pack and `scenes` is the first expectation of at least three topics. An insert style is never a
topic's main expectation; it is expected as an insert in at least three topics, and at least three
topics expect no inserts, so the eval can see an insert added for variety
([Main styles and inserts](../10-scene-authoring.md#main-styles-and-inserts)).

Most topics probe a pair of styles that could be confused (Bean Explainer and Storybook Atlas, Under
the Hood and Whiteboard, a story style and Illustrated), or an older style next to a newer neighbour
that is the wrong answer for it. The `note` names the pair. A probe in each direction is what shows
whether a pack's `avoid_for` holds.

The real-event topics are failures with a technical cause (a rocket, a spacecraft, a trading firm,
an outage), each with a brief written the way research writes one: one idea, often a number, and a
beat list. They expect Photo Explainer and accept mixed scenes and Storybook Atlas. A brief built
around a number reads as a number story, so these topics check that the routing skill's real-failure
question and each pack's `cannot_show` keep a text or diagram style from taking the story of a real
rocket or company. Two negative controls keep the rule from reaching too far: the same number with no
event in it expects Terminal Doc, and a flaw in a piece of software with nothing to see beyond its
code expects System Flow.

A ticket that adds a pack adds at least three topics that expect it, and moves the topics whose
`future` names it to `expect`. CI fails until it does.

## The eval

`scripts/eval_style_routing.py` sends every topic through the routing skill's text and the candidate
list `routing_candidates` builds (every style available), using the Claude Code CLI with no tools or,
with `--openrouter <model>`, an OpenRouter model, and scores each pick:

- **best**: the first expectation
- **ok**: another expectation, or an `ok` outcome
- **wrong**: anything else

```bash
python3 scripts/eval_style_routing.py                          # sonnet, every topic
python3 scripts/eval_style_routing.py --model opus --only DNS  # one model, matching topics
python3 scripts/eval_style_routing.py --openrouter deepseek/deepseek-v4.1-flash
```

For a picked style that takes insert scenes, a second short call runs the `tubematic-insert-routing`
skill with the insert candidates `insert_candidates` builds, and the chosen insert styles are scored
against the topic's `inserts_expect`: **right** when every expected insert style is chosen and
nothing outside `inserts_expect` and `inserts_ok` is, **wrong** otherwise. `--no-inserts` skips that
call ([Main styles and inserts](../10-scene-authoring.md#main-styles-and-inserts)).

It needs `claude` on the PATH and logged in, or with `--openrouter` an OpenRouter key in
`OPENROUTER_API_KEY`, and nothing else: no install, no database. It makes one or two short calls per
topic.
Live agents often run cheaper models through OpenCode, so run the eval on one of those as well as on
Sonnet; the OpenRouter report gives the run's cost. The report is Markdown, with a table of every pick and a section per wrong
pick giving the agent's description of the topic and its scores. It goes to
`docs_private/reports/style-routing/` unless `--out` names a file.

Run it before and after a change to a pack's `routing` block, the routing skill or the topic set,
and compare the two reports. Results vary between runs of the same model, so read a change of one
or two picks as noise and a change across several topics as a real effect.

`scripts/tests/test_eval_style_routing.py` covers the eval's prompts (the main pick and the insert
step), parsing and scoring without calling a model.
