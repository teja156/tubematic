import os
import subprocess

from flask import Flask, jsonify

from api_auth import create_auth_blueprint, install_auth
from pipeline import create_pipeline_blueprint
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 4000))
    app.run(host="0.0.0.0", port=port, threaded=True)
