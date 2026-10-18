Resume topic generation for a paused curriculum seed domain. New videos can be filed there again.

User's input: $ARGUMENTS (project_id or domain name)

If $ARGUMENTS is empty, ask: "Which domain do you want to resume? (provide the project ID or name)"

Step 1 — Resolve the project:
  Call tubematic:list_projects() and find the project matching $ARGUMENTS (by id or name, case-insensitive).
  If not found: tell the user and list available domains.
  If already active: tell the user and do nothing.

Step 2 — Activate it:
  tubematic:set_project_status(project_id=PROJECT_ID, status="active")

Step 3 — Tell the user:
- The domain is now active
- Scheduled research runs will enumerate it again
- Trending and mining proposals can be filed here again
