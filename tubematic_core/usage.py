"""Per-call usage recording and the read-side cost summaries (TMDEV-107).

Every paid call records one usage_events row as soon as the provider's
response exists — on the success path and on every failure after it, because
a response that failed to parse was still billed. The row keeps the units the
provider reported, its raw usage object, and the price applied at the time.

How a row is costed (`cost_basis`):
- `credits`  — ElevenLabs. Units are plan credits (the `character-cost`
               header); no dollar figure, because installs are assumed to be
               on a subscription that prepays them.
- `reported` — Claude and OpenCode sessions, which report their own list-price
               cost. Recorded as given.
- `priced`   — units × rates from tubematic_core.prices, snapshotted onto the row.
- `unpriced` — no rate known. cost_usd stays NULL, never 0, and the event is
               counted and shown; adding a price later fills it in.

All costs are API list prices and ignore subscriptions, plan credits and
discounts — the UI says so wherever it shows one.

`record_usage` NEVER raises: recording is bookkeeping and must not fail a
video. It is also never silent — every failure is logged, so a broken ledger
cannot go unnoticed the way unwritable poll logs once did.

Stdlib only.
"""
import json
import logging
import sqlite3
import threading

from tubematic_core import db as tdb
from tubematic_core import prices

log = logging.getLogger(__name__)

AGENT_OPERATIONS = ("agent_pipeline", "agent_research", "agent_profile", "agent_unscoped")
RESEARCH_OPERATIONS = ("agent_research", "mining")

# Log an unpriced model once per process, not once per call.
_warned_unpriced = set()
_warned_lock = threading.Lock()


def _warn_unpriced_once(service: str, model: str) -> None:
    with _warned_lock:
        if (service, model) in _warned_unpriced:
            return
        _warned_unpriced.add((service, model))
    log.warning("No price known for %s model %r — its calls are recorded as unpriced. "
                "Add a price on Settings → Costs to fill them in.", service, model or "(unknown)")


def _video_links(videos):
    """Normalise `videos` to [(video_id, stage)] — accepts ids, (id, stage) or dicts."""
    out, seen = [], set()
    for v in videos or ():
        if isinstance(v, dict):
            vid, stage = v.get("video_id"), v.get("stage")
        elif isinstance(v, (tuple, list)):
            vid, stage = (v[0], v[1] if len(v) > 1 else None)
        else:
            vid, stage = v, None
        if vid and vid not in seen:
            seen.add(vid)
            out.append((str(vid), stage or None))
    return out


def record_usage(db_path, *, service: str, model: str = "", operation: str,
                 units: dict = None, raw=None, request_id: str = None, videos=(),
                 session_id: str = None, reported_cost_usd: float = None,
                 estimated: bool = False, event_key: str = None):
    """Append one usage event. Returns its id, or None if recording failed.

    `videos` is the video(s) the call was for: an id, (id, stage) pairs, or
    {"video_id", "stage"} dicts. Empty for calls that belong to no video.

    `event_key` makes the write idempotent: an event already recorded under
    the same key is not recorded again, and its existing id is returned.
    """
    try:
        units = {k: v for k, v in (units or {}).items() if v}
        request_id = request_id if isinstance(request_id, str) else None
        con = tdb.connect(db_path)
        try:
            con.execute("BEGIN IMMEDIATE")
            if event_key:
                existing = con.execute("SELECT id FROM usage_events WHERE event_key = ?",
                                       (event_key,)).fetchone()
                if existing:
                    con.execute("COMMIT")
                    return existing[0]
            cost, basis, snapshot = None, "unpriced", None
            if service == "elevenlabs":
                basis = "credits"
            elif reported_cost_usd is not None:
                cost, basis = float(reported_cost_usd), "reported"
            else:
                price = prices.lookup_rates(con, service, model)
                priced = prices.price_units(price, units) if price else None
                if priced is None and not units:
                    log.warning("%s %s call for %s/%s reported no usage — recorded as unpriced",
                                service, operation, service, model or "(unknown)")
                elif priced is None:
                    _warn_unpriced_once(service, model)
                else:
                    cost, was_estimate, applied = priced
                    basis = "priced"
                    estimated = estimated or was_estimate
                    snapshot = json.dumps({"source": price["source"], "rates": applied})
            cur = con.execute(
                "INSERT INTO usage_events (created_at, session_id, service, model, operation, "
                "units, raw_usage, request_id, cost_usd, cost_basis, price_snapshot, estimated, "
                "event_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tdb._now(), session_id, service, model or "", operation, json.dumps(units),
                 json.dumps(raw) if raw is not None else None, request_id, cost, basis,
                 snapshot, int(bool(estimated)), event_key or None))
            event_id = cur.lastrowid
            con.executemany(
                "INSERT OR IGNORE INTO usage_event_videos (event_id, video_id, stage) "
                "VALUES (?, ?, ?)",
                [(event_id, vid, stage) for vid, stage in _video_links(videos)])
            con.execute("COMMIT")
            return event_id
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — bookkeeping must never fail the call it records
        log.exception("Could not record %s usage for %s/%s (videos=%s)", operation, service,
                      model, [v for v, _ in _video_links(videos)])
        return None


