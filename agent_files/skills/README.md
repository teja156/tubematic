# Tubematic skills

A skill is a folder with a `SKILL.md` file: Markdown instructions that an agent CLI (Claude Code,
Codex or OpenCode) reads to learn one job. This folder holds the skills Tubematic ships. The
installer copies each of them into the agent's skills directory:

```bash
python3 onboard.py --install-agent <agent>     # claude, codex or opencode
```

Run it from the repository root. When each skill runs and how the agent layer works is in
[The Agent Layer](../../docs/developer/07-agent-layer.md#the-skills).

## The skills

| Folder | What the agent does with it |
|---|---|
| `tubematic-operator/` | Runs the pipeline: moves each video to its next status with the MCP tools and stops at the human checkpoints |
| `tubematic-topic-research/` | Researches and proposes topics in the curriculum, trending and mining research modes, each with the angle its video will open on |
| `tubematic-style-routing/` | Picks a video's visual style before its script is written, when the person left it on Auto: describes the topic, scores the candidate styles from their style packs and records the choice |
| `tubematic-formula-routing/` | Picks a video's script formula before its script is written, once its visual style is decided: describes the topic's shape, scores the candidate formulas from the formula files, rotates away from the domain's recent formulas and records the choice |
| `tubematic-script-writing-skill/` | Writes a video's script as an ordered list of segments, in the formula picked for the video and in the voice of the video's script profile |
| `tubematic-create-script-writing-skill/` | Builds a script profile: extracts a creator's style from YouTube transcripts and stores it as profile Markdown |
| `tubematic-scene-config/` | Writes `scene-config.json` and the scene TSX files for a voiced video |
| `tubematic-cartoon3d/` | Writes a Cartoon 3D video as TypeScript against the renderer's kit, takes it through the beat gate and submits it |
| `tubematic-system-flow/` | Writes a System Flow video as data (boards, components, connectors and events timed to the narration) for the one `SystemFlow` scene, validates and submits it |
| `tubematic-whiteboard/` | Writes a Whiteboard video as data (regions of handwriting, formulas, doodles and marks timed to the narration) for the one `Whiteboard` scene, validates and submits it |
| `tubematic-bean-explainer/` | Writes a Bean Explainer video as data (sections, shots, the bean's poses and props from the fixed library, timed to the narration) for the one `BeanExplainer` scene, validates and submits it |
| `tubematic-storybook-atlas/` | Writes a Storybook Atlas video as data (chapters, backdrops, the guide's and people's walks, props from the hatched library, plates, timed to the narration) for the one `StorybookAtlas` scene, validates and submits it |
| `tubematic-terminal-doc/` | Writes a Terminal Doc video as data (beats and typographic moves timed to the narration, plus any move written for the video) for the one `TerminalDoc` scene, validates and submits it |
| `tubematic-under-the-hood/` | Writes an Under the Hood video as data (close-up photographs it generates and checks, with labels, arcs, counters and the presenter's poses timed to the narration) for the one `UnderTheHood` scene, validates and submits it |
| `tubematic-case-file-story/` | Writes a Case File Story video as data (painted stills it generates from the video's lead sheet and checks, with meters, punch-ins, count, bars and term cards and the closing choice timed to the narration) for the one `CaseFileStory` scene, validates and submits it |
| `tubematic-mascot-builder/` | Writes or revises one mascot's p5.js drawing code, renders its three model sheets and submits it for human review |
| `tubematic-troubleshooting/` | Diagnoses a broken install with a person, collects redacted evidence and drafts a bug report. A person must ask for it by name |

The table of angle kinds and the angle score in `tubematic-topic-research/SKILL.md` are generated
from `tubematic_core/angles.py` by `scripts/gen_angle_reference.py` in the source repository: edit
the data, then run the script.

`tubematic-script-writing-skill/` owns the scripting rules. Its `formulas/` folder holds one
reference file per script formula. Those files are generated from
`tubematic_core/formulas/` by `scripts/gen_formula_references.py` in the source repository: edit the
data, then run the script. `tubematic-formula-routing/` chooses among the same formulas from the
candidate list `get_video` returns. The style it writes in comes from a
script profile, a database row the agent fetches with `get_script_profile`.
`tubematic-create-script-writing-skill/` builds that row when the poller finds a profile queued
from the dashboard. See
[Script profiles](../../docs/developer/08-scripting-and-voice.md#script-profiles).

## Remotion's skills

`tubematic-scene-config/` tells the agent to invoke the `remotion-best-practices` skill. That skill
and the other official Remotion skills are not in this repository. The installer fetches them from
`remotion-dev/skills` with `npx skills add`. For Claude Code they land beside the skills from this
folder. For Codex and OpenCode they land in `~/.agents/skills/`, which both CLIs also read.

This step needs Node.js 22.20 or newer. With an older Node.js or none, the installer warns and
Remotion's skills are not installed (see
[Node.js](../../docs/user-guide/02-installing.md#nodejs)).

## Rules for editing a skill

- Keep the wording agent-neutral. The installer deploys each folder here to whichever agent you
  install, so name MCP tools and do not name one CLI's own file or web tools.
- Redeploy after an edit. Skills are copied, so a change here reaches an agent only after you run
  `python3 onboard.py --install-agent <agent>` again and restart the agent session.
- Each agent's skills directory comes from its adapter in `scripts/agent_adapters.py`:
  `~/.claude/skills/` for Claude Code, `~/.codex/skills/` for Codex and
  `~/.config/opencode/skills/` for OpenCode. See the
  [Agent CLI Reference](../../docs/developer/22-agent-cli-reference.md).
- When you delete a skill folder, add its name to `onboard/agent_install.py::RETIRED_SKILLS` and to
  `_RETIRED_SKILLS` in `uninstall.py`, so that a redeploy removes the old copy. See
  [Deployment](../../docs/developer/07-agent-layer.md#deployment).

## The troubleshooting skill

`tubematic-troubleshooting/` is the one skill an agent may not start by itself, so a scheduled run
does not reach it. A person asks for it by name: `/tubematic-troubleshooting` in Claude Code,
`$tubematic-troubleshooting` in Codex, or "use the tubematic-troubleshooting skill" in OpenCode.

Each CLI reads its switch from a different place: `disable-model-invocation` and
`metadata: opencode/autoinvoke` in the `SKILL.md` front matter, and `agents/openai.yaml` for
Codex. Keep all three when you edit the skill, and do not add a slash command for it. The reason
is in
[The troubleshooting skill](../../docs/developer/07-agent-layer.md#the-troubleshooting-skill).
