/*
 * SystemFlow: a System Flow insert (TMDEV-224), or the whole of a System
 * Flow video made before System Flow became an insert style.
 *
 * A diagram builds node by node on a dark canvas while points of light travel
 * its connectors, one board per subject, with a camera that keeps what is
 * visible in the diagram band. The agent never writes this file's kind of
 * code: it writes `props.systemFlow` (boards, nodes, edges and events timed to
 * the narration), which the MCP server validates against the rules in
 * ./systemFlow/contract.ts before the video can render.
 *
 * Cheap on the CPU on purpose, and every rule here was measured: no SVG
 * filters (a blur or drop-shadow over a large area made sample renders 10 to
 * 100 times slower), no CSS gradients (a full-frame radial-gradient background
 * alone more than doubled this scene's cost in software GL), glows are a few
 * stacked translucent circles, the camera is an SVG transform attribute (a
 * CSS-transformed layer is re-composited every frame), and layout runs once
 * per board, never per frame. Labels are HTML so the text-layout audit can
 * measure them, placed in screen coordinates at camera-scaled sizes.
 *
 * Fonts are bundled in public/fonts and loaded before the first frame, so a
 * renderer with no internet access renders the same picture.
 */
import React, { useEffect, useMemo, useState } from "react";
import { AbsoluteFill, Easing, continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";
import { ICONS } from "./systemFlow/icons";
import { LIMITS, TIMING, type SFBoard, type SFEvent, type SystemFlowData, type Tone } from "./systemFlow/contract";
import { BOX_H, BOX_W, LABEL_GAP, LABEL_LINE, LABEL_PX, SLOT_W, layoutBoard, pointAlong, type BoardLayout } from "./systemFlow/layout";
import { CHIP_PX, H, W, boardKeys, cameraAt, chipLeft, svgTransform, toScreen, type Cam } from "./systemFlow/camera";

// ── look (tokens from the style card) ─────────────────────────────────────────
// "dark" is the style's own look. "light" is the same diagram on paper, used
// when System Flow is an insert inside a light-canvas main style (TMDEV-224):
// an insert follows its main style's canvas, so a light video never cuts to
// black and its dark captions stay readable over the insert.
type Look = {
  bg: string; blob: string; cyan: string; cyanDim: string; ink: string; boxFill: string; chipBg: string;
  tone: Record<Tone, string>;
};
const LOOKS: Record<"dark" | "light", Look> = {
  dark: {
    bg: "#242724", blob: "#202321", cyan: "#3fb8c8", cyanDim: "#386c6d", ink: "#EAFBFF", boxFill: "#2a2e2b",
    chipBg: "#1a1d1b", tone: { structure: "#3fb8c8", relation: "#8B6CFF", ok: "#B8FF5A", fault: "#EC081F" },
  },
  light: {
    bg: "#f5f4ef", blob: "#ecebe4", cyan: "#0b7f8f", cyanDim: "#a9cdd1", ink: "#15211f", boxFill: "#ffffff",
    chipBg: "#ffffff", tone: { structure: "#0b7f8f", relation: "#5b3fd6", ok: "#3a7d0c", fault: "#cf0a1d" },
  },
};
const DIM = 0.35;

const SANS = "Barlow, system-ui, sans-serif";
const HEAD = "'Space Grotesk', Barlow, system-ui, sans-serif";
const MONO = "'JetBrains Mono', ui-monospace, monospace";

// ── fonts ─────────────────────────────────────────────────────────────────────
const FONTS: [family: string, file: string, weight: string][] = [
  ["Barlow", "fonts/barlow-latin-600-normal.woff2", "600"],
  ["Barlow", "fonts/barlow-latin-700-normal.woff2", "700"],
  ["Space Grotesk", "fonts/space-grotesk-latin-700-normal.woff2", "700"],
  ["JetBrains Mono", "fonts/jetbrains-mono-latin-500-normal.woff2", "500"],
];
let fontsLoaded: Promise<void> | null = null;
function loadFonts(): Promise<void> {
  if (!fontsLoaded) {
    fontsLoaded = Promise.all(
      FONTS.map(([family, file, weight]) =>
        new FontFace(family, `url(${staticFile(file)}) format("woff2")`, { weight })
          .load()
          .then((face) => {
            document.fonts.add(face);
          }),
      ),
    ).then(() => undefined);
  }
  return fontsLoaded;
}

const easeOutExpo = Easing.bezier(0.16, 1, 0.3, 1);
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const ramp = (frame: number, from: number, dur: number) => clamp01((frame - from) / dur);

// ── per-board state at a frame ───────────────────────────────────────────────
type Prepared = { board: SFBoard; layout: BoardLayout; keys: ReturnType<typeof boardKeys>; end: number };

function eventsOf<T extends SFEvent["type"]>(board: SFBoard, type: T): Extract<SFEvent, { type: T }>[] {
  return board.events.filter((e): e is Extract<SFEvent, { type: T }> => e.type === type);
}

/** The node a focus event made active at `frame`, or null. */
function activeNode(board: SFBoard, frame: number): string | null {
  let best: { at: number; node: string } | null = null;
  for (const e of eventsOf(board, "focus")) if (e.at <= frame && (!best || e.at >= best.at)) best = e;
  return best?.node ?? null;
}

const Icon: React.FC<{ name: string; x: number; y: number; size: number; color: string }> = ({ name, x, y, size, color }) => {
  const els = ICONS[name] ?? ICONS.server;
  const k = size / 24;
  return (
    <g transform={`translate(${x - size / 2} ${y - size / 2}) scale(${k})`} fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      {els.map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs }))}
    </g>
  );
};

