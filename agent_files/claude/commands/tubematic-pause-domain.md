Pause topic generation for a curriculum seed domain. No new videos are filed there by scheduled research.

User's input: $ARGUMENTS (project_id or domain name)

If $ARGUMENTS is empty, ask: "Which domain do you want to pause? (provide the project ID or name)"

Step 1 — Resolve the project:
  Call tubematic:list_projects() and find the project matching $ARGUMENTS (by id or name, case-insensitive).
  If not found: tell the user and list available domains.
  If it is not a curriculum seed (is_curriculum_seed=0): do not call anything. Tell the user that
  only curriculum seed domains can be paused. Pausing stops topics being generated FROM a seed; any
  other domain only receives topics researched elsewhere, so pausing it could not stop them. Their
  options are to reject unwanted proposals on the dashboard, or to turn the trending or mining
  strategy off with /tubematic-set-strategy.

Step 2 — Pause it:
  tubematic:set_project_status(project_id=PROJECT_ID, status="paused")
  If it returns an error, tell the user what it says and stop.

Step 3 — Tell the user:
- Topic generation for the domain is now paused
- Scheduled research will neither enumerate it nor file new videos into it
- A topic they submit themselves with /tubematic-submit-new-job is still accepted
- In-flight videos already past TOPIC_PROPOSED will continue processing
- Resume any time with /tubematic-resume-domain PROJECT_ID
