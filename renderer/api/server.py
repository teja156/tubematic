import os
import subprocess
import threading

from flask import Flask, jsonify

import db
import render_gateway
from api_auth import create_auth_blueprint, install_auth
from pipeline import create_pipeline_blueprint
from tubematic_core import renderers
from tubematic_core.auth import read_secret

app = Flask(__name__)

CHROMIUM_BIN = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/render/health")
def render_health():
    result = subprocess.run(
        [CHROMIUM_BIN, "--version"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        return jsonify({"status": "ok", "chromium": result.stdout.strip()})
    return jsonify({"status": "error", "detail": result.stderr.strip()}), 500


app.register_blueprint(create_pipeline_blueprint())
app.register_blueprint(create_auth_blueprint(os.getenv("TUBEMATIC_DB", "/data/tubematic.db")))
# Raises if the token file is missing or empty, so the API refuses to start
# rather than starting open.
install_auth(app, read_secret("api_token"))


def start_render_gateway():
    """Make sure the built-in renderer's row exists, then serve the render
    gateway (render_gateway.py) over TLS in a daemon thread. Returns the
    server, or None when the gateway cannot start (its TLS pair missing or
    unusable, its port taken): then renderers cannot reach the API, but the
    API still serves the dashboard."""
    db_path = os.getenv("TUBEMATIC_DB", "/data/tubematic.db")
    # The migration creates the row; this restores one a hand edit removed.
    # create_pipeline_blueprint() above has already migrated the database.
    with db.conn(db_path) as con:
        renderers.ensure_builtin(con)
    gateway = render_gateway.create_gateway_app(
        db_path, os.getenv("TUBEMATIC_JOBS_DIR", "/jobs"), os.getenv("OUTPUT_BASE_PATH", "/output_videos"))
    server = render_gateway.make_gateway_server(
        gateway, "0.0.0.0", int(os.getenv("TUBEMATIC_GATEWAY_PORT", "4443")))
    if server is not None:
        threading.Thread(target=server.serve_forever, name="render-gateway", daemon=True).start()
    return server


def main() -> None:
    start_render_gateway()
    port = int(os.getenv("PORT", 4000))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
