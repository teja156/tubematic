/*
 * The Storybook Atlas model sheet: the guide, the people and the backdrops,
 * drawn once so a person can approve them. One page per frame:
 *   0  the guide's poses
 *   1  people: a cast of examples
 *   2  one person in every pose
 *   3  the knobs: hats, hair and faces
 *   4+ each backdrop as a whole chapter frame (plaque, guide, a person, the caption label)
 *   then the prop library, every state of each prop in its box, with a check
 *      that the drawing fits the box (red when it overflows)
 * Render a page with `npx remotion still src/index.ts StorybookSheet out.png --frame=<page>`.
 * With `--props='{"hold":<page>,"frames":<n>}'` every one of n frames shows that
 * page, with a chapter page's plaque arriving as the frames run: a render-cost
 * probe. `"drop":["backdrop","plaque","person","guide","caption"]` leaves layers
 * out, to measure what each one costs.
 * `{"group":"<prop group>"}` shows only that group's props, from frame 0;
 * `{"chapter":"<backdrop>"}` shows only that backdrop's chapter frame.
 * Not used by any video.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Bitmap, CanvasBitmap, type Drawing } from "./bitmap";
import { BACKDROPS, backdropDrawing, paperDrawing, type Backdrop } from "./backdrops";
import { FACES, HATS, HAIRS, PERSON_BOX, PERSON_POSES, personDrawing, type Person } from "./figure";
import { NUMERALS, Plaque } from "./frame";
import { useStorybookFonts } from "./fonts";
import { GUIDE_BOX, GUIDE_POSES, guideDrawing } from "./guide";
import { PROPS, PROP_GROUPS } from "./props";
import { BoxCheck, libraryDrawing } from "./props/draw";
import { BANDS, INK, IVORY, SERIF, TEXT, W } from "./palette";

const FIRST_BACKDROP_PAGE = 4;
const FIRST_PROP_PAGE = FIRST_BACKDROP_PAGE + BACKDROPS.length;
const PROP_IDS = Object.keys(PROPS);
const PROPS_PER_PAGE = 9;
export const SHEET_PAGES = FIRST_PROP_PAGE + Math.ceil(PROP_IDS.length / PROPS_PER_PAGE);

/** A figure drawing with its feet at (x, y), scaled and optionally mirrored. */
export const Placed: React.FC<{ d: Drawing; box: { footX: number; footY: number }; x: number; y: number; s?: number; flip?: boolean }> = ({
  d, box, x, y, s = 1, flip,
}) => (
  <Bitmap d={d} left={x - box.footX} top={y - box.footY}
    transform={s !== 1 || flip ? `scale(${flip ? -s : s}, ${s})` : undefined} origin={[box.footX, box.footY]} />
);

const Label: React.FC<{ x: number; y: number; text: string; size?: number }> = ({ x, y, text, size = 30 }) => (
  <div style={{ position: "absolute", left: x - 200, top: y, width: 400, textAlign: "center", fontFamily: SERIF, fontSize: size, color: TEXT }}>{text}</div>
);

/** A preview of the caption label (the real one is drawn by Subtitles with background "label"). */
const SampleCaption: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ position: "absolute", left: 0, width: W, top: 1520, display: "flex", justifyContent: "center" }}>
    <div style={{
      background: IVORY, color: TEXT, fontFamily: SERIF, fontWeight: 500, fontSize: 56, lineHeight: 1.12, padding: "14px 34px 18px",
      border: `2px solid ${INK}`, boxShadow: "5px 6px 0 rgba(47,34,24,0.22)", display: "flex", alignItems: "center", gap: 22,
      maxWidth: 900, textAlign: "center",
    }}>
      <span style={{ width: 12, height: 12, background: TEXT, transform: "rotate(45deg)", flex: "none" }} />
      <span>{text}</span>
      <span style={{ width: 12, height: 12, background: TEXT, transform: "rotate(45deg)", flex: "none" }} />
    </div>
  </div>
);

export const SAMPLE_CAST: (Person & { name: string })[] = [
  { name: "Ada Lovelace", build: "short", skin: "light", hair: "bun", hairColor: "dark", face: "none", hat: "none", garment: "dress", color: "plum" },
  { name: "Charles Babbage", build: "tall", skin: "light", hair: "bald", hairColor: "grey", face: "none", hat: "tophat", garment: "frockcoat", color: "ink" },
  { name: "Thomas Edison", build: "tall", skin: "light", hair: "short", hairColor: "grey", face: "none", hat: "none", garment: "suit", color: "navy" },
  { name: "Nikola Tesla", build: "tall", skin: "light", hair: "short", hairColor: "dark", face: "moustache", hat: "bowler", garment: "frockcoat", color: "ink" },
  { name: "Grace Hopper", build: "short", skin: "light", hair: "curly", hairColor: "grey", face: "none", hat: "none", garment: "suit", color: "navy" },
  { name: "Lab assistant", build: "short", skin: "brown", hair: "short", hairColor: "dark", face: "beard", hat: "none", garment: "labcoat", color: "moss" },
  { name: "Typesetter", build: "tall", skin: "tan", hair: "short", hairColor: "brown", face: "none", hat: "cap", garment: "overalls", color: "brick" },
  { name: "Telegraph clerk", build: "short", skin: "deep", hair: "long", hairColor: "dark", face: "none", hat: "bonnet", garment: "waistcoat", color: "ochre" },
];

