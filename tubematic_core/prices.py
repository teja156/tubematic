"""Model prices: where a rate comes from, and how usage units become dollars (TMDEV-107).

**Sources, per model and never per field.** A manual rate typed on Settings
wins; otherwise the synced rate — OpenRouter's /api/v1/models when it lists
the model, LiteLLM's price file only when it does not (today that is the
OpenAI image models); otherwise the built-in snapshot shipped with the release;
otherwise the call is *unpriced*. One model's rates always come from one source:
mixing fields from two feeds would make a wrong figure impossible to trace.

Neither feed is authoritative — both are third parties reading the vendors'
pricing pages. They are what a self-hosted install can read without auth.

**Never fetched at call time.** A render must not depend on GitHub. Rates are
synced weekly by the worker (and by Settings → Sync now) into model_prices.

ElevenLabs is deliberately absent: voice is recorded in plan credits and never
priced, because installs are assumed to be on a subscription that prepays them.
Claude and OpenCode sessions report their own list-price cost and never reach
this table either.

Stdlib only — imported by the MCP server, Flask, the worker and host scripts.
"""
import json
import logging
import pathlib
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SNAPSHOT_PATH = pathlib.Path(__file__).resolve().parent / "prices_snapshot.json"

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
LITELLM_URL = ("https://raw.githubusercontent.com/BerriAI/litellm/main/"
               "model_prices_and_context_window.json")

# Unit kinds a usage event can carry. Counts are tokens, except `credits`
# (ElevenLabs plan credits), which is recorded but never priced.
UNIT_KINDS = ("input", "input_audio", "input_image", "output", "reasoning",
              "output_image", "cache_read", "cache_write", "cache_write_1h")

# Feed field → unit kind. Both feeds quote USD per token.
_OPENROUTER_FIELDS = {
    "prompt": "input",
    "completion": "output",
    "internal_reasoning": "reasoning",
    "audio": "input_audio",
    "image": "input_image",
    "image_output": "output_image",
    "input_cache_read": "cache_read",
    "input_cache_write": "cache_write",
    "input_cache_write_1h": "cache_write_1h",
}
_LITELLM_FIELDS = {
    "input_cost_per_token": "input",
    "output_cost_per_token": "output",
    "output_cost_per_reasoning_token": "reasoning",
    "input_cost_per_audio_token": "input_audio",
    "input_cost_per_image_token": "input_image",
    "output_cost_per_image_token": "output_image",
    "cache_read_input_token_cost": "cache_read",
    "cache_creation_input_token_cost": "cache_write",
    "cache_creation_input_token_cost_above_1hr": "cache_write_1h",
}

# A rate may move at most this factor in one sync. Anything bigger — or a drop
# to zero — is treated as upstream breakage and the old rate is kept.
MAX_SYNC_MOVE = 5.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Name mapping ──────────────────────────────────────────────────────────────

def openrouter_id(service: str, model: str):
    """Our (service, model) → OpenRouter's id, or None for a service it can't price.

    Anthropic ids differ in punctuation: claude-opus-5-5 is anthropic/claude-opus-5.5,
    and a dated snapshot suffix (-20251001) is not part of OpenRouter's id.
    """
    if not model:
        return None
    if service == "gemini":
        return f"google/{model}"
    if service == "openai":
        return f"openai/{model}"
    if service == "anthropic":
        base = re.sub(r"-\d{8}$", "", model)
        return "anthropic/" + re.sub(r"(\d)-(\d)", r"\1.\2", base)
    return None


def litellm_id(service: str, model: str):
    if not model:
        return None
    if service == "gemini":
        return f"gemini/{model}"
    if service in ("openai", "anthropic"):
        return model
    return None


# ── Feed normalisation ────────────────────────────────────────────────────────

