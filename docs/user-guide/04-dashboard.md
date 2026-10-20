# The Dashboard

The dashboard is the human half of Tubematic. Every decision the AI agent is not allowed to make
alone — approving a topic, approving a script before it costs money, signing off a finished video —
happens here. It is also where you create videos, steer research, configure the install, watch cost
accumulate, and read the AI reviewer's findings. **It is the recommended way to run Tubematic**: you
never need to open an agent session yourself, because the scheduled pipeline starts the agent for
you. Agent slash commands exist as an optional alternative — see
[Using Tubematic — Agent commands](03-using-tubematic.md#agent-commands).

It runs on **port 3000**: open <http://localhost:3000> on the machine Tubematic is installed on. How
to start it, and how it fits into a day's work, is in [Using Tubematic](03-using-tubematic.md). How
it is built — the request guard, the proxy and stream routes, the components — is in
[Dashboard internals](../developer/15-dashboard.md).

---

## Signing in

The dashboard has one password. Onboarding asks for it the first time; after that it is set or
changed on the host with `python onboard.py --set-password`. There is no sign-up, no second user and
no password reset in the dashboard itself.

- **A sign-in lasts seven days, fixed.** Using the dashboard does not extend it; after seven days
  you sign in again.
- **Sign out** is at the right of the top bar.
- **Changing the password signs every browser out**, including yours.
- **Wrong passwords back off.** After five failed attempts the login page asks you to wait, longer
  each time, up to 15 minutes. Restarting the API container clears the wait.
- **A session that ends while a page is open is noticed within 30 seconds**, and the browser is sent
  to the login page; after signing in you return to the page you were on.

The dashboard listens on the local machine only. To use it from another machine, put HTTPS in front
of it — over plain HTTP the password and the session cookie cross the network readable. See
[Infrastructure — Using the dashboard from another machine](../developer/16-infrastructure.md#using-the-dashboard-from-another-machine).

---

## The top bar

Every page shares one bar. From left to right it holds the page tabs, then:

- **The version badge** — the installed version, for example `v1.2.3`. It is the quickest way to
  check which version an install is on, to make a bug report unambiguous, and to confirm an upgrade
  landed ([Upgrading](07-upgrading.md)). It is re-read every 30 seconds, so a page left open across
  an upgrade changes by itself. It **disappears while the API is down** rather than showing a stale
  or guessed number, and comes back once the API answers. A source checkout of a release tag shows
  that release; a checkout of the development branch shows `vdevelop`.
- **The timezone** the dashboard is showing times in (see [Times](#times)).
- **`SYS ● NOMINAL`**, the health indicator. It turns red with `ERROR` when the API stops answering;
  hover over it for the reason.
- **Sign out.**

On a window narrower than about 1640 pixels the tabs move to a second row instead of squeezing.

### The update banner

When a newer **stable** release of Tubematic is out, a strip under the top bar says so on every
page: *Tubematic vX.Y.Z is available. This install is on vA.B.C.* It links to that release's notes
on GitHub and to [Upgrading](07-upgrading.md). The dashboard does not upgrade anything itself.

- **✕ hides it for that version**, in that browser. It comes back when a still newer release is
  published, or in another browser.
- **Only stable releases count.** A prerelease such as `v2.1.0-rc.1` or `v2.1.0-beta` never shows
  the banner. An install that is itself on a prerelease is offered the stable release that follows
  it.
- **It goes away by itself** once the install is upgraded, within about ten minutes on a page left
  open.
- **A checkout of the development branch never shows it**, because `develop` is not a release and
  has nothing to compare against.

To do this, the dashboard asks GitHub for the project's releases at most once every two hours, while
a dashboard page is open. It sends no data about your install: the request is the same public,
unauthenticated one anyone can make. If GitHub cannot be reached (an offline install, a firewall),
no banner shows and nothing else is affected. There is no setting to switch it off.

---

## Pages

| Page | What it is for |
|---|---|
| **Pipeline** (`/`) | The board: every video that is not archived, by status, plus the Quick Actions inbox of everything waiting for you. See [The pipeline board](#the-pipeline-board) |
| **New Video** | Create a video from a topic you give it — the way to ask for a specific video. See [New Video](#new-video) |
| **Library** | Finished work — videos at Video Ready, Video Approved, Scheduled, Publishing and Published. A status filter, a strategy filter, a sort (newest, oldest, highest or lowest score) and a search over title and topic. A scheduled video's card says when it goes out |
| **Archive** | Videos whose files were deleted, by you or by the [retention setting](05-settings.md#video-retention). Each keeps its title, project, status, archive date, total views and post links; opening one shows its window read-only |
| **Topics** | Where topics come from: which research modes are on, the mining URL list, and every project domain with its settings. See [Topics](#topics) |
| **Projects** | Pick a domain on the left, see and act on its videos on the right. A domain at its topic cap carries an "expired" badge |
| **Script Profiles** | Teach the pipeline a writing style from YouTube videos. See [Script Profiles](#script-profiles) |
| **Socials** | Connect publishing accounts and choose which ones Tubematic may post to. Does nothing until publishing is enabled |
| **Analytics** | Two tabs. **Videos**: views, likes, comments and shares of published videos. **Spend**: what the install has spent. See [Analytics](#analytics) |
| **Logs** | Structured logs from every service, filtered by service, minimum level, text and number of rows. Logs refresh when a filter changes or you press the refresh button; there is no live tail |
| **Settings** | Every install setting, in tabs, plus the pipeline pause switch. See [The settings page](#the-settings-page) |

The Pipeline, Library, Projects and Script Profiles pages refresh themselves every 5 seconds, so you
can leave one open.

### The pipeline board

The top of the page holds six counters: topics awaiting you, scripts ready, videos ready, videos in
the pipeline, published and failed.

**Quick Actions** lists only the videos waiting for a decision, grouped by checkpoint in pipeline
order — Topic Proposed, Script Ready, Video Ready — oldest first in each group. The pills above the
list, one per checkpoint with its count, hide or show a group. The filter resets when the page
reloads, on purpose: a filter forgotten in one browser can never leave videos waiting on you unseen.
Each row carries the controls its decision needs (see [Making decisions](#making-decisions)); a row
flashes green or red and disappears once you act on it.

Below it, the **board** has a column per status in pipeline order — Topic Proposed, Topic Approved,
Script Ready, Voicing, Voice Ready, Rendering, Video Ready, Video Approved, Scheduled, Publishing,
Published — and three side columns: Rejected, Revision Requested and Failed. A video waiting for the
renderer is shown under Rendering, since from your side waiting and rendering are the same thing.
What each status means is in [The Pipeline](../developer/02-pipeline.md#the-states).

A card shows:

- a score dot — the topic's producibility score, or "—" for a video submitted on the New Video page,
  which is not scored
- the title, the research mode that found it, and how long ago it last changed
- a progress bar while something is working on it
- for a scheduled post, when it goes out, in the timezone it was scheduled in
- **STUCK** when the scheduled agent has stopped retrying it: three sessions in a row left it where
  they found it. Open it to read why, then press **Retry agent** or change its status
- the choices made for it (script profile, visual style, agent, model, effort) wherever they can no
  longer be changed, so they never vanish. A choice left on **Auto** shows what the agent actually
  picked, marked as automatic

While [Auto Pilot](06-publishing.md#auto-pilot) is switched on, a one-line notice sits above Quick Actions.

### The video window

Clicking a card or row opens the video's window. Its tabs are **Topic**, **Script**, **Video**,
**Publishing Results**, **Comments** and **Logs**. Script, Video and Publishing Results appear once
there is something to show; Logs is always there, because a video's log matters most when nothing
else about it worked. The Video tab plays the render; in most browsers the player's own menu can save it, and
the file is also on the host under `~/.tubematic-data/output_videos/<project>/<video id>.mp4`.

**Comments is a read-only thread** of what you and the agent have said. You add a comment only
through **Request Revision**, so every note you leave comes with the status change that makes the
agent read it.

The side panel holds the actions available at the video's status, a **Published to** section
linking to each live post, the video's details, its cost and the AI review's findings.

- **Cost** is split by provider and model. ElevenLabs is shown in plan credits, never dollars. An
  agent session from before one-session-per-video could cover several videos; the window shows this
  video's even share beside the whole session. A call with no known price is counted beside the
  total rather than shown as `$0`. Every dollar figure is the provider's API list price, not what a subscription bills.
- **Voice** and **Voice model** appear wherever there is no voice picker to show them. The model is
  the one ElevenLabs was actually called with; before voicing it is the voice's current setting,
  marked "(current setting)". A voice no longer on the roster shows by its id, marked
  "(not in roster)".

### New Video

Creates a video from a topic you give it. It asks for:

- a **title**, required, at most 70 characters, with a live counter. A longer title is refused, not
  cut
- the **topic** — the full brief the script is written from
- optionally the agent, model, effort, script profile, visual style and voice, the same choices a
  topic offers at its checkpoint

**Automatically approve topic** is ticked by default, which sends the video straight to scripting.
Untick it to review the topic on the Pipeline page first.

The agent picker starts on **Automatic (dealt by weight)**, which leaves the choice to the install's
agent shares, exactly as for any other new video; the model picker stays disabled until you pick an
agent. The voice picker's **Default** names the voice the video will actually get.

Every submission lands in a domain called **Manual Videos** and is not scored. Why is explained in
[Where topics come from](../developer/02-pipeline.md#where-topics-come-from). A refused submission
shows the reason and keeps what you typed; a successful one clears the title and topic but keeps the
pickers, since videos submitted in a row usually share them.

### Topics

- **Research modes** — curriculum, trending and mining, each switched on or off. Mining needs a Gemini
  API key: without one its toggle is greyed out (hover it for why), and it comes back on its own
  once a key is added under Settings → API Keys.
- **Mining sources** — the YouTube videos mining reads. Only a YouTube video URL is accepted, at most
  50 of them, and each is stored as `https://www.youtube.com/watch?v=<id>`, so a second spelling of
  the same video is a duplicate. The **Add** button lights only for a URL that will be accepted.
- **Domains** — every project domain. When you add one, its description is the scope research
  works from: write it in as many paragraphs as it needs, up to 2000 characters (the counter under
  the box shows how many you have used), and drag the box's corner to make it taller. The list
  shows the start of it on one line. A curriculum seed has a **Pause topic generation** button;
  what a pause does is in [Using Tubematic](03-using-tubematic.md#domain-pause-curriculum-seeds-only).
  Every row has:
  - a **default visual style** and **default script profile**, which preselect those choices on the
    domain's curriculum videos
  - a **default voice**, which every new video in the domain starts with
  - a **Topic cap** (25–750) with "N filed" beside it — every topic the domain has ever had,
    archived and rejected ones included. A domain at its cap shows **EXPIRED** and receives no more
    researched topics until you raise it. See [Using Tubematic](03-using-tubematic.md#topic-cap-per-domain)

  A default voice that has left the roster shows as "(removed)", and a default profile that has
  been deleted as "Unavailable profile". **Illustrated** is greyed out until an OpenAI key is
  stored.

### Script Profiles

A script profile teaches the pipeline to write in a particular creator's style. Give it a name and
up to 10 YouTube URLs, one per line. The transcripts are fetched straight away — this needs the
youtube-transcript.io key — and the style is written by the next agent session, even while the
pipeline is paused. A profile moves through **Pending**, **Generating** and **Ready**; a profile
that fails twice shows **Failed** and has to be deleted and created again, since profiles cannot be
edited. A ready profile can be picked for any topic awaiting approval. What a profile captures, and
what it deliberately leaves out, is in
[Scripting and Voice — Script profiles](../developer/08-scripting-and-voice.md#script-profiles).

### Analytics

**Videos** lists every published post with its views, likes, comments and shares, filterable by
platform and account and sortable by any figure. Graphs beside the table show views per platform,
per account and gained per month; click a bar to filter by it, and again to clear it. A post nothing
has been reported for reads "—" rather than 0. **Refresh metrics** reads the latest figures at once
instead of waiting for the hourly read — see [Publishing — Analytics](06-publishing.md#analytics).
Socials and Analytics stay empty until [publishing](06-publishing.md) is enabled.

**Spend** shows spend over today, this week (from Monday), this month (the default) or any range of
days, in the host's timezone. It is the one place spend that belongs to no single video shows up:
topic research and mining, script-profile builds and voice previews. With an ElevenLabs key that has
the optional `user_read` permission it also shows the plan's credit pool, which follows ElevenLabs'
own billing period rather than the chosen range.

---

## Making decisions

Each checkpoint offers its actions on the Quick Actions row and in the video's window. Which
checkpoint is which, and why each exists, is in
[The Pipeline — Human checkpoints](../developer/02-pipeline.md#human-checkpoints).

| Where | Action | What happens |
|---|---|---|
| Topic Proposed | **Approve** | The agent writes the script next. The choices on the row go with the approval |
| Topic Proposed | **Reject** | The topic leaves the pipeline. A comment is optional |
| Script Ready | **Approve** | Voicing starts — **this is where ElevenLabs spending begins** |
| Video Ready | **Approve** | The video moves to Video Approved. Nothing is posted anywhere by this |
| Any checkpoint | **Revise** | Opens the Request Revision dialog. A comment is required: say what to change, and the agent reworks it |
| Video Approved | **Publish** | Opens the publish dialog — accounts, title and caption, privacy, now or scheduled. Only with publishing enabled. See [Publishing a video](06-publishing.md#publishing-a-video) |
| Scheduled | **Cancel schedule** | Takes the post back and returns the video to Video Approved. Refused if the post is already going out. See [Scheduling a post](06-publishing.md#scheduling-a-post) |
| Failed, after a publish | **Retry publishing** | Tubematic first asks whether a post went live anyway. If one did, nothing is posted again and the video settles as published. If none did, the video goes back to Video Approved and the publish dialog opens. See [When publishing goes wrong](06-publishing.md#when-publishing-goes-wrong) |
| Flagged STUCK | **Retry agent** | Clears the flag so the scheduled agent tries again |
| Most statuses | **Delete** | Asks first, then deletes the video's files and moves it to the Archive. Not offered while something is working on the video, nor while it is scheduled, publishing, at Voice Ready or at Revision Requested |

**The choices that ride with an approval.** A Topic Proposed row carries a script-profile picker, a
visual-style picker, a voice picker with a preview button, and agent, model and effort pickers.
Script Ready carries the voice, agent, model and effort pickers. In the video's window the same
pickers are stacked, and at Video Ready they serve Request Revision, since approving a video hands
nothing to an agent. Each picker has a small caption naming it.

- **Script profile and visual style are fixed once the topic is approved.** Pick them at the topic.
  **Illustrated** needs an OpenAI key and is greyed out without one.
- **Pick the voice at the topic if it uses a different ElevenLabs model.** The script is written for
  its voice's model, so each voice is labelled with its model. At Topic Proposed every voice is
  offered; leave the picker alone and the video keeps the voice it already has — its domain's default
  voice, or the install default. At Script Ready a voice whose model cannot speak the written
  script is greyed out with the reason. To switch to it, request a revision naming the voice, and
  the agent rewrites the script for it. Why the model matters is in
  [Scripting and Voice — The model follows the voice](../developer/08-scripting-and-voice.md#the-model-follows-the-voice).
- **Agent, model and effort can change at every checkpoint.** Picking a different agent resets the
  model to that agent's default and says so. The model list is exactly what the install checked
  against that agent's CLI. Effort's blank option means "this agent's own level" and names it, for
  example `high (agent default)`. On a Quick Actions row whose agent cannot run — not installed,
  uninstalled, or the agent list has not loaded — model and effort are greyed out, with the reason
  on hover; the agent picker stays live, because switching to an installed agent is the way out.

**"Status conflict — action already taken"** means the video moved since the page last refreshed —
someone or something else acted first. Nothing is wrong; refresh. Any other refusal is shown in the
API's own words.

Revising first saves your comment and then changes the status. If the status change is refused, the
comment is still saved.

---

## The settings page

**The pause switch sits above the tabs and applies the moment you click it.** It stops new agent
work; see [Using Tubematic](03-using-tubematic.md#pausing-the-pipeline).

The tabs are **AI Review**, **Research**, **Voice**, **Images**, **Rendering**, **Logs**,
**Retention**, **API Keys**, **Publishing**, **Notifications**, **Scheduling**, **Agents**,
**Preferences**, **Costs** and **Auto Pilot**. What every setting does, with its default, is in
[Settings](05-settings.md).

Most tabs save the same way. Edits stay on the page until you press that tab's **Save**, which saves
only that tab. A tab with unsaved edits shows an amber dot, and leaving it asks first. A few tabs
work differently, noted below.

- **AI Review** — off by default and labelled **Experimental**. It needs a Gemini key, and if the
  review itself fails, the video still reaches your review as if it had passed — so check a video's
  comments to see whether a review ran.
- **Images** — the OpenAI model for scene images and the one for the Illustrated style's characters.
  There is no provider choice: every image comes from OpenAI.
- **Voice** — up to five named voices and the default one. Each voice has its own ElevenLabs model
  and a ▶ button that plays a sample of it with that model; there is no install-wide model.
- **Scheduling** — how many agent sessions run at once and the session timeout, plus read-only
  research figures: runs used in the last 24 hours, when the next one frees, and the last research
  run.
- **API Keys** — each key shows as a mask, never the key itself. Type over it to replace the key,
  or clear the field to remove it. A new key applies to the next call with no restart.
- **Notifications** — the Discord webhook URL lives here rather than under API Keys, beside the
  triggers it serves. Saving a URL checks the webhook exists, without posting anything.
- **Preferences** — one large box for your standing instructions to the agent, with a live count
  against the 6000-character limit.
- **Agents** — outside the tab's Save. Choosing the default agent or an agent's default model saves
  at once, and each agent's share of new videos has its own Save button. Every installed agent is listed with its
  workspace and models; an uninstalled one stays listed, read-only. **Models cannot be added or
  removed here**: the dashboard has no agent CLI to check a model against, so that is
  `python onboard.py --install-agent <agent>` on the host. Uninstalling is
  `python onboard.py --uninstall-agent <agent>`.
- **Costs** — saves immediately. Lists the price of every model Tubematic prices itself (Gemini,
  OpenAI and Codex; Claude Code and OpenCode report their own cost, and ElevenLabs is credits), where
  each price came from, and the last price sync. **Sync now** refreshes prices, **Override** sets a
  price no sync will change, **Reset** drops it, and **Add price** on a model with unpriced calls
  prices those calls retroactively. See [Settings — Costs](05-settings.md#costs).
- **Auto Pilot** — saves as a whole with its own **Save**. It holds the on/off switch, the gap
  between publishes, a box per project with that project's accounts under it, a posts-per-day number
  per account, and the most videos in progress at once. **The warning above the switch is always on
  screen, read it.** A save that widens what Auto Pilot acts on — turning it on, or adding a project
  while it is on — asks for confirmation first and says how many videos are waiting in the newly
  covered projects, because they are approved the moment it saves. Only accounts enabled on Socials
  and connected are offered; with publishing off there are none, and selected projects are approved
  and then wait at Video Approved. What Auto Pilot does is in [Publishing — Auto Pilot](06-publishing.md#auto-pilot).

---

## Times

Every time on the dashboard is in the **timezone of the machine Tubematic runs on**, not your
browser's — the top bar names it. Someone viewing from another timezone sees the same times as the
host's logs. If the dashboard cannot learn the host's timezone it falls back to UTC.

The one exception is scheduling a post, where you choose the timezone (yours by default) and the
card then shows the time in the zone you picked.
