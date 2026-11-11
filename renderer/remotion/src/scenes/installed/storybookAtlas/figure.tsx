/*
 * People: stiff, flat picture-book figures. A person is made of knobs (build,
 * skin, hair, face, hat, garment, colour) on one rig, so a video can show Ada
 * Lovelace or Thomas Edison by name and costume, never by a likeness.
 *
 * Drawn facing right in three-quarter view, feet at the origin, in a 520 x 760
 * box. Facing left is the bitmap mirrored. Each distinct look is one cached
 * bitmap (./bitmap.tsx). The walk is on twos: two drawings, each held two
 * frames, while the scene slides the bitmap along the floor.
 */
import React from "react";
import type { Drawing } from "./bitmap";
import { FloorShadow, Sh, circle, ellipse, poly } from "./ink";
import { CREAM, GARMENT_COLORS, GOLD, INK, SKIN } from "./palette";

export const BUILDS = ["tall", "short"] as const;
export const SKINS = Object.keys(SKIN) as (keyof typeof SKIN)[];
export const HAIRS = ["short", "long", "bun", "curly", "bald"] as const;
export const HAIR_COLORS = ["dark", "brown", "auburn", "grey", "fair"] as const;
export const FACES = ["none", "moustache", "beard"] as const;
export const HATS = ["none", "tophat", "bowler", "cap", "bonnet"] as const;
export const GARMENTS = ["frockcoat", "suit", "dress", "labcoat", "overalls", "waistcoat"] as const;
export const COLORS = Object.keys(GARMENT_COLORS) as (keyof typeof GARMENT_COLORS)[];
export const PERSON_POSES = ["stand", "walk1", "walk2", "point", "hold", "think", "surprised"] as const;

export type Person = {
  build: (typeof BUILDS)[number];
  skin: keyof typeof SKIN;
  hair: (typeof HAIRS)[number];
  hairColor: (typeof HAIR_COLORS)[number];
  face: (typeof FACES)[number];
  hat: (typeof HATS)[number];
  garment: (typeof GARMENTS)[number];
  color: keyof typeof GARMENT_COLORS;
};
export type PersonPose = (typeof PERSON_POSES)[number];

export const PERSON_BOX = { width: 520, height: 760, footX: 260, footY: 730 } as const;

const HAIR_HEX: Record<Person["hairColor"], string> = {
  dark: "#2B2420", brown: "#5C3D2A", auburn: "#8A4529", grey: "#9C968E", fair: "#C9A86A",
};
const TROUSER = "#3B3A40";
const SHOE = "#231A14";
const SHIRT = CREAM;

type Arm = [upper: number, lower: number];
type Pose = { legs: [number, number]; far: Arm; near: Arm; head: number };
const POSES: Record<PersonPose, Pose> = {
  stand: { legs: [-3, 3], far: [6, 4], near: [-6, -4], head: 0 },
  walk1: { legs: [-16, 16], far: [16, 10], near: [-16, -6], head: 0 },
  walk2: { legs: [16, -16], far: [-16, -6], near: [16, 10], head: 0 },
  point: { legs: [-3, 3], far: [6, 4], near: [96, 6], head: -4 },
  hold: { legs: [-3, 3], far: [30, 70], near: [34, 66], head: 6 },
  think: { legs: [-3, 3], far: [10, 4], near: [-77, 216], head: 8 },
  surprised: { legs: [-6, 6], far: [-150, -10], near: [150, 10], head: -8 },
};

function seg(x: number, y: number, a: Arm, l1: number, l2: number) {
  const r1 = (a[0] * Math.PI) / 180, r2 = ((a[0] + a[1]) * Math.PI) / 180;
  const ex = x + l1 * Math.sin(r1), ey = y + l1 * Math.cos(r1);
  return { ex, ey, hx: ex + l2 * Math.sin(r2), hy: ey + l2 * Math.cos(r2) };
}

