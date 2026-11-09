"""Test helper: the renderer client (render_agent.py) wired to the real render
gateway app (render_gateway.create_gateway_app) on a migrated temporary
database, through an httpx WSGITransport — client and server tested together,
end to end, without TLS (one test in test_render_agent.py adds real TLS).

`make_env` points both halves at temporary directories: the gateway's jobs and
output dirs, the shared generated-scene tree (the built-in renderer's renders
compile the same tree the gateway bundles, as in the compose file), and the
renderer's own Remotion dir and job directory. Remotion itself is a fake Popen
(FakeRemotion) that writes the output file a real render would.
"""
import io
import json
import sqlite3
from pathlib import Path
from unittest import mock

import httpx

import pipeline
import render_agent
import render_gateway
import render_results

VERSION = "9.9.9"
BUILTIN_TOKEN = "builtin-token-for-tests"
GATEWAY_URL = "https://gateway.test"


class Recorder(httpx.BaseTransport):
    """Every request the client sends, before the gateway sees it. A `hook`
    may answer a request itself (return an httpx.Response) or raise."""

    def __init__(self, inner):
        self.inner = inner
        self.requests = []
        self.hook = None

    def handle_request(self, request):
        request.read()
        body = None
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content or b"null")
        self.requests.append({"method": request.method, "path": request.url.path, "json": body,
                              "auth": request.headers.get("authorization", ""),
                              "claim": request.headers.get("x-render-claim", "")})
        if self.hook is not None:
            answer = self.hook(request)
            if answer is not None:
                return answer
        return self.inner.handle_request(request)

    def paths(self, method=None):
        return [r["path"] for r in self.requests if method is None or r["method"] == method]

    def beats(self):
        return [r["json"] for r in self.requests if r["path"] == "/v1/heartbeat"]


class Env:
    def sql(self, sql, params=()):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in con.execute(sql, params).fetchall()]
            con.commit()
            return rows
        finally:
            con.close()

    def video(self, vid="vid-1"):
        return self.sql("SELECT * FROM videos WHERE id = ?", (vid,))[0]

    def renderer(self, rid="builtin"):
        return self.sql("SELECT * FROM renderers WHERE id = ?", (rid,))[0]

    def comments(self, vid="vid-1"):
        return [r["content"] for r in self.sql("SELECT content FROM comments WHERE video_id = ? ORDER BY id", (vid,))]

    def seed(self, vid="vid-1", status="RENDER_QUEUED", project="proj-1", updated="2026-01-01T00:00:00Z",
             visual_style="auto", mascot_id="", mascot_version=0, frames=90, scenes=None, files=True, **cols):
        self.sql("INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
                 "voice_file_path, timeline_path, scene_config_path, visual_style, mascot_id, mascot_version, "
                 "created_at, updated_at) VALUES (?, ?, 't', 'manual', 8, ?, 'x', 'x', 'x', ?, ?, ?, "
                 "'2026-01-01T00:00:00Z', ?)",
                 (vid, project, status, visual_style, mascot_id, mascot_version, updated))
        for k, v in cols.items():
            self.sql(f"UPDATE videos SET {k} = ? WHERE id = ?", (v, vid))
        if files:
            job = self.jobs / vid
            job.mkdir(parents=True, exist_ok=True)
            (job / "audio.mp3").write_bytes(b"AUDIO")
            (job / "timeline.json").write_text(json.dumps({"totalFrames": frames, "fps": 30, "words": []}))
            (job / "scene-config.json").write_text(json.dumps({"scenes": scenes or []}))
        return self.jobs / vid

    def start(self):
        """The renderer's first heartbeat (`started`), as main() sends it."""
        assert render_agent._beat() is True

    def gpu(self, ok=True):
        """A verified (or failed) GPU for the built-in renderer: configured
        in the environment, judged locally, and reported to the gateway."""
        self.monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-aaaa")
        self.monkeypatch.setenv("TUBEMATIC_GPU_NAME", "NVIDIA GeForce GTX 1650")
        self.monkeypatch.setattr(render_agent, "_gpu_verified", ok)
        with render_agent._st.lock:
            render_agent._st.pending_probe = {"at": "2026-01-01T00:00:00.000000Z", "configured": True,
                                              "ok": ok, "error": "" if ok else "SwiftShader",
                                              "gpu": {"uuid": "GPU-aaaa", "name": "NVIDIA GeForce GTX 1650"}}
        assert render_agent._beat() is True


