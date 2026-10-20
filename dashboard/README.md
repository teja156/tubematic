# Tubematic Dashboard

The dashboard is the human-facing control plane for the Tubematic automated YouTube Shorts pipeline. It shows where every video is in the pipeline, lets operators approve or reject topics and scripts, and manages the research domains and scheduling modes that feed the pipeline.

---

## What it does

The main pages, each scoped to a distinct operator workflow. The top bar also links to the Archive,
Projects, Script Profiles, Socials, Analytics, Logs and Settings pages; the full page list is in
[docs/developer/15-dashboard.md](../docs/developer/15-dashboard.md#pages).

### Pipeline (`/`)

The main working view. Shows:
- **Summary strip** — six tiles with live counts of videos in each stage (Topics Awaiting, Scripts Ready, Videos Ready, In Pipeline, Published, Failed)
- **Quick Actions** — inbox of videos waiting for a human decision, grouped by status (Topic Proposed, then Script Ready, then Video Ready, oldest first within each), with a pill per status to hide or show it. Each row shows the right buttons for its checkpoint: Approve/Reject/Revise for topics, Read/Approve/Revise for scripts, Watch/Approve/Revise for finished videos
- **Kanban board** — 11 main columns in pipeline order plus 3 side columns (Rejected, Revision Requested, Failed), so you can see the full in-flight queue at a glance
- **Video modal** — opens on any card click, showing script, video player, a read-only comments thread, the cost per provider and model (at API list prices), and action buttons. A human comment is added only through **Request Revision** (topics, scripts and finished videos), which is also what the action pane's **Revise** opens

### New Video (`/new-video`)

Submit a video by hand, without an agent session: a title, the topic brief, optional agent / model / effort / script profile / visual style / voice, and an **Automatically approve topic** checkbox (on by default). Submissions are filed under the **Manual Videos** domain, unscored.

### Library (`/library`)

Read-only view of all videos that have cleared the pipeline (VIDEO_READY, VIDEO_APPROVED, SCHEDULED — with the time each post goes out — PUBLISHING and PUBLISHED). Supports text search, strategy filter (curriculum / trending / mining / manual), and sort by producibility score or date.

### Topics (`/topics`)

Management view for the research engine:
- **Mode toggles** — turn the three automated research modes (curriculum, trending, mining) on or off for the next scheduled cycle
- **Domain management** — add curriculum seed domains (e.g. "Python Internals"), view video counts per domain, pause or resume topic generation for a curriculum seed, and set each domain's topic cap (a domain at its cap shows EXPIRED and takes no more research topics)

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 15 (App Router, `output: "standalone"`), React 19 |
| Language | TypeScript 5 |
| Styling | Tailwind CSS 4 (utility classes) + inline styles for pixel-precise layout |
| UI primitives | shadcn/ui components (`Dialog`, `Tabs`, `Badge`, `Button`, `Textarea`) |
| Markdown rendering | `react-markdown` + `remark-gfm` (used in comment thread and AI review panel) |
| Build | Turbopack (`next dev --turbopack`, `next build --turbopack`) |

---

## How it connects to the backend

All data flows through a single Next.js proxy route: `app/api/proxy/[...path]/route.ts`.

Every fetch call in every client component is relative, targeting `/api/proxy/<path>`. The proxy route strips that prefix and forwards the request — with the same method, body, and query string — to the renderer Flask API at `RENDERER_URL` (default `http://localhost:4000`). Every response carries `Cache-Control: no-store` so neither the browser nor Next.js ever caches pipeline state.

```
Browser  →  /api/proxy/videos         →  http://localhost:4000/videos
Browser  →  /api/proxy/videos/abc123  →  http://localhost:4000/videos/abc123
Browser  →  /api/proxy/stats          →  http://localhost:4000/stats
```

A second route — `app/stream/[...path]/route.ts` — streams `.mp4` and `.mp3` files directly from the `/output_videos` volume mount with range-request support (HTTP 206), so the browser `<video>` element can scrub without downloading the full file. It serves nothing else, and a symlink that leads out of the volume is a 404 — see `docs/developer/15-dashboard.md` → the stream route.

A third, `app/api/update-check/route.ts`, is the update check behind the "newer release available" banner. It asks GitHub's releases API for this project's releases at most every two hours, caching the list in memory. That cache is the one deliberate exception to `no-store` below: a release list is not pipeline state. See `docs/developer/15-dashboard.md` → Update check.

### Ports

| Service | Port |
|---------|------|
| Dashboard (dev) | 3000 |
| Dashboard (test containers) | 3001 |
| Renderer Flask API | 4000 |
| Renderer test containers | 4001 |
| MCP server (`tubematic-mcp` container) | 4100 |

---

## Development

```bash
npm install
npm run dev      # http://localhost:3000
```

The renderer Flask API must be running (via `docker compose up`) for data to load. Without it, every fetch returns a 502 from the proxy.

Every page needs a sign-in, and the server-side routes read two secrets: `api_token` (sent to Flask) and `session_secret` (signs the login cookie). In a container they are mounted at `/run/secrets`; for `npm run dev` on the host, point the dashboard at your install's copies:

```bash
TUBEMATIC_SECRETS_DIR=~/.tubematic-data/secrets npm run dev
```

and sign in with the dashboard password (`python onboard.py --set-password` sets one).

---

## Key architectural decisions

**One proxy route, not per-resource routes.** All API calls go through `/api/proxy/[...path]`. This means adding a new Flask endpoint requires no dashboard changes — the proxy forwards it automatically.

**The login is enforced in the routes, not the middleware.** `middleware.ts` only redirects a page load that has no session cookie to `/login`; it runs on the Edge runtime, which cannot read the signing secret. The proxy route and the stream route verify the cookie's signature on every request, and every page loads its data through them. See `docs/developer/15-dashboard.md` → Signing in.

**State-changing requests must be same-origin JSON.** The proxy and the login and logout routes refuse a non-`GET` whose `Sec-Fetch-Site` is present and not `same-origin` (403), and one whose body is not `application/json` (415) — `lib/requestGuard.ts`. A new `fetch()` that sends a body must set `Content-Type: application/json`; a bodiless `POST` or `DELETE` needs no type. See `docs/developer/15-dashboard.md` → Cross-site request forgery.

**`cache: "no-store"` everywhere.** Pipeline state changes second-by-second. Any caching produces phantom states (e.g. a video appearing stuck in `TOPIC_APPROVED` when it's already in `VOICING`). This is enforced in the proxy route, all `fetch()` calls in components, and the `dynamic = "force-dynamic"` export on the proxy.

**5-second polling, not WebSockets.** The pipeline advances via a separate cron process, not via browser interactions. Polling at 5 s is simple, predictable, and sufficient.

**Client components for the data-fetching layer.** `PipelineClient` and `LibraryPage` are `"use client"` components that own their own fetch-and-poll loops. Page components (`app/page.tsx`, `app/library/page.tsx`) are thin server components that just mount the client.

---

## Testing

Full technical documentation for both test suites is in [`tests/README.md`](tests/README.md).

Quick reference:

```bash
# Unit tests (Vitest — no infrastructure required)
npm test
npm run test:watch

# E2E tests (Playwright — requires Docker)
npm run test:e2e
npm run test:e2e:headed   # watch the browser
npm run test:e2e:ui       # Playwright interactive UI
```

| Suite | Infrastructure |
|-------|----------------|
| Unit | None — runs anywhere |
| E2E | Docker (auto-started by Playwright global setup) |
