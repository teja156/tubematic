# The Worker

`renderer/api/worker.py` is the process that does the pipeline's background housekeeping without an
agent. It runs in the `tubematic-worker` container, has no HTTP server and no exposed ports, and is
one endless loop over the database: it settles published posts, runs Auto Pilot, polls analytics,
syncs prices, deletes old output, sends checkpoint notifications, flags stalled videos, and keeps
two backstops for rendering. Beside the loop, a thread of its own runs the AI review of every
uploaded render.

It does not render. Rendering and the GPU test are the renderers' (`renderer/api/render_agent.py`,
the built-in one in the `tubematic-renderer` container), and a renderer reaches the database only
through the render gateway in `tubematic-api` — see
[Rendering and Review](11-rendering-and-review.md). The worker and the renderer used to be one loop
in one container, and a render held every other pass for as long as it took. Split, a post that
falls due or a checkpoint Auto Pilot should approve never waits behind a render, and recreating the
renderer (`onboard.py --step gpu` does) never interrupts them.

The worker and the renderer are two of the loops that advance the pipeline with nobody watching.
The third is the poller, which starts agent sessions. See [The Poller](13-the-poller.md). None of
them calls another: the worker and the poller meet the rest in the database, through a video's
status, and a renderer meets it through the gateway.

This page is the worker's loop: what runs, in what order, how often, and the rules every pass
follows. What each pass decides is on the page that owns that subject, linked from the table below.

---

## One tick

```mermaid
flowchart TD
    S[startup: migrate the database] --> P
    P[1 · publishing: release due scheduled posts,<br/>settle posts in flight] --> A
    A[2 · Auto Pilot: approve checkpoints,<br/>start one post] --> M
    M[3 · analytics poll — hourly] --> PR
    PR[4 · price sync — weekly] --> R
    R[5 · retention sweep — hourly] --> N
    N[6 · checkpoint notifications] --> V
    V[7 · stalled-voicing check] --> L
    L[8 · render lease sweep] --> G
    G[9 · GPU-wait sweep] --> SL
    SL[sleep 20 s] --> P
    S --> RT["review thread: AI review of the<br/>oldest uploaded render, one at a time"]
```

