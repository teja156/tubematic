# `dashboard/tests/e2e`

The dashboard driven in a real browser against a real, isolated stack. This is the only suite that
exercises the Next.js app, the Flask API and SQLite together.

```bash
cd dashboard
npm run test:e2e                              # full suite
npm run test:e2e:headed                       # watch it run
npm run test:e2e:ui                           # Playwright's UI mode
npx playwright test specs/settings.spec.ts    # one spec
npx playwright test -g "Approve topic"        # one test by name
```

**Global setup runs `docker compose -f docker-compose.test.yml up -d --build --wait` from the repo
root.** That is a multi-gigabyte build — check `df -h /` before starting.

---

## Infrastructure

| Service | Host port | What it is |
|---|---|---|
| `tubematic-api-test` | 4001 | The Flask API only, against an isolated SQLite database. The MCP server is not started; the `MCP_PORT` variable in `docker-compose.test.yml` is a leftover from when the two shared a container |
| `tubematic-renderer-test` | — | The render worker, same image as the API container, no exposed port. Present so specs that drive a video to `RENDER_QUEUED` actually get rendered |
| `tubematic-dashboard-test` | 3001 | A production Next.js build |

Volumes are separate from the real stack: `test-db-data`, `test-jobs-data`, `test-output-videos`.
Remove them **by name** if you need to clear state — never with `docker volume prune`, which would
also take the real pipeline database and video library.

| File | Role |
|---|---|
| `global-setup.ts` | Builds and starts the containers, waits for health endpoints — then sets the test dashboard password through `python3 -m tubematic_core.auth set-password` inside the API container, signs in once through the real login route, and saves that browser state to `tests/e2e/.auth/state.json` (gitignored) for every spec to start from. |
| `global-teardown.ts` | Tears the containers down and removes the test volumes |
| `fixtures/seed.ts` | HTTP helpers that seed the test database before each test. `patchVideo` adds a placeholder publish title and description whenever it seeds a `script`, since the API refuses a script without them Every helper sends the test API token: the file shadows `fetch` with one that adds it, because the test API refuses any call without it. It also exports `API_AUTH` for the few specs that call the API directly, and `TEST_PASSWORD`. |
| `secrets/` | Fixed, **public** tokens for the test stack only — it runs on throwaway volumes and is torn down after every run. A real install generates random ones |

## Config, and why

From `playwright.config.ts`:

| Setting | Value | Reason |
|---|---|---|
| `workers` | `1` | Every test shares one database — parallelism races |
| `retries` | `1` | One automatic retry for borderline timing flakiness |
| `timeout` | `30_000` | Covers the board's 5-second polling plus container startup variation |
| `baseURL` | `http://localhost:3001` | The test dashboard, not your real one on 3000 |
| `screenshot` | `only-on-failure` | Captured automatically when something breaks |
| `video` | `retain-on-failure` | Kept only when needed for debugging |
| `storageState` | `./tests/e2e/.auth/state.json` | Every spec starts signed in. `auth.spec.ts` overrides it with an empty state to test the signed-out path |

---

## Specs

