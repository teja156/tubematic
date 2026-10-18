Create a video from a topic and drive it through the Tubematic pipeline to a rendered mp4, in this
VQA (video quality assessment) environment — no dashboard, no cron, one human in the loop via chat.

User's topic: $ARGUMENTS

If $ARGUMENTS is empty, ask: "What topic would you like to create a video about?"

This environment deviates from the normal tubematic-operator skill in three ways. Apply these
deviations, then invoke the tubematic-operator skill for everything else (scripting, voicing,
scene authoring, rendering) — its per-status guidance is otherwise unchanged.

**Deviation 1 — skip the operator skill's Setup Check.** This environment has no dashboard
container and no compose file at the agent's cwd the way the Setup Check's `docker compose ps`
checks expect. kasm_post_run_user.sh already brought tubematic-api and tubematic-renderer up and confirmed
`/health` before this session started. If any MCP tool call actually fails, THEN diagnose from
first principles (`docker compose ps`, `curl -s http://localhost:4000/health`) rather than
following the Setup Check's table verbatim — it also references `/tubematic-register-mcp` and the
dashboard container, neither of which exists here.

**Deviation 2 — there is no dashboard, so approvals happen in chat.** At each of the three human
checkpoints below, present the relevant state, wait for the user's explicit go-ahead in this
conversation, then call `tubematic:set_video_status` yourself. Do not advance past a checkpoint on
your own judgment.

  - `TOPIC_PROPOSED` → show the topic and producibility score, **and ask which visual style to
    use** — `auto` (unrestricted: you pick the canvas and use whichever vocabularies the beats
    actually require), `motion_graphics` (dark canvas, no figures at all), `stick` (white canvas,
    hand-drawn line figures) or `illustrated` (generated character artwork, you choose the canvas
    and whether the art is playful or serious). There is no dashboard here, so this chat is the
    only place that choice can be made, and it is frozen the moment the topic is approved.
    Offer `illustrated` only if `get_pipeline_status()` reports `illustrated_available: true` —
    its characters need an OpenAI key, and without one `update_video` refuses it. If it is
    unavailable, say so and why rather than leaving it out silently.

    If the user picks anything other than `auto`, call
    `update_video(video_id, visual_style="<choice>")` **before** approving — the server refuses it
    afterwards with a 409, because the scripting step reads the register before it writes a single
    visual brief.

    Then ask to approve, and
    `set_video_status(new_status="TOPIC_APPROVED", only_if_current_status="TOPIC_PROPOSED")`.
  - `SCRIPT_READY` → **before asking for approval**, stage the script for review by running:

    `/opt/tubematic/.venv/bin/python "$(ls -d ~/tubematic 2>/dev/null || echo /opt/tubematic)"/vqa/stage_script.py <video_id>`

    **If that fails with `ModuleNotFoundError: No module named 'fastmcp'`**, the host venv does not
    carry the MCP server's dependencies — `mcp/requirements.txt` installs inside the container, not
    on the host, so this is expected anywhere but the purpose-built VQA image. Run the same script
    inside the MCP container instead, where those deps live and `/jobs` is a bind mount of the same
    directory:

    `docker exec tubematic-mcp python3 /app/vqa/stage_script.py <video_id>`

    If `/app/vqa` is not present in that image either, read the two values straight from the API
    (`get_video`'s `script_segments` and `tts_text`) and show them in chat — the staged files are a
    convenience for reviewing before spend, not a prerequisite for it.

    This writes two files to `~/.tubematic-data/jobs/<video_id>/`:
      - `script_with_broll.txt` — each segment's spoken text next to its visual/b-roll direction
      - `tts_text.txt` — the text that would actually be sent to ElevenLabs (phoneme tags,
        `<respell>`, `<ipa>`, and the pronunciation lexicon all applied)

    Then stop and show the user: the script itself, **the character count and estimated
    ElevenLabs cost** (cost is non-refundable once voiced — estimate at 0.03 cents per character,
    `len(script) * 0.03` cents), and the two staged file paths so they can review both versions
    before approving the spend. Ask to approve, then
    `set_video_status(new_status="VOICING", only_if_current_status="SCRIPT_READY")`. If a
    revision loop rewrites the script later, re-run the staging command after the fix so the
    files reflect the current version.
  - `VIDEO_READY` → after the render completes, tell the user where the file is (see Deviation 3).

    **Check `gemini_review_enabled` in `get_pipeline_status()` before saying anything about
    review**, rather than assuming. The purpose-built VQA image seeds it `false`, so there a render
    landing at `VIDEO_READY` instead of `REVISION_REQUESTED` is expected and review is on request
    via `/vqa-review <video_id>`. Any other install may well have it on, in which case the render
    is reviewed automatically and a bounce to `REVISION_REQUESTED` is the pipeline working. Saying
    the wrong one sends the user hunting a bug that is not there.

    Ask whether to approve;
    if so, `set_video_status(new_status="VIDEO_APPROVED", only_if_current_status="VIDEO_READY")`.
    Nothing downstream of `VIDEO_APPROVED` (publishing) is implemented — approval here just marks
    the human's sign-off.

**Deviation 3 — file into the fixed VQA project, and report the host output path.** Use
`project_id="proj_vqa"` for `create_video` — skip the operator skill's normal project
matching/creation. The purpose-built VQA image seeds that project; anywhere else it may not exist,
and `create_video` rejects an unknown `project_id` outright. Check `list_projects()` first and,
if it is missing, create it with
`upsert_project(project_id="proj_vqa", name="VQA", description="Video quality assessment")`
before creating the video. Once the video reaches `VIDEO_READY`, tell the user the rendered file
is at:

  `~/.tubematic-data/output_videos/proj_vqa/<video_id>.mp4`

and that it can be opened directly with `mpv <path>`.

Now invoke the tubematic-operator skill and advance this video through the pipeline, applying the
three deviations above at the relevant points.