/** A soft glow from stacked translucent circles: solid fills are cheap to paint,
 *  a radial gradient is not. Used for packet heads. */
const Glow: React.FC<{ x: number; y: number; r: number; color: string; opacity: number }> = ({ x, y, r, color, opacity }) =>
  opacity <= 0 ? null : (
    <g opacity={opacity}>
      {[1, 0.8, 0.62, 0.46, 0.32].map((k, i) => (
        <circle key={i} cx={x} cy={y} r={r * k} fill={color} opacity={0.08} />
      ))}
    </g>
  );

/** The bloom on the active box: translucent outlines stepping outward, about
 *  20 px on screen, the card's "one 18-24 px bloom". */
const Halo: React.FC<{ x: number; top: number; color: string; opacity: number }> = ({ x, top, color, opacity }) =>
  opacity <= 0 ? null : (
    <g opacity={opacity} fill="none" stroke={color}>
      {[6, 12, 18, 24].map((g, i) => (
        <rect key={i} x={x - BOX_W / 2 - g} y={top - g} width={BOX_W + 2 * g} height={BOX_H + 2 * g} rx={10 + g} strokeWidth={6} opacity={0.22 - i * 0.05} />
      ))}
    </g>
  );

// ── one board ─────────────────────────────────────────────────────────────────
const Board: React.FC<{ p: Prepared; frame: number; look: Look }> = ({ p, frame, look }) => {
  const { board, layout } = p;
  const enter: Record<string, number> = {};
  for (const e of eventsOf(board, "node")) enter[e.node] = e.at;
  const drawAt: Record<string, number> = {};
  for (const e of eventsOf(board, "edge")) drawAt[e.edge] = e.at;
  const faultAt: Record<string, number> = {};
  for (const e of eventsOf(board, "fault")) faultAt[e.node] = e.at;
  const active = activeNode(board, frame);
  const packets = eventsOf(board, "packet");
  // A node lights up for a moment when a packet arrives at it.
  const arrivals: Record<string, number> = {};
  for (const pk of packets) {
    const e = layout.edges[pk.edge];
    if (!e) continue;
    const target = pk.reverse ? e.from : e.to;
    const arrive = pk.at + TIMING.packetTravel;
    if (arrive <= frame && (arrivals[target] === undefined || arrive > arrivals[target])) arrivals[target] = arrive;
  }
  const lit = (id: string) => active === null || active === id;
  const edgeLit = (from: string, to: string) => active === null || active === from || active === to;
  const cam = cameraAt(p.keys, frame);
  // A slow drift so a held picture is never frozen.
  const drift = 1 + 0.012 * ramp(frame, board.startFrame, Math.max(1, p.end - board.startFrame));
  const chips = eventsOf(board, "chip");
  const nextChip = (i: number) => chips.filter((c) => c.at > chips[i].at).reduce((m, c) => Math.min(m, c.at), Infinity);

  const c: Cam = { ...cam, s: cam.s * drift };

  return (
    <AbsoluteFill>
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        <g transform={svgTransform(c)}>
        {/* the one bloom: around the active node */}
        {active && layout.nodes[active] && (enter[active] ?? Infinity) <= frame && (
          <Halo x={layout.nodes[active].x} top={layout.nodes[active].boxTop} color={(faultAt[active] ?? Infinity) <= frame ? look.tone.fault : look.cyan} opacity={ramp(frame, activeFocusAt(board, active, frame), 10)} />
        )}

        {/* connectors */}
        {Object.values(layout.edges).map((e) => {
          const t0 = drawAt[e.id];
          if (t0 === undefined || frame < t0) return null;
          const d = easeOutExpo(ramp(frame, t0, TIMING.edgeDraw));
          const end = pointAlong(e.points, 1);
          const color = edgeLit(e.from, e.to) ? look.cyan : look.cyanDim;
          return (
            <g key={e.id} opacity={edgeLit(e.from, e.to) ? 1 : DIM}>
              {/* Dots as circles: a stroke-dasharray made this scene 2.5 times
                  slower to render in software GL. */}
              {e.dots.slice(0, Math.ceil(d * e.dots.length)).map((pt, k) => (
                <circle key={k} cx={pt.x} cy={pt.y} r={2.6} fill={color} />
              ))}
              {d >= 1 && (
                <path
                  d="M -18 -11 L 0 0 L -18 11"
                  fill="none"
                  stroke={color}
                  strokeWidth={5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  transform={`translate(${end.p.x} ${end.p.y}) rotate(${(end.angle * 180) / Math.PI})`}
                />
              )}
            </g>
          );
        })}

        {/* node boxes and icons */}
        {Object.values(layout.nodes).map((n) => {
          const t0 = enter[n.id];
          if (t0 === undefined) return null;
          // A node entering in the video's first frames opens it: it is drawn
          // from frame 0, half grown, so the first frame shows it still moving.
          const tIn = t0 <= TIMING.openWithin ? 0 : t0;
          if (frame < tIn) return null;
          const pIn = ramp(frame, tIn === 0 ? -TIMING.nodeIn / 2 : tIn, TIMING.nodeIn);
          const sc = 0.8 + 0.2 * easeOutExpo(pIn);
          const faulted = (faultAt[n.id] ?? Infinity) <= frame;
          const shake = faulted ? Math.sin((frame - faultAt[n.id]) * 2.2) * 6 * (1 - ramp(frame, faultAt[n.id], 10)) : 0;
          const flash = arrivals[n.id] !== undefined ? 1 - ramp(frame, arrivals[n.id], 14) : 0;
          const stroke = faulted ? look.tone.fault : look.cyan;
          const cy = n.boxTop + BOX_H / 2;
          return (
            <g key={n.id} opacity={pIn * (lit(n.id) ? 1 : DIM)} transform={`translate(${n.x + shake} ${cy}) scale(${sc}) translate(${-n.x} ${-cy})`}>
              <Halo x={n.x} top={n.boxTop} color={look.cyan} opacity={flash} />
              <rect x={n.x - BOX_W / 2} y={n.boxTop} width={BOX_W} height={BOX_H} rx={10} fill={look.boxFill} stroke={stroke} strokeWidth={3 + 2 * flash} />
              <Icon name={board.nodes.find((x) => x.id === n.id)?.icon ?? "server"} x={n.x} y={cy} size={72} color={faulted ? look.tone.fault : look.cyan} />
            </g>
          );
        })}

        {/* packets: a lit head with a short trail */}
        {packets.map((pk, i) => {
          const e = layout.edges[pk.edge];
          if (!e) return null;
          const q = (frame - pk.at) / TIMING.packetTravel;
          if (q < 0 || q > 1) return null;
          const color = look.tone[pk.tone ?? "structure"];
          const along = (v: number) => pointAlong(e.points, pk.reverse ? 1 - v : v).p;
          const head = along(Easing.inOut(Easing.quad)(q));
          return (
            <g key={`pk-${i}`}>
              {[0.16, 0.12, 0.08, 0.04].map((lag, k) => {
                const v = q - lag;
                if (v < 0) return null;
                const pt = along(Easing.inOut(Easing.quad)(v));
                return <circle key={k} cx={pt.x} cy={pt.y} r={7 + k * 1.5} fill={color} opacity={0.12 + 0.12 * k} />;
              })}
              <Glow x={head.x} y={head.y} r={46} color={color} opacity={1} />
              <circle cx={head.x} cy={head.y} r={13} fill={color} />
            </g>
          );
        })}
        </g>
      </svg>

      {/* labels (HTML, so the text audit measures them) */}
      {Object.values(layout.nodes).map((n) => {
        const t0 = enter[n.id];
        if (t0 === undefined || frame < t0) return null;
        // Type on at about 15 characters a second, starting as the box lands.
        let budget = Math.floor(Math.max(0, frame - t0 - TIMING.labelTypeDelay) / TIMING.labelTypeFrames);
        return (
          <div
            key={`l-${n.id}`}
            style={{
              position: "absolute",
              left: toScreen(c, n.x - SLOT_W / 2, 0).x,
              top: toScreen(c, 0, n.boxBottom + LABEL_GAP).y,
              width: SLOT_W * c.s,
              textAlign: "center",
              fontFamily: SANS,
              fontWeight: 600,
              fontSize: LABEL_PX * c.s,
              lineHeight: LABEL_LINE,
              color: look.ink,
              opacity: lit(n.id) ? 1 : DIM,
            }}
          >
            {n.lines.map((line, k) => {
              const shown = line.slice(0, Math.max(0, budget));
              budget -= line.length;
              // Reserve each line's full height from the start so nothing below moves.
              return <div key={k} style={{ minHeight: LABEL_PX * LABEL_LINE }}>{shown || " "}</div>;
            })}
          </div>
        );
      })}

      {/* value chips: on the connector they describe, one at a time */}
      {chips.map((chip, i) => {
        const e = layout.edges[chip.edge];
        if (!e) return null;
        const until = Math.min(chip.at + TIMING.chipHold, nextChip(i));
        if (frame < chip.at || frame >= until) return null;
        const mid = toScreen(c, pointAlong(e.points, 0.5).p.x, pointAlong(e.points, 0.5).p.y);
        const op = ramp(frame, chip.at, 6) * (1 - ramp(frame, until - 6, 6));
        const color = look.tone[chip.tone ?? "structure"];
        return (
          <div
            key={`c-${i}`}
            style={{
              position: "absolute",
              left: chipLeft(chip.text, mid.x, c.s),
              top: mid.y,
              transform: "translateY(-50%)",
              whiteSpace: "nowrap",
              fontFamily: MONO,
              fontWeight: 500,
              fontSize: CHIP_PX * c.s,
              color,
              background: look.chipBg,
              border: `${3 * c.s}px solid ${color}`,
              borderRadius: 10 * c.s,
              padding: `${4 * c.s}px ${16 * c.s}px`,
              opacity: op,
            }}
          >
            {chip.text}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

function activeFocusAt(board: SFBoard, node: string, frame: number): number {
  let at = -Infinity;
  for (const e of eventsOf(board, "focus")) if (e.node === node && e.at <= frame && e.at > at) at = e.at;
  return at === -Infinity ? frame : at;
}

// ── header: pill and headline, outside the camera ────────────────────────────
const Header: React.FC<{ board: SFBoard; frame: number; look: Look }> = ({ board, frame, look }) => {
  const words = board.headline.trim().split(/\s+/);
  // Type on at about 30 characters a second.
  let budget = Math.floor(Math.max(0, frame - board.startFrame) * 1.0);
  return (
    <div style={{ position: "absolute", left: 70, right: 70, top: 0.115 * H, display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 22 }}>
      {board.pill && (
        <div
          style={{
            fontFamily: SANS,
            fontWeight: 600,
            fontSize: 30,
            letterSpacing: 3,
            textTransform: "uppercase",
            color: look.cyan,
            border: `2px solid ${look.cyan}`,
            borderRadius: 999,
            padding: "6px 20px",
            opacity: ramp(frame, board.startFrame, 8),
          }}
        >
          {board.pill.slice(0, LIMITS.pillChars)}
        </div>
      )}
      <div style={{ fontFamily: HEAD, fontWeight: 700, fontSize: 76, lineHeight: 1.2, color: look.ink, minHeight: 2 * 76 * 1.2 }}>
        {words.map((w, i) => {
          const shown = w.slice(0, Math.max(0, budget));
          budget -= w.length + 1;
          const last = i === words.length - 1;
          return (
            <span key={i} style={{ color: last ? look.cyan : look.ink }}>
              {shown}
              {i < words.length - 1 ? " " : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
};

// ── the scene ─────────────────────────────────────────────────────────────────
/** Where an insert sits on the video (TMDEV-224); see CompositionBuilder's InsertPlacement. */
type Placement = { origin: number; lead?: number; palette: "dark" | "light"; shift: number };

export default function SystemFlow({
  systemFlow,
  durationInFrames,
  insert,
}: {
  systemFlow?: SystemFlowData;
  durationInFrames: number;
  insert?: Placement;
}) {
  // As an insert, the data is timed on the video's frames and the scene runs
  // from `origin` for durationInFrames; as a whole video, origin is 0.
  const origin = insert?.origin ?? 0;
  const end = origin + durationInFrames;
  // An insert's Sequence starts `lead` frames early for its way in and runs as
  // long after its window for its way out; it holds its first and last frame
  // through them, so it slides in already showing its picture.
  const raw = useCurrentFrame() + origin - (insert?.lead ?? 0);
  const frame = insert ? Math.min(Math.max(raw, origin), end - 1) : raw;
  const look = LOOKS[insert?.palette === "light" ? "light" : "dark"];
  const shift = insert?.shift ?? 0;
  const [handle] = useState(() => delayRender("SystemFlow: loading bundled fonts"));
  useEffect(() => {
    loadFonts()
      .then(() => continueRender(handle))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error("SystemFlow: font load failed", err);
        continueRender(handle);
      });
  }, [handle]);

  const boards = systemFlow?.boards ?? [];
  const prepared: Prepared[] = useMemo(
    () =>
      boards.map((board, i) => {
        const boardEnd = i + 1 < boards.length ? boards[i + 1].startFrame : end;
        const layout = layoutBoard(board);
        return { board, layout, keys: boardKeys(board, layout, boardEnd), end: boardEnd };
      }),
    // The props are static for the whole render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [systemFlow, end],
  );

  let idx = -1;
  for (let i = 0; i < prepared.length; i++) if (prepared[i].board.startFrame <= frame) idx = i;
  const cur = idx >= 0 ? prepared[idx] : null;
  // Hard cut with a short fade either side; the outgoing board is gone before the cut.
  const fade = cur
    ? (idx === 0 ? 1 : ramp(frame, cur.board.startFrame, TIMING.boardFade)) *
      (idx === prepared.length - 1 ? 1 : 1 - ramp(frame, cur.end - TIMING.boardFade, TIMING.boardFade))
    : 0;

  return (
    <AbsoluteFill style={{ background: look.bg, width: W, height: H, overflow: "hidden" }}>
      {/* the faint darker blob in one corner: a flat shape, never a gradient */}
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        <path d="M 1080 1500 C 960 1530 880 1640 900 1760 C 915 1850 990 1900 1080 1920 Z" fill={look.blob} />
      </svg>
      {cur && (
        // The shift moves the layout clear of the main style's captions; a
        // positioned offset, never a CSS transform (a transformed layer is
        // re-composited every frame in software GL).
        <AbsoluteFill style={{ opacity: fade, top: shift, height: H }}>
          <Board p={cur} frame={frame} look={look} />
          <Header board={cur.board} frame={frame} look={look} />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}
