"""System Flow (TMDEV-196): the checks a System Flow scene-config must pass
before it is written, so an unattended agent cannot ship an overcrowded or
mistimed diagram.

A System Flow video is one installed `SystemFlow` scene spanning every frame.
The agent writes no code for it: `props.systemFlow` holds boards (one diagram
per subject), each with nodes, edges and events timed to the narration's word
frames. The renderer's side of this contract is
renderer/remotion/src/scenes/installed/systemFlow/contract.ts.

Keep in sync: LIMITS, TIMING, TONES, EVENT_TYPES, wrap_label and compute_rows
mirror contract.ts. mcp/tests/test_system_flow.py reads the TypeScript
constants and runs the shared cases in tests/fixtures/system_flow_contract.json
on both sides, so a drift fails a test instead of a render.

Free of the database and of I/O: the caller passes the style, the config, the
narration's word start frames and the pack's icon list.
"""
from __future__ import annotations

import re

SCENE_SRC = "SystemFlow"
PROPS_KEY = "systemFlow"
STYLE_ID = "system_flow"

LIMITS = {
    "maxBoards": 12,
    "maxNodesPerBoard": 9,
    "maxPerRow": 3,
    "maxRows": 3,
    "labelLineChars": 14,
    "labelLines": 2,
    "chipChars": 24,
    "headlineChars": 40,
    "pillChars": 24,
    "maxStillSeconds": 3.5,
}
TIMING = {
    "nodeIn": 16,
    "edgeDraw": 15,
    "packetTravel": 20,
    "chipHold": 75,
    "boardFade": 6,
    "cameraMove": 30,
    "cameraLead": 26,
    "edgeAfterSource": 8,
    "targetWithin": 30,
}
TONES = ("structure", "relation", "ok", "fault")
EVENT_TYPES = ("node", "edge", "packet", "focus", "chip", "fault")

# A board starts on a word: within this many frames of one word's start.
BOARD_SNAP_FRAMES = 2
# A board shorter than this is a flicker, not a diagram.
MIN_BOARD_SECONDS = 2
_ID = re.compile(r"^[a-z0-9_]{1,24}$")
MAX_ERRORS = 12


def is_system_flow_scene(scene) -> bool:
    return (isinstance(scene, dict) and scene.get("src") == SCENE_SRC
            and scene.get("source") == "installed")


