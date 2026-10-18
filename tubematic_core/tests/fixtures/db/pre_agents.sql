-- A database as it stood before the agents table existed (pre-TMDEV-90).
-- Hand-written on purpose: generating it from current code would make it
-- converge trivially and test nothing.
CREATE TABLE projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    is_curriculum_seed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL);
CREATE TABLE videos (
    id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id),
    topic TEXT NOT NULL, strategy TEXT NOT NULL DEFAULT 'manual',
    producibility_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
    title TEXT NOT NULL DEFAULT '', script TEXT NOT NULL DEFAULT '',
    voice_file_path TEXT NOT NULL DEFAULT '', timeline_path TEXT NOT NULL DEFAULT '',
    scene_config_path TEXT NOT NULL DEFAULT '', video_path TEXT NOT NULL DEFAULT '',
    video_version INTEGER NOT NULL DEFAULT 1, gemini_feedback TEXT NOT NULL DEFAULT '',
    youtube_url TEXT NOT NULL DEFAULT '', voice_id TEXT NOT NULL DEFAULT '',
    tts_text TEXT NOT NULL DEFAULT '',
    ai_review_count INTEGER NOT NULL DEFAULT 0,
    render_fail_count INTEGER NOT NULL DEFAULT 0,
    cost_cents_elevenlabs INTEGER NOT NULL DEFAULT 0,
    cost_cents_gemini INTEGER NOT NULL DEFAULT 0,
    cost_cents_claude INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    author TEXT NOT NULL CHECK (author IN ('human','agent')),
    content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

INSERT INTO projects VALUES ('proj_1', 'Networking', 'Deep dives', 1, 'active', '2026-01-01T00:00:00Z');
INSERT INTO videos (id, project_id, topic, status, producibility_score, created_at, updated_at)
VALUES ('vid_a', 'proj_1', 'Alpha', 'VIDEO_READY', 8, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z');
INSERT INTO videos (id, project_id, topic, status, producibility_score, created_at, updated_at)
VALUES ('vid_b', 'proj_1', 'Beta', 'SCRIPT_READY', 6, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z');
-- Stranded at the removed SCRIPTING status; only mcp/server.py's copy recovers it.
INSERT INTO videos (id, project_id, topic, status, producibility_score, created_at, updated_at)
VALUES ('vid_stranded', 'proj_1', 'Gamma', 'SCRIPTING', 5, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z');
INSERT INTO comments (video_id, author, content, created_at)
VALUES ('vid_a', 'human', 'looks good', '2026-01-02T00:00:00Z');

INSERT INTO settings VALUES ('elevenlabs_voice_id', 'my-voice');
INSERT INTO settings VALUES ('max_feedback_loops', '3');
INSERT INTO settings VALUES ('agent_model', 'claude-opus-4');