def _positive(value):
    """A feed rate as a float, or None. Zero counts as absent: a zero rate would
    price a paid call at $0, which is exactly the silent lie unpriced exists
    to avoid."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def normalize_openrouter(feed: dict) -> dict:
    """OpenRouter's /models body → {openrouter_id: {"rates": {...}, "tiered": bool}}."""
    out = {}
    for m in (feed or {}).get("data") or []:
        mid = m.get("id") or ""
        if not mid or mid.endswith(":batch") or mid.endswith(":free"):
            continue
        pricing = m.get("pricing") or {}
        rates = {}
        for field, kind in _OPENROUTER_FIELDS.items():
            rate = _positive(pricing.get(field))
            if rate is not None:
                rates[kind] = rate
        if rates:
            # `overrides` carries long-prompt tiers (a higher rate once one
            # request passes N prompt tokens). Usage arrives as totals, so the
            # tier that applied is unknowable — base rate, flagged estimated.
            out[mid] = {"rates": rates, "tiered": bool(pricing.get("overrides"))}
    return out


def normalize_litellm(feed: dict) -> dict:
    """LiteLLM's price file → {litellm_id: {"rates": {...}, "tiered": bool}}."""
    out = {}
    for key, entry in (feed or {}).items():
        if not isinstance(entry, dict) or key == "sample_spec":
            continue
        rates = {}
        for field, kind in _LITELLM_FIELDS.items():
            rate = _positive(entry.get(field))
            if rate is not None:
                rates[kind] = rate
        if rates:
            tiered = any("above_" in f and "1hr" not in f for f in entry)
            out[key] = {"rates": rates, "tiered": tiered}
    return out


def resolve_from_feeds(service: str, model: str, openrouter: dict, litellm: dict):
    """The rates for one model under the precedence rule, or None.

    Returns {"rates", "tiered", "source"}. OpenRouter first; LiteLLM only when
    OpenRouter does not list the model at all.
    """
    oid = openrouter_id(service, model)
    if oid and oid in openrouter:
        return {**openrouter[oid], "source": "openrouter"}
    lid = litellm_id(service, model)
    if lid and lid in litellm:
        return {**litellm[lid], "source": "litellm"}
    return None


# ── Snapshot ──────────────────────────────────────────────────────────────────

def _key(service: str, model: str) -> str:
    return f"{service}/{model}"


def load_snapshot() -> dict:
    """The built-in snapshot's models, {"service/model": {"rates","tiered","source"}}."""
    try:
        return json.loads(SNAPSHOT_PATH.read_text()).get("models") or {}
    except (OSError, ValueError):
        log.warning("Price snapshot %s is missing or unreadable", SNAPSHOT_PATH)
        return {}


# ── Lookup and pricing ────────────────────────────────────────────────────────

def lookup_rates(con: sqlite3.Connection, service: str, model: str):
    """The rates to apply to (service, model): manual → synced → snapshot → None.

    Returns {"rates": {kind: usd}, "tiered": bool, "source": str} or None.
    """
    rows = con.execute(
        "SELECT unit_kind, usd_per_unit, source, user_override, tiered FROM model_prices "
        "WHERE service = ? AND model = ?", (service, model)).fetchall()
    manual = [r for r in rows if r[3]]
    chosen = manual or rows
    if chosen:
        return {"rates": {r[0]: r[1] for r in chosen},
                "tiered": any(r[4] for r in chosen),
                "source": chosen[0][2]}
    snap = load_snapshot().get(_key(service, model))
    if snap:
        return {"rates": dict(snap.get("rates") or {}), "tiered": bool(snap.get("tiered")),
                "source": "built-in"}
    return None


def price_units(price: dict, units: dict):
    """Cost of `units` under `price`, or None when any billed unit has no rate.

    Returns (cost_usd, estimated, applied_rates) or None. Missing-rate rules:
    - reasoning without a rate is billed at the output rate — every provider
      bills thinking as output, so this is exact;
    - input_audio / input_image without a rate fall back to the input rate,
      flagged estimated;
    - cache_write_1h without a rate falls back to cache_write, estimated;
    - anything else missing makes the whole call unpriced. A partial sum would
      understate the call invisibly; unpriced is visible and repairable.
    No billable units at all is also None, never $0: a billed response whose
    usage could not be read is recorded with empty units, and pricing that as
    free would understate spend with nothing left to repair it from.
    """
    rates = price.get("rates") or {}
    fallbacks = {"reasoning": ("output", False), "input_audio": ("input", True),
                 "input_image": ("input", True), "cache_write_1h": ("cache_write", True)}
    cost, estimated, applied = 0.0, bool(price.get("tiered")), {}
    for kind, count in (units or {}).items():
        if kind == "credits" or not count:
            continue
        rate = rates.get(kind)
        if rate is None and kind in fallbacks:
            alt, is_estimate = fallbacks[kind]
            rate = rates.get(alt)
            estimated = estimated or (rate is not None and is_estimate)
        if rate is None:
            return None
        applied[kind] = rate
        cost += count * rate
    if not applied:
        return None
    return cost, estimated, applied


