/*
 * What is on stage at a frame: a pure function of the data, so the scene, the
 * sheet and the tests read the same answer.
 *
 * The world is one long ground line with a station every GEOMETRY.stationGap
 * pixels. Actors stand in a station's slots; the camera shows one station at a
 * time and glides (or cuts) between them. Events are read in frame order; an
 * actor's state is the sum of its events up to the frame.
 */
import { clamp01, ease } from "../characterKit/geometry";
import {
  GEOMETRY, PROPS, TIMING, W, bodySize, cloneId, propCentre, slotX, stationX,
  type Body, type Face, type Mark, type PCActor, type PCCustomProp, type ProcessCastData, type StationKind,
} from "./contract";

export type ActorState = {
  id: string;
  base: PCActor;
  units: number;
  station: number;
  slot: number;
  /** World x of the feet, and the lift of a hop (negative is up). */
  x: number;
  lift: number;
  /** Frames since the actor last landed, for the squash (-1 when not landing). */
  landed: number;
  enterAt: number;
  from: string;
  exitAt: number;
  /** A clone's first frames show it as a silhouette. */
  silhouette: boolean;
  face: Face;
  mark: Mark | "";
  markAt: number;
  lookAt: string;
  card: string;
  /** Scale from focus (1 when none). */
  scale: number;
  /** 0 to 1 while vanishing into another actor (a merge or a join). */
  vanish: number;
};

export type FlyingCard = { text: string; from: [number, number]; to: [number, number]; t: number };
export type PropState = { station: number; prop: string; text: string; since: number; x: number; y: number };
export type CastState = { camX: number; actors: ActorState[]; props: PropState[]; flying: FlyingCard[] };

type Move = { at: number; fromX: number; toX: number; dur: number; trip: boolean };
type Track = {
  id: string; base: PCActor; units: number; station: number; slot: number;
  enterAt: number; from: string; exitAt: number; cloneAt: number;
  moves: Move[];
  face: Face; mark: Mark | ""; markAt: number; lookAt: string; card: string; cardAt: number;
  vanishAt: number; vanishDur: number; vanishTo: string;
};

const stationIndex = (data: ProcessCastData, id: string) => data.stations.findIndex((s) => s.id === id);
const kindOf = (data: ProcessCastData, i: number): StationKind => data.stations[i]?.kind ?? "stage";

/** Where an actor's feet are at a frame, along the world, and how high it hops. */
function positionAt(t: Track, frame: number): { x: number; lift: number; landed: number } {
  let x = t.moves.length ? t.moves[0].fromX : 0;
  let lift = 0;
  let landed = -1;
  for (const m of t.moves) {
    if (frame < m.at) break;
    const k = clamp01((frame - m.at) / m.dur);
    x = m.fromX + (m.toX - m.fromX) * ease.inOut(k);
    if (k < 1) {
      lift = m.trip ? -Math.abs(Math.sin(k * Math.PI * 2)) * 50 : -Math.sin(k * Math.PI) * 60;
      landed = -1;
    } else {
      lift = 0;
      landed = frame - (m.at + m.dur);
    }
  }
  return { x, lift, landed };
}