def make_env(tmp_path, monkeypatch, builtin=True) -> Env:
    e = Env()
    e.monkeypatch = monkeypatch
    e.tmp = tmp_path
    e.db = str(tmp_path / "t.db")
    pipeline._init_db(e.db)
    e.jobs, e.out, e.secrets = tmp_path / "jobs", tmp_path / "out", tmp_path / "secrets"
    e.srv_remotion = tmp_path / "srv_remotion"
    e.generated = e.srv_remotion / "src" / "scenes" / "generated"
    e.remotion = tmp_path / "remotion"
    e.public = e.remotion / "public"
    e.render_tmp = tmp_path / "render"
    for d in (e.jobs, e.out, e.secrets, e.generated, e.public):
        d.mkdir(parents=True, exist_ok=True)
    (e.secrets / "builtin_renderer_token").write_text(BUILTIN_TOKEN)
    monkeypatch.setattr(render_results, "DB_PATH", e.db)
    monkeypatch.setattr(render_results, "JOBS_DIR", e.jobs)
    monkeypatch.setattr(render_results, "OUTPUT_DIR", e.out)
    monkeypatch.setenv("TUBEMATIC_VERSION", VERSION)
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(e.secrets))
    monkeypatch.setenv("TUBEMATIC_GATEWAY_URL", GATEWAY_URL)
    for var in ("GEMINI_REVIEW_ENABLED", "MAX_RENDER_RETRIES", "WATERMARK_ENABLED", "RENDER_TIMEOUT_SECS",
                "RENDER_STALL_TIMEOUT_SECS", "TUBEMATIC_GPU_UUID", "TUBEMATIC_GPU_NAME", "TUBEMATIC_HOST_GPUS",
                "TUBEMATIC_ENROLL_TOKEN", "TUBEMATIC_RENDERER_NAME"):
        monkeypatch.delenv(var, raising=False)
    if builtin:
        monkeypatch.setenv("TUBEMATIC_RENDERER_BUILTIN", "1")
    else:
        monkeypatch.delenv("TUBEMATIC_RENDERER_BUILTIN", raising=False)
    e.app = render_gateway.create_gateway_app(e.db, e.jobs, e.out, secrets_dir=e.secrets,
                                              remotion_dir=e.srv_remotion)
    e.rec = Recorder(httpx.WSGITransport(app=e.app))

    monkeypatch.setattr(render_agent, "REMOTION_DIR", e.remotion)
    # The built-in renderer compiles the shared tree; a remote one its own copy.
    e.client_generated = e.generated if builtin else tmp_path / "remote_generated"
    e.client_generated.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(render_agent, "GENERATED_DIR", e.client_generated)
    monkeypatch.setattr(render_agent, "RENDER_TMP", e.render_tmp)
    monkeypatch.setattr(render_agent, "RETRY_PAUSE_SECS", 0)
    monkeypatch.setattr(render_agent, "STILLS_SERVER_PORT", 0)
    monkeypatch.setattr(render_agent, "_gpu_verified", False)
    monkeypatch.setattr(render_agent, "_st", render_agent._AgentState())
    monkeypatch.setattr(render_agent, "_client",
                        render_agent.GatewayClient(render_agent.BuiltinIdentity(), transport=e.rec)
                        if builtin else None)
    return e


def finished_proc(argv, returncode=0, stdout="Rendered 1/1\nEncoded 1/1\n", stderr=""):
    proc = mock.MagicMock()
    proc.pid = 4242
    proc.args = argv
    proc.stdout = io.StringIO(stdout)
    proc.stderr = io.StringIO(stderr)
    proc.poll.return_value = returncode
    proc.returncode = returncode
    return proc


class FakeRemotion:
    """subprocess.Popen for `npx remotion render`: writes the output a real
    render writes (when it succeeds) and records each call. `on_start` sees
    the argv first (to look at what is staged while the render runs)."""

    def __init__(self, returncode=0, stderr="", output=b"MP4DATA", hang=False, on_start=None):
        self.returncode, self.stderr, self.output, self.hang, self.on_start = (
            returncode, stderr, output, hang, on_start)
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.on_start is not None:
            self.on_start(argv, kw)
        if self.hang:
            proc = finished_proc(argv, stdout="")
            proc.poll.return_value = None
            proc.returncode = None
            return proc
        if self.returncode == 0 and self.output is not None:
            out = Path(argv[argv.index("Composition") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(self.output)
        return finished_proc(argv, self.returncode, stderr=self.stderr)

    def props(self, i=-1) -> dict:
        argv = self.calls[i][0]
        return json.loads(argv[argv.index("--props") + 1])