| Spec | Covers |
|---|---|
| `auth.spec.ts` | Signing in, starting **signed out** on purpose. A page without a session goes to `/login?next=…` and returns there after signing in; a wrong password is refused and says so; signing out ends the session for the API as well as the pages; `/api/proxy` and `/stream` answer `401` with no session; a forged cookie gets past the presence-only middleware but not the proxy, and the page is sent to `/login`; and the login page has no top bar and does not scroll sideways at 1024px |
| `stream.spec.ts` | `/stream` through the built Next.js server and the real output volume. It plants a 4096-byte `.mp4` and a symlink `leak.mp4` → `/run/secrets/session_secret` on the volume from the **API container**, which mounts it read-write as the other containers do in production (the dashboard's mount is read-only, and the link's target exists only in the dashboard container, which is the point). A `Range: bytes=100-199` request must come back `206` with the right `Content-Range`, exactly those bytes and `Cache-Control: private, no-cache`, and its `ETag` sent back as `If-None-Match` must get a `304` through the built server, and the link must be a `404` whose body does not contain the secret. The unit suite covers every case on a temporary tree; this proves the same against the built route, Docker's mounts and the real secret path |
| `analytics.spec.ts` | The Analytics page's tabs against the real API — it opens on Videos with the **Sort by** menu beside the filters and no spend controls, and the Spend tab shows this month and then Today as **host-zone** days. The browser runs in `Asia/Tokyo` and the test API in `America/New_York`, so the expected day is computed in New York: a Spend tab that took the browser's own zone would name the wrong day for part of every day. A backwards custom range is flagged and its figures hidden rather than sent. The graphs, with `/analytics` answered by the test itself (the stack cannot publish, having no postforme): at 1400px every graph sits right of the table; a mouse wheel over the table scrolls the table and **not the page**; rows grow from 50 to 100 to 120 as the box is scrolled to its end; clicking a platform bar sends the platform filter to the API; and at 1000px the graphs stack between the filters and the table |
| `archive.spec.ts` | Video retention and manual delete — a deleted video leaves the board and the Library, appears in the Archive with its record intact, and opens read-only with no actions |
| `pipeline.spec.ts` | The Kanban board — all column headers render (Scheduled among them), summary-strip counts match seeded data, the `ActionPane` shows the right buttons per status, and each approve/reject/revise transition moves the card. Also asserts the Overview badge shows host-local time with an explicit zone, never bare UTC. Also the visual-style picker: the register travels in the same atomic request as the topic approval, the server returns `409` on a later change, and the board says nothing misleading about a video still on Auto. Those run at `SCRIPT_READY` rather than `TOPIC_APPROVED` on purpose — the action pane only lists videos at a human checkpoint, so an assertion about a card that never renders would pass with the feature removed. One case covers Illustrated with no OpenAI key: the test stack sets none, so the option is disabled, the API answers `400`, and after a key is stored and the page reloaded the option is enabled. It clears the key again in `finally`, so no later spec inherits one. It asserts the option's `disabled` **DOM property**: Playwright's `toBeDisabled()` reports a disabled `<option>` inside an enabled `<select>` as enabled, so that assertion fails against working code. The same rule applies to the voice picker: a voice whose model cannot speak the script (a v2 voice against an `<ipa>` script) is a disabled option, the API refuses it with 409, and approving with the video's own voice goes straight through. At `TOPIC_PROPOSED` the voice picker puts a voice on another model onto the video with the approval; the negative control seeds the video from a project with a default voice and approves untouched, and the project's voice must survive rather than be replaced by the install default. An old script left behind by a topic revision disables no voice there. One case measures the row at 1280px: it does not wrap, the voice picker is the widest control on it, and a button pushed off-screen still reads as visible, so the buttons' right edges are asserted, along with the title keeping its width — the first run of this case failed on both, with the title crushed to nothing. One case checks the inbox's grouping and status filter through the real page: a newer `TOPIC_PROPOSED` card sorts above an older `VIDEO_READY` one, and a pill that hides `VIDEO_READY` keeps it hidden across a poll of `/videos/actionable`. `ActionPane` stays mounted while `PipelineClient` refetches, which a unit test cannot show |
| `modal.spec.ts` | `VideoModal` — opening from a card, the Script tab appearing only when there is a script, the always-present Comments tab, and that a posted comment persists. Also a video made stuck through the same API route the poller reports to: its card shows STUCK, the modal explains why, and Retry agent clears the flag without changing the status. A voiced-status video's modal shows its Voice and Voice model. This drives the real API, because `voice_info` comes only from the single-video fetch and never from the list row the modal opens on |
| `library.spec.ts` | The Library page — only library-eligible videos shown, plus the strategy filter, text search and score sort |
| `projects.spec.ts` | The Projects page — a seeded project appears, clicking it shows its videos, clicking a video opens the modal. One case seeds a project with a long description and an unbroken name, and measures both columns: the project list must stay at its fixed width, the video pane must keep the rest, and the name must wrap inside its row. Another picks a voice in the modal at `TOPIC_PROPOSED` and approves: it is the only proof the Projects page hands the modal the voice roster at all |
| `topics.spec.ts` | The Topics page — nav link, the three mode-toggle chips, toggling a mode off and back on persisting, the add-domain form, its description box sitting below the name (not beside it, where the tall box made the row ragged) with a working counter, the new domain's row keeping that two-paragraph description on one line, pausing and resuming a curriculum seed, and that a domain which is not a seed offers no pause control at all. A default voice picked on a domain row is saved, and the next video filed into the domain starts with it. A domain at its topic cap shows EXPIRED and refuses a curriculum video with `409`; raising the cap on the row saves, clears the badge, survives a reload and lets the next curriculum video in (manual videos fill it, since they are exempt). A seed row's three pickers and the topic cap field each carry their caption, and the row (count, badge and pause button included) still fits at 1280px with the domain name keeping real width and clear of the first caption. At 1280px the pause button must also sit level with the pickers rather than wrap under them, and a three-digit "120 filed" must stay on one line; the projects response is patched in the browser to that count, since filing 120 real topics would only slow the suite. Adding the cap field once pushed the button to a second line while the fit check still passed. The EXPIRED test also checks that an expired seed shows no ACTIVE badge, and that ACTIVE returns with the raised cap. A select sizes to its longest option, and three at that width once left the name about 70px wide with a long word running under "Visual style", while the fit check alone still passed. At 1024px the row must wrap instead, keeping the name's width and the pause button inside the row. The profile list is stubbed in the browser, because a real `READY` profile cannot be made here (creation makes a live transcript call); seeding is covered by the API suites. Mining sources: adding a URL, removing one and adding beside existing ones each survive a reload; the added `youtu.be` URL is listed in the canonical `watch?v=` form the API stores, and every fixture URL carries a real 11-character id, since the API refuses anything else |
| `script-profiles.spec.ts` | The Script Profiles page — the create form against the live API, refusing to submit without a name and a URL, and the empty state. One case measures the two columns with a long profile name, against a stubbed list: a real profile cannot be created here, and seeding one would break the empty-state case |
| `settings.spec.ts` | The Settings page — the AI review model and sampling rate persisting, the API rejecting a sampling rate outside Gemini's valid range, that the review loop cap and render retry cap are independent controls, user preferences persisting with their line breaks while the API refuses text over the cap, the Scheduling tab's agent-session settings persisting (the timeout entered in minutes, stored in seconds), AI review labelled experimental beside its switch, the Images tab offering only the OpenAI catalog with no provider select and the scene-image model persisting, the character model persisting on the Images tab, and every tab staying reachable at 1024px, since the page clips horizontal overflow. The Voice tab has no install-wide model select: changing one voice's model persists on that voice only, and the settings payload carries no `elevenlabs_model_id` or `pronunciation_mode`. The preview endpoint refuses an unknown model before any ElevenLabs call Auto Pilot, against the real API: a project is selected and the switch turned on, the confirmation appears with the warning, **the stored switch is still off until the dialog is confirmed**, and after confirming the saved document carries the project, the gap in minutes and the in-progress limit, the tab counts videos in progress against that limit, and the pipeline board shows its Auto Pilot notice. The narrow-width test measures the Auto Pilot tab, because the last tab added is the first to be pushed off a clipped row. |
| `new-video.spec.ts` | The New Video page against the real API: a submission lands at `TOPIC_APPROVED` in the `manual` domain and shows on the Pipeline with "—" for its score; unchecking auto-approve lands it at `TOPIC_PROPOSED`; a title over 70 cannot be submitted. The test stack installs no agents, so this runs the Automatic path |
| `topbar.spec.ts` | `TopBar` — the health indicator showing `NOMINAL` when the API is up, the version badge rendering a version served by the real API (a number, or `develop` on the development branch), and every nav link routing correctly. At 1024px, 1280px and 1600px the page does not scroll sideways, the last tab, Sign out and the health indicator are on screen, and the tabs sit on a second row inside the taller header. At 1640px (the breakpoint) and 1920px the bar stays one 56px row with nothing squeezed onto a second line — the original defect wrapped the active tab, the timezone and SYS onto two and three lines before it overflowed. Measured after the version badge renders, since it adds width. A browser measurement because the breakpoint is a CSS media query, which jsdom does not apply |

