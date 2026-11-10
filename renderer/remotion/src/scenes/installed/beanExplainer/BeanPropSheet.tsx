/*
 * The Bean Explainer model sheet: everything the agent can put on stage, drawn
 * once so a person can approve it. One page per frame:
 *   0  the bean's poses
 *   1  its faces
 *   2  its accessories (with the tints) and reaction marks
 *   3+ the prop library, each with a sample text and its act part-way through
 * Render a page with `npx remotion still src/index.ts BeanPropSheet out.png --frame=<page>`.
 * Not used by any video.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { HAND, ROUND, useBeanFonts } from "../BeanExplainer";
import { Bean, INK } from "./bean";
import { ACCESSORIES, FACES, FIELDS, MARKS, POSES, PROPS, TINTS, type Accessory, type Face, type MarkType, type Pose, type PropId, type Tint } from "./contract";
import { DRAWINGS, WHOLE_PROP_ACTS, wholePropMotion } from "./props";

const SAMPLE_TEXT: Partial<Record<PropId, string>> = {
  phone: "Your account is locked", browser: "paypa1.com", laptop: "ERROR 404", sign: "WET FLOOR", document: "TERMS",
  note: "buy milk", speech: "Wait, what?", thought: "Did I lock it?", pricetag: "$4.99", calendar: "MON",
  envelope: "URGENT!!", banknote: "$100", creditcard: "4242 4242", chartup: "SAVINGS", chartdown: "SLEEP",
};
const PROP_IDS = Object.keys(PROPS) as PropId[];
export const PROPS_PER_PAGE = 12;
const FIRST_PROP_PAGE = 3;
export const SHEET_PAGES = FIRST_PROP_PAGE + Math.ceil(PROP_IDS.length / PROPS_PER_PAGE);

const Caption: React.FC<{ x: number; y: number; text: string }> = ({ x, y, text }) => (
  <text x={x} y={y} textAnchor="middle" fontSize={34} fill={INK} style={{ fontFamily: HAND }}>{text}</text>
);

type BeanAtProps = { x: number; y: number; s: number; pose?: Pose; face?: Face; accessory?: Accessory; tint?: Tint; mark?: MarkType; uid: string };
const BeanAt: React.FC<BeanAtProps> = (p) => (
  <Bean frame={40} fps={30} x={p.x} y={p.y} scale={p.s} pose={p.pose ?? "stand"} prevPose={p.pose ?? "stand"} poseT={1}
    face={p.face ?? "neutral"} look="front" swapFrame={-100} marks={p.mark ? [{ type: p.mark, start: 10 }] : []} enter={1}
    accessory={p.accessory ?? "none"} tint={p.tint ?? "cream"} seed={0} font={ROUND} uid={p.uid} />
);

/** Beans on a grid: `cols` across, each cell `cellH` tall, feet near the cell's bottom. */
function Grid({ items, cols, top, cellH, scale }: { items: (Omit<BeanAtProps, "x" | "y" | "s" | "uid"> & { caption: string })[]; cols: number; top: number; cellH: number; scale: number }) {
  const cellW = 1080 / cols;
  return (
    <g>
      {items.map((it, i) => {
        const x = cellW * (i % cols) + cellW / 2;
        const feet = top + Math.floor(i / cols) * cellH + cellH - 70;
        const { caption, ...bean } = it;
        return (
          <g key={i}>
            <BeanAt {...bean} x={x} y={feet} s={scale} uid={`g${top}-${i}`} />
            <Caption x={x} y={feet + 50} text={caption} />
          </g>
        );
      })}
    </g>
  );
}