const Tube: React.FC<{ pts: [number, number][]; w: number; color: string }> = ({ pts, w, color }) => {
  const d = `M${pts.map(([x, y]) => `${x} ${y}`).join("L")}`;
  return (
    <g>
      <path d={d} fill="none" stroke={INK} strokeWidth={w + 6} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
};

/** A sleeve and hand. */
const ArmView: React.FC<{ x: number; y: number; a: Arm; sleeve: string; skin: string; long: boolean }> = ({ x, y, a, sleeve, skin, long }) => {
  const { ex, ey, hx, hy } = seg(x, y, a, long ? 92 : 80, long ? 88 : 76);
  return (
    <g>
      <Tube pts={[[x, y], [ex, ey], [hx, hy]]} w={26} color={sleeve} />
      <path d={circle(hx, hy, 13)} fill={skin} stroke={INK} strokeWidth={3} />
    </g>
  );
};

/** A trouser leg and shoe from the hip, swinging about it. */
const LegView: React.FC<{ x: number; y: number; a: number; len: number; color: string }> = ({ x, y, a, len, color }) => {
  const r = (a * Math.PI) / 180;
  const fx = x + len * Math.sin(r), fy = Math.min(-8, y + len * Math.cos(r));
  return (
    <g>
      <Tube pts={[[x, y], [fx, fy]]} w={34} color={color} />
      <path d={`M${fx - 18} ${fy + 6} q0 -16 18 -16 l20 4 q14 4 14 12z`} fill={SHOE} stroke={INK} strokeWidth={3} />
    </g>
  );
};

/** A shoe alone, for a figure whose legs are under a long skirt or coat. */
const Shoe: React.FC<{ x: number; a: number }> = ({ x, a }) => {
  const fx = x + 30 * Math.sin((a * Math.PI) / 180);
  return <path d={`M${fx - 18} -2 q0 -16 18 -16 l20 4 q14 4 14 12z`} fill={SHOE} stroke={INK} strokeWidth={3} />;
};

function Hair({ p, hx, hy, r, back }: { p: Person; hx: number; hy: number; r: number; back: boolean }) {
  const c = HAIR_HEX[p.hairColor];
  if (p.hair === "long" && back) {
    return <Sh d={`M${hx - r - 6} ${hy - 10} Q${hx - r - 18} ${hy + r + 40} ${hx - r + 4} ${hy + r + 64} L${hx + r * 0.2} ${hy + r + 60} Q${hx + r * 0.1} ${hy + 10} ${hx - r} ${hy - 10}Z`} fill={c} penOp={0.25} sw={3} />;
  }
  if (back) return null;
  switch (p.hair) {
    case "bald":
      return <Sh d={`M${hx - r - 2} ${hy + 4} Q${hx - r - 4} ${hy - 16} ${hx - r + 10} ${hy - 22} L${hx - r + 14} ${hy + 10}Z`} fill={c} pen="none" sw={2.5} />;
    case "short":
      return <Sh d={`M${hx - r - 4} ${hy + 6} Q${hx - r - 8} ${hy - r - 10} ${hx + 4} ${hy - r - 6} Q${hx + r + 2} ${hy - r + 2} ${hx + r - 4} ${hy - r * 0.45} Q${hx + 4} ${hy - r * 0.62} ${hx - r * 0.35} ${hy - r * 0.2} L${hx - r + 8} ${hy + 14}Z`} fill={c} penOp={0.25} sw={3} />;
    case "long":
      return <Sh d={`M${hx - r - 6} ${hy + 10} Q${hx - r - 10} ${hy - r - 14} ${hx + 6} ${hy - r - 8} Q${hx + r + 4} ${hy - r} ${hx + r - 2} ${hy - r * 0.35} Q${hx + 6} ${hy - r * 0.7} ${hx - r * 0.3} ${hy - r * 0.15} L${hx - r + 6} ${hy + 18}Z`} fill={c} penOp={0.25} sw={3} />;
    case "bun":
      return (
        <g>
          <Sh d={circle(hx - r * 0.7, hy - r * 0.95, r * 0.42)} fill={c} penOp={0.25} sw={3} />
          <Sh d={`M${hx - r - 4} ${hy + 6} Q${hx - r - 8} ${hy - r - 8} ${hx + 4} ${hy - r - 4} Q${hx + r} ${hy - r + 4} ${hx + r - 6} ${hy - r * 0.45} Q${hx + 2} ${hy - r * 0.6} ${hx - r * 0.4} ${hy - r * 0.15} L${hx - r + 8} ${hy + 14}Z`} fill={c} penOp={0.25} sw={3} />
        </g>
      );
    case "curly": {
      const bumps = Array.from({ length: 7 }, (_, i) => {
        const a = Math.PI * (0.95 + i * 0.16);
        return circle(hx - 4 + (r + 4) * Math.cos(a), hy - 6 + (r + 4) * Math.sin(a), r * 0.36);
      });
      return <g>{bumps.map((d, i) => <Sh key={i} d={d} fill={c} penOp={0.25} sw={3} />)}</g>;
    }
  }
}

function Hat({ p, hx, hy, r }: { p: Person; hx: number; hy: number; r: number }) {
  const c = GARMENT_COLORS[p.color];
  const top = hy - r;
  switch (p.hat) {
    case "none":
      return null;
    case "tophat":
      return (
        <g>
          <Sh d={`M${hx - r * 0.72} ${top + 8} L${hx - r * 0.66} ${top - 92} L${hx + r * 0.7} ${top - 92} L${hx + r * 0.76} ${top + 8}Z`} fill="#2A2830" pen="l" penOp={0.18} sw={3} />
          <rect x={hx - r * 0.72} y={top - 14} width={r * 1.48} height={12} fill={c} stroke={INK} strokeWidth={2} />
          <Sh d={ellipse(hx + 2, top + 8, r * 1.12, 10)} fill="#2A2830" pen="none" sw={3} />
        </g>
      );
    case "bowler":
      return (
        <g>
          <Sh d={`M${hx - r * 0.8} ${top + 12} Q${hx - r * 0.8} ${top - 58} ${hx + 2} ${top - 58} Q${hx + r * 0.84} ${top - 58} ${hx + r * 0.84} ${top + 12}Z`} fill="#3A2E28" pen="l" penOp={0.18} sw={3} />
          <Sh d={ellipse(hx + 4, top + 12, r * 1.1, 9)} fill="#3A2E28" pen="none" sw={3} />
        </g>
      );
    case "cap":
      return (
        <g>
          <Sh d={`M${hx - r * 0.95} ${top + 18} Q${hx - r} ${top - 26} ${hx + 6} ${top - 26} Q${hx + r} ${top - 22} ${hx + r * 0.96} ${top + 12}Z`} fill={c} penOp={0.25} sw={3} />
          <Sh d={`M${hx + r * 0.5} ${top + 10} Q${hx + r * 1.2} ${top + 4} ${hx + r * 1.42} ${top + 18} L${hx + r * 0.6} ${top + 22}Z`} fill={c} penOp={0.25} sw={3} />
        </g>
      );
    case "bonnet":
      return (
        <g>
          <Sh d={`M${hx - r * 1.05} ${hy + r * 0.5} Q${hx - r * 1.3} ${top - 34} ${hx + r * 0.2} ${top - 30} Q${hx + r * 1.4} ${top - 22} ${hx + r * 1.15} ${hy - r * 0.15} Q${hx + r * 0.4} ${top + 2} ${hx - r * 0.5} ${hy + r * 0.2}Z`} fill={c} penOp={0.25} sw={3} />
          <path d={`M${hx - r * 0.62} ${hy + r * 0.3} Q${hx - r * 0.4} ${hy + r * 1.0} ${hx + r * 0.1} ${hy + r * 1.02}`} fill="none" stroke={c} strokeWidth={6} strokeLinecap="round" />
          <path d={`M${hx + r * 0.1} ${hy + r * 1.02} l-16 -10 l0 20z M${hx + r * 0.1} ${hy + r * 1.02} l16 -10 l0 20z`} fill={c} stroke={INK} strokeWidth={2} strokeLinejoin="round" />
        </g>
      );
  }
}

/** A person in a pose, feet at (0, 0), facing right. */
export const PersonFigure: React.FC<{ p: Person; pose: PersonPose }> = ({ p, pose }) => {
  const q = POSES[pose];
  const tall = p.build === "tall";
  const L = tall ? 260 : 220; // hip to sole
  const T = tall ? 200 : 178; // shoulder to hip
  const R = tall ? 54 : 52; // head radius
  const hipY = -L;
  const shY = hipY - T;
  const hx = 8, hy = shY - 22 - R;
  const skin = SKIN[p.skin];
  const g = GARMENT_COLORS[p.color];
  const sw = 64; // shoulder half-width
  const hw = 46; // hip half-width

  // what each garment colours
  let sleeve: string = g, trousers: string = TROUSER, coatLen = 0, coatColor: string = g, shirtFront = false, skirt = false, bib = false, vest = false;
  switch (p.garment) {
    case "frockcoat": coatLen = L * 0.62; break;
    case "suit": coatLen = 30; shirtFront = true; break;
    case "labcoat": coatLen = L * 0.58; coatColor = "#ECE8DC"; sleeve = "#ECE8DC"; trousers = g; break;
    case "overalls": sleeve = SHIRT; trousers = g; bib = true; coatLen = 0; break;
    case "waistcoat": sleeve = SHIRT; vest = true; coatLen = 0; break;
    case "dress": skirt = true; break;
  }
  const longSleeve = true;

  return (
    <g>
      <FloorShadow cx={6} w={170} />
      {/* hair that falls behind the shoulders */}
      <g transform={`rotate(${q.head} ${hx} ${shY - 10})`}>
        <Hair p={p} hx={hx} hy={hy} r={R} back />
      </g>
      {/* far arm */}
      <ArmView x={-sw + 12} y={shY + 14} a={q.far} sleeve={shade(sleeve)} skin={skin} long={longSleeve} />
      {/* legs, or shoes under a skirt */}
      {skirt ? (
        <g>
          <Shoe x={-18} a={q.legs[0]} />
          <Shoe x={18} a={q.legs[1]} />
        </g>
      ) : (
        <g>
          <LegView x={-hw + 20} y={hipY} a={q.legs[0]} len={L - 6} color={shade(trousers)} />
          <LegView x={hw - 20} y={hipY} a={q.legs[1]} len={L - 6} color={trousers} />
        </g>
      )}
      {/* torso and garment */}
      {skirt ? (
        <g>
          <Sh d={poly([[-hw + 4, hipY - 8], [hw - 4, hipY - 8], [hw + 50 + q.legs[1] * 0.6, -26], [-hw - 50 + q.legs[0] * 0.6, -26]])} fill={g} penOp={0.22} sw={3.5} />
          <path d={`M${-hw - 50 + q.legs[0] * 0.6} -26 L${hw + 50 + q.legs[1] * 0.6} -26`} stroke={INK} strokeWidth={3} />
          <Sh d={`M${-sw} ${shY + 12} Q${-sw} ${shY - 4} ${-sw + 20} ${shY - 6} L${sw - 20} ${shY - 6} Q${sw} ${shY - 4} ${sw} ${shY + 12} L${hw - 2} ${hipY} L${-hw + 2} ${hipY}Z`} fill={g} penOp={0.22} sw={3.5} />
          <path d={`M${-hw + 2} ${hipY} L${hw - 2} ${hipY}`} stroke={INK} strokeWidth={4} />
          <path d={`M${-16} ${shY - 6} q16 18 32 0`} fill={CREAM} stroke={INK} strokeWidth={2.5} />
        </g>
      ) : (
        <g>
          {/* shirt/torso */}
          <Sh d={`M${-sw} ${shY + 12} Q${-sw} ${shY - 4} ${-sw + 20} ${shY - 6} L${sw - 20} ${shY - 6} Q${sw} ${shY - 4} ${sw} ${shY + 12} L${hw} ${hipY + 4} L${-hw} ${hipY + 4}Z`}
            fill={coatLen > 0 ? coatColor : sleeve === SHIRT ? SHIRT : g} penOp={0.2} sw={3.5} />
          {coatLen > 0 && coatLen < 60 && (
            <Sh d={`M${-hw - 2} ${hipY} L${hw + 2} ${hipY} L${hw + 4} ${hipY + coatLen} L${-hw - 4} ${hipY + coatLen}Z`} fill={coatColor} penOp={0.2} sw={3.5} />
          )}
          {coatLen >= 60 && (
            <g>
              {/* two tails parted at the front, the trousers showing between them */}
              <Sh d={`M${-hw - 4} ${hipY} L${-2} ${hipY} L${-10 + q.legs[0] * 0.4} ${hipY + coatLen - 8} L${-hw - 16 + q.legs[0] * 0.6} ${hipY + coatLen}Z`} fill={shade(coatColor)} penOp={0.2} sw={3.5} />
              <Sh d={`M${4} ${hipY} L${hw + 4} ${hipY} L${hw + 16 + q.legs[1] * 0.6} ${hipY + coatLen} L${16 + q.legs[1] * 0.4} ${hipY + coatLen - 8}Z`} fill={coatColor} penOp={0.2} sw={3.5} />
            </g>
          )}
          {(shirtFront || coatLen > 0) && (
            <g>
              <path d={poly([[-14, shY - 6], [14, shY - 6], [4, shY + 70], [-4, shY + 70]])} fill={SHIRT} stroke={INK} strokeWidth={2.5} />
              {p.garment !== "labcoat" && <path d={poly([[-5, shY + 4], [5, shY + 4], [7, shY + 58], [0, shY + 66], [-7, shY + 58]])} fill={shade(g)} stroke={INK} strokeWidth={2} />}
              <path d={`M-14 ${shY - 6} L-30 ${shY + 90} M14 ${shY - 6} L30 ${shY + 90}`} stroke={INK} strokeWidth={2.5} />
            </g>
          )}
          {vest && (
            <g>
              <Sh d={`M${-sw + 14} ${shY + 6} L${-14} ${shY - 2} L0 ${shY + 60} L${14} ${shY - 2} L${sw - 14} ${shY + 6} L${hw - 2} ${hipY + 4} L${-hw + 2} ${hipY + 4}Z`} fill={g} penOp={0.22} sw={3} />
              {[0, 1, 2].map((i) => <path key={i} d={circle(0, shY + 80 + i * 34, 4.5)} fill={GOLD} stroke={INK} strokeWidth={1.5} />)}
            </g>
          )}
          {bib && (
            <g>
              <Sh d={`M${-34} ${shY + 50} L34 ${shY + 50} L${hw} ${hipY + 4} L${-hw} ${hipY + 4}Z`} fill={g} penOp={0.22} sw={3} />
              <path d={`M-28 ${shY + 52} L-40 ${shY - 2} M28 ${shY + 52} L40 ${shY - 2}`} stroke={g} strokeWidth={9} />
              <path d={`M-28 ${shY + 52} L-40 ${shY - 2} M28 ${shY + 52} L40 ${shY - 2}`} stroke={INK} strokeWidth={2} />
            </g>
          )}
          {p.garment === "labcoat" && <path d={`M0 ${shY + 70} L0 ${hipY + coatLen - 10}`} stroke={INK} strokeWidth={2.5} />}
        </g>
      )}
      {/* neck and head */}
      <rect x={hx - 14} y={shY - 28} width={28} height={30} fill={skin} stroke={INK} strokeWidth={3} />
      <g transform={`rotate(${q.head} ${hx} ${shY - 10})`}>
        <Sh d={circle(hx, hy, R)} fill={skin} pen="none" sw={3.5} />
        {/* nose to the facing side, an ear on the far side */}
        <path d={`M${hx + R - 6} ${hy - 6} q16 12 2 20`} fill={skin} stroke={INK} strokeWidth={3} strokeLinejoin="round" />
        <path d={ellipse(hx - R * 0.42, hy + 8, 10, 14)} fill={skin} stroke={INK} strokeWidth={2.5} />
        <path d={`M${hx - R * 0.42 - 3} ${hy + 2} q5 6 0 12`} fill="none" stroke={INK} strokeWidth={2} opacity={0.6} />
        <path d={circle(hx + R * 0.38, hy - 6, 5)} fill={INK} />
        {pose === "surprised" ? (
          <path d={ellipse(hx + R * 0.42, hy + R * 0.48, 6, 8)} fill={INK} />
        ) : (
          <path d={`M${hx + R * 0.24} ${hy + R * 0.5} q10 4 18 -2`} fill="none" stroke={INK} strokeWidth={2.5} strokeLinecap="round" />
        )}
        {p.face === "moustache" && <path d={`M${hx + R * 0.14} ${hy + R * 0.34} q16 -10 34 2 q-16 8 -34 -2z`} fill={HAIR_HEX[p.hairColor]} stroke={INK} strokeWidth={2} />}
        {p.face === "beard" && (
          <Sh d={`M${hx - R * 0.55} ${hy + 6} Q${hx - R * 0.5} ${hy + R * 1.3} ${hx + R * 0.35} ${hy + R * 1.1} Q${hx + R * 0.95} ${hy + R * 0.7} ${hx + R * 0.86} ${hy + R * 0.3} Q${hx + R * 0.5} ${hy + R * 0.62} ${hx + R * 0.1} ${hy + R * 0.42} Q${hx - R * 0.3} ${hy + R * 0.4} ${hx - R * 0.55} ${hy + 6}Z`}
            fill={HAIR_HEX[p.hairColor]} penOp={0.25} sw={2.5} />
        )}
        <Hair p={p} hx={hx} hy={hy} r={R} back={false} />
        <Hat p={p} hx={hx} hy={hy} r={R} />
      </g>
      {/* near arm */}
      <ArmView x={sw - 12} y={shY + 14} a={q.near} sleeve={sleeve} skin={skin} long={longSleeve} />
      {/* the lab coat's pocket pen, a small brass watch chain on the waistcoat: touches that read as costume */}
      {p.garment === "labcoat" && <path d={`M${-30} ${shY + 60}h4v-22h-4z`} fill={GOLD} stroke={INK} strokeWidth={1.5} />}
      {p.garment === "waistcoat" && <path d={`M-30 ${hipY - 30} q20 16 30 0`} fill="none" stroke={GOLD} strokeWidth={3} />}
    </g>
  );
};

/** A colour a little darker, for the far limb. */
function shade(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.max(0, Math.round(v * 0.8));
  const r = f(n >> 16), gg = f((n >> 8) & 255), b = f(n & 255);
  return `#${((r << 16) | (gg << 8) | b).toString(16).padStart(6, "0")}`;
}

export function personKey(p: Person): string {
  return `${p.build}.${p.skin}.${p.hair}.${p.hairColor}.${p.face}.${p.hat}.${p.garment}.${p.color}`;
}

/** A person in a pose as a cached drawing (feet at PERSON_BOX.footX/footY). */
export function personDrawing(p: Person, pose: PersonPose): Drawing {
  return {
    key: `person:${personKey(p)}:${pose}`,
    width: PERSON_BOX.width,
    height: PERSON_BOX.height,
    render: () => (
      <g transform={`translate(${PERSON_BOX.footX} ${PERSON_BOX.footY})`}>
        <PersonFigure p={p} pose={pose} />
      </g>
    ),
  };
}