---

## What these encode

**`workers: 1` is not a performance oversight.** All specs share one seeded database. Raising it
produces failures that look like flakes and are not.

**The renderer container is deliberately in the test stack.** Without it, any spec that drives a
video to `RENDER_QUEUED` would hang there forever, because nothing would claim it.

**The split loop caps have a spec, not just a unit test.** `max_render_retries` and
`ai_review_max_loops` were one key once, and the regression — granting a review loop silently halving
the render-retry budget — is only visible through the real settings round-trip.

**A spec must reach the API through `BASE` from `fixtures/seed.ts`, never a hand-written URL.** One
spec hardcoded `http://localhost:4000` — the *production* port. It failed whenever the production
stack was down, and when that stack was up it would have exercised the wrong database entirely while
still reporting green. `BASE` is exported so there is no reason to retype a host.

**The settings save specs guard a real defect, not just a round-trip.** `SaveBar` must stay at module
scope in `dashboard/app/settings/page.tsx`. Declared inside the page component it gets a new function
identity every render, so React treats it as a different component type and rebuilds the `<button>`
DOM node. Because a numeric field commits on blur, clicking SAVE straight from a focused number input
replaced the button between `mousedown` and `mouseup`, the browser never synthesized a `click`, and
the first click on SAVE silently did nothing — no request, no toast, the tab still reading "unsaved
change". Selects and checkboxes were unaffected, so the page looked fine in most of the suite.