def reprice_unpriced(con: sqlite3.Connection, service: str, model: str) -> int:
    """Price this model's unpriced events now that a rate exists. Returns the count.

    Only `unpriced` rows are touched: an event that was priced keeps the price
    it was charged at, whatever the table says now.
    """
    price = lookup_rates(con, service, model)
    if not price:
        return 0
    n = 0
    rows = con.execute("SELECT id, units FROM usage_events WHERE service = ? AND model = ? "
                       "AND cost_basis = 'unpriced'", (service, model)).fetchall()
    for event_id, units_json in rows:
        try:
            units = json.loads(units_json or "{}")
        except ValueError:
            continue
        priced = price_units(price, units)
        if priced is None:
            continue
        cost, estimated, applied = priced
        con.execute(
            "UPDATE usage_events SET cost_usd = ?, cost_basis = 'priced', estimated = ?, "
            "price_snapshot = ? WHERE id = ?",
            (cost, int(estimated), json.dumps({"source": price["source"], "rates": applied,
                                                "repriced_at": _now()}), event_id))
        n += 1
    return n


# ── Manual rates ──────────────────────────────────────────────────────────────

def set_manual_rates(con: sqlite3.Connection, service: str, model: str, rates: dict) -> int:
    """Replace a model's rates with manual ones, then price its unpriced events.

    A manual rate is never touched by a sync. Returns how many events it priced.
    """
    clean = {}
    for kind, value in (rates or {}).items():
        if kind not in UNIT_KINDS:
            raise ValueError(f"unknown unit kind {kind!r}; expected one of {', '.join(UNIT_KINDS)}")
        rate = _positive(value)
        if rate is None:
            raise ValueError(f"rate for {kind!r} must be a positive number, got {value!r}")
        clean[kind] = rate
    if not clean:
        raise ValueError("at least one rate is required")
    now = _now()
    con.execute("DELETE FROM model_prices WHERE service = ? AND model = ?", (service, model))
    con.executemany(
        "INSERT INTO model_prices (service, model, unit_kind, usd_per_unit, source, "
        "effective_from, user_override, tiered) VALUES (?, ?, ?, ?, 'manual', ?, 1, 0)",
        [(service, model, k, v, now) for k, v in clean.items()])
    log.info("Manual price set for %s/%s: %s", service, model, clean)
    return reprice_unpriced(con, service, model)


def clear_manual_rates(con: sqlite3.Connection, service: str, model: str) -> None:
    """Drop a manual override. The model falls back to the snapshot until the next sync."""
    con.execute("DELETE FROM model_prices WHERE service = ? AND model = ? AND user_override = 1",
                (service, model))
    log.info("Manual price cleared for %s/%s", service, model)


# ── Sync ──────────────────────────────────────────────────────────────────────

def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "tubematic-price-sync"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def models_in_use(con: sqlite3.Connection) -> set:
    """(service, model) pairs worth syncing.

    The snapshot's list (every model Tubematic itself can pick), anything that
    has actually been recorded through the table, and the installed Codex
    agent's models. Claude and OpenCode report their own cost and never need a
    table rate, so their models are not synced.
    """
    models = set()
    for key in load_snapshot():
        service, _, model = key.partition("/")
        models.add((service, model))
    for service, model in con.execute(
            "SELECT DISTINCT service, model FROM usage_events "
            "WHERE model != '' AND cost_basis IN ('priced', 'unpriced')"):
        models.add((service, model))
    try:
        row = con.execute("SELECT models FROM agents WHERE id = 'codex' "
                          "AND archived_at IS NULL").fetchone()
        for m in json.loads(row[0]) if row and row[0] else []:
            if isinstance(m, str) and m:
                models.add(("openai", m))
    except (sqlite3.Error, ValueError):
        pass
    return models


