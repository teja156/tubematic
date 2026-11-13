/*
 * IsometricInfographic: the whole of an Isometric Infographic video, as one scene.
 *
 * One floating isometric board on cream paper (a town, a port, a campus) built
 * from flat three-tone blocks: one followed thing travels a route that draws
 * ahead of it, buildings drop in with a squash, a stage lifts while the rest
 * steps back, a wall cuts away to show what is inside, a stack explodes, label
 * pins name what matters with a big number, a readout counts with a row of
 * Isotype cubes, and the video can end on the whole board with its legend.
 * The engine fills free land with trees and free city with blocks, so a few
 * props make a full board. Captions are the shared Subtitles layer's `card`.
 *
 * The agent never writes this file's kind of code: it writes `props.isometric`
 * (boards, props on tile coordinates, routes, movers, pins and camera moves
 * timed to the narration), which the MCP server validates against
 * ./isometric/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL): the board is one Canvas 2D
 * layer of flat faces in depth order; the paper is a canvas drawn once; text
 * is DOM; no SVG paths, filters or stroke-dasharray.
 */
import React, { useLayoutEffect, useMemo, useRef } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { GEOMETRY, H, LIMITS, TIMING, W, grouped, type IsometricData, type Pin } from "./isometric/contract";
import { colorOf, drawBoard, makeBoardCache, paintPaper, pinAnchor } from "./isometric/draw";
import { PIN, pinLayout, type PinSlot } from "./isometric/pins";
import { JOST, useIsometricFonts } from "./isometric/fonts";
import { INK, PALETTE, miniCube } from "./isometric/kit";
import { boardIndexAt, easeInOut, easeOutBack, ramp, readoutAt } from "./isometric/stage";

const G = GEOMETRY;

const PinView: React.FC<{ data: IsometricData; boardIndex: number; pin: Pin; slot: PinSlot; frame: number; dim: number }> = ({ data, boardIndex, pin, slot, frame, dim }) => {
  const b = data.boards[boardIndex];
  const prop = b.props.find((p) => p.id === pin.on);
  if (!prop || frame < pin.at) return null;
  const p = ramp(frame, pin.at, TIMING.pin);
  const [ax, ay] = pinAnchor(data, b, prop, frame);
  // a pin whose thing the camera has moved out of the band is not shown
  if (ay < G.bandTop || ay > G.bandBottom || ax < G.safeLeft || ax > G.safeRight) return null;
  const up = PIN.up + slot.lane * PIN.laneStep, rule = PIN.rule;
  const dot = easeOutBack(Math.min(1, p / 0.18));
  const lead = easeInOut((p - 0.12) / 0.33);
  const ru = easeInOut((p - 0.4) / 0.25);
  const tx = easeInOut((p - 0.6) / 0.4);
  const right = slot.right;
  const topY = ay - up * lead;
  const textLeft = right ? ax + 14 : ax - rule;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, opacity: dim }}>
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        <line x1={ax} y1={ay} x2={ax} y2={topY} stroke={INK} strokeWidth={2.5} />
        {ru > 0 ? <line x1={ax} y1={ay - up} x2={ax + (right ? 1 : -1) * rule * ru} y2={ay - up} stroke={INK} strokeWidth={2.5} /> : null}
        <circle cx={ax} cy={ay} r={9 * dot} fill="#FFF8EC" stroke={INK} strokeWidth={3} />
        <circle cx={ax} cy={ay} r={3.2 * dot} fill={INK} />
      </svg>
      <div style={{
        position: "absolute", left: textLeft, top: ay - up + 4, width: rule, color: INK, fontFamily: JOST,
        opacity: tx, transform: `translateY(${((1 - tx) * 10).toFixed(1)}px)`, whiteSpace: "nowrap",
      }}>
        <div style={{ fontWeight: 600, fontSize: 40, letterSpacing: 3, lineHeight: "48px" }}>{pin.label.toUpperCase()}</div>
        {pin.value ? (
          <div style={{ fontWeight: 400, fontSize: 64, lineHeight: "70px" }}>
            {pin.value}
            {pin.unit ? <span style={{ fontSize: 40, marginLeft: 8 }}>{pin.unit}</span> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
};

const Cubes: React.FC<{ n: number; color: string }> = ({ n, color }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, 560, 80);
    for (let i = 0; i < n; i++) miniCube(ctx, 24 + i * 42, 44, 24, color);
  });
  return <canvas ref={ref} width={560} height={80} style={{ position: "absolute", left: 60, top: 532 }} />;
};

