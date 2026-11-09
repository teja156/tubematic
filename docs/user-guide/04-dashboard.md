# The Dashboard

The dashboard is where you run Tubematic: you create videos, approve them, publish them and change
settings. Open `http://localhost:3000` on the machine Tubematic is installed on. To open it from
another machine, see [Remote Access](09-remote-access.md).

[Using Tubematic](03-using-tubematic.md) describes the daily routine. This page describes each
screen.

---

## Signing in

The dashboard has one password, which you set during the install. It has no user accounts.

- A sign-in lasts seven days. Using the dashboard does not extend it.
- After five wrong passwords the login page makes you wait, longer each time, up to 15 minutes.
- To change the password, or if you forgot it, run `python3 onboard.py --set-password` on the
  machine. This signs every browser out.

## The top bar

The bar at the top of every page holds the page tabs. To their right it shows:

| Item | Meaning |
|---|---|
| A version, such as `v2.0.0` | The version that is running. It disappears while the dashboard cannot reach the API |
| A timezone | The timezone every time on the dashboard is shown in. See [Times](#times) |
| `SYS ● NOMINAL` | Tubematic is reachable. It turns red and reads `ERROR` when the API stops answering. Hover over it for the reason |
| **Sign out** | Ends your session |

### The update banner

When a newer release of Tubematic is published, a strip under the top bar says so and links to its
release notes and to [Upgrading](07-upgrading.md). Press **✕** to hide it until the next release.

To learn about releases, the dashboard asks GitHub for the project's public release list, at most
once every two hours while a page is open. It sends nothing about your install. The dashboard does
not upgrade anything by itself.

---

## Pages

| Tab | What it is for |
|---|---|
| **Pipeline** | Every video by status, and the list of videos waiting for you |
| **New Video** | Create a video from a topic you type |
| **Library** | Videos from Video Ready onwards, with filters, sorting and search |
| **Archive** | Videos whose files were deleted. Their records, links and view counts remain |
| **Topics** | Research modes, mining sources and your domains |
| **Projects** | One domain at a time, with its videos |
| **Profiles** | Script profiles and mascots |
| **Socials** | The social accounts Tubematic may post to |
| **Analytics** | Views and likes of published videos, and what the install has spent |
| **Logs** | Log records from every part of Tubematic |
| **Settings** | Every setting, and the switch that pauses the pipeline |

Pipeline, Library, Projects and Profiles refresh every 5 seconds, so you can leave one open.

### Pipeline

The page has three parts.

**Overview** shows six counts: topics awaiting you, scripts ready, videos ready, videos in the
pipeline, published and failed.

**Quick Actions** lists the videos that need a decision, grouped as Topic Proposed, Script Ready and
Video Ready, oldest first. Each row has the buttons and pickers for its decision. See
[Making decisions](#making-decisions). The three pills above the list hide or show a group.

The board below has a column for each status, in the order a video moves through them, followed by
Rejected, Revision Requested and Failed. Click a card to open the video. A card shows:

- the topic's score out of 10, or a dash for a video you created yourself,
- the title,
- how the topic was found: curriculum, trending, mining or manual,
- how long ago the video was created,
- **STUCK**, when the agent has stopped retrying it
  (see [When a video is STUCK](03-using-tubematic.md#when-a-video-is-stuck)),
- for a scheduled post, when it goes out.

Two notices can appear on this page:

- An amber line above Quick Actions while [Auto Pilot](14-auto-pilot.md) is on.
- A red **NOTHING CAN RENDER** banner when videos are waiting to render and no renderer can take
  them. It links to **Settings → Rendering**. See
  [Troubleshooting](08-troubleshooting.md#nothing-can-render).

### The video window

Click a card or a row to open the video. The left side has tabs:

| Tab | Shows |
|---|---|
| **Topic** | The full topic |
| **Script** | The script, segment by segment, with a note on what each segment shows. Appears once a script exists |
| **Video** | The player. Appears once the video is rendered |
| **Publishing Results** | Each account the video was posted to, with its status, link and any error |
| **Comments** | Everything you and the agent have said about the video. You add to it through **Request Revision** |
| **Logs** | Log records for this video from every part of Tubematic |

The panel on the right holds:

- the buttons and pickers for the video's current status,
- links to the live posts, under **Published to**,
- the video's details: how the topic was found, its score, its script profile, visual style, voice
  and agent,
- the **Cost** panel,
- the AI review's findings, if AI review ran.

The **Cost** panel lists what the video spent, by provider and model. ElevenLabs is shown in credits.
A call with no known price reads "unpriced" and is left out of the total. Dollar figures are each
provider's API list price, so they differ from what a subscription bills you.

To save the video, use the player's own menu, or take the file from
`~/.tubematic-data/output_videos/<domain>/<video id>.mp4`.

### New Video

Creates a video from a topic you type.

| Field | Notes |
|---|---|
| **Title** | Required. Up to 70 characters. It is the name shown on cards |
| **Topic** | Required. The full brief the agent writes the script from |
| **Agent**, **Model**, **Effort** | Optional. **Automatic** lets Tubematic choose the agent by share |
| **Script profile**, **Visual style**, **Voice** | Optional |
| **Automatically approve topic** | Ticked by default, so the agent starts on the script. Untick it to review the topic on the Pipeline page first |

The video is filed under a domain called **Manual Videos** and has no score. After you submit, the
page keeps your picks, so you can enter the next video.

### Library and Archive

**Library** lists videos at Video Ready, Video Approved, Scheduled, Publishing and Published. You can
filter by status and by how the topic was found, sort by date or score, and search titles and
topics.

**Archive** lists videos whose files were deleted, by you or by the
[retention settings](05-settings.md#retention). Each keeps its title, domain, status, total views
and post links. An archived video cannot be played or restored.

### Topics

Holds the research mode toggles, the mining sources, and a row for each domain. Each row sets the
domain's default visual style, voice, script profile and mascot, and its topic cap. A curriculum
seed also has a **Pause topic generation** button.

[Using Tubematic](03-using-tubematic.md#where-topics-come-from) explains each of these.

### Projects

Pick a domain on the left to see its videos on the right. You can act on a video here as you would
on the Pipeline page.

### Profiles

Two pages share this tab. Script profiles are covered in
[Using Tubematic](03-using-tubematic.md#script-profiles), and mascots in
[Visual Styles and Mascots](13-visual-styles-and-mascots.md#mascots).

### Socials and Analytics

**Socials** connects social accounts and chooses which ones Tubematic may post to.
**Analytics** has two tabs:

- **Videos** lists each published post with its views, likes, comments and shares. You can filter by
  platform and account. A dash means the platform reported no figure.
- **Spend** shows what the install spent today, this week, this month or over a range of days. It
  includes spend that belongs to no single video, such as research.

**Socials** and the **Videos** tab stay empty until you set up [Publishing](06-publishing.md).

### Logs

Shows log records from every part of Tubematic. Filter by service, by level and by text. The page
does not update by itself. Press the refresh button, or change a filter, to load new records.

### Settings

See [Settings](05-settings.md).

---

## Making decisions

You decide on a video from its Quick Actions row or from its window. The buttons have shorter names
on the row.

| Status | Button | What it does |
|---|---|---|
| Topic Proposed | **Approve Topic** | The agent writes the script next |
| Topic Proposed | **Reject Topic** | The topic leaves the pipeline |
| Script Ready | **Approve Script** | The agent voices the script. ElevenLabs charges from here |
| Video Ready | **Approve Video** | The video moves to Video Approved. Nothing is posted |
| Any of the three above | **Request Revision** | Opens a dialog for your comment. The agent reworks the topic, script or video |
| Video Approved | **Publish…** | Opens the publish dialog. See [Publishing](06-publishing.md#publishing-a-video) |
| Scheduled | **Cancel schedule** | Takes the post back. The video returns to Video Approved |
| Failed, after a publish | **Retry publishing** | Checks whether a post went out anyway, then lets you publish again if none did |
| A STUCK video | **Retry agent** | Lets the agent try again |
| Most statuses | **Delete Video** | Deletes the video's files and moves its record to the Archive |

**Publish…**, **Cancel schedule** and **Retry publishing** appear only when publishing is set up.

**Delete Video** is not offered while Tubematic is working on the video, while a post is scheduled
or going out, or while a revision is pending.

### Choices you make with an approval

Pickers beside the buttons set how the next stage is done.

| Status | Pickers |
|---|---|
| Topic Proposed | Script profile, visual style, mascot, voice, agent, model, effort |
| Script Ready | Voice, agent, model, effort |
| Video Ready | Agent, model, effort. These apply when you request a revision |

- The script profile, visual style and mascot are fixed once you approve the topic.
- You can change the voice at Topic Proposed and at Script Ready. At Script Ready, a voice whose
  model cannot speak the script is greyed out. Each voice is labelled with its model. The **▶**
  button beside the picker plays a sample.
- You can change the agent, model and effort at each of the three statuses. Picking another agent
  resets the model to that agent's default.

If you leave a picker alone, the video keeps what it has.

### If an action is refused

A "Status conflict" message means the video moved after the page last refreshed, for example
because Auto Pilot approved it. Refresh the page. Any other refusal shows the reason.

---

## Times

The dashboard shows every time in the timezone of the machine Tubematic runs on. The top bar names
that timezone. Someone in another timezone sees the same times you do.

Scheduling a post is the exception. There you choose the timezone, and the video's card shows the
time in the zone you chose.
