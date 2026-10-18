# Tests

Every test suite in the repository, what each file guards, and how to run it.

Tests live beside the code they cover; this folder documents them in one place so you can find the
suite that covers a change without grepping for it.

---

## The suites

| | Runner | Covers |
|---|---|---|
| **[`tubematic_core/tests`](tubematic-core.md)** | pytest | The package shared by every process — schema migrations, structured logging, the version string |
| **[`mcp/tests`](mcp.md)** | pytest | The MCP server — agent tools, the scene-work claim, `validate_job`, the text-layout audit |
| **[`renderer/api/tests`](renderer-api.md)** | pytest | The Flask API, the render worker, Gemini review, host timezone |
| **[`onboard/tests`](onboard.md)** | pytest | The onboarding wizard — fields, steps, validators, and what each action writes |
| **[`scripts/tests`](scripts.md)** | pytest | `poll.py` — the cron entrypoint, its decision tree and prompt construction |
| **[`vqa/tests`](vqa.md)** | pytest | The VQA utilities shipped in the VQA Kasm image |
| **[`dashboard/tests/unit`](dashboard-unit.md)** | vitest | React components, route handlers, date/timezone helpers |
| **[`dashboard/tests/e2e`](dashboard-e2e.md)** | Playwright | The dashboard driven in a real browser against a real stack |

Two typecheck gates are not test suites but are run the same way — see [Typechecks](#typechecks).

---

## Running everything

### Python

```bash
python -m pytest tubematic_core/tests
python -m pytest mcp/tests
python -m pytest renderer/api/tests
python -m pytest onboard/tests
python -m pytest scripts/tests
python -m pytest vqa/tests
```

> **Run `scripts/tests` and `renderer/api/tests` separately.** Neither parent directory has an
> `__init__.py`, so pytest's default import mode treats each `tests/` subdirectory as a top-level
> package literally named `tests`. Whichever is collected first wins the name and the second fails to
> import. Other combinations are fine — `onboard/` has an `__init__.py` and `mcp/tests` has none, so
> neither collides.

`pytest` is **not** installed by `scripts/requirements.txt` or by the wizard's bootstrap. Install it
yourself.

Some suites need the package dependencies of the code they cover — `mcp/tests` needs `fastmcp`,
`httpx` and `pillow` from `mcp/requirements.txt`. Each suite's page says so where
it applies.

### JavaScript

```bash
cd dashboard
npm test                 # vitest
npm run test:e2e         # Playwright — builds the Docker test stack first
```

The Playwright suite's global setup runs `docker compose -f docker-compose.test.yml up -d --build
--wait` from the repo root. That is a multi-gigabyte build — check `df -h /` first.

### Typechecks

```bash
cd dashboard          && npx tsc --noEmit
cd renderer/remotion  && npx tsc --noEmit    # exactly what validate_job runs per video
```

The second one matters more than it looks: `validate_job` runs `tsc --noEmit` over the whole Remotion
project for **every** video, so a type error anywhere in that tree fails validation pipeline-wide,
not just for the scene that introduced it.

Both need Node 22. `/usr/bin/node` may be older; if a suite fails with a Node version error, load nvm
first:

```bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22
```

Keep the nvm invocation out of a pipeline — `nvm use 22 | cat` runs it in a subshell and the PATH
change dies with it.

---

## Where verification belongs

Getting this wrong produces confident, wrong results.

| Kind of check | Where | Why |
|---|---|---|
| Unit tests, `tsc`, `vitest`, reading code | Your machine | Platform-independent |
| Anything measuring **text geometry** | **A container** | `system-ui` resolves to a different font face outside the container. Host-measured pixel numbers are fiction |
| A real render | **A container** | Same font problem, plus `--ignore-scripts` means no local headless Chromium |
| Onboarding, or bringing up the stack | **A disposable environment** | Fixed container names and ports collide with an existing stack, and Docker leaves root-owned bind sources behind |

A clean typecheck on your machine proves the *tree* typechecks. `validate_job` runs `tsc` against the
container's own `node_modules`; the Dockerfile installs from the same lockfile, so the two agree
today — but if that install line changes, the local result stops transferring.

---

## Conventions for these pages

**No test counts.** They are stale on the next commit. Say what a file guards, not how many
assertions it makes. Run the suite if you want a number.

**Say why, not just what.** A line like *"`workers: 1` — tests share a single DB, parallelism
races"* survives a refactor. *"`workers` is set to 1"* does not.

**Record the traps.** Several suites exist because of a specific bug or a non-obvious constraint. If
a test encodes a decision someone might reverse, the page should say so — that is the part worth
reading.

**Update these pages in the same commit as the tests.** A suite page that lists files which no longer
exist is worse than no page, because it is believed. See `CLAUDE.md`.
