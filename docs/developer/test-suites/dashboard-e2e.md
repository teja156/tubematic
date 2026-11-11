# `dashboard/tests/e2e`

The suite drives the dashboard in Chromium against an isolated Docker stack. It is the one suite
that exercises the Next.js app, the Flask API and SQLite together. It needs Docker, Node 22 and
Playwright's browsers.

```bash
cd dashboard
npm run test:e2e                              # full suite
npm run test:e2e:headed                       # watch it run
npm run test:e2e:ui                           # Playwright's UI mode
npx playwright test specs/settings.spec.ts    # one spec
npx playwright test -g "Approve topic"        # one test by name
```

Every run builds the test stack's images first, which takes several gigabytes of disk.
[Development: Tests](../17-development.md#tests) has the setup.

## Infrastructure

[The test stack](../16-infrastructure.md#the-test-stack) is `docker-compose.test.yml`, with its own
project name, network and volumes.

| Service | Host port | What it is |
|---|---|---|
| `tubematic-api-test` | 4001 | The Flask API and the render gateway, on an isolated SQLite database |
| `tubematic-worker-test` | none | The worker: publishing, Auto Pilot, notifications and the other background passes |
| `tubematic-renderer-test` | none | The built-in renderer. It has no database and takes its work from the render gateway |
| `tubematic-dashboard-test` | 3001 | A production Next.js build |

The stack has no MCP server, no poller, no installed agents, no GPU, no OpenAI key and no postforme
key. Several specs stub one response in the browser for that reason.

The volumes are `test-db-data`, `test-jobs-data` and `test-output-videos`. To clear state by hand,
remove them by name. `docker volume prune` is not limited to the test stack.

The support files:

- `global-setup.ts` starts the stack, sets the test password with
  `python3 -m tubematic_core.auth set-password` inside the API container, signs in through the real
  login route and saves the browser state to `tests/e2e/.auth/state.json`. `global-teardown.ts`
  removes the containers and the volumes.
- `fixtures/seed.ts` holds the HTTP helpers that seed the database, and adds the test API token to
  each call. `patchVideo` adds a placeholder publish title and description when it seeds a `script`,
  because the API refuses a script without them. The file exports `BASE`, `API_AUTH` and
  `TEST_PASSWORD` for specs that call the API directly.
- `secrets/` holds fixed, public tokens that are valid for the test stack only.

A spec reaches the API through `BASE`. A hand-written `http://localhost:4000` aims at a real
install on the same machine: the spec fails when that install is down, and passes against the wrong
database when it is up.

## Configuration

From `playwright.config.ts`:

| Setting | Value | Reason |
|---|---|---|
| `workers` | `1` | Every test shares one database, so parallel tests race and fail at random |
| `retries` | `1` | One retry absorbs timing variation. Reproduce a failure before you call it a flake |
| `timeout` | `30_000` | Covers the board's 5-second polling plus container startup variation |
| `baseURL` | `http://localhost:3001` | The test dashboard. A real install uses 3000 |
| `timezoneId` | `Asia/Tokyo` | The API runs in `America/New_York`. A time that matches the API's zone proves the dashboard did not use the browser's |
| `screenshot` | `only-on-failure` | Captured when a test fails |
| `video` | `retain-on-failure` | Kept only for a failed test |
| `storageState` | `./tests/e2e/.auth/state.json` | Every spec starts signed in. `auth.spec.ts` overrides it with an empty state |

## Sign-in and media

### `auth.spec.ts`

Covers [signing in](../15-dashboard.md#signing-in) through the built app, starting signed out.

- A page without a session goes to `/login?next=…` and returns after sign-in. A wrong password is
  refused with a message.
- Signing out ends the session for the API proxy as well as for the pages, and `/api/proxy` and
  `/stream` answer `401` with no session.
- A forged cookie passes the middleware, which checks only that a cookie is present. The proxy
  refuses it and the page goes to `/login`.

### `stream.spec.ts`

Covers the [`/stream` route](../15-dashboard.md#dashboardappstreampathroutets) through the built
Next.js server and the real output volume. A `Range` request returns the requested bytes as a `206`,
its `ETag` sent back returns a `304`, and a symlink on the volume that points at the dashboard's
session secret returns a `404` without the secret.

The unit suite covers every case on a temporary tree
([`stream-route.test.ts`](dashboard-unit.md#stream-routetestts)). This spec proves the same against
Docker's mounts and the real secret path.

Needs: `docker compose exec` into the API container, which plants the files. The API container
mounts the output volume read-write, the dashboard mounts it read-only, and the link's target exists
only in the dashboard container.

## Board and video window

### `pipeline.spec.ts`

Covers [the pipeline board](../15-dashboard.md#the-pipeline-board) and
[Quick Actions](../15-dashboard.md#quick-actions) against the real API.

- Each status shows its own buttons, and each approve, reject and revise moves the card. The
  `VIDEO_READY` row offers no publish action.
- The voice picker at `SCRIPT_READY`: a picked voice is stored with the approval, and a voice whose
  model cannot speak the script is a disabled option that the API refuses with `409`.
- The voice picker at `TOPIC_PROPOSED`: a voice on another model goes onto the video with the
  approval, and an untouched picker keeps the domain's default voice.
- The visual style travels in the same request as the topic approval, and the API answers `409` to
  a later change. Illustrated with no OpenAI key is a disabled option that the API refuses with
  `400`.
- The style picker offers the list `GET /visual-styles` serves and nothing else, System Flow and Whiteboard
  included, and a System Flow pick is stored with the approval.
- A status pill that hides a group keeps it hidden across a poll.
- At 1280px the `TOPIC_PROPOSED` row's buttons stay on screen and the title keeps its width.
- A `TOPIC_PROPOSED` row shows the topic's angle with its kind and score. At 1280px a long angle
  stays on one line no wider than the title column, with the buttons on screen, and the row drops
  the angle once the video is at `SCRIPT_READY`.

Trap: assert a disabled `<option>` with `toHaveJSProperty("disabled", true)`. Playwright's
`toBeDisabled()` reports a disabled option inside an enabled `<select>` as enabled.

Trap: the read-only style case runs at `SCRIPT_READY`. Quick Actions lists only videos at a human
checkpoint, so at `TOPIC_APPROVED` no card renders and an assertion about it passes with the feature
removed.

Trap: the 1280px case measures positions with `boundingBox()`, because Playwright counts a button
pushed off screen as visible.

Needs: the Illustrated case stores an OpenAI key and clears it in `finally`, so that no later spec
inherits one.

### `modal.spec.ts`

Covers [the video window](../15-dashboard.md#the-video-window) against the real API.

- The window opens from a card. The Script tab shows only when there is a script, and Comments is
  read-only.
- A revision comment persists, and a revision at `SCRIPT_READY` moves the video to
  `REVISION_REQUESTED`.
- A video flagged stuck through `POST /videos/<id>/agent-outcome`, the route the poller reports to,
  shows STUCK on its card, and **Retry agent** clears the flag without changing the status.
- A `PARTIALLY_PUBLISHED` video sits in the Published column tagged PARTIAL, and **Mark as
  published** moves it to `PUBLISHED`.
- A video whose style Auto picked shows the reason, and **Switch to …** moves it to
  `TOPIC_APPROVED` with the runner-up as its style. The pick is seeded in the API container with
  `docker compose exec`, because only the agent's `choose_visual_style` writes one and the test
  stack runs no agent.
- A video with a script record shows the formula and the opening type by the labels the real
  `GET /script-formulas` returns, the openings and the warnings. A script written over HTTP then
  clears the record. The record is seeded the same way, because only `update_video` writes one.
- The Topic tab shows a topic's angle with the kind label the real `GET /angle-kinds` returns.
  **Edit** stores a new sentence and kind and clears the score. After the topic is approved the
  block has no Edit button and the API refuses the same write.

Trap: the Voice and Voice model rows need the real API, because `voice_info` comes only from the
single-video fetch and the list row the window opens on does not carry it.

Trap: match the window's title by its heading. The topic renders twice in the window (the header
falls back to `title || topic`), so a plain `getByText` fails Playwright's strict mode.

### `topbar.spec.ts`

Covers `TopBar` in the built app ([Components](../15-dashboard.md#components)).

- The health indicator, the nav links, the version badge and the timezone badge, which shows the
  API's host zone.
- The disk-usage figure opens a popup inside the viewport that says the Docker half is not
  measured.
- At 1024px, 1280px and 1600px the page does not scroll sideways and the tabs sit on a second row.
  At 1640px (the breakpoint) and 1920px the bar is one row.

Trap: the layout is measured in a browser, after the version and disk-usage badges render. Both
badges add width, and the breakpoint is a CSS media query that the unit suite's DOM does not apply.

## Pages

### `library.spec.ts`

Covers the Library page: it lists only library-eligible videos, and the research-mode filter, the
text search and the score sort work against the real API.

### `archive.spec.ts`

Covers manual delete and the Archive page. A deleted video leaves the board and the Library and
appears in the Archive with its record intact, and it opens read-only with no actions.

### `projects.spec.ts`

Covers the Projects page: a seeded domain, its videos and the video window. A voice picked in the
window at `TOPIC_PROPOSED` is stored with the approval, which proves the page hands the window the
voice roster.

Trap: the [two-column pages](../15-dashboard.md#pages) need `minWidth: 0` on the fixed column, and
`toBeVisible()` passes on a pane squeezed to a sliver, so the layout case measures `boundingBox()`.
The fixture needs a long description, because short text cannot widen the column. The unbroken name
uses underscores: a hyphen is a line-break opportunity, so a hyphenated name passes against the
broken layout.

### `script-profiles.spec.ts`

Covers the Script Profiles page: the create form against the live API, the empty state, and the
same two-column measurement as [`projects.spec.ts`](#projectsspects) with a long unbroken name.

Needs: the layout case stubs the profile list in the browser. Creating a real profile makes a live
transcript call, and seeding one would break the empty-state case.

### `mascots.spec.ts`

Covers the Mascots page against the real API.

- The built-in Tubi is listed as `READY` and offers only **Ask for a variation**. Its sheets load
  through the [authenticated image route](../15-dashboard.md#dashboardappmascot-sheetspathroutets),
  which refuses a path that is not a sheet and a request with no session.
- A new mascot is filed as `PENDING` and can be archived.
- The Profiles tab stays active on `/mascots` and fits the one-row top bar at 1640px.
- `/settings?tab=rendering` opens the Rendering tab with the default-mascot picker.

Needs: a unique mascot name per run and per retry. The id is a slug of the name, so a retry would
collide with the mascot a failed attempt left behind.

### `topics.spec.ts`

Covers [the Topics page](../15-dashboard.md#the-topics-page).

- A curriculum seed can be paused and resumed. A domain that is not a seed offers no pause control.
- A default voice picked in a domain's panel is saved, and the next video filed into the domain
  starts with it. The same holds for an effort, which also survives a reload.
- A domain at its topic cap shows EXPIRED and refuses a curriculum video with `409`. Raising the cap
  in the panel reopens it.
- At 1280px a seed row with three chips is one line: the pause and **Edit defaults** buttons sit
  beside the name and chips, and the name keeps its width. The open panel sits under that line,
  each of its eight controls has a caption and stays inside it, and opening it moves nothing on the
  line. At 1024px the line wraps and the buttons and controls stay inside the row.
- A mining source added or removed survives a reload.

Trap: the row case asserts each position separately. A check that the row fits its container still
passes when the pause button wraps to a second line or when the chips squeeze the name.

Needs: two stubbed responses in the row case. A `READY` script profile cannot be made in the stack,
and the projects response is patched to a three-digit count and three defaults, because filing 120
topics would slow the suite. The cap case fills the domain with manual videos, which are exempt
from the cap. The stack installs no agents, so the effort is the only agent default a browser can
set here.

### `new-video.spec.ts`

Covers [the New Video page](../15-dashboard.md#the-new-video-page) against the real
`POST /videos/manual`. A submission lands at `TOPIC_APPROVED` in the `manual` domain with a dash for
its score, or at `TOPIC_PROPOSED` with auto-approve cleared. The stack installs no agents, so the
spec runs the Automatic path only. A submission with no angle is stored with none, a typed angle
needs its kind before the form submits, and a given angle is stored with score 0.

### `analytics.spec.ts`

Covers the Analytics page's three tabs.

- At 1400px the graphs sit right of the table, a mouse wheel over the table scrolls the table and
  leaves the page still, and rows load 50 at a time. At 1000px the graphs stack above the table.
- Clicking a platform bar sends the platform filter to the API.
- At 1680px the list's ten columns fit its box. At 1680px and 1000px the page does not scroll
  sideways, on the Videos tab or the Watch time tab, and the Watch time tab shows its `TOO FEW` tag.
- The Watch time tab reads the real API, which has nothing published and says so.
- The Spend tab shows this month and Today as days in the host's zone, and a backwards custom range
  is flagged and not sent.

Trap: the expected day is computed in `America/New_York`, the API's zone, while the browser runs in
`Asia/Tokyo`. A Spend tab that resolved "today" in the browser's zone names the wrong day for part
of every day ([Time](../15-dashboard.md#time)).

Needs: the graph cases answer `/analytics` in the browser, because the stack cannot publish.

### `settings.spec.ts`

Covers [the settings page](../15-dashboard.md#the-settings-page) against the real API.

- An edit is staged until **SAVE** is clicked, and each tab's values persist through a reload.
- A voice's model is stored on that voice only, and the preview endpoint refuses an unknown model
  before any ElevenLabs call.
- Auto Pilot: the stored switch stays off until the confirmation dialog is confirmed.
- The Renderers panel shows the built-in renderer's startup probe as CPU rendering with a
  SwiftShader renderer string.

Trap: `SaveBar` must stay at module scope in `dashboard/app/settings/page.tsx`. Declared inside the
page component it is a new component type on every render, so React rebuilds the button between
`mousedown` and `mouseup` when a number field commits on blur, and the click on **SAVE** is lost.

Trap: the page clips horizontal overflow, so a tab pushed past the right edge cannot be reached. The
1024px case measures the last tab, because the newest tab is the first one pushed off.

Trap: `max_render_retries` and `ai_review_max_loops` have a spec because only the real settings
round trip shows one key changing the other.

Needs: up to four minutes for the Renderers case. The probe is a Remotion still in the real image,
and this is the one place the round trip from the renderer through Chromium and the API to the
dashboard runs.

## Known gaps

- CI runs this suite only on a release tag and on a manual dispatch, and the job does not block
  ([Releases: `ci.yml`](../18-releases.md#ciyml-pull-requests-and-pushes)). Run it yourself after a
  change to `ActionPane`, `VideoModal`, `TopBar` or the Settings page.
- No spec drives a topic through scripting, voicing, rendering and review. The suite tests the
  dashboard against a seeded database.
- The stack has no postforme key, so no spec publishes a video. The publishing dialogs are covered
  by the unit suite.
