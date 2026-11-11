/*
 * The Storybook Atlas model sheet: the guide, the people and the backdrops,
 * drawn once so a person can approve them. One page per frame:
 *   0  the guide's poses
 *   1  people: a cast of examples
 *   2  one person in every pose
 *   3  the knobs: hats, hair and faces
 *   4+ each backdrop as a whole chapter frame (plaque, guide, a person, the caption label)
 * Render a page with `npx remotion still src/index.ts StorybookSheet out.png --frame=<page>`.
 * With `--props='{"hold":<page>,"frames":<n>}'` every one of n frames shows that
 * page, with a chapter page's plaque arriving as the frames run: a render-cost
 * probe. `"drop":["backdrop","plaque","person","guide","caption"]` leaves layers
 * out, to measure what each one costs.
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
import { BANDS, INK, IVORY, SERIF, TEXT, W } from "./palette";

const FIRST_BACKDROP_PAGE = 4;
export const SHEET_PAGES = FIRST_BACKDROP_PAGE + BACKDROPS.length;

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

const SAMPLE_CHAPTERS: Record<Backdrop, { title: string; byline: string; caption: string; person: number; pose: "point" | "hold" | "think" }> = {
  study: { title: "The Notes", byline: "London, 1843", caption: "Ada wrote what no one else could see.", person: 0, pose: "hold" },
  workshop: { title: "The Workshop", byline: "Menlo Park, 1879", caption: "Edison tried a thousand filaments.", person: 2, pose: "think" },
  nightsky: { title: "The Spark", byline: "Colorado Springs, 1899", caption: "Tesla listened to the night sky.", person: 3, pose: "point" },
};

function ChapterPage({ b, n, t, drop = [] }: { b: Backdrop; n: number; t: number; drop?: string[] }) {
  const c = SAMPLE_CHAPTERS[b];
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

export const StorybookSheet: React.FC<{ hold?: number; frames?: number; drop?: string[] }> = ({ hold, drop }) => {
  useStorybookFonts("StorybookSheet");
  const frame = useCurrentFrame();
  const page = hold ?? frame;
  return (
    <AbsoluteFill>
      {page < FIRST_BACKDROP_PAGE && <CanvasBitmap d={PAPER} />}
      {page === 0 && <GuidePage />}
      {page === 1 && <CastPage />}
      {page === 2 && <PosesPage />}
      {page === 3 && <KnobsPage />}
      {page >= FIRST_BACKDROP_PAGE && <ChapterPage b={BACKDROPS[page - FIRST_BACKDROP_PAGE]} n={page - FIRST_BACKDROP_PAGE} t={hold === undefined ? 60 : frame} drop={drop} />}
    </AbsoluteFill>
  );
};