def wrap_label(label: str) -> list[str]:
    """Greedy word wrap at LIMITS['labelLineChars']; a single longer word keeps
    its own line (and is refused by check). Same rule as contract.ts."""
    lines: list[str] = []
    for word in label.split():
        if lines and len(lines[-1]) + 1 + len(word) <= LIMITS["labelLineChars"]:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def compute_rows(node_ids: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Each node's row: 0 when no edge points to it, else one below the lowest
    row among the nodes pointing to it. Same rule as contract.ts; the layout
    pins dagre to these rows, so counting them here counts the frame."""
    preds: dict[str, list[str]] = {n: [] for n in node_ids}
    for a, b in edges:
        if b in preds:
            preds[b].append(a)
    rows: dict[str, int] = {}

    def visit(n: str, depth: int) -> int:
        if n in rows:
            return rows[n]
        if depth > len(node_ids):
            return 0
        ps = preds.get(n, [])
        r = 0 if not ps else max(visit(p, depth + 1) for p in ps) + 1
        rows[n] = r
        return r

    for n in node_ids:
        visit(n, 0)
    return rows


def _has_cycle(node_ids: list[str], edges: list[tuple[str, str]]) -> bool:
    succ: dict[str, list[str]] = {n: [] for n in node_ids}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
    state: dict[str, int] = {}

    def dfs(n: str) -> bool:
        state[n] = 1
        for m in succ.get(n, []):
            if state.get(m) == 1 or (m not in state and dfs(m)):
                return True
        state[n] = 2
        return False

    return any(n not in state and dfs(n) for n in node_ids)


def _connected(node_ids: list[str], edges: list[tuple[str, str]]) -> bool:
    if len(node_ids) <= 1:
        return True
    adj: dict[str, set[str]] = {n: set() for n in node_ids}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, todo = {node_ids[0]}, [node_ids[0]]
    while todo:
        for m in adj[todo.pop()]:
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return len(seen) == len(node_ids)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a System Flow video is exactly the one SystemFlow
    scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes if is_system_flow_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The SystemFlow scene draws a whole System Flow video and is used only when the "
                    "video's visual_style is system_flow (chosen at the topic). Build this video's "
                    "scenes from the other components.")
        return ""
    if len(scenes) != 1 or not uses:
        return ("A System Flow video is exactly one scene: {\"type\": \"generated\", \"source\": "
                "\"installed\", \"src\": \"SystemFlow\", \"startFrame\": 0, \"durationInFrames\": "
                "<totalFrames>, \"props\": {\"systemFlow\": {...}}}. Put every diagram in its boards.")
    return ""


def check(config: dict, fps: int, word_starts: list[int], icons: list[str]) -> list[str]:
    """Every problem with a System Flow config's one scene, as messages that
    name the board, node or event and what to change. [] when it is sound.
    Call after check_scene_use passed for a system_flow video."""
    errs: list[str] = []

    def err(msg: str) -> None:
        if len(errs) < MAX_ERRORS:
            errs.append(msg)

    total = config.get("totalFrames")
    scene = config["scenes"][0]
    if scene.get("startFrame") != 0 or scene.get("durationInFrames") != total:
        err(f"The SystemFlow scene must start at frame 0 and last totalFrames ({total}) frames.")
    flow = (scene.get("props") or {}).get(PROPS_KEY)
    if not isinstance(flow, dict) or not isinstance(flow.get("boards"), list) or not flow["boards"]:
        return errs + ["props.systemFlow.boards must be a non-empty list of boards."]
    boards = flow["boards"]
    if len(boards) > LIMITS["maxBoards"]:
        err(f"{len(boards)} boards; at most {LIMITS['maxBoards']}. Merge subjects that share components.")
    starts = [b.get("startFrame") if isinstance(b, dict) else None for b in boards]
    if not all(_int(s) for s in starts):
        return errs + ["Every board needs a whole-number startFrame."]
    if starts[0] != 0:
        err("The first board must start at frame 0.")
    min_len = int(MIN_BOARD_SECONDS * fps)
    still = int(LIMITS["maxStillSeconds"] * fps)
    for i, board in enumerate(boards):
        start = starts[i]
        end = starts[i + 1] if i + 1 < len(boards) else total
        where = f"Board {i + 1} (frames {start}-{end - 1})"
        if end - start < min_len:
            err(f"{where} is shorter than {MIN_BOARD_SECONDS} s; boards must start in increasing order "
                "and each must hold its diagram long enough to read.")
            continue
        if i > 0 and word_starts and min(abs(start - w) for w in word_starts) > BOARD_SNAP_FRAMES:
            nearest = min(word_starts, key=lambda w: abs(start - w))
            err(f"{where} starts at frame {start}, which is not on a word; cut on a word boundary "
                f"(the nearest word starts at {nearest}).")
        _check_board(board, where, start, end, still, icons, err)
        if len(errs) >= MAX_ERRORS:
            break
    return errs


def _check_board(board: dict, where: str, start: int, end: int, still: int, icons: list[str], err) -> None:
    headline = board.get("headline")
    if not isinstance(headline, str) or not headline.strip():
        err(f"{where}: headline must be a short phrase (at most {LIMITS['headlineChars']} characters).")
    elif len(headline.strip()) > LIMITS["headlineChars"]:
        err(f"{where}: headline is {len(headline.strip())} characters; at most {LIMITS['headlineChars']}.")
    pill = board.get("pill")
    if pill is not None and (not isinstance(pill, str) or not pill.strip() or len(pill) > LIMITS["pillChars"]):
        err(f"{where}: pill, when present, must be at most {LIMITS['pillChars']} characters.")

    nodes = board.get("nodes")
    edges = board.get("edges")
    events = board.get("events")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list) or not isinstance(events, list):
        err(f"{where}: nodes (non-empty), edges and events must all be lists.")
        return
    if len(nodes) > LIMITS["maxNodesPerBoard"]:
        err(f"{where} has {len(nodes)} nodes; at most {LIMITS['maxNodesPerBoard']}. Split it into two boards.")
    ids: list[str] = []
    for n in nodes:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not _ID.match(nid):
            err(f"{where}: node id {nid!r} must be 1-24 lowercase letters, digits or underscores.")
            continue
        if nid in ids:
            err(f"{where}: node id {nid!r} is used twice.")
            continue
        ids.append(nid)
        label = n.get("label")
        if not isinstance(label, str) or not label.strip():
            err(f"{where}: node {nid!r} needs a label.")
        else:
            lines = wrap_label(label)
            if len(lines) > LIMITS["labelLines"] or any(len(l) > LIMITS["labelLineChars"] for l in lines):
                err(f"{where}: node {nid!r} label {label!r} does not fit {LIMITS['labelLines']} lines of "
                    f"{LIMITS['labelLineChars']} characters; shorten it.")
        if n.get("icon") not in icons:
            err(f"{where}: node {nid!r} icon {n.get('icon')!r} is not one of {sorted(icons)}.")

    pairs: list[tuple[str, str]] = []
    for e in edges:
        a, b = (e.get("from"), e.get("to")) if isinstance(e, dict) else (None, None)
        if a not in ids or b not in ids:
            err(f"{where}: edge {a!r}>{b!r} must join two of this board's nodes.")
            continue
        if a == b or (a, b) in pairs:
            err(f"{where}: edge {a}>{b} is a loop or a duplicate.")
            continue
        pairs.append((a, b))
    if _has_cycle(ids, pairs):
        err(f"{where}: the edges form a cycle. Draw each connection once, in the direction things first "
            "travel; a reply travels back over the same edge as a packet with \"reverse\": true.")
        return
    if not _connected(ids, pairs):
        err(f"{where}: every node must be connected to the diagram; put unrelated components on their own board.")
    rows = compute_rows(ids, pairs)
    if rows:
        n_rows = max(rows.values()) + 1
        if n_rows > LIMITS["maxRows"]:
            err(f"{where}: the diagram is {n_rows} rows deep (a chain of {n_rows} nodes); at most "
                f"{LIMITS['maxRows']}. Split the chain across boards.")
        for r in range(n_rows):
            in_row = [n for n in ids if rows[n] == r]
            if len(in_row) > LIMITS["maxPerRow"]:
                err(f"{where}: row {r + 1} holds {len(in_row)} nodes ({', '.join(in_row)}); at most "
                    f"{LIMITS['maxPerRow']} side by side.")

    edge_ids = {f"{a}>{b}" for a, b in pairs}
    node_at: dict[str, int] = {}
    edge_at: dict[str, int] = {}
    change_points = [start]
    typed: list[dict] = []
    for k, ev in enumerate(events):
        if not isinstance(ev, dict) or ev.get("type") not in EVENT_TYPES:
            err(f"{where}: event {k + 1} needs a type, one of {list(EVENT_TYPES)}.")
            continue
        at = ev.get("at")
        if not _int(at) or not start <= at < end:
            err(f"{where}: {ev['type']} event {k + 1} at {at!r} must be a frame inside the board ({start}-{end - 1}).")
            continue
        change_points.append(at)
        typed.append(ev)
        if ev["type"] == "node":
            if ev.get("node") not in ids:
                err(f"{where}: node event at {at} names {ev.get('node')!r}, which is not a node of this board.")
            elif ev["node"] in node_at:
                err(f"{where}: node {ev['node']!r} enters twice; one node event per node.")
            else:
                node_at[ev["node"]] = at
        elif ev["type"] == "edge":
            if ev.get("edge") not in edge_ids:
                err(f"{where}: edge event at {at} names {ev.get('edge')!r}; edges are named \"from>to\".")
            elif ev["edge"] in edge_at:
                err(f"{where}: edge {ev['edge']!r} draws twice; one edge event per edge.")
            else:
                edge_at[ev["edge"]] = at
    for n in ids:
        if n not in node_at:
            err(f"{where}: node {n!r} never enters; give it a node event.")
    for e in edge_ids:
        if e not in edge_at:
            err(f"{where}: edge {e!r} is never drawn; give it an edge event.")

    for ev in typed:
        at, kind = ev["at"], ev["type"]
        if kind == "edge" and ev.get("edge") in edge_at:
            a, b = ev["edge"].split(">")
            if a in node_at and at < node_at[a] + TIMING["edgeAfterSource"]:
                err(f"{where}: edge {ev['edge']} draws at {at}, before {a!r} has landed "
                    f"(at {node_at[a]}); draw it from {node_at[a] + TIMING['edgeAfterSource']} on.")
            if b in node_at and node_at[b] > at + TIMING["targetWithin"]:
                err(f"{where}: edge {ev['edge']} draws at {at} but {b!r} enters only at {node_at[b]}; "
                    f"bring {b!r} in by {at + TIMING['targetWithin']} so the arrow does not point at nothing.")
        elif kind in ("packet", "chip"):
            e = ev.get("edge")
            if e not in edge_ids:
                err(f"{where}: {kind} at {at} names edge {e!r}; edges are named \"from>to\".")
                continue
            if e in edge_at and at < edge_at[e] + TIMING["edgeDraw"]:
                err(f"{where}: {kind} on {e} at {at} comes before the edge has finished drawing "
                    f"(from {edge_at[e] + TIMING['edgeDraw']} on).")
            if ev.get("tone", "structure") not in TONES:
                err(f"{where}: {kind} at {at} tone {ev.get('tone')!r} must be one of {list(TONES)}.")
            if kind == "packet":
                if "reverse" in ev and not isinstance(ev["reverse"], bool):
                    err(f"{where}: packet at {at}: reverse must be true or false.")
                if at + TIMING["packetTravel"] > end:
                    err(f"{where}: packet on {e} at {at} would still be travelling when the board ends at {end}.")
            else:
                text = ev.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["chipChars"]:
                    err(f"{where}: chip at {at} text must be 1-{LIMITS['chipChars']} characters (a value, "
                        "a status, a port).")
        elif kind in ("focus", "fault"):
            nid = ev.get("node")
            if nid not in ids:
                err(f"{where}: {kind} at {at} names {nid!r}, which is not a node of this board.")
            elif nid in node_at and at < node_at[nid]:
                err(f"{where}: {kind} on {nid!r} at {at} comes before it enters (at {node_at[nid]}).")

    change_points.append(end)
    change_points.sort()
    for a, b in zip(change_points, change_points[1:]):
        if b - a > still:
            err(f"{where}: nothing changes on screen from frame {a} to {b} ({(b - a)} frames); add a "
                f"packet, focus or chip at least every {LIMITS['maxStillSeconds']} s so the picture never stalls.")
            break


def board_windows(config: dict) -> list[tuple[int, int]]:
    """(start, end) of each board in a System Flow config, for the text audit:
    one whole-video scene would otherwise be sampled as a single scene."""
    try:
        scene = config["scenes"][0]
        boards = scene["props"][PROPS_KEY]["boards"]
        total = config["totalFrames"]
        starts = [b["startFrame"] for b in boards]
    except (KeyError, IndexError, TypeError):
        return []
    return [(s, starts[i + 1] if i + 1 < len(starts) else total) for i, s in enumerate(starts)]
