/*
 * The map of a map beat: today's countries (world-atlas 1:110m, from Natural
 * Earth) drawn flat in the house colours, fitted to the beat's focus countries,
 * with regions filling in, arrows growing between them and hand-lettered
 * labels.
 *
 * The borders are today's: a historical region is shown as the modern
 * countries it covers, with its own label. The map is one inline SVG whose
 * country paths are worked out once per beat (memoised on the focus list);
 * only a fill fading in or an arrow growing changes from frame to frame.
 */
import { geoArea, geoCentroid, geoMercator, geoPath, type GeoPermissibleObjects } from "d3-geo";
import React, { useMemo } from "react";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";
import { FILLS, GEOMETRY, type FillColor } from "./contract";
import { HAND, INK, LAND, SEA } from "./ink";

type Country = { type: "Feature"; id?: string; properties: { name: string }; geometry: GeoPermissibleObjects };
const topo = world as unknown as Topology;
const COUNTRIES: Country[] = (feature(topo, topo.objects.countries) as unknown as { features: Country[] }).features;

/**
 * A country's largest landmass: the map fits and labels a country by its
 * mainland, since a far territory (France's French Guiana, Norway's Svalbard)
 * would stretch the fit across an ocean and pull the label out to sea.
 */
function mainland(c: Country): GeoPermissibleObjects {
  const g = c.geometry as unknown as { type: string; coordinates: number[][][][] };
  if (g.type !== "MultiPolygon") return c.geometry;
  let best = g.coordinates[0], area = -1;
  for (const poly of g.coordinates) {
    const a = geoArea({ type: "Polygon", coordinates: poly } as never);
    if (a > area) { area = a; best = poly; }
  }
  return { type: "Polygon", coordinates: best } as unknown as GeoPermissibleObjects;
}
const MAINLAND = new Map(COUNTRIES.map((c) => [c.properties.name, mainland(c)]));

const [MX, MY, MW, MH] = GEOMETRY.map;
const PAD = 60;

/** The projection fitted to the focus countries, inside the map's area. */
export function mapProjection(focus: readonly string[]) {
  const parts = focus.map((n) => MAINLAND.get(n)).filter((g): g is GeoPermissibleObjects => !!g);
  const fc = (parts.length
    ? { type: "GeometryCollection", geometries: parts }
    : { type: "FeatureCollection", features: COUNTRIES }) as unknown as GeoPermissibleObjects;
  return geoMercator().fitExtent([[MX + PAD, MY + PAD], [MX + MW - PAD, MY + MH - PAD]], fc);
}

/** A region's centre on screen, for arrows and labels. */
export function regionCentre(focus: readonly string[], name: string): [number, number] | null {
  const m = MAINLAND.get(name);
  if (!m) return null;
  const p = mapProjection(focus)(geoCentroid(m as never));
  return p ? [p[0], p[1]] : null;
}

/** A curved arrow from a to b, grown to `t` of its length, with its head once grown. */
function arrowPath(a: [number, number], b: [number, number], t: number): { line: string; head: string | null } {
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const c: [number, number] = [mx - dy * 0.22, my + dx * 0.22];
  const at = (u: number): [number, number] => [
    (1 - u) ** 2 * a[0] + 2 * (1 - u) * u * c[0] + u * u * b[0],
    (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * c[1] + u * u * b[1],
  ];
  const n = 24, pts: [number, number][] = [];
  for (let i = 0; i <= n; i++) pts.push(at((i / n) * t));
  const line = pts.map((p, i) => `${i ? "L" : "M"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  if (t < 1) return { line, head: null };
  const [x, y] = pts[n], [px, py] = pts[n - 2];
  const ang = Math.atan2(y - py, x - px), L = 34, wing = 0.55;
  const head = `M ${(x - L * Math.cos(ang - wing)).toFixed(1)} ${(y - L * Math.sin(ang - wing)).toFixed(1)} L ${x.toFixed(1)} ${y.toFixed(1)} L ${(x - L * Math.cos(ang + wing)).toFixed(1)} ${(y - L * Math.sin(ang + wing)).toFixed(1)}`;
  return { line, head };
}

export type MapState = {
  fills: { region: string; color: string; t: number }[];
  arrows: { from: string; to: string; t: number }[];
  labels: { region: string; text: string; t: number }[];
};

export const MapView: React.FC<{ focus: readonly string[]; state: MapState }> = ({ focus, state }) => {
  const key = focus.join("|");
  const base = useMemo(() => {
    const proj = mapProjection(focus);
    const path = geoPath(proj);
    const paths = new Map<string, string>();
    for (const c of COUNTRIES) {
      const d = path(c.geometry as never);
      if (d) paths.set(c.properties.name, d);
    }
    const centre = (n: string) => {
      const m = MAINLAND.get(n);
      const p = m ? proj(geoCentroid(m as never)) : null;
      return p ? ([p[0], p[1]] as [number, number]) : null;
    };
    return { paths, centre };
    // the map depends on the focus list alone
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const all = useMemo(() => [...base.paths.values()].join(" "), [base]);
  return (
    <svg width={1080} height={1920} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <clipPath id="ph-map-clip"><rect x={MX} y={MY} width={MW} height={MH} rx={18} /></clipPath>
      </defs>
      <g clipPath="url(#ph-map-clip)">
        <rect x={MX} y={MY} width={MW} height={MH} fill={SEA} />
        <path d={all} fill={LAND} stroke={INK} strokeWidth={2.5} strokeLinejoin="round" />
        {state.fills.map((f) => {
          const d = base.paths.get(f.region);
          return d ? <path key={`f-${f.region}`} d={d} fill={FILLS[f.color as FillColor] ?? f.color} opacity={f.t} stroke={INK} strokeWidth={3} strokeLinejoin="round" /> : null;
        })}
        {state.arrows.map((a, i) => {
          const p = base.centre(a.from), q = base.centre(a.to);
          if (!p || !q || a.t <= 0) return null;
          const { line, head } = arrowPath(p, q, a.t);
          return (
            <g key={`a-${i}`} fill="none" stroke={INK} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round">
              <path d={line} />
              {head ? <path d={head} /> : null}
            </g>
          );
        })}
      </g>
      <rect x={MX} y={MY} width={MW} height={MH} rx={18} fill="none" stroke={INK} strokeWidth={7} />
      {state.labels.map((l) => {
        const p = base.centre(l.region);
        if (!p) return null;
        return (
          <text key={`l-${l.region}`} x={p[0]} y={p[1] + 12} textAnchor="middle" fontFamily={HAND} fontWeight={700} fontSize={44}
            fill={INK} stroke="#FFFFFF" strokeWidth={8} paintOrder="stroke" opacity={l.t}>{l.text}</text>
        );
      })}
    </svg>
  );
};