const PAPER = paperDrawing();

function GuidePage() {
  return (
    <>
      <Label x={540} y={120} text="The guide: every pose (waistcoat colours vary)" size={40} />
      {GUIDE_POSES.map((pose, i) => {
        const col = i % 3, row = Math.floor(i / 3);
        const x = 200 + col * 340, y = 560 + row * 400;
        const coat = (["blue", "sage", "brick", "plum", "mustard"] as const)[i % 5];
        return (
          <React.Fragment key={pose}>
            <Placed d={guideDrawing(pose, coat)} box={GUIDE_BOX} x={x} y={y} s={1.2} />
            <Label x={x} y={y + 30} text={pose} />
          </React.Fragment>
        );
      })}
    </>
  );
}

function CastPage() {
  return (
    <>
      <Label x={540} y={60} text="People: knobs, not likenesses" size={40} />
      {SAMPLE_CAST.map((p, i) => {
        const col = i % 4, row = Math.floor(i / 4);
        const x = 150 + col * 260, y = 900 + row * 820;
        return (
          <React.Fragment key={p.name}>
            <Placed d={personDrawing(p, "stand")} box={PERSON_BOX} x={x} y={y} s={0.95} />
            <Label x={x} y={y + 24} text={p.name} size={28} />
          </React.Fragment>
        );
      })}
    </>
  );
}

function PosesPage() {
  const p = SAMPLE_CAST[3];
  return (
    <>
      <Label x={540} y={60} text={`${p.name}: every pose`} size={40} />
      {PERSON_POSES.map((pose, i) => {
        const col = i % 4, row = Math.floor(i / 4);
        const x = 150 + col * 260, y = 860 + row * 820;
        return (
          <React.Fragment key={pose}>
            <Placed d={personDrawing(p, pose)} box={PERSON_BOX} x={x} y={y} s={0.9} />
            <Label x={x} y={y + 24} text={pose} size={28} />
          </React.Fragment>
        );
      })}
    </>
  );
}

function KnobsPage() {
  const base: Person = { build: "tall", skin: "tan", hair: "short", hairColor: "brown", face: "none", hat: "none", garment: "suit", color: "moss" };
  const rows: { title: string; items: Person[]; names: string[] }[] = [
    { title: "hats", items: HATS.map((hat) => ({ ...base, hat, hair: hat === "bonnet" ? "long" : base.hair })), names: [...HATS] },
    { title: "hair", items: HAIRS.map((hair) => ({ ...base, hair, garment: "dress", color: "brick", build: "short" as const })), names: [...HAIRS] },
    { title: "faces and garments", items: [...FACES.map((face) => ({ ...base, face, garment: "waistcoat" as const })), { ...base, garment: "labcoat" }, { ...base, garment: "overalls", hat: "cap" }], names: [...FACES, "labcoat", "overalls"] },
  ];
  return (
    <>
      {rows.map((r, ri) => (
        <React.Fragment key={r.title}>
          <Label x={540} y={60 + ri * 620} text={r.title} size={36} />
          {r.items.map((p, i) => {
            const x = 120 + i * 210, y = 610 + ri * 620;
            return (
              <React.Fragment key={i}>
                <Placed d={personDrawing(p, "stand")} box={PERSON_BOX} x={x} y={y} s={0.68} />
                <Label x={x} y={y + 8} text={r.names[i]} size={26} />
              </React.Fragment>
            );
          })}
        </React.Fragment>
      ))}
    </>
  );
}

type SampleChapter = { title: string; byline: string; caption: string; person: number; pose: "point" | "hold" | "think" };
const SAMPLE_CHAPTERS: Partial<Record<Backdrop, SampleChapter>> = {
  study: { title: "The Notes", byline: "London, 1843", caption: "Ada wrote what no one else could see.", person: 0, pose: "hold" },
  workshop: { title: "The Workshop", byline: "Menlo Park, 1879", caption: "Edison tried a thousand filaments.", person: 2, pose: "think" },
  nightsky: { title: "The Spark", byline: "Colorado Springs, 1899", caption: "Tesla listened to the night sky.", person: 3, pose: "point" },
  laboratory: { title: "The Laboratory", byline: "Paris, 1898", caption: "The flasks held a new kind of light.", person: 5, pose: "hold" },
  street: { title: "The High Street", byline: "London, 1812", caption: "Gas lamps lit the street for the first time.", person: 1, pose: "point" },
  countryside: { title: "The Fields", byline: "Berkshire, 1701", caption: "Jethro Tull sowed his seeds in rows.", person: 2, pose: "think" },
  harbour: { title: "The Harbour", byline: "Bristol, 1838", caption: "The tall ships waited for the morning tide.", person: 7, pose: "point" },
  blueprint: { title: "The Plan", byline: "Philadelphia, 1946", caption: "Every wire was drawn before it was built.", person: 4, pose: "think" },
  factory: { title: "The Mill", byline: "Manchester, 1790", caption: "One engine turned a hundred spindles.", person: 6, pose: "point" },
  maproom: { title: "The Chart Room", byline: "Lisbon, 1760", caption: "Every voyage began with a better map.", person: 3, pose: "point" },
};

