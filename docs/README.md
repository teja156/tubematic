# Tubematic — Documentation

Tubematic turns a topic into a finished YouTube Short: it researches topics, writes a script, voices
it, generates imagery, animates it in code, renders an mp4, has an AI watch the result for defects,
and stops at three points where a human has to say yes.

Every scene is a React component an AI agent writes for that specific video, compiled and rendered by
[Remotion](https://remotion.dev). The output is real code, which is why you can read exactly what
produced any frame.

[![Watch the Tubematic walkthrough](https://raw.githubusercontent.com/teja156/tubematic/develop/logos/social/tubematic-walkthrough-1280x720.png)](https://youtu.be/-y9zBSg8WEc)

The documentation is split by who is reading. Pick the entry point that matches what you want to do.

| You want to… | Start at |
|---|---|
| Get it running and make a first video | **[Quickstart](quickstart.md)** |
| Install, run, operate and upgrade it | **[User guide](#user-guide)** |
| Understand how it works, change it, or build on it | **[Developer docs](#developer-docs)** |
| See what changed in a release | **[Release notes](release-notes.md)** |

---

## User guide

For anyone running Tubematic. No knowledge of the code is assumed.

| | |
|---|---|
| **[1 · Overview](user-guide/01-overview.md)** | What it is, what it produces, the design decisions that shape everything else, and a glossary. **Read this first** |
| **[2 · Installing](user-guide/02-installing.md)** | Prerequisites, what the dashboard exposes on the network, the install wizard, installing an agent, your first video, verifying and uninstalling |
| **[3 · Using Tubematic](user-guide/03-using-tubematic.md)** | The day-to-day: the ways to make videos, scheduling, the control knobs, the checkpoints you approve, pausing and monitoring |
| **[4 · The Dashboard](user-guide/04-dashboard.md)** | Signing in, every page and what it is for, and the actions you take there |
| **[5 · Settings](user-guide/05-settings.md)** | Every setting: what it does, its default, and when to change it |
| **[6 · Publishing](user-guide/06-publishing.md)** | Connecting social accounts, publishing and scheduling posts, and Auto Pilot |
| **[7 · Upgrading](user-guide/07-upgrading.md)** | Moving to a new version, versioning, backups, and rollback |
| **[8 · Troubleshooting](user-guide/08-troubleshooting.md)** | Symptoms and where the cause usually is |
| **[9 · Remote Access](user-guide/09-remote-access.md)** | Using the dashboard from another machine: Twingate, or HTTPS with Caddy or nginx |

## Developer docs

For contributors and anyone integrating with or extending Tubematic.

| | |
|---|---|
| **[1 · Architecture](developer/01-architecture.md)** | Containers, processes, how they talk, where files live, the repository map, and the failure model |
| **[2 · The Pipeline](developer/02-pipeline.md)** | The state machine in full — every status, every transition, the human checkpoints, and the revision loop |
| **[3 · Database](developer/03-database.md)** | Every table and column, the migration model, and how to add one |
| **[4 · Settings internals](developer/04-settings.md)** | How settings and credentials are stored, masked and verified, and how to add a setting |
| **[5 · HTTP API](developer/05-http-api.md)** | Every Flask route — parameters, responses, status codes, and known quirks |
| **[6 · MCP Server](developer/06-mcp-server.md)** | Every agent tool, `validate_job`'s checks, and the scene-work claim |
| **[7 · The Agent Layer](developer/07-agent-layer.md)** | Skills, slash commands, installing an agent and how videos are assigned to one |
| **[8 · Scripting and Voice](developer/08-scripting-and-voice.md)** | Script segments, length budget, pronunciation and pause markup, `timeline.json`, script profiles |
| **[9 · The Remotion Project](developer/09-remotion-project.md)** | The frame model, compositions, dynamic scene dispatch, `scene-config.json`, the installed component library |
| **[10 · Scene Authoring](developer/10-scene-authoring.md)** | How a scene gets written — the two visual registers, the PHOTO / HYBRID / DIAGRAM / STICK taxonomy, cadence, the revision path, adding a component |
| **[11 · Rendering and Review](developer/11-rendering-and-review.md)** | Rendering, timeouts and retries, Gemini video review, the text-layout audit |
| **[12 · The Worker](developer/12-the-worker.md)** | The always-on loop that renders, settles posts, runs Auto Pilot and the timed sweeps — every pass, its order and how often it runs |
| **[13 · The Poller](developer/13-the-poller.md)** | `poll.py`, the cron-started supervisor that runs agent sessions — the loop, the three lanes, one stage per session, timeouts and orphans |
| **[14 · Publishing internals](developer/14-publishing.md)** | The postforme client, schema, routes, the worker's publishing passes, and the design decisions behind them |
| **[15 · Dashboard internals](developer/15-dashboard.md)** | The Next.js app — stack, the request guard, the proxy and stream routes, components, the action model |
| **[16 · Infrastructure](developer/16-infrastructure.md)** | Compose services, authentication, volumes, images, cron, and day-to-day operating commands |
| **[17 · Development](developer/17-development.md)** | Where verification belongs, release tooling, the CI workflow shape, conventions, and contributing |
| **[18 · Releases](developer/18-releases.md)** | What a release consists of, release branches, image tags, and how migrations ship |
| **[Test suites](developer/test-suites/README.md)** | Every test suite — what each file guards, how to run it, and the traps each one encodes |

---

## Reading routes

**Just want to run it.** [Quickstart](quickstart.md) → [Using Tubematic](user-guide/03-using-tubematic.md)
→ [The Dashboard](user-guide/04-dashboard.md), and [Remote Access](user-guide/09-remote-access.md) to
use it from another machine.

**Want to change how videos look.** [Overview](user-guide/01-overview.md) →
[The Remotion Project](developer/09-remotion-project.md) → [Scene Authoring](developer/10-scene-authoring.md).
This is the main extension surface.

**Want to change how the AI behaves.** [The Pipeline](developer/02-pipeline.md) →
[The Agent Layer](developer/07-agent-layer.md) → [MCP Server](developer/06-mcp-server.md). Most behaviour
lives in markdown skills, not code.

**Integrating something external.** [Architecture](developer/01-architecture.md) →
[HTTP API](developer/05-http-api.md) → [Database](developer/03-database.md).

**Something is broken.** [Troubleshooting](user-guide/08-troubleshooting.md).

---

## Conventions in these docs

- Code is cited by **symbol** — `pipeline.py::patch_video` — never by line number, so a citation
  cannot rot when a file is edited above it.
- Diagrams are inline ```mermaid fences, rendered natively by GitHub. There is no build step.
- No test counts, suite totals, or dated claims. Run the suite.
- Each explanation lives on one page; others link to it. A user-guide page covers what you do and
  see, and links to the developer page that explains how it works.
- Where a design decision looks wrong or over-engineered, the reason is stated. Those notes are the
  most valuable part of this documentation and the easiest to accidentally undo.

**These documents are public and must never carry stale information.** Any change that adds or alters
a tool, route, settings key, status, schema column, component or skill rule is not finished until the
relevant page reflects it — and until the neighbouring claims it invalidated have been re-checked.
See [Development — Keeping the docs true](developer/17-development.md#keeping-the-docs-true).