function PropsPage({ page }: { page: number }) {
  const ids = PROP_IDS.slice(page * PROPS_PER_PAGE, (page + 1) * PROPS_PER_PAGE);
  return (
    <g>
      {ids.map((id, i) => {
        const cx = 190 + (i % 3) * 350, cy = 330 + Math.floor(i / 3) * 420;
        const box = PROPS[id];
        const k = Math.min(1, 300 / box.w, 300 / box.h);
        const act = box.acts[0] ?? "";
        const whole = (WHOLE_PROP_ACTS as readonly string[]).includes(act);
        // whole-prop acts are motion; the sheet shows the prop at rest
        const [mx, my, mr, ms, pivot] = whole ? wholePropMotion(act, 400, box.h) : [0, 0, 0, 1, 0];
        const Draw = DRAWINGS[id];
        return (
          <g key={id}>
            <rect x={cx - 165} y={cy - 170} width={330} height={340} rx={18} fill="none" stroke={INK} strokeWidth={2} opacity={0.25} />
            <g transform={`translate(${cx + mx} ${cy + my}) scale(${k * ms}) rotate(${mr} 0 ${pivot})`}>
              <Draw frame={40} actT={act && !whole ? 10 : -1} text={SAMPLE_TEXT[id] ?? ""} round={ROUND} hand={HAND} />
            </g>
            <Caption x={cx} y={cy + 205} text={act ? `${id} · ${act}` : id} />
          </g>
        );
      })}
    </g>
  );
}

/**
 * Measure mode (`--props='{"measure":"<prop>"}'`): the prop alone, centred on
 * white at scale 1, drawn at its rest and at many moments of its act on top of
 * one another, so the inked pixels are every place the drawing can reach. Its
 * PROPS box in contract.ts is sized from this picture. Whole-prop acts (a spin,
 * a swing) are left out: they last under a second.
 */
const Measure: React.FC<{ id: PropId }> = ({ id }) => {
  const Draw = DRAWINGS[id];
  const act = PROPS[id].acts[0] ?? "";
  const drawn = act && !(WHOLE_PROP_ACTS as readonly string[]).includes(act);
  const moments = [-1, ...(drawn ? [0, 3, 6, 9, 12, 16, 20, 25, 30, 40, 50, 60] : [])];
  return (
    <AbsoluteFill style={{ background: "#ffffff" }}>
      <svg width={1080} height={1920}>
        <g transform="translate(540 960)">
          {moments.map((t) => (
            <Draw key={t} frame={t < 0 ? 0 : t} actT={t} text={SAMPLE_TEXT[id] ? "W".repeat(PROPS[id].text) : ""} round={ROUND} hand={HAND} />
          ))}
        </g>
      </svg>
    </AbsoluteFill>
  );
};

export const BeanPropSheet: React.FC<{ measure?: string }> = ({ measure }) => {
  const page = useCurrentFrame();
  useBeanFonts("BeanPropSheet");
  if (measure && measure in PROPS) return <Measure id={measure as PropId} />;
  const titles = ["Bean Explainer: poses", "faces", "accessories, tints, marks"];
  const title = titles[page] ?? `props ${page - FIRST_PROP_PAGE + 1} of ${SHEET_PAGES - FIRST_PROP_PAGE}`;
  return (
    <AbsoluteFill style={{ background: FIELDS.yellow }}>
      <svg width={1080} height={1920}>
        <text x={540} y={110} textAnchor="middle" fontSize={64} fontWeight={700} fill={INK} style={{ fontFamily: ROUND }}>{title}</text>
        {page === 0 && <Grid cols={4} top={150} cellH={590} scale={0.52} items={POSES.map((pose) => ({ pose, caption: pose }))} />}
        {page === 1 && <Grid cols={4} top={150} cellH={860} scale={0.8} items={FACES.map((face) => ({ face, caption: face }))} />}
        {page === 2 && (
          <>
            <Grid cols={4} top={150} cellH={430} scale={0.42}
              items={ACCESSORIES.map((accessory, i) => ({ accessory, tint: TINTS[i % TINTS.length], face: "happy" as Face, caption: `${accessory} · ${TINTS[i % TINTS.length]}` }))} />
            <Grid cols={4} top={1010} cellH={430} scale={0.42} items={MARKS.map((mark) => ({ mark, face: "shocked" as Face, caption: mark }))} />
          </>
        )}
        {page >= FIRST_PROP_PAGE && <PropsPage page={page - FIRST_PROP_PAGE} />}
      </svg>
    </AbsoluteFill>
  );
};
