// The visual half of the part gate (TMDEV-181): one agent-made part on a lit
// gallery terrace, with the things the vision judge needs for scale and style
// beside it — a bystander (1.5-1.8 m) on one side, a kit crate (0.8 m) on the
// other, and the 1 m measuring stick. Rendered twice by gate/gateCli.ts, from
// the three-quarter view and nearly end-on, then shown to the judge.
// Props: { spec: PartSpec; view?: "quarter" | "end"; night?: boolean }
import * as THREE from "three";
import { compilePart } from "../partCompile";
import { deriveDims, type PartSpec } from "../partGrammar";
import { CODE_PARTS } from "../partSpecs/code/index";
import { measureCodePart } from "../partSpecs/code/measure";
import { makePart } from "../parts";
import { Figure, figureHeight, type FigureSpec } from "../../kit/Figure";
import { GalleryView, type Page } from "./PartsGallery";

const VIEW_YAW = { quarter: -0.45, end: -1.25, close: -0.45 } as const;
/** the gate's style companion for a cast figure: drawn by the same drawer, so "the same cast" is judged against a
 *  person in the house style (the hand-made kit bystander has filled sleeves and trousers, and failed correct figures) */
export const TOWNSMAN: FigureSpec = { blurb: "a townsman", jacket: "#5d7a3a", pants: "#3b3f52", boots: "#4a3426", hat: "hair", hair: "#4a3020", skin: 1, seed: 11 };
export type GateView = keyof typeof VIEW_YAW;

/** a code part shown through the same page: its dims are measured, its group comes from makePart */
export const codeGateSpec = (name: string): PartSpec => ({ name, blurb: CODE_PARTS[name].blurb, prims: [] });

export const gatePage = (spec: PartSpec, view: GateView): Page => {
  const isCode = !!CODE_PARTS[spec.name] && spec.prims.length === 0;
  const d = isCode ? measureCodePart(spec.name) : deriveDims(spec);
  const yaw = VIEW_YAW[view];
  const gap = 0.5;
  // the flankers stand across the screen: along the part's x in the 3/4 view,
  // along its z when it is seen end-on (its x then runs toward the camera)
  const across = view === "end" ? d.d : d.w;
  const w = across + 2 * gap + 0.9 + 0.8; // part, a bystander and a crate with gaps between
  const tall = Math.max(d.h, 1.8);
  const along = view === "end" ? Math.max(d.w, 0.8) : Math.max(d.d, 0.8);
  return {
    title: `Gate: ${spec.name} (${view} view)`,
    cols: 1, rows: 1, sx: w + 0.4, fit: Math.max(w * 0.9, tall * 0.85, along * 0.75), yaw,
    items: [{
      label: spec.name,
      sub: `${d.w} x ${d.h} x ${d.d} m; bystander and 0.8 m crate for scale`,
      size: { w, h: tall, d: along, zc: 0 },
      stick: true,
      build: (m, ctx, make) => {
        const g = new THREE.Group();
        g.add(isCode ? makePart(spec.name, 3, m, ctx) : compilePart(spec, 3, m, ctx));
        const by = make("bystander", 2, m, ctx);
        const crate = make("crate", 3, m, ctx);
        const left = -(across / 2 + gap + 0.45);
        const right = across / 2 + gap + 0.4;
        if (view === "end") {
          by.position.z = -left;
          crate.position.z = -right;
          by.rotation.y = -yaw; // the card faces the camera, not the part
        } else {
          by.position.x = left;
          crate.position.x = right;
        }
        g.add(by, crate);
        return g;
      },
    }],
  };
};

/** a cast figure on the gate terrace: standing, then mid-wave, beside the bystander and the crate */
export const figurePage = (name: string, fig: FigureSpec, view: GateView): Page => {
  const h = figureHeight(fig);
  const yaw = VIEW_YAW[view];
  if (view === "close") {
    // the figure alone, filling the frame: a moustache, a cap brim or a held paper must be visible to be judged
    return {
      title: `Gate: ${name} (close)`,
      cols: 1, rows: 1, sx: 1.2, fit: h * 0.9, yaw,
      items: [{
        label: name, sub: `${h.toFixed(2)} m tall`, size: { w: 0.7, h, d: 0.1, zc: 0 }, stick: false,
        build: () => {
          const g = new THREE.Group();
          const f = new Figure(fig);
          f.redraw({ phase: 0, walk: 0, lid: 0, gesture: "none", beat: 1 });
          f.mesh.rotation.y = -yaw;
          g.add(f.mesh);
          return g;
        },
      }],
    };
  }
  const w = 0.9 + 0.5 + 0.9 + 0.5 + 0.8;
  return {
    title: `Gate: ${name} (${view} view)`,
    cols: 1, rows: 1, sx: w + 0.4, fit: Math.max(w * 0.9, 1.9 * 0.85), yaw,
    items: [{
      label: name,
      sub: `${h.toFixed(2)} m tall; townsman and 0.8 m crate for scale`,
      size: { w, h: Math.max(h, 1.8), d: 0.8, zc: 0 },
      stick: true,
      build: (m, ctx, make) => {
        const g = new THREE.Group();
        const f = new Figure(fig);
        f.redraw({ phase: 0, walk: 0, lid: 0, gesture: view === "end" ? "wave" : "none", beat: 1 });
        f.mesh.rotation.y = -yaw; // the card faces the camera
        g.add(f.mesh);
        const tm = new Figure(TOWNSMAN);
        tm.redraw({ phase: 0, walk: 0, lid: 0, gesture: "none", beat: 1 });
        const by = tm.mesh;
        const crate = make("crate", 3, m, ctx);
        const left = -(0.45 + 0.5 + 0.45), right = 0.45 + 0.5 + 0.4;
        if (view === "end") {
          // seen end-on the row runs toward the camera: spread the flankers along z instead
          by.position.z = -left;
          crate.position.z = -right;
        } else {
          by.position.x = left;
          crate.position.x = right;
        }
        by.rotation.y = -yaw;
        g.add(by, crate);
        return g;
      },
    }],
  };
};

export const PartGate: React.FC<Record<string, unknown>> = (props) => {
  const code = props.code as string | undefined;
  const view = (props.view as GateView | undefined) ?? "quarter";
  const v: GateView = view in VIEW_YAW ? view : "quarter";
  if (props.figure) return <GalleryView page={figurePage(String(props.figureName ?? "figure"), props.figure as FigureSpec, v)} night={!!props.night} />;
  const spec = code ? codeGateSpec(code) : (props.spec as PartSpec | undefined);
  if (!spec) throw new Error("PartGate needs a spec, code or figure prop");
  return <GalleryView page={gatePage(spec, v)} night={!!props.night} />;
};