def _set_setting(con, key: str, value: str) -> None:
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def _plausible(old: dict, new: dict) -> bool:
    for kind, rate in new.items():
        prev = old.get(kind)
        if prev and (rate / prev > MAX_SYNC_MOVE or prev / rate > MAX_SYNC_MOVE):
            return False
    return True


def sync_prices(con: sqlite3.Connection, fetch=None) -> dict:
    """Refresh synced rates for every model in use. Never raises.

    Rules that make running this unattended safe: only models in use are
    touched; a manual row is never overwritten; a move of more than
    MAX_SYNC_MOVE× is rejected as upstream breakage; every applied change is
    logged with its old and new value; and any failure — either feed down,
    unparseable, anything — keeps every existing price and is recorded in
    `last_price_sync_error` for Settings to show.

    Both feeds are fetched whole, every time. A conditional GET (ETag → 304)
    was considered and rejected: a 304 carries no body, and a newly-used model
    still needs the whole feed to be looked up — and OpenRouter's copy is
    needed even when only LiteLLM changed, to know which source wins.
    """
    fetch = fetch or _fetch_json
    result = {"ok": False, "updated": [], "rejected": [], "missing": [], "error": ""}
    in_savepoint = False
    try:
        openrouter = normalize_openrouter(fetch(OPENROUTER_URL))
        litellm = normalize_litellm(fetch(LITELLM_URL))
        if not openrouter or not litellm:
            raise ValueError("a price feed came back empty")
        # All-or-nothing: a failure part-way through must not leave half the
        # models on new rates. A savepoint works whether or not the caller's
        # connection is in autocommit mode.
        con.execute("SAVEPOINT price_sync")
        in_savepoint = True
        now = _now()
        for service, model in sorted(models_in_use(con)):
            rows = con.execute("SELECT unit_kind, usd_per_unit, source, user_override "
                               "FROM model_prices WHERE service = ? AND model = ?",
                               (service, model)).fetchall()
            if any(r[3] for r in rows):
                continue
            found = resolve_from_feeds(service, model, openrouter, litellm)
            if not found:
                result["missing"].append(f"{service}/{model}")
                continue
            old = {r[0]: r[1] for r in rows}
            old_source = rows[0][2] if rows else ""
            if old == found["rates"] and old_source == found["source"]:
                continue
            if not _plausible(old, found["rates"]):
                log.warning("Price sync rejected %s/%s: %s → %s moves more than %s×; "
                            "keeping the old rates", service, model, old, found["rates"],
                            MAX_SYNC_MOVE)
                result["rejected"].append(f"{service}/{model}")
                continue
            con.execute("DELETE FROM model_prices WHERE service = ? AND model = ?",
                        (service, model))
            con.executemany(
                "INSERT INTO model_prices (service, model, unit_kind, usd_per_unit, source, "
                "effective_from, user_override, tiered) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                [(service, model, k, v, found["source"], now, int(found["tiered"]))
                 for k, v in found["rates"].items()])
            log.info("Price sync updated %s/%s from %s: %s → %s", service, model,
                     found["source"], old or "(none)", found["rates"])
            result["updated"].append(f"{service}/{model}")
            reprice_unpriced(con, service, model)
        if result["missing"]:
            log.info("Price sync: no feed lists %s — calls to them stay unpriced until a "
                     "price is added on Settings → Costs", ", ".join(result["missing"]))
        _set_setting(con, "last_price_sync_ok_at", now)
        _set_setting(con, "last_price_sync_error", "")
        con.execute("RELEASE price_sync")
        in_savepoint = False
        result["ok"] = True
    except Exception as e:  # noqa: BLE001 — a sync must never break its caller
        log.warning("Price sync failed; keeping the existing prices: %s", e)
        result.update(updated=[], rejected=[], missing=[], error=str(e)[:300])
        try:
            if in_savepoint:
                con.execute("ROLLBACK TO price_sync")
                con.execute("RELEASE price_sync")
            _set_setting(con, "last_price_sync_error", result["error"])
        except sqlite3.Error:
            pass
    return result
