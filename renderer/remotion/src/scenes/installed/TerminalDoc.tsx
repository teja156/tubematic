/*
 * TerminalDoc: the whole of a Terminal Doc video, as one scene.
 *
 * A dark typographic documentary where the text is the picture: sparse
 * monospace capitals on near-black, letters that lift and arc into new
 * orders, numbers that resolve out of glyph noise, a grey ciphertext wall,
 * hairline brackets tying a claim to its source, one red or blue glow at a
 * time. Two skins: the house look and amber CRT phosphor.
 *
 * The agent writes `props.terminalDoc` (beats and moves timed to the
 * narration), which the MCP server validates against ./terminalDoc/contract.ts
 * before the video can render. Where no shipped move fits, the agent may write
 * its own move (`generated/<video_id>/move-<name>.tsx`, listed in
 * `customMoves`), built from ./terminalDoc/kit.
 *
 * Render cost on the CPU renderer (software GL), in CPU-seconds per frame over
 * the skill's whole example video, captions included: 0.18 in the house skin,
 * 0.27 in the CRT skin (its glass layer and the bloom on every glyph); System
 * Flow's example is 0.17 and Bean Explainer's 0.28. The research sample this
 * style came from cost 1.95, almost all of it a DOM ciphertext wall under a
 * CSS mask and two full-frame gradients: see ./terminalDoc/backdrop.tsx for
 * what replaced them. Everything else settles, so a held frame repaints
 * nothing but the captions' caret.
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame } from "remotion";
import { H, TIMING, W, type TDCustomMove, type TerminalDocData } from "./terminalDoc/contract";
import { useTerminalFonts } from "./terminalDoc/fonts";
import { CrtGlass, LEVEL1, Wall } from "./terminalDoc/backdrop";
import { clamp01, ease, skinTokens, type MoveProps } from "./terminalDoc/kit";
import { ElementView, camFor, type MoveContext } from "./terminalDoc/moves";
import { beatIndexAt, beatState, pushScale, wallAt, type StageState } from "./terminalDoc/stage";

function useCustomMoves(list: TDCustomMove[]): Record<string, React.FC<MoveProps>> | null {
  const [draws, setDraws] = useState<Record<string, React.FC<MoveProps>> | null>(list.length ? null : {});
  const [handle] = useState(() => (list.length ? delayRender("TerminalDoc: loading the video's own moves") : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(list.map((c) => import(`../generated/${c.src}.tsx`).then((m: { default: React.FC<MoveProps> }) => [c.id, m.default] as const)))
      .then((pairs) => {
        setDraws(Object.fromEntries(pairs));
        continueRender(handle);
      })
      // A move that cannot load fails the render rather than leave a beat empty.
      .catch((err) => cancelRender(err));
    // The moves are static for the whole render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle]);
  return draws;
}

const Beat: React.FC<{ state: StageState; ctx: MoveContext }> = ({ state, ctx }) => (
  <>
    {state.elements.map((el) => (
      <ElementView key={el.id} el={el} ctx={ctx} />
    ))}
  </>
);

export default function TerminalDoc({ terminalDoc, durationInFrames }: { terminalDoc?: TerminalDocData; durationInFrames: number }) {
  const frame = useCurrentFrame();
  const ready = useTerminalFonts("TerminalDoc");
  const data: TerminalDocData = terminalDoc ?? { skin: "house", beats: [] };
  const customList = data.customMoves ?? [];
  const customDraw = useCustomMoves(customList) ?? {};
  const custom = Object.fromEntries(customList.map((c) => [c.id, c]));
  const skin = skinTokens(data.skin);

  const bi = beatIndexAt(data, frame);
  const state = beatState(data, bi, frame, durationInFrames);
  const cam = camFor(pushScale(state.push, frame, ease.arc));
  const ctx: MoveContext = { frame, skin, glows: state.glows, cam, custom, customDraw };

  // The CRT-off collapse: the previous beat, frozen on its last frame,
  // squeezes to a line and then to a dot while the new beat starts.
  const beat = bi >= 0 ? data.beats[bi] : null;
  const collapseT = beat?.cut === "collapse" && bi > 0 ? frame - beat.start : Infinity;
  let collapsing: React.ReactNode = null;
  if (collapseT < TIMING.collapse) {
    const prevFrame = beat!.start - 1;
    const prev = beatState(data, bi - 1, prevFrame, durationInFrames);
    const prevCtx: MoveContext = { ...ctx, frame: prevFrame, glows: prev.glows, cam: camFor(pushScale(prev.push, prevFrame, ease.arc)) };
    const k = clamp01(collapseT / TIMING.collapse);
    const sy = Math.max(0.004, 1 - k / 0.6);
    const sx = k < 0.6 ? 1 : Math.max(0.004, 1 - (k - 0.6) / 0.4);
    collapsing = (
      <div style={{ position: "absolute", inset: 0, transform: `scale(${sx}, ${sy})`, transformOrigin: "50% 44%", filter: undefined, opacity: 1 - k * 0.3 }}>
        <Beat state={prev} ctx={prevCtx} />
      </div>
    );
  }

  const wall = wallAt(data, frame);
  const level = (lv: number) => (lv >= 2 ? 1 : lv === 1 ? LEVEL1 : 0);
  const wallOp = wall.since === -Infinity ? 0 : level(wall.prev) + (level(wall.level) - level(wall.prev)) * clamp01((frame - wall.since) / TIMING.reveal);
  const showNew = collapseT >= TIMING.collapse * 0.6;

  return (
    <AbsoluteFill style={{ background: skin.canvas, width: W, height: H, overflow: "hidden" }}>
      <Wall frame={frame} opacity={wallOp} skin={skin} ready={ready} />
      {collapsing}
      {showNew && <Beat state={state} ctx={ctx} />}
      {skin.name === "crt" && <CrtGlass />}
    </AbsoluteFill>
  );
}