# ── Units from provider usage objects ─────────────────────────────────────────

def _modality_counts(details) -> dict:
    out = {}
    for d in details or []:
        if isinstance(d, dict):
            mod = str(d.get("modality") or "").upper()
            out[mod] = out.get(mod, 0) + int(d.get("tokenCount") or 0)
    return out


def gemini_units(usage_metadata) -> dict:
    """Gemini `usageMetadata` → unit counts.

    Text, video and document input bill at the input rate; image and audio
    input have their own rates. Cached tokens are part of the prompt count and
    are split out into cache_read. Thinking tokens are `reasoning`. Image
    output (the image models) is `output_image`.
    """
    um = usage_metadata if isinstance(usage_metadata, dict) else {}
    units = {"input": 0, "input_audio": 0, "input_image": 0}
    prompt = _modality_counts(um.get("promptTokensDetails"))
    cached = _modality_counts(um.get("cacheTokensDetails"))
    if prompt:
        for mod, n in prompt.items():
            n -= cached.get(mod, 0)
            kind = {"AUDIO": "input_audio", "IMAGE": "input_image"}.get(mod, "input")
            units[kind] += max(n, 0)
        units["cache_read"] = sum(cached.values()) or int(um.get("cachedContentTokenCount") or 0)
        if not cached and units["cache_read"]:
            units["input"] = max(units["input"] - units["cache_read"], 0)
    else:
        cache_read = int(um.get("cachedContentTokenCount") or 0)
        units["input"] = max(int(um.get("promptTokenCount") or 0) - cache_read, 0)
        units["cache_read"] = cache_read
    units["input"] += int(um.get("toolUsePromptTokenCount") or 0)
    out_details = _modality_counts(um.get("candidatesTokensDetails"))
    if out_details:
        units["output_image"] = out_details.get("IMAGE", 0)
        units["output"] = sum(n for m, n in out_details.items() if m != "IMAGE")
    else:
        units["output"] = int(um.get("candidatesTokenCount") or 0)
    units["reasoning"] = int(um.get("thoughtsTokenCount") or 0)
    return {k: v for k, v in units.items() if v}


def openai_image_units(usage) -> dict:
    """OpenAI Images API `usage` → unit counts.

    Input splits into text and image tokens (the reference image of an edit);
    output is image tokens. Without an output split, all output is image.
    """
    u = usage if isinstance(usage, dict) else {}
    units = {}
    in_details = u.get("input_tokens_details") or {}
    if in_details:
        units["input"] = int(in_details.get("text_tokens") or 0)
        units["input_image"] = int(in_details.get("image_tokens") or 0)
    else:
        units["input"] = int(u.get("input_tokens") or 0)
    out_details = u.get("output_tokens_details") or {}
    if out_details:
        units["output_image"] = int(out_details.get("image_tokens") or 0)
        units["output"] = int(out_details.get("text_tokens") or 0)
    else:
        units["output_image"] = int(u.get("output_tokens") or 0)
    return {k: v for k, v in units.items() if v}


# ── Read side ─────────────────────────────────────────────────────────────────

def _rows(con, sql, args=()):
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return cur.execute(sql, args).fetchall()


