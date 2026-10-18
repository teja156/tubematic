# Tubematic Skills

Skills are agent-agnostic instruction sets. Load the relevant skill at the start of any session — the skill contains everything the agent needs to complete the task.

| Task | Skill file |
|---|---|
| Run the pipeline / advance statuses | `tubematic-operator/SKILL.md` |
| Generate a `scene-config.json` | `tubematic-scene-config/SKILL.md` |
| Research and propose topics | `tubematic-topic-research/SKILL.md` |
| Write a video script | `tubematic-script-writing-skill/SKILL.md` |
| Build a script profile from transcripts | `tubematic-create-script-writing-skill/SKILL.md` |
| Troubleshoot an install and draft a bug report (explicit-only, see below) | `tubematic-troubleshooting/SKILL.md` |
| Write Remotion scene components | `remotion-best-practices` skill *(installed by `python onboard.py --install-agent <agent>`, not committed to this repo)* |

## Notes

- `tubematic-script-writing-skill/` is committed and always installed. It owns the whole
  scripting contract; the per-creator *style* it writes in is a **script profile** — a DB row
  built from YouTube transcripts on the dashboard, selected per video, and fetched at write
  time via `get_script_profile`. `tubematic-create-script-writing-skill/` is what builds one,
  invoked by the poller for a profile the dashboard has queued.
- Every skill in this directory is deployed to whichever agent is being installed, so its wording
  must stay agent-neutral: name MCP tools, never one agent's own file or web tools. Each agent's
  skills directory is declared by its adapter in `scripts/agent_adapters.py`
  (`~/.claude/skills/` for Claude Code, `~/.codex/skills/` for Codex,
  `~/.config/opencode/skills/` for OpenCode).
- The official Remotion skills (`remotion-best-practices` and friends) are **not** vendored in this
  repo — `python onboard.py --install-agent <agent>` installs them fresh from `remotion-dev/skills`
  via the `npx skills add` CLI, which requires Node.js >= 22. They land in that agent's skills
  directory, beside the ones committed here.
- `tubematic-troubleshooting/` is **explicit-only**: no agent may pick it up by itself, so a
  scheduled run can never wander into it. A person invokes it by name — `/tubematic-troubleshooting`
  in Claude Code, `$tubematic-troubleshooting` in Codex, "use the tubematic-troubleshooting skill"
  in OpenCode. Each CLI reads the switch from a different place: `disable-model-invocation` in the
  frontmatter (Claude Code), `metadata: opencode/autoinvoke` (OpenCode), and
  `agents/openai.yaml` (Codex). There is deliberately no slash command for it: in Claude Code a
  command reaches a skill through the model, which is exactly what the switch blocks.
- Skills are deployed by copying, so editing one here changes nothing for a running agent until you
  re-run `python onboard.py --install-agent <agent>` and restart the agent session.
