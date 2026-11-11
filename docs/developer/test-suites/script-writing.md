# Script writing

The agent writes a script by following the `tubematic-script-writing-skill` skill and one
[formula](../08-scripting-and-voice.md#formulas). What it writes is a model's work, so no unit test
can judge it. Two things cover it: tests that keep the skill and the formula data in step, and a
comparison you run by hand.

## What CI checks

- `tubematic_core/tests/test_formulas.py` validates every formula file.
- `tubematic_core/tests/test_script_checks.py` covers each
  [script warning](../08-scripting-and-voice.md#script-warnings).
- `scripts/tests/test_script_writing_skill.py` fails when the skill's generated formula files differ
  from the data, or when the skill stops naming `update_video`'s real arguments.

## The topic set

`scripts/eval_script_topics.json` holds topics of different shapes that no install owns: a device
that behaves strangely, a tool that gives a wrong-looking answer, a process, a wrong belief, a
design question, an outage, a loophole, an unexplained signal, one person's decision, a scale, a
checklist and a failed project. Each topic is:

| Field | Holds |
|---|---|
| `title`, `brief` | The topic as the agent sees it at `TOPIC_APPROVED`. The brief carries the facts a writer needs |
| `shape` | The kind of topic it is, for a reader of the report |

Change the set rarely. A comparison across runs is only as good as the set staying the same.

## The comparison

`scripts/eval_script_writing.py` has a model write each topic's script twice, using the Claude Code
CLI with no tools:

- the old side follows the skill as it was at a git ref (`--old-ref`, the `v2.1.1` tag by default)
- the new side follows the skill in your checkout, with every formula file appended, since the run
  has no tool to read one

It then runs the script warnings over both sides.

```bash
python3 scripts/eval_script_writing.py                          # sonnet, every topic, both sides
python3 scripts/eval_script_writing.py --model opus --only pudding
python3 scripts/eval_script_writing.py --sides new              # the current skill only
```

It needs `claude` on the PATH and logged in, and git for the old side. It needs no install and no
database. It makes two calls per topic and prints the cost the CLI reports.

The report is a folder under `docs_private/reports/script-baseline/`, or the folder `--out` names:

| File | Holds |
|---|---|
| `summary.md` | One row per topic (words and warnings on each side, the formula and opening the new side chose), each warning's count per side, and the range of lengths |
| `<topic>.md` | The two scripts for one topic, segment by segment, with the openings drafted and the warnings |
| `results.json` | Everything above as data |

Run it before and after a change to the skill, a formula file or the checks, and compare the two
reports. Results vary between runs of the same model, so read a difference on one or two topics as
noise and a difference across most of the set as a real effect. The warnings count stock shapes.
Read the scripts themselves to judge the writing.

`scripts/tests/test_eval_script_writing.py` covers the comparison's prompt, parsing, scoring and
report without calling a model.
