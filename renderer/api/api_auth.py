"""Bearer-token check for the whole API, and the dashboard's password login (TMDEV-152).

`install_auth` goes on the *app*, not the pipeline blueprint, for two reasons:
a route added anywhere is covered by default, and the health routes live on the
app so that blueprint hooks never see them. They are exempted by endpoint name,
never by path prefix, so `/healthz-anything` is not accidentally open.
"""
import hmac
import threading
import time

from flask import Blueprint, jsonify, request

from tubematic_core import auth as core_auth

OPEN_ENDPOINTS = frozenset({"health", "render_health"})

# scrypt is deliberately slow; an unbounded body would make each attempt
# arbitrarily expensive before the throttle ever counts it.
MAX_PASSWORD_LEN = 1024


def install_auth(app, token: str) -> None:
    expected = token.encode()

    @app.before_request
    def _require_token():
        if request.endpoint in OPEN_ENDPOINTS:
            return None
        scheme, _, presented = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(presented.strip().encode(), expected):
            return jsonify({"error": "unauthorized"}), 401
        return None


class LoginThrottle:
    """Install-wide backoff on failed logins: a few free tries, then 2^n seconds.

    Global rather than per client, because every login arrives from the
    dashboard container and a forwarded client address is spoofable. An
    attacker can therefore make the owner wait too -- up to MAX_WAIT -- which
    is the accepted price for a single-operator install. In memory, so an API
    restart clears it.

    It also admits one password check at a time. A check that has passed the
    backoff runs scrypt (about 32 MiB, deliberately slow) before its result is
    recorded, so without the slot a burst of concurrent logins would all pass
    the backoff and hash at once. A login that finds the slot taken is refused
    with a short wait rather than queued, so neither memory nor request threads
    pile up.
    """
    FREE_FAILURES = 5
    MAX_WAIT = 900

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._locked_until = 0.0
        self._checking = threading.Lock()

    def retry_after(self) -> int:
        with self._lock:
            return max(0, int(round(self._locked_until - self._clock())))

    def begin(self) -> int:
        """Take the check slot. 0 means go ahead (call finish() after); otherwise
        the seconds to wait, and nothing is held."""
        if not self._checking.acquire(blocking=False):
            return 1
        wait = self.retry_after()
        if wait:
            self._checking.release()
        return wait

    def finish(self, ok: bool | None) -> None:
        """Record the result (None: no password was checked) and free the slot."""
        try:
            if ok is not None:
                self.record(ok)
        finally:
            self._checking.release()

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self._failures, self._locked_until = 0, 0.0
                return
            self._failures += 1
            extra = self._failures - self.FREE_FAILURES
            if extra > 0:
                self._locked_until = self._clock() + min(2 ** extra, self.MAX_WAIT)


def create_auth_blueprint(db_path: str, throttle: LoginThrottle | None = None) -> Blueprint:
    bp = Blueprint("auth", __name__)
    throttle = throttle or LoginThrottle()

    @bp.post("/auth/login")
    def login():
        password = (request.get_json(silent=True) or {}).get("password")
        if not isinstance(password, str) or not password or len(password) > MAX_PASSWORD_LEN:
            return jsonify({"error": "password required"}), 400
        wait = throttle.begin()
        if wait:
            return (jsonify({"error": f"too many login attempts; try again in {wait}s"}),
                    429, {"Retry-After": str(wait)})
        ok = None
        try:
            stored = core_auth.admin_password_hash(db_path)
            if stored is None:
                return jsonify({"error": "no admin password is set; "
                                         "run: python onboard.py --set-password"}), 503
            ok = core_auth.verify_password(password, stored)
        finally:
            throttle.finish(ok)
        if not ok:
            return jsonify({"error": "wrong password"}), 401
        return jsonify({"ok": True})

    return bp