def video_costs(con: sqlite3.Connection, video_id: str) -> dict:
    """Everything the video modal's cost section shows, for one video.

    Non-agent calls are grouped per (service, model, operation). An agent
    session covers one video since the poller runs one session per video and
    stage (TMDEV-129); one recorded before that could cover a batch, and is
    split evenly across the videos it was for. `share_usd` is this video's part
    and `session_total_usd` the whole session.
    `total_usd` adds the non-agent costs and the agent share — never whole
    sessions, which would count one session once per video.
    """
    events = _rows(con,
        "SELECT e.*, l.stage, (SELECT COUNT(*) FROM usage_event_videos x "
        "WHERE x.event_id = e.id) AS batch_size FROM usage_events e "
        "JOIN usage_event_videos l ON l.event_id = e.id WHERE l.video_id = ? "
        "ORDER BY e.created_at, e.id", (video_id,))
    lines, sessions = {}, {}
    total, unpriced, credits = 0.0, 0, 0
    for e in events:
        units = json.loads(e["units"] or "{}")
        if e["operation"] in AGENT_OPERATIONS:
            key = e["session_id"] or f"event-{e['id']}"
            s = sessions.setdefault(key, {
                "session_id": key, "created_at": e["created_at"], "stage": e["stage"],
                "operation": e["operation"], "batch_size": e["batch_size"] or 1,
                "models": [], "total_usd": 0.0, "share_usd": 0.0, "unpriced": False,
                "estimated": False})
            s["models"].append(e["model"])
            if e["cost_usd"] is None:
                s["unpriced"] = True
                unpriced += 1
            else:
                s["total_usd"] += e["cost_usd"]
                s["share_usd"] += e["cost_usd"] / (e["batch_size"] or 1)
            s["estimated"] = s["estimated"] or bool(e["estimated"])
            continue
        key = (e["service"], e["model"], e["operation"])
        line = lines.setdefault(key, {
            "service": e["service"], "model": e["model"], "operation": e["operation"],
            "calls": 0, "cost_usd": None, "credits": 0, "unpriced_calls": 0,
            "estimated": False})
        line["calls"] += 1
        line["credits"] += int(units.get("credits") or 0)
        credits += int(units.get("credits") or 0)
        line["estimated"] = line["estimated"] or bool(e["estimated"])
        if e["cost_basis"] == "unpriced":
            line["unpriced_calls"] += 1
            unpriced += 1
        elif e["cost_usd"] is not None:
            line["cost_usd"] = (line["cost_usd"] or 0.0) + e["cost_usd"]
            total += e["cost_usd"]
    agent = None
    if sessions:
        rows = list(sessions.values())
        share = sum(s["share_usd"] for s in rows)
        models = sorted({m for s in rows for m in s["models"] if m})
        agent = {
            "models": models,
            "share_usd": share,
            "session_total_usd": sum(s["total_usd"] for s in rows),
            "sessions": rows,
            "shared": any(s["batch_size"] > 1 for s in rows),
            "estimated": any(s["estimated"] for s in rows),
        }
        total += share
    return {
        "has_usage": bool(events),
        "lines": list(lines.values()),
        "agent": agent,
        "total_usd": total,
        "credits": credits,
        "unpriced_calls": unpriced,
    }


def last_voice_model(con: sqlite3.Connection, video_id: str) -> str | None:
    """The ElevenLabs model this video's most recent voicing call was sent with,
    or None when the ledger holds none (never voiced, or voiced before the
    ledger existed). Read for the video modal (TMDEV-147): the video row keeps
    only voice_id, and a roster voice's model can be edited after voicing, so
    the ledger is the only record of the model the audio was made with."""
    row = con.execute(
        "SELECT e.model FROM usage_events e "
        "JOIN usage_event_videos l ON l.event_id = e.id "
        "WHERE l.video_id = ? AND e.service = 'elevenlabs' AND e.operation = 'voice' "
        "ORDER BY e.created_at DESC, e.id DESC LIMIT 1", (video_id,)).fetchone()
    return row[0] if row else None


def spend_summary(con: sqlite3.Connection, since: str, until: str = None) -> dict:
    """Spend in [since, until) — ISO timestamps, `until` open-ended when None —
    split the way the Analytics page's Spend tab shows it.

    `videos` is every call tied to at least one video (agent sessions in full,
    since across all videos their shares add back up to the session). The rest
    is split into research & mining and other agent sessions (script profiles,
    and the unscoped fallback run). Voice is plan credits, not dollars.
    """
    # Exclusive upper bound: an event exactly at `until` belongs to the next
    # range, so two adjacent ranges never count it twice.
    window, args = "e.created_at >= ?", (since,)
    if until is not None:
        window, args = window + " AND e.created_at < ?", (since, until)
    rows = _rows(con,
        "SELECT e.operation, e.service, e.cost_usd, e.cost_basis, e.estimated, e.units, "
        "EXISTS(SELECT 1 FROM usage_event_videos l WHERE l.event_id = e.id) AS has_video "
        f"FROM usage_events e WHERE {window}", args)
    buckets = {"videos": 0.0, "research": 0.0, "agent_other": 0.0, "other": 0.0}
    out = {"since": since, "until": until, "total_usd": 0.0, "unpriced_calls": 0, "estimated": False,
           "voice_credits": 0, "preview_credits": 0}
    for r in rows:
        if r["service"] == "elevenlabs":
            n = int(json.loads(r["units"] or "{}").get("credits") or 0)
            out["preview_credits" if r["operation"] == "voice_preview" else "voice_credits"] += n
            continue
        if r["cost_basis"] == "unpriced":
            out["unpriced_calls"] += 1
            continue
        cost = r["cost_usd"] or 0.0
        out["estimated"] = out["estimated"] or bool(r["estimated"])
        if r["has_video"]:
            buckets["videos"] += cost
        elif r["operation"] in RESEARCH_OPERATIONS:
            buckets["research"] += cost
        elif r["operation"] in AGENT_OPERATIONS:
            buckets["agent_other"] += cost
        else:
            buckets["other"] += cost
        out["total_usd"] += cost
    out.update(buckets)
    out["video_count"] = con.execute(
        "SELECT COUNT(DISTINCT l.video_id) FROM usage_event_videos l "
        f"JOIN usage_events e ON e.id = l.event_id WHERE {window}",
        args).fetchone()[0]
    return out
