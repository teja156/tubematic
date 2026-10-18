-- Older than pre_agents.sql: animatability_score not yet renamed, no voice_id,
-- no tts_text, no notified_status, no publishing tables.
CREATE TABLE projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    is_curriculum_seed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL);
CREATE TABLE videos (
    id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id),
    topic TEXT NOT NULL, strategy TEXT NOT NULL DEFAULT 'manual',
    animatability_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
    title TEXT NOT NULL DEFAULT '', script TEXT NOT NULL DEFAULT '',
    voice_file_path TEXT NOT NULL DEFAULT '', timeline_path TEXT NOT NULL DEFAULT '',
    scene_config_path TEXT NOT NULL DEFAULT '', video_path TEXT NOT NULL DEFAULT '',
    video_version INTEGER NOT NULL DEFAULT 1, gemini_feedback TEXT NOT NULL DEFAULT '',
    youtube_url TEXT NOT NULL DEFAULT '',
    cost_cents_elevenlabs INTEGER NOT NULL DEFAULT 0,
    cost_cents_gemini INTEGER NOT NULL DEFAULT 0,
    cost_cents_claude INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL,
    author TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

INSERT INTO projects VALUES ('proj_old', 'Legacy', '', 0, 'active', '2025-06-01T00:00:00Z');
INSERT INTO videos (id, project_id, topic, status, animatability_score, created_at, updated_at)
VALUES ('vid_old', 'proj_old', 'Ancient', 'VIDEO_READY', 7, '2025-06-01T00:00:00Z', '2025-06-02T00:00:00Z');
-- Pre-rename statuses, recovered by 0001.
INSERT INTO videos (id, project_id, topic, status, animatability_score, created_at, updated_at)
VALUES ('vid_rr', 'proj_old', 'Old revision', 'VIDEO_REVISION_REQUESTED', 4, '2025-06-01T00:00:00Z', '2025-06-02T00:00:00Z');
INSERT INTO videos (id, project_id, topic, status, animatability_score, created_at, updated_at)
VALUES ('vid_ready', 'proj_old', 'Old ready', 'RENDER_READY', 5, '2025-06-01T00:00:00Z', '2025-06-02T00:00:00Z');