| # | Pass | Symbol | Runs | Does nothing unless | Owned by |
|---|---|---|---|---|---|
| 1 | Publishing | `_poll_publishing_videos` | every tick | publishing is on and a postforme key is stored | [Publishing](14-publishing.md#the-worker) |
| 2 | Auto Pilot | `_sweep_auto_pilot` | every tick | Auto Pilot is on, the pipeline is not paused, a project is selected. The [in-progress limit](14-publishing.md#the-in-progress-limit) holds back only new scripts and topics, never finished videos or scheduling | [Publishing](14-publishing.md#auto-pilot) |
| 3 | Analytics poll | `_poll_video_metrics` | hourly | publishing is on and a postforme key is stored | [Publishing](14-publishing.md#the-worker) |
| 4 | Price sync | `_sync_prices_if_due` | weekly | always runs when due | [Settings](../user-guide/05-settings.md#costs) |
| 5 | Retention sweep | `_sweep_retention` | hourly | either retention key is above 0 | [Rendering and Review](11-rendering-and-review.md#retention) |
| 6 | Notifications: the three checkpoints, a partial publish, `FAILED` | `_sweep_notifications` | every tick | a webhook and at least one trigger are set | [The Pipeline](02-pipeline.md#notifications) |
| 7 | Stalled-voicing check | `_sweep_stalled_voicing` | every tick | the pipeline is not paused | [The Pipeline](02-pipeline.md#script_ready--the-money-checkpoint) |
| 8 | Render lease sweep | `_sweep_render_leases` | every tick | a `RENDERING` video, not yet uploaded, whose lease has run out or which no renderer holds | [Rendering and Review](11-rendering-and-review.md#leases-restarts-and-lost-renderers) |
| 9 | GPU-wait sweep | `_sweep_gpu_waits` | every tick | a GPU-only video is queued and no renderer that could take it is online | [Rendering and Review](11-rendering-and-review.md#videos-that-render-on-the-gpu-only) |
| — | AI review | `_review_once`, on its own thread (`_start_review_thread`) | continuously: every 5 s when idle, 1 s after a review | a `RENDERING` video has been uploaded (`render_uploaded_at` set) | [Rendering and Review](11-rendering-and-review.md#ai-review) |

The loop itself is `worker.py::main`.

**The review is a thread, not a pass**, because one review is a paid Gemini call that takes minutes
(upload, wait for the file to become `ACTIVE`, then the model watches it). As a pass it would hold
every other pass for that long — the very thing splitting the worker from the renderer removed. It
reviews one video at a time, oldest upload first, so several reviews never race for the same quota.
It always moves the video on (`VIDEO_READY` or `REVISION_REQUESTED`), and a worker restart mid-review
simply reviews again, because the row is still `RENDERING` and uploaded.

**The two render sweeps are backstops, not the render path.** A renderer that restarts says so in
its first heartbeat and the gateway re-queues its renders at once; the lease sweep is for one that
never comes back. The GPU-wait sweep exists because a GPU-only video is offered only to a renderer
whose GPU passed its test, so with none at all it would wait for ever.

## What a tick is

A tick is one trip round the loop. Every pass is short, so after the last one the worker sleeps
`WORKER_POLL_INTERVAL_SECS` (default 20 seconds) and goes round again. So every pass runs about
every 20 seconds. The interval is a plain environment variable, not a settings row. When it is
unset the worker falls back to `RENDER_POLL_INTERVAL_SECS`, which set this loop's interval when it
still ran inside the renderer, so an existing override keeps applying.

"Hourly" and "weekly" mean *at most* that often. Those passes are checked every tick and skipped
until their interval has passed.

Nothing is lost if a tick runs late: every pass works from the database's current state, not from
a queue of events, so it simply catches up on the next tick.

## The order, and why

The order is not arbitrary, and two positions are load-bearing.

- **Publishing runs before Auto Pilot.** The publishing pass releases scheduled posts that are due
  and settles posts in flight. Auto Pilot's slot calculation reads those same rows to see when each
  account last posted, so it must see them settled first. The in-progress limit counts posts
  waiting at `SCHEDULED` and settled ones leave it, so the count must also be read after that pass,
  or a new video would wait one tick longer than it should.
- **Auto Pilot runs before notifications.** A checkpoint Auto Pilot approves has already moved on by
  the time the notification sweep looks, so it is never also announced as waiting for a human.
  Swap the two and every auto-approved script sends a "needs your approval" message.

## Rules every pass follows

**A pass never raises into the loop.** `main` has no exception handler, deliberately: an escaping
exception ends the process, and every other pass with it, publishing included, until the container
restarts. A pass that fails every time would then crash-loop the container. So each pass catches
its own exceptions, logs them and returns. A broken sweep costs that sweep, not the others.

**A throttled pass stamps its time before it does its work.** The hourly and weekly passes record
"last run" in a settings row first, then run. A pass that dies half-way is therefore not retried
twenty seconds later, and again twenty seconds after that. The stamp rows are listed under
[Settings](04-settings.md#undeclared-rows).

**Settings are read on every use, never cached.** Each pass reads what it needs from the settings
table when it runs. Turning Auto Pilot off, changing a retention period or rotating a key applies
on the next tick, with no restart.

**Every status change is guarded on the status it expects.** A pass moves a video with
`UPDATE … WHERE id = ? AND status = ?`, so a human or an agent who acted first wins and the pass
does nothing. This is what makes it safe for the worker, the render gateway, the rest of the API
and the MCP server to all write the same table.

**A pass that only observes must not touch `updated_at`.** That column is the render queue's
ordering key and the stalled-voicing clock. The notification sweep and the stalled-voicing check
record what they have seen in their own columns for that reason.

**Pausing the pipeline stops very little here.** Pause is an instruction to the poller not to start
agent sessions. In the worker only two passes read it: Auto Pilot does nothing while paused, and
the stalled-voicing check stops its clock. Publishing, analytics, retention and notifications all
carry on, because a post already scheduled is work the human has asked for. Neither do the render
sweeps, the review thread or the renderers.

## What it never does

- **It never renders, and never claims.** A video at `RENDER_QUEUED` goes to a renderer only
  through the gateway's claim. The worker moves a render-stage video in three cases only: the review
  thread finishes an uploaded render, the lease sweep re-queues a lost one, and the GPU-wait sweep
  fails a queued GPU-only video no renderer can take. Each is guarded on the status and columns it
  expects, so a renderer's result that arrived first wins.
- **It never starts an agent.** Agent sessions are the poller's. When work needs an agent, the
  video's status says so and the poller picks it up.
- **It never takes a request.** The dashboard's Publish, Retry and Cancel actions go to the Flask
  API, which acts at once and leaves rows for the worker to settle. The one thing the two share in
  code is `pipeline.py::start_publish`, which the API calls for a human and the worker calls for
  Auto Pilot, so both run the same claim, upload and reconciliation rules.
- **It never trusts a stored file path.** The retention sweep finds a video's mp4 and job directory
  from the video's and project's ids, not from the row's path columns, as the render gateway does — see
  [Refused before anything renders](11-rendering-and-review.md#refused-before-anything-renders).

## Watching it

```bash
docker compose logs -f tubematic-worker
```

Every line is prefixed `[worker]`, and a line about one video carries its id in brackets. The same
records go to the structured log the dashboard's Logs page reads, under the `worker` service; see
[Troubleshooting](../user-guide/08-troubleshooting.md#logs).

A quiet log on an idle install is normal: a pass with nothing to do logs nothing.

## Adding a pass

1. Write `_your_pass_once()` and a wrapper `_your_pass()` that calls it inside `try`/`except
   Exception` and logs the exception. Copy `_sweep_stalled_voicing` for the shape.
2. If it should not run every tick, gate it on a settings-row stamp written before the work, as
   `_sweep_retention` does.
3. Call it from `worker.py::main`, and decide its position against the two ordering rules above.
   It must not block: a pass that waits on something slow delays every other pass by as long.
   Rendering is in `render_agent.py`, and the AI review on its own thread, for exactly that reason.
4. Guard every status write on the status you expect, and do not write `updated_at` unless the pass
   really is advancing the video.
5. Add the row to the table on this page, and document what the pass decides on the page that owns
   the subject.
