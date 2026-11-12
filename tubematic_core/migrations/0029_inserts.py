"""0029 — main styles and insert scenes (TMDEV-224).

System Flow and Terminal Doc stop being whole-video styles: a video has one
main style, and short insert scenes from the insert styles. This migration
adds what records the insert decision and moves what still holds an insert
style as its main one.

New columns:
- videos.insert_mode: 'auto' (the agent decides whether inserts help) or
  'none' (no inserts). A person sets it at the topic checkpoint; it is seeded
  from the domain's default when the video is filed.
- videos.insert_styles: '' while undecided, then a JSON list of the insert
  style ids the script may use ('[]' = none). Written once by the agent
  (choose_inserts) before the script.
- videos.insert_reason: one sentence on why, shown beside it.
- projects.default_insert_mode: the insert_mode new videos in the domain take.

Data changes:
- A domain whose default style is system_flow or terminal_doc gets 'auto'.
- A video not yet voiced (TOPIC_PROPOSED, TOPIC_APPROVED, SCRIPT_READY) whose
  style is system_flow or terminal_doc goes back to Auto, as the dashboard's
  switch-style does: its style pick, recorded renderer and canvas, and formula
  pick are cleared, and one at SCRIPT_READY returns to TOPIC_APPROVED so its
  agent picks a main style and writes a new script. Nothing has been voiced, so
  no voice credit is lost. A comment on the video says why.
- A video already voiced or later keeps its style and finishes as a
  whole-video System Flow or Terminal Doc (the validators keep that path for a
  video whose stored style is one of them).
- Every video past TOPIC_APPROVED gets insert_styles '[]': its script was
  written before inserts existed, so its scenes never get any.

The style ids, statuses and SQL are written out here rather than imported: a
shipped migration must do the same thing forever.

One-way. 2.2.x refuses a newer schema, so a rollback means restoring the
automatic pre-migration backup.

*** THIS FILE HAS SHIPPED ONCE MERGED. DO NOT EDIT IT. ***
"""
import datetime

_INSERT_STYLES = ("system_flow", "terminal_doc")
_UNVOICED = ("TOPIC_PROPOSED", "TOPIC_APPROVED", "SCRIPT_READY")
_LABELS = {"system_flow": "System Flow", "terminal_doc": "Terminal Doc"}


def _columns(con, table: str) -> set:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def up(con):
    videos = _columns(con, "videos")
    if "insert_mode" not in videos:
        con.execute("ALTER TABLE videos ADD COLUMN insert_mode TEXT NOT NULL DEFAULT 'auto'")
    if "insert_styles" not in videos:
        con.execute("ALTER TABLE videos ADD COLUMN insert_styles TEXT NOT NULL DEFAULT ''")
    if "insert_reason" not in videos:
        con.execute("ALTER TABLE videos ADD COLUMN insert_reason TEXT NOT NULL DEFAULT ''")
    if "default_insert_mode" not in _columns(con, "projects"):
        con.execute("ALTER TABLE projects ADD COLUMN default_insert_mode TEXT NOT NULL DEFAULT 'auto'")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    marks = ",".join("?" * len(_INSERT_STYLES))
    unvoiced = ",".join("?" * len(_UNVOICED))

    con.execute(f"UPDATE projects SET default_visual_style = 'auto' "
                f"WHERE default_visual_style IN ({marks})", _INSERT_STYLES)

    rows = con.execute(
        f"SELECT id, visual_style, status FROM videos WHERE visual_style IN ({marks}) "
        f"AND status IN ({unvoiced}) AND archived_at IS NULL",
        _INSERT_STYLES + _UNVOICED).fetchall()
    for vid, style, status in rows:
        con.execute(
            "UPDATE videos SET visual_style = 'auto', style_pick = '', style_runner_up = '', "
            "style_reason = '', resolved_renderer = '', resolved_visual_style = '', "
            "formula_pick = '', formula_runner_up = '', formula_reason = '', formula_evidence = '', "
            "insert_styles = '', insert_reason = '', "
            "status = CASE WHEN status = 'SCRIPT_READY' THEN 'TOPIC_APPROVED' ELSE status END, "
            "agent_no_progress_count = 0, agent_stuck_at = NULL, updated_at = ? WHERE id = ?",
            (now, vid))
        label = _LABELS[style]
        then = ("Its agent picks a main style and writes a new script; the old script is discarded."
                if status == "SCRIPT_READY" else "Auto picks its main style when it is approved."
                if status == "TOPIC_PROPOSED" else "Its agent picks a main style before the script.")
        con.execute(
            "INSERT INTO comments (video_id, author, content, created_at) VALUES (?, 'human', ?, ?)",
            (vid, f"Upgrade to 2.3.0: {label} is now an insert style, shown in short scenes inside "
                  f"another style, never a whole video. This video's style is back on Auto. {then}",
             now))

    con.execute(
        "UPDATE videos SET insert_styles = '[]' WHERE insert_styles = '' "
        "AND status NOT IN ('TOPIC_PROPOSED', 'TOPIC_APPROVED')")