/** The tracks of every actor and clone, built from the events up to `frame`. */
function tracksAt(data: ProcessCastData, frame: number): { tracks: Map<string, Track>; props: PropState[]; flying: FlyingCard[]; camera: { from: number; to: number; at: number; cut: boolean } } {
  const tracks = new Map<string, Track>();
  const byId = new Map(data.cast.map((c) => [c.id, c]));
  const props = new Map<number, PropState>();
  const flying: FlyingCard[] = [];
  let camera = { from: 0, to: 0, at: -1000, cut: true };
  const occupied = (station: number, except = "") =>
    new Set([...tracks.values()].filter((t) => t.id !== except && t.station === station && t.exitAt < 0 && t.vanishAt < 0).map((t) => t.slot));

  for (const e of data.events) {
    if (e.frame > frame) break;
    const f = e.frame;
    switch (e.type) {
      case "enter": {
        const base = byId.get(e.who);
        const st = stationIndex(data, e.station);
        if (!base || st < 0) break;
        const x = slotX(st, kindOf(data, st), e.slot);
        tracks.set(e.who, {
          id: e.who, base, units: base.units ?? 1, station: st, slot: e.slot, enterAt: f, from: e.from ?? "pop", exitAt: -1, cloneAt: -1,
          moves: [{ at: f, fromX: x, toX: x, dur: 1, trip: false }], face: "neutral", mark: "", markAt: -1, lookAt: "", card: "", cardAt: -1,
          vanishAt: -1, vanishDur: 1, vanishTo: "",
        });
        break;
      }
      case "move": {
        const t = tracks.get(e.who);
        const st = stationIndex(data, e.station);
        if (!t || st < 0) break;
        const x0 = positionAt(t, f).x;
        const trip = st !== t.station;
        t.moves.push({ at: f, fromX: x0, toX: slotX(st, kindOf(data, st), e.slot), dur: trip ? TIMING.trip : TIMING.hop, trip });
        t.station = st;
        t.slot = e.slot;
        break;
      }
      case "exit": {
        const t = tracks.get(e.who);
        if (t) t.exitAt = f;
        break;
      }
      case "clone": {
        const t = tracks.get(e.who);
        if (!t) break;
        const free = Array.from({ length: (kindOf(data, t.station) === "stage" ? GEOMETRY.stageSlots : GEOMETRY.slots).length }, (_, i) => i)
          .filter((s) => !occupied(t.station).has(s));
        for (let n = 1; n < e.count && free.length; n++) {
          const slot = free.shift()!;
          const x = slotX(t.station, kindOf(data, t.station), slot);
          const id = cloneId(e.who, n);
          tracks.set(id, {
            ...t, id, slot, enterAt: f, from: "pop", cloneAt: f, exitAt: -1, card: "", cardAt: -1, mark: "", markAt: -1,
            moves: [{ at: f, fromX: x, toX: x, dur: 1, trip: false }], vanishAt: -1, vanishDur: 1, vanishTo: "",
          });
        }
        break;
      }
      case "merge": {
        const t = tracks.get(e.who);
        if (!t) break;
        const target = positionAt(t, f).x;
        for (const c of tracks.values()) {
          if (c.id === e.who || !c.id.startsWith(e.who) || !/^\d+$/.test(c.id.slice(e.who.length)) || c.vanishAt >= 0) continue;
          c.moves.push({ at: f, fromX: positionAt(c, f).x, toX: target, dur: TIMING.merge, trip: c.station !== t.station });
          c.vanishAt = f;
          c.vanishDur = TIMING.merge;
          c.vanishTo = e.who;
        }
        break;
      }
      case "join": {
        const t = tracks.get(e.who);
        const o = tracks.get(e.with);
        if (!t || !o) break;
        o.moves.push({ at: f, fromX: positionAt(o, f).x, toX: positionAt(t, f).x, dur: TIMING.merge, trip: false });
        o.vanishAt = f;
        o.vanishDur = TIMING.merge;
        o.vanishTo = e.who;
        if (frame >= f + TIMING.merge) t.units += o.units;
        break;
      }
      case "react": {
        const t = tracks.get(e.who);
        if (!t) break;
        t.face = e.face;
        if (e.mark) {
          t.mark = e.mark;
          t.markAt = f;
        }
        break;
      }
      case "look": {
        const t = tracks.get(e.who);
        if (t) t.lookAt = e.at;
        break;
      }
      case "carry": {
        const t = tracks.get(e.who);
        if (t) {
          t.card = e.text;
          t.cardAt = f;
        }
        break;
      }
      case "hand": {
        const a = tracks.get(e.from);
        const b = tracks.get(e.to);
        if (!a || !b) break;
        const text = a.card;
        const k = (frame - f) / TIMING.hand;
        const pa = positionAt(a, f), pb = positionAt(b, f + TIMING.hand);
        const ha = bodySize(a.base.body, a.units).h, hb = bodySize(b.base.body, b.units).h;
        if (k < 1) flying.push({ text, from: [pa.x, GEOMETRY.groundY - ha - 60], to: [pb.x, GEOMETRY.groundY - hb - 60], t: clamp01(k) });
        a.card = "";
        if (k >= 1) {
          b.card = text;
          b.cardAt = f + TIMING.hand;
        }
        break;
      }
      case "prop": {
        const st = stationIndex(data, e.station);
        if (st < 0) break;
        const box = propBoxSize(e.prop, data.customProps ?? []);
        const c = propCentre(st, kindOf(data, st), box);
        props.set(st, { station: st, prop: e.prop, text: e.text ?? "", since: f, x: c.x, y: c.y });
        break;
      }
      case "focus":
        break;
      case "camera": {
        const st = stationIndex(data, e.station);
        if (st < 0) break;
        const now = cameraAt(camera, f);
        camera = { from: now, to: stationX(st), at: f, cut: e.move === "cut" };
        break;
      }
    }
  }
  return { tracks, props: [...props.values()], flying, camera };
}

