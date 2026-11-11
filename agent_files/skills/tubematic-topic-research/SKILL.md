---
name: tubematic-topic-research
description: Research and propose new video topics using the curriculum, trending, or mining strategies
---

# Tubematic Topic Research Skill

**Invoke this skill when:** researching and proposing new video topics during a scheduled research
run. The operator skill and `/tubematic-submit-new-job` also send you to one section of it, **The
angle**, to find the angle of a single topic that already exists.

Tool signatures are in the MCP docstrings. This skill covers the workflow, what an angle is, and
the two scores.

---

## Research Workflow

> **Note:** Per-run topic caps and trending sources are configured during onboarding or on the Settings dashboard; they arrive embedded in the research prompt.

**Before researching**, call `list_projects()` once to get the current project list. If the prompt
carries no USER PREFERENCES block (an interactive session), read `user_preferences` from
`get_pipeline_status()` once. Either way, apply only the parts about topics — subjects to favour or
avoid, audience, angle — when choosing and scoring candidates.

For each active strategy:
1. Research topic candidates using that strategy's method (below)
2. Find each candidate's angle (**The angle**, below). A subject with no honest angle is dropped
   here, before anything else
3. Score every remaining candidate twice: the producibility rubric and the angle score. Drop
   anything below 5 on either
4. For each surviving candidate, file it into the right domain (**universal filing rule**):
   - Match to an existing project by subject/domain
   - **If the best-matching project is paused** (`status='paused'`) **or expired**
     (`expired` is true in `list_projects()`), **skip the candidate.**
     Do not file it into a loosely related domain instead, and do not create a new domain
     for it. A pause means "no videos on this subject right now", not "not in this row of
     the database"; an expired domain already holds as many topics as its `topic_cap`
     allows. `create_video` refuses a paused or expired project anyway; treat that refusal
     the same way, as a skip, never as a reason to retry somewhere else. Name each skipped
     candidate in your run summary.
   - **Deduplicate against that project** (see the Deduplication Rule) — drop the candidate
     if its core mechanism is > 70% similar to a topic already there
   - Only if **no** project matches the subject at all, paused, expired or not, call
     `upsert_project` to create one — a new project has no topics to deduplicate against
   - Call `create_video` with the topic, a short title, strategy name, producibility score,
     project_id, and the angle: `angle` (the sentence), `angle_kind` and `angle_score`.
     **Both text fields, every time:** `topic` is the full descriptive
     brief you researched — the thing the producibility score is about — and `title` is a
     short headline for it, at most 70 characters, which is what dashboard cards show.
     Write the title as a real headline, not the first 70 characters of the topic.
     `create_video` refuses a research topic that carries no angle, or one whose angle scores
     below 5. Treat that refusal as a drop: never reword the angle or raise its score to get
     the topic through.
   - Call `add_comment` with the rationale for both scores: which signals each one counted.
     The angle itself is stored on the video, so do not repeat it there