export interface IsometricInfographicProps {
  isometric: IsometricData;
}

export default function IsometricInfographic({ isometric }: IsometricInfographicProps) {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  useIsometricFonts("IsometricInfographic");
  const data: IsometricData = isometric ?? { title: "", boards: [] };
  const paper = useRef<HTMLCanvasElement>(null);
  const world = useRef<HTMLCanvasElement>(null);
  const cache = useMemo(makeBoardCache, []);
  const bi = boardIndexAt(data, frame);
  const board = data.boards[bi];
  const layout = useMemo(() => (board ? pinLayout(data, board) : []), [isometric, board]); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    if (paper.current) paintPaper(paper.current);
  }, []);
  useLayoutEffect(() => {
    const ctx = world.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    if (!board) return;
    // the board stays in its band, under the title and readout and above the caption card, however far the camera zooms
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, G.bandTop, W, G.bandBottom - G.bandTop);
    ctx.clip();
    drawBoard(ctx, data, board, bi, frame, cache);
    ctx.restore();
  });

  const ro = readoutAt(data, frame);
  const cubes = data.readout?.cubes && ro.shown ? Math.min(LIMITS.maxCubes, Math.ceil(ro.value / Math.max(1, data.readout.cubes.per) - 1e-6)) : 0;
  const dimProp = (board?.lifts ?? []).filter((l) => l.at <= frame).pop()?.prop;
  const legendP = data.legend && frame >= data.legend.at ? easeOutBack(ramp(frame, data.legend.at, TIMING.legend)) : 0;
  void durationInFrames;
  return (
    <AbsoluteFill style={{ width: W, height: H, overflow: "hidden", color: INK, fontFamily: JOST }}>
      <canvas ref={paper} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }} />
      <canvas ref={world} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }} />
      {board ? (board.pins ?? []).map((pin, i) => (
        <PinView key={i} data={data} boardIndex={bi} pin={pin} slot={layout[i]} frame={frame} dim={dimProp && dimProp !== pin.on ? 0.45 : 1} />
      )) : null}
      <div style={{ position: "absolute", left: G.safeLeft, top: G.titleTop, fontWeight: 600, fontSize: 60, letterSpacing: 5, lineHeight: 1, whiteSpace: "nowrap" }}>
        {data.title.toUpperCase()}
      </div>
      {data.readout && ro.shown ? (
        <>
          <div style={{ position: "absolute", left: 72, top: G.readoutTop, fontWeight: 500, fontSize: 40, letterSpacing: 4 }}>{data.readout.label.toUpperCase()}</div>
          <div style={{ position: "absolute", left: 66, top: G.readoutTop + 42, fontWeight: 400, fontSize: 150, lineHeight: 1, fontVariantNumeric: "tabular-nums", color: ro.red ? PALETTE.red : INK }}>
            {grouped(ro.value)}
            <span style={{ fontSize: 75, marginLeft: 12 }}>{data.readout.unit}</span>
          </div>
          {cubes > 0 ? <Cubes n={cubes} color={colorOf(data.readout.cubes!.color, PALETTE.red)} /> : null}
        </>
      ) : null}
      {data.legend && legendP > 0 ? (
        <div style={{ position: "absolute", left: G.safeLeft, top: G.legendTop, display: "flex", gap: 40, opacity: Math.min(1, legendP * 1.5), transform: `translateY(${((1 - legendP) * 20).toFixed(1)}px)` }}>
          {data.legend.items.map((it, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 30, height: 30, background: colorOf(it.color, PALETTE.red), transform: "rotate(45deg) scale(0.8)" }} />
              <span style={{ fontSize: 40, fontWeight: 600, letterSpacing: 3 }}>{it.label.toUpperCase()}</span>
            </div>
          ))}
        </div>
      ) : null}
    </AbsoluteFill>
  );
}
