/*
 * What the Case File Story scene shows at a frame: which beat, the camera on
 * its still, each meter's value, and how far a card has built. Pure
 * functions, so vitest can pin them without a browser.
 */
import {
  CAMERA, GEOMETRY, TIMING, formatValue, partFrames, shotScale, shotView,
  type BarsCard, type CaseFileData, type Choice, type CountCard, type Shot,
} from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeOut = (t: number) => 1 - (1 - clamp01(t)) ** 3;

/** The index of the beat on screen at `frame` (the last one started). */
export function beatIndexAt(data: CaseFileData, frame: number): number {
  let idx = 0;
  data.beats.forEach((b, i) => {
    if (frame >= b.start) idx = i;
  });
  return idx;
}

/** The end frame of beat `i`. */
export function beatEnd(data: CaseFileData, i: number, total: number): number {
  return i + 1 < data.beats.length ? data.beats[i + 1].start : total;
}

/** The part of a shot's still on screen at a frame, as an SVG viewBox in frame pixels. */
export function viewAt(beat: Shot | Choice, frame: number, fps: number): [number, number, number, number] {
  const t = frame - beat.start;
  const punch = beat.type === "shot" ? beat.punch : undefined;
  const punchAfter = punch ? punch.frame - beat.start : null;
  const punched = punchAfter !== null && t >= punchAfter;
  const [u, v] = punched ? punch!.at : (beat.focus ?? [CAMERA.focusU, CAMERA.focusV]);
  return shotView(shotScale(t, fps, punchAfter), u, v);
}

/** Every meter's value once the shots that have started by `frame` have set theirs. */
export function meterValues(data: CaseFileData, frame: number): Record<string, number> {
  const values: Record<string, number> = {};
  for (const m of data.hud) values[m.id] = m.value;
  for (const b of data.beats) {
    if (b.start > frame) break;
    if (b.type === "shot" && b.set) Object.assign(values, b.set);
  }
  return values;
}

export interface HudCell {
  id: string;
  label: string;
  text: string;
  /** The value shown before this beat's cut, while the new one dissolves in; null when unchanged. */
  from: string | null;
  /** 0..1: how far the new value has dissolved in. */
  mix: number;
}

/** The meter row at a frame, or null while a card, a close-up or the choice hides it. */
export function hudAt(data: CaseFileData, frame: number): HudCell[] | null {
  const beat = data.beats[beatIndexAt(data, frame)];
  if (!beat || beat.type !== "shot" || beat.hud === false) return null;
  const now = meterValues(data, frame);
  const before = meterValues(data, beat.start - 1);
  const mix = clamp01((frame - beat.start) / TIMING.hudDissolve);
  return data.hud.map((m) => {
    const changed = before[m.id] !== now[m.id];
    return {
      id: m.id, label: m.label, text: formatValue(m.kind, now[m.id]),
      from: changed && mix < 1 ? formatValue(m.kind, before[m.id]) : null,
      mix: changed ? mix : 1,
    };
  });
}

/** The large meter panel over a shot: the value it shows at a frame and how full its bar is (0..1). */
export function panelAt(data: CaseFileData, shot: Shot, frame: number): { label: string; text: string; fill: number; counting: boolean } | null {
  const meter = data.hud.find((m) => m.id === shot.panel);
  if (!meter) return null;
  const from = meterValues(data, shot.start - 1)[meter.id];
  const to = meterValues(data, shot.start)[meter.id];
  const k = easeOut((frame - shot.start) / TIMING.panelCount);
  const value = Math.round(from + (to - from) * k);
  const fill = meter.kind === "percent" ? clamp01(value / 100) : clamp01(to === 0 ? 0 : value / Math.max(from, to));
  return { label: meter.label, text: formatValue(meter.kind, value), fill, counting: k < 1 };
}

/**
 * A count card at a frame: how many icons its grid holds (forty, or the number
 * itself when that is smaller), how many are filled, the counter's text, and
 * whether the result has landed.
 */
export function countAt(card: CountCard, frame: number): { total: number; cells: number; text: string; result: boolean } {
  const t = frame - card.start;
  const k = clamp01((t - TIMING.countStart) / TIMING.countFrames);
  const total = Math.max(1, Math.min(GEOMETRY.gridCols * GEOMETRY.gridRows, Math.floor(card.to)));
  return {
    total, cells: Math.floor(k * total),
    text: formatValue(card.kind, Math.round(card.to * k)), result: frame >= partFrames(card)[2],
  };
}

/** How many bars of a bars card are up at a frame, and whether its payoff line is. */
export function barsAt(card: BarsCard, frame: number): { shown: number; payoff: boolean } {
  const parts = partFrames(card);
  return { shown: card.bars.filter((b) => frame >= b.frame).length, payoff: frame >= parts[parts.length - 1] };
}

/**
 * The stretches in which nothing new appears apart from the slow push, as
 * [from, to] frames: from each part of a beat (contract.ts partFrames) to the
 * next, and from the last part to the beat's end. The validator refuses one
 * longer than LIMITS.maxStillSeconds.
 */
export function quietSpans(data: CaseFileData, total: number): [number, number][] {
  const spans: [number, number][] = [];
  data.beats.forEach((b, i) => {
    const frames = [...partFrames(b), beatEnd(data, i, total)];
    for (let k = 1; k < frames.length; k++) spans.push([frames[k - 1], frames[k]]);
  });
  return spans;
}
