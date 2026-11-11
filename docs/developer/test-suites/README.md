# Test suites

Each test suite lives beside the code it covers. The pages in this folder say what each test file
guards and which decision a refactor of that code would undo. Start from the table, open the page
for the suite that covers your change, and find the file by its subject heading.

## The suites

| Suite | Covers | Page | Command |
|---|---|---|---|
| `tubematic_core/tests` | The package every process shares: migrations, the database helpers, backups, logging, auth, the usage ledger and prices, ids and job paths, and the voice, renderer and mascot rules | [tubematic-core.md](tubematic-core.md) | `python -m pytest tubematic_core/tests` |
| `mcp/tests` | The MCP server: the agent's tools, the scene-work claim, `validate_job` and the text-layout audit | [mcp.md](mcp.md) | `python -m pytest mcp/tests` |
| `renderer/api/tests` | The Flask API, the render gateway, the renderer, the worker, AI review and the publishing client | [renderer-api.md](renderer-api.md) | `python -m pytest renderer/api/tests` |
| `onboard/tests` | The onboarding wizard, agent install, the Compose overrides, stack control and `upgrade.py` | [onboard.md](onboard.md) | `python -m pytest onboard/tests` |
| `scripts/tests` | The poller and the agent adapters, the release tooling and the CI workflows, the service scripts and the Kasm images | [scripts.md](scripts.md) | `python -m pytest scripts/tests` |
| `vqa/tests` | The helper scripts of the video quality assessment image | [vqa.md](vqa.md) | `python -m pytest vqa/tests` |
| `renderer/remotion/cartoon-tools/audio/tests` | The mixing rules of the Cartoon 3D soundtrack engine | [cartoon-audio.md](cartoon-audio.md) | `python -m pytest renderer/remotion/cartoon-tools/audio/tests` |
| `dashboard/tests/unit` | React components, route handlers and `lib/` helpers, under vitest | [dashboard-unit.md](dashboard-unit.md) | `cd dashboard && npm test` |
| `dashboard/tests/e2e` | The dashboard in a real browser against a Docker test stack, under Playwright | [dashboard-e2e.md](dashboard-e2e.md) | `cd dashboard && npm run test:e2e` |
| `renderer/remotion` | Pure helpers of the Remotion project (`*.test.ts` beside the code), under vitest | [renderer-remotion.md](renderer-remotion.md) | `cd renderer/remotion && npm test` |
| Style routing eval | Auto's style picks against a fixed topic set, through the Claude Code CLI. Run by hand, never in CI | [style-routing.md](style-routing.md) | `python3 scripts/eval_style_routing.py` |

Run the Python commands from the repository root. [Development: Tests](../17-development.md#tests)
owns the set-up each command needs (the packages to install, Node 22, the Docker build behind the
Playwright suite) and the two typecheck commands.
[Where verification belongs](../17-development.md#where-verification-belongs) says which checks
are valid on your machine and which need a container.

CI runs the seven Python suites as one matrix job per directory, and the dashboard unit suite in
its `dashboard` job. The Playwright suite runs on a version tag or a manual dispatch. The
`remotion` job runs the typecheck and does not run that project's vitest suite
([Releases: `ci.yml`](../18-releases.md#ciyml-pull-requests-and-pushes)).

## Run each Python suite on its own

Run each suite in its own `pytest` invocation. Suites collected in one run break each other's
imports:

- `scripts/tests` and `renderer/api/tests` each have an `__init__.py` under a parent directory that
  is not a package, so both claim the top-level package name `tests`.
- `tubematic_core/tests` and `mcp/tests` have no `__init__.py` and share two test file names
  (`test_visual_style.py`, `test_voice_models.py`), so pytest imports both files under one module
  name.
- `mcp/tests` fails beside `renderer/api/tests` and beside `vqa/tests`. Each of those imports a
  module named `server` first (`renderer/api/server.py`, or `mcp/server.py` through
  `vqa/stage_script.py`), before `mcp/tests` has pointed the server at a temporary database, so
  the run stops on the container's database path, `/data`.

## How the guards were checked

Each guard described on these pages was verified by removing it from the code and watching a test
fail. When you add a guard, do the same before you document it.

## Glossary

| Term | Meaning on these pages |
|---|---|
| Pin | A test pins a value, a wording or a piece of source text when it fails as soon as that thing changes. Tubematic also pins a choice to a video, by writing the resolved agent, model or voice on its row |
| Negative control | A test of the case that must stay allowed, kept beside the tests of a refusal. It fails when the check starts to refuse too much |
| Fail open | When the check itself breaks, the work goes on. [AI review](../21-ai-review.md#fail-open) and the [text-layout audit](../11-rendering-and-review.md#the-audit-is-advisory) fail open |
| Fail closed | When the check cannot decide, it refuses. The upgrade's [removed-component check](../18-releases.md#the-removed-component-check) fails closed |
| The claim | One of two locks. [The scene-work claim](../06-mcp-server.md#the-scene-work-claim) gives one agent session a video's scene work. [The render claim](../11-rendering-and-review.md#the-claim) gives one renderer a queued video |
| The lease | The time a render claim holds its video. Each heartbeat extends it ([Leases](../19-render-gateway.md#leases)) |
| The hold | One of two flags. `videos.auto_pilot_hold` keeps Auto Pilot from scheduling a video again ([Stopping one video](../14-publishing.md#stopping-one-video)). `render_claim_hold_until` stops the built-in renderer's claims while the `gpu` step recreates it ([The Compose override](../20-gpu-and-remote-renderers.md#the-compose-override)) |
| Lane | One of the four kinds of agent session the poller runs side by side: pipeline, research, script profiles, mascots ([The four lanes](../13-the-poller.md#the-four-lanes)) |
| The deck | The shuffled list of agent ids that new videos are dealt from, by weight ([Assignment](../07-agent-layer.md#assignment)) |
| Seed | A curriculum seed is a domain that curriculum topics are enumerated from ([Where topics come from](../02-pipeline.md#where-topics-come-from)). To seed a value is to copy a default onto a new row, such as a domain's default voice onto a new video |
| Frozen | A per-video choice is frozen when a write to it is refused because the video is outside the statuses where it may be set ([Frozen choices](../02-pipeline.md#frozen-choices)) |

## Writing these pages

Every page uses one entry per test file, grouped under headings by subject:

```
### `test_x.py`

Covers <the code under test, by symbol or file>.

- <One behaviour group the file guards.>
- <Another. Two to five bullets, one per group of behaviour.>

Trap: <the decision a refactor would undo, and what goes wrong when it does>

Needs: <a real process, a binary or a skip condition, when it is not obvious>
```

- Say what the file guards and why. The test names carry the inputs, the status codes and the
  cases, so leave them out.
- Write a `Trap:` line when a test protects a decision that looks wrong or that someone might
  reverse. State the decision and its consequence in one to three sentences. The account of how it
  was found belongs in the commit message.
- Where a developer page explains the mechanism, name the rule in a clause and link to that page.
- Write no test counts. They are wrong after the next commit.
- Give every test file one entry, and remove the entry when the file goes. Update the page in the
  same commit as the test, as [Keeping the docs true](../17-development.md#keeping-the-docs-true)
  requires.