After all strategies are done: call `mark_research_done` to record when research last completed
(for display only — scheduling is governed by `poll.py`'s two run caps, not this timestamp).
Then end with the **Run summary** (below).

---

## The angle

A topic is worth a video when it already holds something to wait for. The angle is that thing,
written down: **one sentence, at most 300 characters, saying what the video's opening will use.**
The person approving the topic reads it beside the title, and the script writer builds the opening
on it and starts from the script formula its kind points to.

**The angle comes from what you already read** for the candidate: the seed domain's subject, the
trending item and its discussion, the mined video. Fetch nothing extra to find one. It is never
invented: no made-up incident, person, number or quote.

**A subject with no honest angle is not proposed.** If the material gives none of the kinds below
a real footing, drop the subject and name it in the run summary. Do not dress a definition up
until it passes: "X is a data structure, but it is surprisingly clever" is not a paradox.

**When you were sent here for one existing topic** (a video picked up with no angle, or a topic a
person just submitted), only the kinds, the rules for the sentence and the score below apply. Work
from that topic's text. Nothing is dropped and no score floor applies: if the topic has no honest
angle, it simply goes on without one, as the skill or command that sent you says.

The kinds, what a topic must hold for each, and where the script will start from:

<!-- angle-reference:start (generated by scripts/gen_angle_reference.py) -->
| Kind (`angle_kind`) | The topic has | The script will start from |
|---|---|---|
| **Paradox** (`paradox`) | Something the viewer owns or uses works in a way that seems impossible, or a system does something that looks like a loss and is not. The viewer has felt the contradiction; a definition with a 'but' added does not count. | Paradox, Mechanism, Reframe |
| **Broken expectation** (`broken_expectation`) | A tool did something that looks wrong, and the viewer has met it or can reproduce it. There is a visible symptom. | Broken Expectation |
| **Process** (`process`) | A process with a natural order that the viewer starts without seeing the rest of: a request, a boot, a login, a payment. One thing can be followed from start to finish, and the end is something the viewer does not already know. | Follow the Flow |
| **Myth** (`myth`) | A belief most people hold is wrong, and a real mechanism, study or figure shows it. Not a trivia correction, and not a myth already debunked everywhere. | Myth, Break, Model |
| **Design question** (`design_question`) | A design decision that looks stupid from outside, or a question newcomers keep asking, answered by a real rule or constraint that has a source. | Why Don't They Just |
| **Incident** (`incident`) | A real outage, loss, bug or breach with a timeline: a public account gives times, numbers and a decision a person made. | Incident File |
| **Scheme** (`scheme`) | A scam, a fraud, a loophole or an exploit that works as a loop of four steps or fewer, run by someone who meant it. | Scheme Machine |
| **Anomaly** (`anomaly`) | Evidence that looked wrong: every reading normal during a failure, a record that should not exist. The anomaly is real and its answer is not common knowledge. | Anomaly File |
| **Scene** (`scene`) | One person inside one moment: a near miss, a strange true incident, an ordinary life in a big event. The moment comes from a real account, or from the story's own canon when the subject is a story. Not a biography, and testimony is never invented. | Scene Story |
| **Measure** (`measure`) | Something with a natural measure the video can climb: size, cost, speed, time to break, risk. The numbers are real and each has something to compare it to. | Escalating Ladder |

**Angle score.** Sum the signals and clamp to 0–10. A research candidate needs 5 or more.

| Signal | Points |
|---|---|
| The angle names one thing the viewer waits for: an outcome, a cause, a number or a name the video can hold back and then give | +3 |
| The viewer has met it: they own the thing, have seen the failure or hold the belief | +2 |
| The material you read gives real specifics for it: a named incident, a date, a figure, a pair of numbers | +2 |
| It carries a stake or a contrast: a loss, a before and after, a number against a benchmark, one actor who meant it | +2 |
| The answer is not common knowledge | +1 |
| The angle is a definition, an overview or a list label ("what X is", "five things about X") | −3 |
| It needs facts the material does not give: an invented incident, person or number | −3 |
| The answer is already told everywhere | −2 |
<!-- angle-reference:end -->

How to write the sentence:

- State the thing itself, with its specifics: the symptom, the number, the name, the moment.
  "Deleting a log file frees no disk space while a program still holds it open", not "A surprising
  fact about deleting files".
- It is a note to the reviewer and the writer. It is not a line of the script and not a title.
- One angle per topic. If a subject has two, take the stronger; the other may be its own topic.
- The `topic` brief still says what the video covers. The angle says why someone keeps watching.

**Examples:**
- "Python list over-allocation" → *"Appending one item to a list can reserve room for several
  more, so the list holds more memory than what you put in it."* `paradox`. Waits for the cause +3,
  the viewer uses lists +2, a contrast between what was added and what was reserved +2 = **7** ✓
- "TCP three-way handshake" → *"A connection costs three packets before one byte of the page moves,
  and a flood of connections left at the second packet is enough to take a server down."*
  `process`. Waits for what the third packet is for +3, a stake +2, not common knowledge +1 = **6** ✓
- "Storming of the Dragonpit" → *"Four dragons died to a crowd on foot because they were chained
  under a dome, the one place a dragon cannot use the sky."* `design_question` (the question
  viewers of the story ask: why did they not fly away). Waits for the reason +3, specifics from
  the story +2, a stake +2 = **7** ✓