function cameraAt(c: { from: number; to: number; at: number; cut: boolean }, frame: number): number {
  if (c.cut || frame >= c.at + TIMING.glide) return frame >= c.at ? c.to : c.from;
  return c.from + (c.to - c.from) * ease.inOut(clamp01((frame - c.at) / TIMING.glide));
}

/** A prop's box at scale 1: the library's, or the size a custom prop declares. */
export function propBoxSize(prop: string, custom: readonly PCCustomProp[]): { w: number; h: number } {
  if (prop in PROPS) return PROPS[prop as keyof typeof PROPS];
  const c = custom.find((q) => q.id === prop);
  return c ? { w: c.w, h: c.h } : { w: 0, h: 0 };
}

/** The actor in focus at a frame, or "". */
export function focusAt(data: ProcessCastData, frame: number): string {
  let who = "";
  for (const e of data.events) {
    if (e.frame > frame) break;
    if (e.type === "focus") who = e.who;
  }
  return who;
}

/** The whole cast at a frame, in the world's coordinates. */
export function castAt(data: ProcessCastData, frame: number): CastState {
  const { tracks, props, flying, camera } = tracksAt(data, frame);
  const focus = focusAt(data, frame);
  const focusStation = focus ? tracks.get(focus)?.station ?? -1 : -1;
  const actors: ActorState[] = [];
  for (const t of tracks.values()) {
    if (t.exitAt >= 0 && frame >= t.exitAt + TIMING.enter) continue;
    if (t.vanishAt >= 0 && frame >= t.vanishAt + t.vanishDur) continue;
    const p = positionAt(t, frame);
    let scale = kindOf(data, t.station) === "stage" ? GEOMETRY.stageScale : 1;
    if (focus && t.station === focusStation) scale *= t.id === focus ? GEOMETRY.focusScale : GEOMETRY.focusOthers;
    actors.push({
      id: t.id, base: t.base, units: t.units, station: t.station, slot: t.slot, x: p.x, lift: p.lift, landed: p.landed,
      enterAt: t.enterAt, from: t.from, exitAt: t.exitAt,
      silhouette: t.cloneAt >= 0 && frame < t.cloneAt + TIMING.silhouette,
      face: t.face, mark: t.mark && frame < t.markAt + TIMING.mark ? t.mark : "", markAt: t.markAt, lookAt: t.lookAt,
      card: t.card, scale, vanish: t.vanishAt >= 0 ? clamp01((frame - t.vanishAt) / t.vanishDur) : 0,
    });
  }
  return { camX: cameraAt(camera, frame), actors, props, flying };
}

/** A world x on screen, for a camera at camX. */
export const toScreen = (worldX: number, camX: number) => worldX - camX + W / 2;

/** A seeded blink: two frames every few seconds, different for each actor. */
export function blinkAt(frame: number, seed: number): boolean {
  const period = 84 + (seed % 37);
  return (Math.floor(frame / 2) * 2 + (seed % period)) % period < 2;
}

export type { Body };
