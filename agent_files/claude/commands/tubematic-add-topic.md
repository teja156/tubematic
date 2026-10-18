Add a curriculum seed domain for scheduled topic research.

User's input: $ARGUMENTS

Format: "NAME — DESCRIPTION" or just "NAME"
Examples:
  /tubematic-add-topic Python Internals — CPython memory management, GIL, bytecode
  /tubematic-add-topic Networking Fundamentals

If $ARGUMENTS is empty, ask:
  "What broad domain should curriculum mode research? Provide a name and optional description, e.g. 'Python Internals — CPython memory management, GIL, bytecode'"

Step 1 — Parse $ARGUMENTS:
  - Split on " — " or " - " to separate name from description.
  - Generate a slug: lowercase, hyphens, alphanumeric only (e.g. "Python Internals" → "python-internals").

Step 2 — Check for an existing project:
  Call tubematic:list_projects() and look for a project with the same slug or a very similar name.
  - If one exists and is_curriculum_seed=1: tell the user it's already a seed domain and show its status.
  - If one exists but is_curriculum_seed=0: update it using upsert_project with is_curriculum_seed=True.
  - If none exists: create it.

Step 3 — Create or update:
  tubematic:upsert_project(
    project_id=SLUG,
    name=NAME,
    description=DESCRIPTION,
    is_curriculum_seed=True,
    status="active"
  )

Step 4 — Tell the user:
- The domain was added (or updated) as a curriculum seed
- It will be enumerated on the next scheduled research run
- They can pause it at any time with /tubematic-pause-domain SLUG
- It can hold up to its topic_cap topics (100 unless changed, at most 750). Once it holds that many
  it is expired and research stops filing into it; raise the cap on the dashboard's Topics page
- They can check active seed domains with /tubematic-list-strategies