- "What a hash table is" → a definition: the angle would be a list label −3, and nothing is
  waited for. **Dropped, no angle** ✗

---

## Producibility Scoring

Score ≥ 5 required to propose. This number says whether the pipeline can show the topic; the angle
score above says whether anyone will stay to watch it. A candidate needs both. Sum the signals below and clamp to 0–10. A topic scores on
whichever track fits; scoring on both simply means the topic is rich on both tracks, and says
nothing about how its scenes should be built — that is decided per-beat downstream.

**DIAGRAM track — the pipeline draws it in SVG**

| Signal | Points |
|---|---|
| Step-by-step process with discrete stages | +2 |
| Before/after comparison (state A vs state B) | +2 |
| Countable elements (≤ 12, e.g. "Python allocates 8 slots") | +2 |
| Flow diagram or state machine exists for this topic | +2 |
| Terminal / scriptable output (output known at script time) | +1 |

**PHOTO track — the pipeline generates images of it**

| Signal | Points |
|---|---|
| The topic is about a named character, real person, creature or animal | +2 |
| A specific real place, structure, or physical object with a distinctive look | +2 |
| One specific dramatic or historical moment (a battle, an ambush, a launch, a signing) | +2 |

**Penalties**

| Signal | Points |
|---|---|
| Requires genuinely live, unpredictable output (real network latency, random results) | −3 |
| Scores zero on **both** tracks — nothing to see and nothing to track | −3 |
| Requires real archival footage or a real screen recording that cannot be generated as a still | −2 |

**Examples:**
- "Storming of the Dragonpit" → named characters +2, real structure +2, one specific moment +2, step-by-step +2 = **8** ✓
- "Python list over-allocation" → step +2, before/after +2, countable +2 = **6** ✓
- "TCP three-way handshake" → step +2, countable +2, flow +2 = **6** ✓
- "Best Python libraries 2026" → no track scores, both-tracks-zero −3 = **0** ✗

A candidate that scores on the PHOTO track will classify PHOTO downstream in
`tubematic-scene-config`'s subject test (or, where a beat turns on *where* or *in what order*,
HYBRID) — write its hook angle and `visual` briefs photographically (name the subject, the moment,
the framing), not as an abstract diagram.

---

## Strategy: Curriculum

Enumerate sub-topics from **user-seeded domains only** — these are projects where `is_curriculum_seed=1` and `status='active'`. Do not pick arbitrary broad topics.

1. From `list_projects()`, filter to `is_curriculum_seed=1 AND status='active'` and `expired` false
2. For each seed domain: generate sub-topics that each explain ONE mechanism in 60–90 seconds and have an angle (respect the per-run target given in the research prompt; if no target is given, default to 3–5 new candidates; not exhaustive). Look for the angle first. Ask of the seed's subject what in it looks impossible, fails in front of its user, is widely believed and wrong, looks like a stupid design, went wrong on a known day, can be gamed, left evidence that made no sense, happened to one person, or can be measured. A mechanism that answers none of these is a definition: skip it
3. Score both numbers, deduplicate against the seed domain's own topics (`list_project_topics`), and propose survivors

Good sub-topics: specific mechanisms (GIL, reference counting, list over-allocation), each entered through its angle. Not vague overviews ("Python performance").

**If no seed domains exist:** skip curriculum strategy and note this — the user needs to add domains with `/tubematic-add-topic`.

---

## Strategy: Trending

Find what's hot in tech right now and extract producible angles.