**The two-column pages assert geometry, because `toBeVisible()` cannot see a collapsed column.**
The Projects and Script Profiles pages give their left column a fixed `flex: "0 0 340px"`. That width
holds only with `minWidth: 0`. Without it, a flex item grows to its min-content width. A project
description (rendered `nowrap`) or a profile name with no spaces then widens the left column past
900px, and the right pane is squeezed to a sliver. A card squeezed like that still counts as visible,
so these cases measure `boundingBox()` instead. They also need long text to have any effect: with the
short fixture text the other specs use, the column never grows and the page cannot show the bug. The
profile name uses underscores rather than hyphens. A hyphen is a line-break opportunity, so a
hyphenated name passed against the broken page. Once the column holds its width, the same unbroken
name must wrap inside its row rather than paint over the video pane, so each case also checks that
the name's right edge stays within the row.

**Reproduce before dismissing a failure as a flake.** The mining-sources failure here was written off
as a pre-existing flake in two separate sessions before turning out to be a real, deterministic bug.

---

## Known gaps

- **The suite is only as current as its last run.** It went a long stretch without one, and in that
  window three specs silently drifted out of step with the product: two expected a `Publish` button
  on the `VIDEO_READY` card after publishing became a separate human-only step from `VIDEO_APPROVED`,
  and one matched a topic string that the modal had started rendering twice (the header falls back to
  `title || topic`, and the Topic tab shows the topic too), which trips Playwright's strict mode.
  None of these were product faults. Run the suite after any change to `ActionPane`, `VideoModal` or
  the Settings page rather than trusting that it still describes the UI.

- **There is no end-to-end pipeline test.** Nothing drives a topic through scripting → voicing →
  render → review. This suite is browser-level dashboard testing against a seeded database; the full
  pipeline path is still verified by hand.
