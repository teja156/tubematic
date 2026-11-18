"""Installing, reviewing and removing external visual styles (TMDEV-253).

Staging (`POST /external-styles/pending`) is open to anyone with the API token,
the way the dashboard and an agent command both reach it. Confirming an install
needs the dashboard password in the body as well: the dashboard relays every
call with the same API token an agent on the host can read, so the token cannot
tell a person from an agent, and the password can. It shares the login's
throttle, so the route is no way around it.

Removal is refused while an unfinished video or a domain uses the style.
"""
import base64
import binascii
import json

from flask import Blueprint, jsonify, request

import db
from tubematic_core import auth as core_auth
from tubematic_core import external_styles as texternal
from tubematic_core import style_install as tinstall
from tubematic_core import visual_styles as tvs

# A video in these statuses (or archived) no longer needs its style's package.
FINISHED_STATUSES = ("PUBLISHED", "PARTIALLY_PUBLISHED", "FAILED", "TOPIC_REJECTED")


def _err(message, status=400):
    return jsonify({"error": message}), status


def create_styles_blueprint(db_path: str, throttle) -> Blueprint:
    bp = Blueprint("external_styles", __name__)

    def settings(con) -> dict:
        rows = {r[0]: r[1] for r in con.execute("SELECT key, value FROM settings WHERE key IN "
                                                 "('external_styles_in_auto', 'style_gallery_url')")}
        try:
            auto = json.loads(rows.get("external_styles_in_auto") or "[]")
        except ValueError:
            auto = []
        from pipeline import SETTINGS_SPEC  # the default lives with the key
        url = rows.get("style_gallery_url", SETTINGS_SPEC["style_gallery_url"][1])
        return {"auto": auto if isinstance(auto, list) else [], "gallery_url": url}

    def users(con, sid: str) -> dict:
        marks = ",".join("?" * len(FINISHED_STATUSES))
        videos = [dict(r) for r in con.execute(
            f"SELECT id, status, COALESCE(NULLIF(title, ''), topic) AS title FROM videos "
            f"WHERE visual_style = ? AND archived_at IS NULL AND status NOT IN ({marks}) ORDER BY created_at",
            (sid, *FINISHED_STATUSES)).fetchall()]
        domains = [dict(r) for r in con.execute(
            "SELECT id, name FROM projects WHERE default_visual_style = ? ORDER BY name", (sid,)).fetchall()]
        return {"videos": videos, "domains": domains}

    @bp.get("/external-styles")
    def list_installed():
        """Every package in the styles folder, valid or not, with its approval record."""
        records = texternal.approvals(texternal.STYLES_DIR)
        with db.conn(db_path) as con:
            conf = settings(con)
            out = []
            for sid, found in texternal.load(texternal.STYLES_DIR).items():
                rec = records.get(sid) or {}
                block = (found.pack or {}).get("external") or {}
                use = users(con, sid)
                out.append({
                    "id": sid, "label": (found.pack or {}).get("label") or rec.get("label") or sid,
                    "ok": found.ok, "reason": found.reason, "needs_review": found.needs_review,
                    "version": block.get("version") or rec.get("version", ""),
                    "author": block.get("author", ""), "licence": block.get("licence", ""),
                    "homepage": block.get("source", ""),
                    "renderer": (found.pack or {}).get("renderer", ""),
                    "needs_gpu": bool(((found.pack or {}).get("needs") or {}).get("gpu")),
                    "source": rec.get("source"), "reviewed": bool(rec.get("reviewed")),
                    "installed_at": rec.get("installed_at", ""),
                    "in_auto": sid in conf["auto"],
                    "unfinished_videos": len(use["videos"]), "domains": use["domains"],
                })
        return jsonify({"styles": out, "pending": tinstall.list_pending(), "gallery_url": conf["gallery_url"]})

    @bp.get("/external-styles/gallery")
    def gallery():
        with db.conn(db_path) as con:
            url = settings(con)["gallery_url"]
        if not url:
            return jsonify({"gallery_url": "", "styles": [], "error": "No gallery address is set."})
        try:
            entries = tinstall.gallery_index(url)
        except tinstall.InstallError as exc:
            return jsonify({"gallery_url": url, "styles": [], "error": str(exc)})
        records = texternal.approvals(texternal.STYLES_DIR)
        for e in entries:
            e["installed_version"] = (records.get(e["id"]) or {}).get("version")
        return jsonify({"gallery_url": url, "styles": entries})

    @bp.post("/external-styles/pending")
    def stage():
        body = request.get_json(silent=True) or {}
        kind = body.get("kind")
        source = {k: body.get(k) for k in ("kind", "url", "ref", "id", "name", "filename")}
        if kind == "zip":
            try:
                source["data"] = base64.b64decode(body.get("data") or "", validate=True)
            except (binascii.Error, ValueError, TypeError):
                return _err("data must be the zip file, base64-encoded")
        elif kind == "incoming":
            return _err("an incoming folder is staged by the agent through MCP")
        with db.conn(db_path) as con:
            url = settings(con)["gallery_url"]
        try:
            record = tinstall.stage(source, index_url=url)
        except tinstall.InstallError as exc:
            return _err(str(exc))
        return jsonify(record), 201

    @bp.get("/external-styles/pending/<pid>")
    def pending(pid):
        try:
            record = tinstall.get(pid)
        except tinstall.InstallError as exc:
            return _err(str(exc), 404)
        with db.conn(db_path) as con:
            record["in_use"] = users(con, record["style_id"])
        return jsonify(record)

    @bp.get("/external-styles/pending/<pid>/file")
    def pending_file(pid):
        try:
            return jsonify({"path": request.args.get("path", ""),
                            "text": tinstall.read_file(pid, request.args.get("path", ""))})
        except tinstall.InstallError as exc:
            return _err(str(exc), 404)

    @bp.delete("/external-styles/pending/<pid>")
    def discard(pid):
        try:
            tinstall.discard(pid)
        except tinstall.InstallError as exc:
            return _err(str(exc), 404)
        return jsonify({"ok": True})

    @bp.post("/external-styles/pending/<pid>/confirm")
    def confirm(pid):
        """The human yes. Needs the dashboard password; see the module docstring."""
        password = (request.get_json(silent=True) or {}).get("password")
        if not isinstance(password, str) or not password or len(password) > 1024:
            return _err("Enter your dashboard password to install a style.", 401)
        wait = throttle.begin()
        if wait:
            return (jsonify({"error": f"too many password attempts; try again in {wait}s"}),
                    429, {"Retry-After": str(wait)})
        ok = None
        try:
            stored = core_auth.admin_password_hash(db_path)
            ok = bool(stored) and core_auth.verify_password(password, stored)
        finally:
            throttle.finish(ok)
        if not ok:
            return _err("wrong password", 401)
        try:
            result = tinstall.confirm(pid)
        except tinstall.InstallError as exc:
            return _err(str(exc), 409)
        return jsonify(result)

    @bp.delete("/external-styles/<sid>")
    def remove(sid):
        if not tvs.is_external(sid):
            return _err("only an installed external style can be removed", 404)
        with db.conn(db_path) as con:
            use = users(con, sid)
            if use["videos"] or use["domains"]:
                parts = []
                if use["videos"]:
                    parts.append(f"{len(use['videos'])} unfinished video(s)")
                if use["domains"]:
                    parts.append("the domain(s) " + ", ".join(d["name"] for d in use["domains"]))
                return _err(f"{sid} is still used by {' and '.join(parts)}. Finish those videos or switch "
                            "them and the domains to another style, then remove it.", 409)
            conf = settings(con)
            if sid in conf["auto"]:
                con.execute("UPDATE settings SET value = ? WHERE key = 'external_styles_in_auto'",
                            (json.dumps([s for s in conf["auto"] if s != sid]),))
        try:
            tinstall.remove(sid)
        except tinstall.InstallError as exc:
            return _err(str(exc), 404)
        return jsonify({"ok": True})

    return bp