1. Scan the trending sources listed in the research prompt (configured on the Settings dashboard or during onboarding). Use your web-fetch and web-search tools to retrieve each source — these are public pages requiring no authentication or captcha solving. Supported sources: **GitHub Trending**, **Hacker News** (Show HN + technical posts), **Lobsters**, **Dev.to**. If no sources are listed in the prompt, fall back to GitHub Trending + Hacker News.
2. For each item: ask "What is the ONE mechanism here I can show visually in 60 seconds?", and what the item itself gives the opening: the failure the post describes, the number in its benchmark, the design decision people argue about under it. Take the angle from the item and its discussion
3. Score both numbers, deduplicate, and propose survivors using the universal filing rule

Good topic: new open-source tool → "How does X's core algorithm work?", entered through what the post shows (the benchmark figure, the bug it was written to end). Not: "X released version 3".

---

## Strategy: Mining

Spin off topics that were mentioned briefly in YouTube videos. Gemini processes
the videos natively — no local transcript files are involved.

**Requires:** a Gemini API key configured on the Settings dashboard. While none is
stored, mining is left out of your active strategies altogether — do not mine.
If `mine_youtube_topics` still returns an error about the key, skip mining, report
it in your research summary, and continue with other strategies.

1. Call `get_mining_sources()` to retrieve the configured YouTube URLs.
   If the list is empty, skip mining and note it in your summary.
2. Choose the most relevant project domain (`project_id`). Call `list_projects()` if unsure.
3. Call `mine_youtube_topics(project_id=..., youtube_urls=[...])` **once**.
   It files at most this run's mining cap itself: it asks Gemini only for what is
   left under the cap, shows it the topics that already exist, asks for an
   angle with each candidate, and skips any candidate that still repeats one,
   scores below 5, or comes back with no angle or an angle scoring below 5. Each run starts from a
   different URL, and asks at most as many URLs as topics it may file, so a run
   can end with URLs untried — the next run carries on from there.
   Pass the list exactly as `get_mining_sources()` returned it. The tool refuses
   the whole call, with no Gemini call made, if any URL is not a YouTube video
   URL, and refuses a call made while another mining run is in progress.
4. **Do not file extra mining topics with `create_video`, and do not reject what the
   tool filed.** If it filed fewer than the cap, that is this run's result.
5. If the tool returns an `error` key, report it and skip mining gracefully. Do not
   retry it in the same run.
6. Report in the run summary: how many topics were proposed, and every entry of `not_filed`
   with its reason.

**Example:** a video on Python internals briefly mentions "reference counting" →
spin-off: "How Python's reference counting actually works" (score: 6).

---

## Deduplication Rule

**Never set a topic to `TOPIC_REJECTED`.** Rejecting a topic is the human's decision at the
topic checkpoint, and the MCP server refuses it. A candidate that duplicates an existing topic, or
would go over a per-run cap, is simply never filed — don't file it and then reject it.

Before calling `create_video`, call `list_project_topics(project_id)` for the project you are
filing into (once per project per run is enough — add what you file yourself as you go) and check
for overlap. Use it, not `list_videos`: `list_videos` never shows an archived video, so a topic
that was made and deleted, or swept by retention, would come back. `list_project_topics` lists
every topic ever filed there, archived and rejected ones included — a topic the human turned down
counts as covered too.

Compare against each existing `topic` — the brief — not its `title`, which is only a short display
name and can omit the very mechanism you are checking for. If an existing `topic` covers the same
core mechanism (even with different wording), skip the candidate and note it was deduplicated.

---

## Run summary

End the run with a short summary, after `mark_research_done`. It is the only record of what the
run decided not to propose, so it is never skipped, even when nothing was filed. For each strategy:

- **Filed**: each topic's title, its angle kind and its two scores.
- **Dropped**: every candidate you did not file, by name, with one reason each: no angle, angle
  score below 5, producibility below 5, a duplicate of an existing topic, or its domain is paused
  or expired. For mining, list what `not_filed` returned, with the reasons it gave.
