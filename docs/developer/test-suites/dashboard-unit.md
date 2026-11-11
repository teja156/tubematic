# `dashboard/tests/unit`

The suite covers the Next.js dashboard's pages, components, route handlers and `lib/` helpers. It
runs under vitest with `@testing-library/react` and `@testing-library/jest-dom` in happy-dom, with
`TZ=UTC` set by `vitest.config.ts`. Every test mocks `fetch`, so the suite needs no browser, container or network.

```bash
cd dashboard
npm test                      # vitest run
npm run test:watch
npm test -- settings-page     # one file
```

[Dashboard internals](../15-dashboard.md) owns the behaviour these tests guard, and gives the full
reason behind each trap below. happy-dom does no layout, so widths, wrapping and breakpoints are
tested in [the end-to-end suite](dashboard-e2e.md).

Two rules recur across the entries:

- An untouched picker (one nobody has changed) does not send a value the page worked out
  ([What each approval sends](../15-dashboard.md#what-each-approval-sends)).
- A metric nobody reported renders as a dash, because "not reported" and "reported as zero" are
  different claims.

## Pages

### `pipeline-client.test.tsx`

Covers `components/PipelineClient.tsx`, the root of
[the pipeline board](../15-dashboard.md#the-pipeline-board).

- Loading and 5-second polling. A stale response that arrives after a newer one is dropped.
- The voice roster, the OpenAI-key state and the agents reach `ActionPane`.
- The **Nothing can render** banner shows when videos are queued and no renderer can take one,
  including when the only online renderer's credential has expired. It stays down when `/renderers`
  cannot be read.

### `library-page.test.tsx`

Covers `app/library/page.tsx`.

- Loading, polling, and a search over both the short title and the full topic.
- Delete and Request Revision from the video window reach the API, and a refused action is
  reported.
- `publishingEnabled` comes from `/settings` and is off until that answers and after a failed read.

Trap: the page filters statuses in the browser, so a status missing from its list does not appear.
One case guards `PARTIALLY_PUBLISHED`, which is listed under its own **Partially published** state.

Trap: the Library lists the videos that **Publish…**, **Retry publishing** and **Cancel schedule**
apply to, so the video window needs the publishing flag here.

### `projects-page.test.tsx`

Covers `app/projects/page.tsx`: the domain list, the videos of the selected domain, polling and
dates in the host timezone. The active or paused badge appears on a curriculum seed only, because
no other domain can be paused. The expired badge appears on any domain at its topic cap.

### `projects-page-action-extra.test.tsx`

Covers the Projects page's own action dispatcher ([Actions](../15-dashboard.md#actions)).

- The picks the video window passes as the action's `extra` argument travel in the same `PATCH` as
  the status change.
- The page hands the video window the voice roster and `publishingEnabled` from `/settings`.

Trap: a dispatcher that drops `extra` still renders the pickers and the request still succeeds, so
the picks are lost with no error. The API freezes them at approval, so they cannot be applied later.

### `projects-page-agent-picker.test.tsx`

Covers the Projects page with the real `VideoModal`, on the path where nobody touches the agent
picker. Approving a topic sends no `agent_id` and approving a script sends no agent field, before
and after `/agents` answers. A picked agent does reach the `PATCH`.

Trap: a test that always picks an agent cannot catch a page that submits a guessed agent as an
explicit value.

### `topics-page.test.tsx`

Covers `app/topics/page.tsx`, [the Topics page](../15-dashboard.md#the-topics-page).

- Mining sources: a refused save shows the API's message, and a successful save lists what the API
  stored. The Mining toggle is disabled while the API reports `mining_available: false`.
- The pause control appears on a curriculum seed only, labelled "Pause topic generation".
- The default pickers on a domain row and in the add form (visual style, voice, script profile,
  mascot) are found by their captions. A default that has left the roster or the profile list stays
  visible as removed or unavailable.
- The mascot default offers "Use install default", "None" and each pickable mascot. Mascots are
  disabled with the reason unless the GPU is working, and while the GPU status has not loaded.
- The topic cap field saves on blur and reverts an invalid entry. EXPIRED shows on any domain at
  its cap, and an expired seed hides ACTIVE and keeps PAUSED.
- The add form's description keeps interior newlines and stops at 2000 code points.

Trap: [`POST /projects`](../05-http-api.md#post-projects) replaces the whole row, so every edit
re-sends every field. A field left out is reset by that edit: an omitted `default_mascot_id` returns
the domain to the install default, and an omitted `topic_cap` resets the cap to 100.

Trap: after a cap edit, the count and the expired state come from the row the API returns. The count
the page loaded can be stale, because research may have filed a topic in between.

### `new-video-page.test.tsx`

Covers the request body of [the New Video page](../15-dashboard.md#the-new-video-page).

- Untouched pickers send no `agent_id` and `""` for `agent_model` and `agent_effort`. A picked
  agent pins its default model.
- The voice picker's **Default** names the voice the API will give the video.
- Submit is blocked with a title over 70 code points, and a refusal keeps the input.

### `script-profiles-page.test.tsx`

Covers `app/script-profiles/page.tsx`: the list with each status, the create form (a name and one
URL per line, both required), a `FAILED` profile's stored error and delete after a confirm.
Selecting a row fetches the full row, because the list omits the markdown.

### `mascots.test.tsx`

Covers `app/mascots/page.tsx`.

- The create form sends a name and description, or `surprise: true` alone for **Surprise me**.
- An `IN_REVIEW` mascot shows its draft and approved sheets through `/mascot-sheets/…`. **Approve**
  sends no body, and **Request changes** needs a comment.
- The review actions follow the status. A built-in offers **Ask for a variation** (`based_on`) in
  place of **Request changes**, and an archived mascot offers nothing.

Trap: **Archive** is disabled while another action on the mascot is in flight, and that action's
buttons are disabled during an archive, because the two requests race at the API.

### `profiles-nav.test.tsx`

Covers `components/ProfilesNav.tsx`, the sub-nav on the Script Profiles and Mascots pages: both
links render and the current page is marked. The two pages share one top-bar tab, because another
tab does not fit the bar's one-row layout.

### `settings-page.test.tsx`

Covers `app/settings/page.tsx`, [the settings page](../15-dashboard.md#the-settings-page).

- Staged saving: **SAVE** sends only the edited field, and switching tabs with unsaved edits asks
  first. The pause switch applies at once.
- Each tab saves only its own keys, with its bounds and units (timeouts shown in minutes and stored
  in seconds).
- An API key renders as the mask the server returned. Clearing the field posts an empty string.
- Voice: each roster row picks its own model, and a save carries the roster with no
  `elevenlabs_model_id` or `pronunciation_mode` key. A row's speed is saved with it, 1.00 is not
  sent, the speed is disabled on a model that ignores it, and moving a voice to such a model drops
  its speed. A preview sends the row's model and speed.
- Agents: the default, weight, default model and effort each `PATCH` at once, and the tab issues no
  `DELETE`.
- The Rendering tab's default-mascot picker lists only pickable mascots and saves
  `default_mascot_id` alone. Mascots are disabled with the reason while the GPU is not working, and
  "No mascot" and a held value stay selectable. The same tab shows the Renderers panel.
- The Retention tab's backlog line is left out when `/retention/backlog` fails, and the field stays
  usable.

Trap: the Discord webhook URL is the credential, because anyone who holds it can post to the
channel. Its input stays a masked field on the Notifications tab, off the API keys tab.

Trap: the effort select stays usable for an agent with an empty `models` list. The effort levels
come from the CLI, so a broken model list must not remove the effort control.

### `renderers-panel.test.tsx`

Covers `components/RenderersPanel.tsx` ([Renderers](../15-dashboard.md#renderers)).

- One card per renderer, the built-in one first, with its status chip, GPU verdict and the device
  Chromium got.
- Each button sends its request, and an API refusal shows on that renderer's card.
- The panel polls every 3 seconds while a GPU test is outstanding and every 20 seconds otherwise.
- **Add renderer** shows the token and the host command once and forgets both on close.
- A response of the wrong shape is not drawn as a renderer list.

Trap: the host command in the dialog does not contain the token. The script asks for it, which keeps
the token out of the renderer machine's process list and shell history.

### `costs-panel.test.tsx`

Covers `components/CostsPanel.tsx`, the settings page's Costs tab. Each model names the source of
its rate or says it has none, the last successful sync and a failed sync are both shown, and only a
manual rate offers **Reset**.

Trap: a price is typed per million tokens and sent per token.

### `auto-pilot-panel.test.tsx`

Covers `components/AutoPilotPanel.tsx` and `lib/autoPilot.ts`
([Auto Pilot](../15-dashboard.md#auto-pilot)).

- The whole warning is always on screen.
- A save that widens what Auto Pilot acts on opens a confirmation that names how many videos are
  approved at once, and nothing is sent until it is confirmed.
- Only accounts that are allowed and connected are offered.
- The gap shows in hours and is sent in minutes. At the in-progress limit the tab says why nothing
  new starts.

Trap: a response that is not a configuration (a proxy error, another suite's fetch mock) must not
render as "off, no domains", because a **SAVE** on that view overwrites the real configuration.

Trap: an account chosen earlier that is not offered any more stays visible and ticked. Hidden, it
could not be removed, and every save would send it again.

Trap: the periodic refresh changes only the in-progress count, so an unsaved edit survives it.

### `socials-page.test.tsx`

Covers `app/socials/page.tsx` ([Publishing surfaces](../15-dashboard.md#publishing-surfaces)).

- Accounts are grouped by platform, and the count reflects only the enabled ones.
- An allowlisted account that is gone upstream is flagged and can still be unticked, which is the
  one way to clean a stale entry out.
- Connect runs one at a time and falls back to a link when the browser blocks the tab.

Trap: saving sends account ids only. Display data is read live on every load, and a stored username
would be a second copy that goes stale.

Trap: the Connect tab opens inside the click, because a popup blocker allows `window.open` only
then. The URL cannot be fetched ahead, because its `state` is single-use.

### `analytics-page.test.tsx`

Covers `app/analytics/page.tsx`, the **Videos** tab.

- The totals count published videos, and each publication has its own row.
- Platform and account filters go to the API, from the menus and from a clicked graph bar.
- An unreported metric renders a dash and sorts below a real 0. The watch columns do the same, a
  share above 100% is shown as reported, and the legend says what a dash means.
- The Watch time tab's panel mounts when its tab opens.
- When the account-name lookup fails, the page shows the id with the platform and still filters.
- The table renders 50 rows and adds 50 when its end comes into view of the table's own scroll box.
  A browser with no `IntersectionObserver` gets every row.

### `analytics-charts.test.tsx`

Covers `components/AnalyticsCharts.tsx`. Bars run highest first, scaled against the largest.
Clicking a bar sets the filter and clicking the selected bar clears it. A month where views fell
keeps its negative figure and draws no height.

Trap: an entry with nothing reported comes last as a dash with no bar. An empty bar would claim that
nobody watched.

### `watch-time-panel.test.tsx`

Covers `components/WatchTimePanel.tsx`, the Analytics page's **Watch time** tab.

- The first request names no account and the select shows the account the API answered for.
  Picking an account sends its id.
- Changing **Group by** redraws the table from the same response.
- The **Group by** list is the response's list of groupings, and a group whose `key` is the empty
  string ("Not recorded") gets a row like any other.
- A group under the response's `min_group` is tagged `TOO FEW` and still listed.
- A figure only some of a group's videos report shows how many, with `too few` under the
  threshold, and a figure none reports is a dash.
- An error answer, and an answer of another shape, show an error line.
- After a pick that fails, the table of the account shown before is gone, and it returns when that
  account is picked again.

Trap: a measure with `n` of 0 has a null median. Formatting it as a number would show 0, which says
that nobody watched.

### `spend-card.test.tsx`

Covers `components/SpendCard.tsx`, the Analytics page's **Spend** tab.

- Unpriced calls are called out beside the total. The ElevenLabs pool shows when the key can read
  it, labelled as the billing period, and recorded credits show otherwise.
- A backwards or half-empty custom range is flagged and not sent, and the previous range's figures
  are hidden.

Trap: a preset is sent by name, and the label shows the days the API returns. The card sends no
dates of the browser's own, because `TimeZoneProvider` is UTC until the host zone arrives
([Time](../15-dashboard.md#time)).

### `archive-page.test.tsx`

Covers `app/archive/page.tsx`. The page asks the API for archived videos only and lists them most
recently archived first. A deleted video keeps its publication links and its views summed across
platforms, which is how analytics outlive the files.

### `logs-page.test.tsx`

Covers `app/logs/page.tsx`. Records render in the order the API returned them, the service and
level options come from the response, the filters go on the query string and refresh is on demand
with no polling.

Trap: an API error shows as an error. Rendered as an empty list, it would read as "no logs".

## Components

### `action-pane.test.tsx`

Covers `components/ActionPane.tsx`, [Quick Actions](../15-dashboard.md#quick-actions), and the
pickers on its rows.

- Rows are grouped by status in pipeline order, and a pill hides its group. With every status
  filtered out the pane says no actions match and keeps the pills.
- [Voice](../15-dashboard.md#voice-picker): a voice in `voice_conflicts` is disabled with the
  reason, and a voice that left the roster is listed as itself, disabled.
- Script profile: a held profile that is not offered stays visible and can be cleared.
- [Agent, model and effort](../15-dashboard.md#agent-model-and-effort-pickers): a changed agent
  swaps in its own models, and all three are greyed while no agent can run the video. An untouched
  approval sends `""` for the effort.
- [Visual style](../15-dashboard.md#visual-style-picker): a video left on Auto shows the style the
  agent chose, marked automatic. A page that passes no key state leaves Illustrated enabled.
- [Mascot](../15-dashboard.md#mascot-picker): the picker is hidden when nothing can be picked.
  Mascots are disabled with the reason unless the GPU is working, and while the GPU status has not
  loaded. `mascot_id` travels with `approve-topic` only when the picker shows. Choosing Cartoon 3D
  or Under the Hood clears and locks the picker and sends an empty mascot.
- A refused approval (`onAction` resolving `false`) brings the row back so the pick can be changed.
- Every picker is found by its caption (`getByLabelText`), which proves the caption is the control's
  accessible name.

Trap: a picker's shown value is recomputed on every render. A value captured at mount shows one
voice and sends another when `/settings` answers late.

Trap: at `TOPIC_PROPOSED` an untouched approval sends no `voice_id`. Sending the shown voice pins
the install default over the voice the video got from its domain.

Trap: an untouched mascot picker re-sends a held, still-pickable mascot, even with the GPU not
usable. Stripping it would remove the mascot from a video nobody edited.

### `video-modal.test.tsx`

Covers `components/VideoModal.tsx`, [the video window](../15-dashboard.md#the-video-window).

- **Reject Topic** fires at once. **Request Revision** opens the dialog, posts the comment and then
  fires the revise action.
- The Script tab renders segmented and legacy flat scripts, and shows pronunciation and pause
  markup as the authored words.
- The Video tab plays `/stream/<project_id>/<id>.mp4` whatever `video_path` holds.
- The Actions block carries the same pickers as a Quick Actions row, under the same rules. The
  mascot cases cover its caption, the GPU gate, the `approve-topic` payload and the lock for Cartoon
  3D and Under the Hood.
- Once the pickers are gone, their values show read-only. The Voice and Voice model rows come from
  `voice_info` and are hidden while the voice picker is up.
- The Rendered by and Render time rows show the last render's renderer with GPU or CPU, fall back to
  the renderer id when no name was recorded, and are hidden on a video with no render recorded.
- A scheduled video says when it goes out, in the zone it was picked in. **Cancel schedule** calls
  the API after a confirm, and the window offers no Delete.
- The Publishing Results tab lists a published post's counts and watch figures, with "not reported"
  in words where the platform gave none. A post with no snapshot shows one line saying so, and a
  failed target shows no figures.

Trap: the component stays mounted between videos. A pick made for one video (agent, effort, voice)
must be forgotten when another opens, or the second video's approval writes it.

Trap: the picker label cases are scoped to the Actions block, because a read-only row elsewhere in
the window carries the same caption.

Trap: `publishingEnabled` defaults to off, so a page that does not fetch settings cannot publish.

### `video-modal-delete.test.tsx`

Covers the video window's Delete action: it is offered at the deletable statuses only, fires once
after a confirm and deletes nothing on cancel. An archived video shows the Archived badge.

### `video-modal-switch-style.test.tsx`

Covers the video window's **Why this style** row and **Switch to …** button
([Auto's style pick](../15-dashboard.md#autos-style-pick)).

- An Auto pick shows its reason and runner-up. A style a person chose shows neither.
- The switch is offered only at `SCRIPT_READY` with a runner-up, posts to `/switch-style` after a
  confirm, does nothing when the confirm is declined, and shows the server's refusal.

### `video-modal-script-record.test.tsx`

Covers `components/ScriptRecord.tsx` on the video window's Script tab and `lib/scriptFormulas.ts`
([The video window](../15-dashboard.md#the-video-window)).

- A script with a record shows its formula and opening type by their labels, the three openings
  with the one in use marked, and every warning.
- A script with no record shows the segments and nothing else, and makes no request for the names.
- The ids are shown when the names cannot be loaded, and for an id the list does not know.
- A segment shows its `beat` label only when it has one. The block holds no control.

### `video-modal-segment-voices.test.tsx`

Covers the Script tab's voice per segment
([Voice picker](../15-dashboard.md#voice-picker)).

- At `SCRIPT_READY`, with a second voice on the roster, each segment has a picker whose first option
  is the video's voice. A voice the API lists as unable to speak the segment is disabled with the
  reason as its title.
- A pick sends a `PATCH` holding only `segment_voices`, and a refusal shows its message.
- With one voice on the roster there is no picker. After `SCRIPT_READY` a segment's own voice is
  shown by name.

### `video-modal-retry-agent.test.tsx`

Covers **Retry agent**, `lib/videoStatus.ts::isAgentStuck` and the board card's STUCK tag. The
control is offered for a stuck video that is not archived, posts to `agent-retry` and refetches the
video.

Trap: a stuck video sits at an agent status, where the window otherwise shows no Actions block, so
the block's own condition must admit a stuck video.

### `video-modal-retry-publish.test.tsx`

Covers **Retry publishing** and `lib/videoStatus.ts::canRetryPublish`
([`POST /videos/<id>/publish/retry`](../14-publishing.md#post-videosidpublishretry)).

- The control is offered for a `FAILED` video that has publication rows. It is not offered for a
  failed render, an archived video or an install with publishing off.
- It refreshes in place when the server adopted a live post, and opens the Publish dialog when
  nothing was live.

### `video-modal-mark-published.test.tsx`

Covers **Mark as published**, `lib/videoStatus.ts::canMarkPublished` and the window's handling of
late responses ([A partial publish](../14-publishing.md#a-partial-publish)).

- The control is offered at `PARTIALLY_PUBLISHED` only, with publishing switched off too, because
  it is the only way out of that status.
- Confirming sends a `PATCH` guarded by `onlyIfCurrentStatus`.
- Only the newest response for the video on screen lands, and a failed refresh clears the rows.

Trap: confirming hands the video to retention, which dates from the first successful post, so a
partial publish older than `retention_days` loses its file on the next pass. The dialog carries a
download link, and Confirm stays disabled until the publication rows have loaded.

Trap: without the numbering of refreshes, a retry that finishes after the next video opened swaps
the window back to the old video.

### `publish-dialog.test.tsx`

Covers `components/PublishDialog.tsx`.

- The dialog offers only allowlisted, still-connected accounts and refuses to publish with no
  target or an empty title.
- It prefills the title and description the agent wrote, and opens on the video's own title when
  that call fails.
- Scheduling: the timezone defaults to the browser's, and nothing is sent until a date and a time
  are picked.

Trap: publishing cannot be undone. No account is ticked in advance, and on reopen the dialog drops
the previous video's selection, metadata and schedule.

Trap: the body carries the wall time and the zone, and the API converts
([Scheduling a post](../14-publishing.md#scheduling-a-post)). The dialog sends no UTC instant,
because the API owns daylight saving.

Needs: a zone named as the browser's CLDR list names it. The scheduling case uses `Asia/Calcutta`,
which the tz database calls `Asia/Kolkata`.

### `revise-dialog.test.tsx`

Covers `components/ReviseDialog.tsx`. The dialog sets an inline width narrower than the video
window beneath it and uses a shrinkable grid column, so a long title cannot widen it. **Send** stays
disabled until there is non-blank text.

### `cost-breakdown.test.tsx`

Covers `components/CostBreakdown.tsx`, the video window's cost card
([Components](../15-dashboard.md#components)). ElevenLabs shows as credits, unpriced calls are
counted and not shown as `$0`, and a video with no recorded usage says so.

Trap: a shared agent session shows this video's share beside the whole session, and the total adds
the share. Adding whole sessions counts one session once for every video in its batch.

Trap: the Agent row case asserts one element per model name and its `nowrap`, because happy-dom
cannot see a wrapped line. A joined string breaks after a hyphen in the narrow sidebar.

### `kanban-board.test.tsx`

Covers `components/KanbanBoard.tsx` column placement. `PARTIALLY_PUBLISHED` has no column of its
own and is folded into Published through `extraStatuses`. A status with neither does not appear on
the board.

### `kanban-card.test.tsx`

Covers `components/KanbanCard.tsx` and `lib/utils.ts::scoreLabel`.

- The display name is the short title and falls back to the topic.
- An unscored video (score 0, which only the New Video page creates) reads as a dash.
- Only a `SCHEDULED` card shows a post time, in the zone it was picked in.
- A `PARTIALLY_PUBLISHED` card is tagged PARTIAL, because it shares the Published column.

### `summary-strip.test.tsx`

Covers `components/SummaryStrip.tsx`. In Pipeline sums the eight in-flight statuses, `SCHEDULED`
included, and leaves out the checkpoint statuses. Published counts `PARTIALLY_PUBLISHED` too.

### `mining-sources.test.tsx`

Covers `components/MiningSources.tsx` and `canonicalYouTubeUrl`, the panel's copy of the API's URL
rule ([Mining sources](../05-http-api.md#mining-sources)). The accepted forms come back as
`https://www.youtube.com/watch?v=<id>`, and **Add** does not add a second spelling of a listed
video.

Trap: the rule is copied so that the button lights only for what the API will store. The API still
validates.

### `voice-preview-button.test.tsx`

Covers `components/VoicePreviewButton.tsx`.

- A second click replays the cached sample without a fetch. One button shows play or pause and
  follows the audio's own events.
- A change of voice, model or speed fetches a new sample, and a slow response for a model that is
  not selected any more is dropped.
- A model is sent in a JSON body with its `Content-Type`, because the proxy refuses a body without
  one.

### `timezone-provider.test.tsx`

Covers `components/TimeZoneProvider.tsx` ([Time](../15-dashboard.md#time)). A valid IANA zone and
label are accepted. A missing field, a human label in the zone slot, a non-ok response and a
rejected fetch each degrade to UTC.

### `topbar-version.test.tsx`

Covers the top bar's [version badge](../15-dashboard.md#version). It shows the version the API
reports and renders nothing when the version is unavailable. It is polled, so it picks up a new
version after an upgrade and drops the version while the API is down.

Trap: a wrong version in a bug report is worse than none, so the badge has no fallback text.

Needs: the disk-usage figure fetches first, so the sequenced mocks answer `/storage` separately
(`besideDiskUsage`).

### `disk-usage.test.tsx`

Covers `components/DiskUsage.tsx` ([Disk usage](../15-dashboard.md#disk-usage)).

- The popup says "not measured yet" without a host snapshot and "unknown" for a figure Docker
  could not give.
- With two or more old images, the old-image line and both totals carry "≥".
- The component renders nothing on a `404`, another body shape or a network error, because a wrong
  figure misleads more than none.

### `update-banner.test.tsx`

Covers `components/UpdateBanner.tsx` ([Update check](../15-dashboard.md#update-check)).

- The banner names both versions and links the release and the upgrade guide with `noopener`. It
  renders nothing for no update, a failed request or a link that is not `https://`, and does not
  check on `/login`.
- ✕ hides that version for later page loads, and a newer version brings the banner back. When
  storage throws, the dismissal lasts for the page.

## Routes and helpers

### `proxy-route.test.ts`

Covers [`app/api/proxy/[...path]/route.ts`](../15-dashboard.md#dashboardappapiproxypathroutets),
the route every dashboard API call goes through.

- Without a valid session the answer is `401` and Flask is not called. Every upstream call carries
  the API token.
- Responses are not cached.
- A `POST` or `DELETE` whose `Sec-Fetch-Site` is not `same-origin` is a `403`, and a body that is
  not JSON is a `415`. A missing header, any `GET` and a bodiless `POST` pass.

Trap: a `401` from Flask becomes a `502` that names the fix. Relayed as a `401`, it sends the
browser to `/login` in a loop.

Trap: the query string must reach Flask. A dropped `?status=PUBLISHED` returns every video, which
looks like a fault in the page.

Trap: an empty form `POST` is a `415`, because a form always sends a `Content-Type`. The guard
exists because `SameSite=Strict` does not stop a page on another port or a sibling subdomain
([Cross-site request forgery](../15-dashboard.md#cross-site-request-forgery)).

### `stream-route.test.ts`

Covers [`app/stream/[...path]/route.ts`](../15-dashboard.md#dashboardappstreampathroutets), on a
real temporary directory tree with only the session mocked.

- Access: no session is a `401` before the filesystem is touched. A `..` escape, a symlink that
  leads outside the root, a directory, a FIFO and any extension other than `.mp4` and `.mp3` are
  each a `404`.
- A directory swapped for a symlink between `realpath` and `open` is a `404`, by the descriptor's
  `/proc/self/fd` path on Linux and by device and inode with `process.platform` set to `darwin`.
- The file handle is closed on an abort, a cancelled body and a `304`.
- The body is a stream. Single ranges, invalid ranges, `If-None-Match` and `If-Range` follow the
  route's rules.

Trap: the filesystem is real because the defects are filesystem behaviour (a symlink followed by
`open`, a FIFO that blocks it), which a mocked `fs` cannot show.

Trap: `O_NOFOLLOW` guards only the last path component, so the descriptor check is what refuses a
swapped directory. The swap runs inside a wrapped `open()` so that the race is deterministic.

Trap: an `ETag` built from size and mtime alone survives a same-size re-render with its mtime
restored, and the browser replays the old video.

Needs: `mkfifo` on the path, and a filesystem with symlinks.

### `mascot-sheets-route.test.ts`

Covers [`app/mascot-sheets/[...path]/route.ts`](../15-dashboard.md#dashboardappmascot-sheetspathroutets),
the authenticated image relay.

- No session is a `401`, and Flask is not asked.
- Only `<id>/versions/<n>/sheets/<turn|feels|act>` is served, and any other path is a `404` before
  Flask is asked. Ids follow the Python `MASCOT_ID_RE`, underscores included.
- Only `image/png` and `image/jpeg` are relayed. A `401` from Flask is a `502`, so the browser is
  not sent to `/login`.

### `auth-routes.test.ts`

Covers the login and logout routes ([Signing in](../15-dashboard.md#signing-in)), on the real
`next/server`.

- The password goes to Flask with the API token, and only a `200` sets the cookie. The backoff
  passes through as `429` with its `Retry-After`.
- Both routes refuse a request that is not `same-origin` with `403` and a non-JSON body with `415`.

Trap: Flask refusing the dashboard's token (`unauthorized`) is a `502`. Shown as a wrong password,
it would hide a broken install behind a login error.

### `middleware.test.ts`

Covers `middleware.ts`. A page load with no session cookie is redirected to `/login` with its path
and query in `next`, and a request with the cookie passes.

Trap: the middleware checks only that the cookie is present, and the proxy, stream and mascot-sheet
routes verify the signature. The matcher leaves out the API routes, `/stream`, `/mascot-sheets`,
Next's assets and `/login`, so that a `fetch()`, a `<video>` or an `<img>` gets a `401` from its
route and never the login page's HTML.

### `session.test.ts`

Covers `lib/session.ts` and `lib/sessionCookie.ts`.

- A forged, expired or `alg: none` token does not verify, and a missing `session_secret` fails
  closed.
- Rotating `session_secret` signs every browser out, which is how `--set-password` does it. Both
  secrets are read on every call, so a rotation needs no restart.
- `safeNext` keeps the post-login redirect same-site.

Trap: the cookie is `Secure` only when the browser came over HTTPS. Always `Secure`, it would make
sign-in over plain HTTP on a LAN impossible.

### `update-check-route.test.ts`

Covers `app/api/update-check/route.ts` ([Update check](../15-dashboard.md#update-check)).

- Without a session the answer is `401`, and neither the API nor GitHub is called.
- `develop`, an API that sends no `github_repo` and a malformed repository never reach GitHub. An
  unreachable API or GitHub answers "no update".

Trap: the installed version is read on every request while GitHub's list stays cached, so the banner
clears as soon as an upgrade lands.

### `update-check-lib.test.ts`

Covers `lib/updateCheck.ts`, the update check's decision layer.

- Only a newer stable release is offered. Versions compare by SemVer precedence, so an install on
  `2.1.0-rc.1` is offered `2.1.0`, and `develop` is offered nothing.
- `isRepo` accepts only a bare `owner/name`, because the value goes into a URL.
- GitHub's list is asked at most once in 2 hours, and a failure keeps the last good list and is
  retried after 15 minutes. The request carries a `User-Agent`, which GitHub requires.

Trap: the newest release is chosen by version. GitHub lists by creation date, so a later patch to an
older line comes first in the list.

Trap: a prerelease is recognised by its tag as well as by GitHub's flag, because a release can be
published without the flag.

### `agents-lib.test.ts`

Covers `lib/agents.ts`, the rules `ActionPane` and `VideoModal` share
([Agent, model and effort pickers](../15-dashboard.md#agent-model-and-effort-pickers)).

- `agentOptions` offers only live agents and shows a video's own uninstalled agent disabled.
- A changed agent carries its own default model and never a model from the previous agent's list.

Trap: only `topicApprovalPayload` pins a model. On every other action `agentPicksPayload` sends
only what was touched, whether or not the agent list loaded, so a slow `GET /agents` cannot move a
video to another agent.

### `voices-lib.test.ts`

Covers `lib/voices.ts` ([Voice picker](../15-dashboard.md#voice-picker)). `topicVoicePayload`
carries a voice only when one was picked. `shownVoice` is the pick, else the video's own voice, else
the install default. `voiceMissing` detects a voice with no roster entry, so the picker can list it.
`voiceLabel` names a speed only when it is not 1.00, and `segmentVoiceConflict` reads the API's
per-segment conflicts.

### `visual-styles.test.ts`

Covers `lib/visualStyles.ts` ([Visual-style picker](../15-dashboard.md#visual-style-picker)).

- The options are the fetched style list in pack order, `auto` first. A style whose pack needs an
  OpenAI key or a GPU is disabled with the reason, and an experimental one is labelled.
- `illustratedAvailable` reads the masked `openai_api_key`, where `""` means unset, so the key
  never reaches the browser.
- `cartoon3dAvailable` is true only while the GPU probe says working, and `styleOptions` tells an
  untested GPU apart from a missing one.
- Before the list loads, a picker offers only the value it holds, and a label shows the raw id.
- `videoStyleLabel` names the world an Auto video settled on, and marks a style Auto picked before
  the script with the style's label, or Mixed scenes with its canvas, after the word Auto.

`packStyles.ts` builds the style list from the real pack files in `tubematic_core/style_packs/`, and
`vitest.setup.ts` makes `useVisualStyles()` return it in every test, so no test holds its own copy
of the list.

Trap: settings and GPU status that have not loaded count as available, so the API gives the refusal
and a page that loads neither does not grey an option out wrongly.

### `visual-styles-provider.test.tsx`

Covers `components/VisualStylesProvider.tsx`: it fetches `GET /visual-styles` once and shares the
list, and stays `null` when the API fails, so pickers fall back to the value they hold.

### `mascots-lib.test.ts`

Covers `lib/mascots.ts` ([Mascot picker](../15-dashboard.md#mascot-picker)).

- `mascotGate` is open only while the GPU is working.
- `mascotOptions` keeps a held mascot that is still pickable selectable. One that is not pickable
  shows as unavailable and is never read as None.
- `approvalMascot` sends no mascot for Cartoon 3D, or for a style the served list marks `mascot:
  false`; with the list not loaded it leaves the pick to the API.

Trap: the gate fails closed while the GPU status has not loaded, the opposite of the visual-style
rule. An untouched picker could otherwise send a mascot the API refuses.

### `renderers-lib.test.ts`

Covers `lib/renderers.ts`, the rules behind the Renderers panel and the board's banner
([Renderers](../15-dashboard.md#renderers)).

- `rendererStatus` lets the first thing that stops a renderer taking work win: disabled, then
  credential expired, then needs upgrade, then offline.
- The GPU verdict is read from the renderer's probe only.
- `nothingCanRender` is raised when a video is queued and no renderer is enabled, online, on this
  version and holding an unexpired credential. A busy renderer still counts.
- `formatRenderDuration` reads seconds, minutes and hours, and gives a dash for a time that was not
  reported.

Trap: `nothingCanRender` judges credential expiry by the same rule and the same `now` as the status
chip, so a card that says credential expired cannot keep the banner down.

### `video-status.test.ts`

Covers `lib/videoStatus.ts`: `canDelete`, `deleteVideo` and `patchVideo`. An archived video is
refused at any status, and `patchVideo` names a lost status race as a conflict and passes any other
refusal on in the API's words.

Trap: `DELETABLE_STATUSES` is asserted equal to the full allowed set, with no status missing or
extra, because the set is copied from the API
([Copied constants](../15-dashboard.md#copied-constants)).

### `video-modal-utils.test.ts`

Covers the two `/stream` URL builders in `lib/utils.ts`. `videoStreamUrl` builds a render's URL
from the video's own domain id and video id, each encoded as one path segment, under `default_proj`
when there is no domain (where the render gateway stores the file). `videoToStreamUrl` rewrites the
`/output_videos/…` path a voice preview comes back with.

Trap: `videoStreamUrl` never reads `video_path`. A row that names another video's file must not play
that file.

### `datetime.test.ts`

Covers `lib/datetime.ts` ([Time](../15-dashboard.md#time)).

- `formatDate`, `formatDateShort`, `formatDateTime` and `formatClock` use the zone they are given
  and return a dash for unparseable input.
- A timestamp stored with no zone designator is read as UTC.
- The scheduling helpers `formatScheduled`, `wallClock` and `addDays`.

Trap: the suite runs with `TZ=UTC` and asserts a non-UTC zone in the same file, which proves the
explicit `timeZone` argument does the work and no host default does.

### `palette-contrast.test.ts`

Covers the secondary text tokens in `app/globals.css`. The test parses the stylesheet and computes
WCAG contrast ratios.

- `--dim` and `--mute` each clear AA (4.5:1) on `--bg`, `--panel` and `--panel-2`.
- The order `ink > ink-2 > dim > mute` holds, so secondary text cannot be brightened until it
  competes with primary text.
- Every `--muted-foreground` declaration is `var(--dim)`, so the shadcn token cannot drift from the
  palette.

Trap: the secondary tokens are used at 10 and 11px, where contrast matters most.