function ChapterPage({ b, n, t, drop = [] }: { b: Backdrop; n: number; t: number; drop?: string[] }) {
  const c: SampleChapter = SAMPLE_CHAPTERS[b] ?? { title: "A Chapter", byline: "Somewhere, 1900", caption: "The story went on from here.", person: 4, pose: "point" };
  const on = (k: string) => !drop.includes(k);
  return (
    <>
      {on("backdrop") && <CanvasBitmap d={backdropDrawing(b)} />}
      {on("plaque") && <Plaque t={t} numeral={NUMERALS[n]} title={c.title} byline={c.byline} />}
      {on("person") && <Placed d={personDrawing(SAMPLE_CAST[c.person], c.pose)} box={PERSON_BOX} x={600} y={BANDS.floor} />}
      {on("guide") && <Placed d={guideDrawing(b === "nightsky" ? "look" : "point", "blue")} box={GUIDE_BOX} x={330} y={BANDS.floor} s={1} />}
      {on("caption") && <SampleCaption text={c.caption} />}
    </>
  );
}

/** Nine props a page, in a 3 x 3 grid; each state side by side, fitted to its cell, the box outlined. */
function PropsPage({ page, group }: { page: number; group?: string }) {
  const all = group ? Object.keys(PROP_GROUPS[group] ?? {}) : PROP_IDS;
  const ids = all.slice(page * PROPS_PER_PAGE, (page + 1) * PROPS_PER_PAGE);
  return (
    <>
      {ids.map((id, i) => {
        const e = PROPS[id];
        const cellW = 360, cellH = 600;
        const cx = (i % 3) * cellW + cellW / 2, base = 120 + Math.floor(i / 3) * cellH + 420;
        const [w, h] = e.box;
        const s = Math.min(1, 320 / (w * e.states + 20 * (e.states - 1)), 400 / h);
        const total = (w * e.states + 20 * (e.states - 1)) * s;
        return (
          <React.Fragment key={id}>
            {Array.from({ length: e.states }, (_, st) => {
              const left = cx - total / 2 + st * (w + 20) * s;
              return (
                <React.Fragment key={st}>
                  <div style={{ position: "absolute", left, top: base - h * s, width: w * s, height: h * s, outline: "1px dashed rgba(47,34,24,0.35)" }} />
                  <Bitmap d={libraryDrawing(id, st)} left={left} top={base - h * s}
                    transform={s === 1 ? undefined : `scale(${s})`} origin={[0, 0]} />
                </React.Fragment>
              );
            })}
            <Label x={cx} y={base + 10} text={`${id} (${e.place})`} size={28} />
            <div style={{ position: "absolute", left: cx - 170, top: base + 50, width: 340, textAlign: "center", fontFamily: SERIF, fontSize: 22, color: TEXT }}>
              {e.acts.join(", ")}{e.portal ? ", portal" : ""}
            </div>
            <BoxCheck entry={e} x={cx} y={base + 80} />
          </React.Fragment>
        );
      })}
    </>
  );
}

export const StorybookSheet: React.FC<{ hold?: number; frames?: number; drop?: string[]; group?: string; chapter?: Backdrop }> = ({
  hold, drop, group, chapter,
}) => {
  useStorybookFonts("StorybookSheet");
  const frame = useCurrentFrame();
  if (group) {
    return (
      <AbsoluteFill>
        <CanvasBitmap d={PAPER} />
        <PropsPage page={frame} group={group} />
      </AbsoluteFill>
    );
  }
  if (chapter) {
    return (
      <AbsoluteFill>
        <ChapterPage b={chapter} n={Math.max(0, BACKDROPS.indexOf(chapter)) % 5} t={60} />
      </AbsoluteFill>
    );
  }
  const page = hold ?? frame;
  return (
    <AbsoluteFill>
      {(page < FIRST_BACKDROP_PAGE || page >= FIRST_PROP_PAGE) && <CanvasBitmap d={PAPER} />}
      {page === 0 && <GuidePage />}
      {page === 1 && <CastPage />}
      {page === 2 && <PosesPage />}
      {page === 3 && <KnobsPage />}
      {page >= FIRST_PROP_PAGE && <PropsPage page={page - FIRST_PROP_PAGE} />}
      {page >= FIRST_BACKDROP_PAGE && page < FIRST_PROP_PAGE && <ChapterPage b={BACKDROPS[page - FIRST_BACKDROP_PAGE]} n={(page - FIRST_BACKDROP_PAGE) % 5} t={hold === undefined ? 60 : frame} drop={drop} />}
    </AbsoluteFill>
  );
};
