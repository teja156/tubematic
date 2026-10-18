Create a new video job from a user-provided topic.

User's topic: $ARGUMENTS

If $ARGUMENTS is empty, ask: "What topic would you like to create a video about?"

Step 0 — Call tubematic:get_pipeline_status() once and read user_preferences: the operator's standing
preferences for every video. Apply only the parts about topics (framing, audience, the brief and
title you write below) and ignore the rest. Reuse this same result in the later steps that need it.

Step 1 — Score the topic using the producibility rubric. Sum the signals below and clamp to 0-10;
a topic scores on whichever track fits, and scoring on both just means it is rich on both tracks
(how each beat is shown is decided per-beat downstream, not here).
  DIAGRAM track:
  +2 step-by-step process with discrete stages
  +2 before/after comparison (state A vs state B)
  +2 countable elements (12 or fewer)
  +2 flow diagram or state machine
  +1 terminal/scriptable output
  PHOTO track:
  +2 named character, real person, creature or animal
  +2 specific real place, structure, or distinctive physical object
  +2 one specific dramatic or historical moment
  Penalties:
  -3 live or unpredictable output
  -3 scores zero on both tracks
  -2 requires real footage that can't be generated as a still

Step 2 — If score < 5: explain why the topic scores too low and suggest how to reframe it. Do NOT create a video.

Step 3 — If score ≥ 5: match or create a project domain.
  Call tubematic:list_projects() and find the best matching domain for this topic.
  - If a match exists and its status is 'active', use that project_id.
  - If a match exists but is 'paused' or expired (`expired` is true — it already holds as many topics as its topic_cap allows), inform the user and ask if they want to file it there anyway or create a new domain. Filing there works: a topic the user submits directly is accepted even into a paused or expired domain.
  - If no match exists, call tubematic:upsert_project(project_id=<slug>, name=<domain name>) to create one.

Step 3.5 — Ask which voice to use, if there's a real choice:
  Call tubematic:get_pipeline_status() and read elevenlabs_voices and elevenlabs_voice_id. Each
  voice carries its own ElevenLabs model_id, and the model decides which pronunciation markup the
  script can use — show it next to the name.
  - If elevenlabs_voices has 2 or more entries: list the names with their models (marking the
    default — the domain's default_voice_id from list_projects if it has one, else
    elevenlabs_voice_id) and ask the user which to use. Pass their choice as voice_id to
    create_video below.
  - If it has 0 or 1 entries, skip the question — there's no real choice, and leaving voice_id
    blank already gives the video its domain's default voice, or the install default.

Step 3.6 — Ask which script profile to write in, if there is one:
  Call tubematic:list_script_profiles().
  - If it returns one or more profiles with status "READY": list them by name, plus a
    "none (generic style)" option, and ask which to use. Remember the chosen id (or none).
  - If it returns none, skip the question — "none" is the only available answer anyway, and
    leaving the profile unset is exactly what it means.
  - A profile whose status is not "READY" is still building; mention it as unavailable rather
    than offering it, since setting it would be rejected.

Step 4 — Create the video and immediately approve it.
  First write a SHORT_TITLE for the user's topic: a headline of at most 70 characters, which is
  what dashboard cards show. Compose it, don't clip — TOPIC stays whole and is what the score and
  the script are about, so the title is a name for it, not the first 70 characters of it. If the
  user's topic is already 70 characters or fewer, use it as the title unchanged.
  tubematic:create_video(topic=TOPIC, title=SHORT_TITLE, strategy="manual", producibility_score=SCORE, project_id=PROJECT_ID, voice_id=CHOSEN_VOICE_ID)
  The result carries the video's agent_id — the agent this video was dealt.

  If the user asked for a specific agent (e.g. "have Codex do it"), move the video to it: call
  tubematic:get_pipeline_status(), find that agent in `agents` (only live agents are listed, and
  only those are accepted), and pass agent_id=<its id> in the update_video call below. From here
  on "the video's agent" means that one. Do not ask about the agent otherwise — the deal already
  picked one.

  Then ask which model to use, if there's a real choice:
    Call tubematic:get_pipeline_status() and read `agents`. The video's agent is the entry whose
    id equals its agent_id — the returned one, or the one the user asked for above (if agent_id is
    null, the entry with is_default true).
    - If that agent's `models` has 2 or more entries: list them, marking the first as the default,
      and ask which to use. Only these are accepted — the list was validated when the agent was
      installed, and any other name is rejected.
    - If it has 0 or 1 entries, skip the question. Leaving the model unset means the agent's
      default (its first model).

  Then ask which effort level to run at:
    The same `agents` entry carries that agent's own `effort`. Offer "low", "medium", "high",
    "xhigh" and "max", marking that one as the default, and ask which to use. Higher levels
    think harder, cost more and take longer. Ask this every time — unlike the model list, all
    five are always available for every agent.
    If the user picks the agent's own level, leave it unset rather than passing it: unset means
    "follow the agent", so the video keeps tracking that agent's level if it is changed later.

  If a script profile was chosen in Step 3.6, or an agent, a non-default model or effort just now
  (any of them), set them in one call — this must happen BEFORE the status flip below, since these
  fields are refused once the video has left TOPIC_PROPOSED:
    tubematic:update_video(video_id=<returned_id>, agent_id=CHOSEN_AGENT_ID, script_profile_id=CHOSEN_PROFILE_ID, agent_model=CHOSEN_MODEL, agent_effort=CHOSEN_EFFORT)
  (pass only the ones that were chosen)
  tubematic:set_video_status(video_id=<returned_id>, new_status="TOPIC_APPROVED", only_if_current_status="TOPIC_PROPOSED")

Manual submissions are initiated by the user — that intent IS the approval. Skip TOPIC_PROPOSED entirely.

Then add a comment explaining the score:
  tubematic:add_comment(video_id=<returned_id>, author="agent", content="Submitted via /tubematic-submit-new-job. Score: SCORE/10. RATIONALE. Domain: PROJECT_NAME.")

Step 5 — Tell the user:
- The video ID that was created
- The producibility score and what drove it
- The domain/project it was filed under
- Which script profile it will be written in (or that it uses the generic style)
- Which agent, model and effort level it will run under (or that it uses the agent's own defaults)
- That the video is at TOPIC_APPROVED and will be picked up for scripting on the next pipeline poll
