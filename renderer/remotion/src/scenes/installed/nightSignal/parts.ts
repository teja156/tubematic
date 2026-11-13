/*
 * Night Signal's pictogram library, as data: every person pose, animal and
 * object is a list of flat shapes (circles, rounded rectangles, round-capped
 * lines and polygons) in tones of the house palette, drawn by draw.ts on the
 * Canvas 2D picture band. An agent's own parts (`customParts`) use the same
 * shapes, so one drawing routine draws both and the part sheet shows exactly
 * what the video will.
 *
 * Coordinates: pixels at the band's scale, the origin at the middle of the
 * thing's feet, y negative upwards. A standing person is about 330 tall.
 *
 * "hole" is the canvas colour: a wide hole line under a limb leaves the gap
 * that keeps a joint readable without an outline.
 */
import type { Shape, Tone } from "./contract";

type Pt = [number, number];

const line = (points: Pt[], width: number, tone: Tone = "ink"): Shape => ({ shape: "line", points, width, tone });
const rect = (x: number, y: number, w: number, h: number, r = 0, tone: Tone = "ink"): Shape => ({ shape: "rect", x, y, w, h, r, tone });
const circle = (cx: number, cy: number, r: number, tone: Tone = "ink"): Shape => ({ shape: "circle", cx, cy, r, tone });
const poly = (points: Pt[], tone: Tone = "ink"): Shape => ({ shape: "poly", points, tone });

// ── people ─────────────────────────────────────────────────────────────────
interface PoseDef {
  legs: [Pt[], Pt[]];
  back: Pt[];
  front: Pt[];
  /** Torso and head move down by this much (sitting). */
  drop?: number;
  /** Lean of the torso and head, as an x shift of the head (running, scared). */
  lean?: number;
  extra?: Shape[];
}

const LEGS: [Pt[], Pt[]] = [[[-19, -118], [-21, -12]], [[19, -118], [21, -12]]];

export const POSES: Record<string, PoseDef> = {
  stand: { legs: LEGS, back: [[-30, -205], [-44, -150], [-40, -100]], front: [[30, -205], [44, -150], [40, -100]] },
  walk: {
    legs: [[[-15, -118], [-48, -12]], [[15, -118], [42, -12]]],
    back: [[-30, -205], [-62, -152], [-74, -112]], front: [[30, -205], [58, -152], [72, -110]],
  },
  point: { legs: LEGS, back: [[-30, -205], [-44, -150], [-40, -100]], front: [[30, -205], [96, -214], [158, -226]] },
  phone: {
    legs: LEGS, back: [[-30, -205], [-44, -150], [-40, -100]], front: [[30, -205], [62, -140], [104, -178]],
    extra: [rect(92, -234, 44, 72, 9), rect(99, -225, 30, 50, 4, "core")],
  },
  hold: { legs: LEGS, back: [[-30, -205], [-6, -160], [60, -168]], front: [[30, -205], [70, -150], [112, -166]] },
  scared: {
    legs: [[[-19, -118], [-34, -12]], [[19, -118], [30, -12]]], lean: -10,
    back: [[-30, -205], [-64, -250], [-48, -302]], front: [[30, -205], [64, -250], [48, -302]],
  },
  hands_up: { legs: LEGS, back: [[-30, -210], [-56, -292], [-66, -372]], front: [[30, -210], [56, -292], [66, -372]] },
  wave: { legs: LEGS, back: [[-30, -205], [-44, -150], [-40, -100]], front: [[30, -205], [78, -262], [96, -334]] },
  sit: {
    legs: [[[-15, -72], [54, -72], [56, -12]], [[15, -72], [78, -72], [80, -12]]], drop: 58,
    back: [[-30, -147], [-36, -96], [10, -88]], front: [[30, -147], [66, -110], [100, -112]],
    extra: [rect(-60, -66, 150, 14, 6, "grey"), line([[-46, -54], [-46, -10]], 12, "grey"), line([[76, -54], [76, -10]], 12, "grey")],
  },
  run: {
    legs: [[[-15, -118], [-58, -46], [-86, -30]], [[15, -118], [58, -76], [74, -12]]], lean: 18,
    back: [[-26, -205], [-70, -172], [-98, -184]], front: [[34, -205], [78, -196], [98, -240]],
  },
  sleep: {
    // Lying down, drawn whole below (the torso is horizontal).
    legs: [[], []], back: [], front: [],
  },
};

/** The shapes of a person in `pose`. The head is the last shape, so it can be drawn faceless (blurred). */
export function personShapes(pose: string): Shape[] {
  if (pose === "sleep") {
    return [
      line([[40, -58], [178, -58]], 32), line([[40, -30], [178, -30]], 32),
      rect(-120, -96, 170, 86, 36),
      line([[-70, -62], [20, -34]], 46, "hole"), line([[-70, -62], [20, -34]], 28),
      circle(-168, -60, 38),
    ];
  }
  const p = POSES[pose] ?? POSES.stand;
  const d = p.drop ?? 0;
  const lean = p.lean ?? 0;
  const shapes: Shape[] = [];
  shapes.push(line(p.back, 28));
  for (const leg of p.legs) shapes.push(line(leg, 32));
  shapes.push(rect(-44 + lean * 0.4, -238 + d, 88, 136, 36));
  shapes.push(line(p.front, 44, "hole"), line(p.front, 28));
  if (p.extra) shapes.push(...p.extra);
  shapes.push(circle(lean, -292 + d, 38));
  return shapes;
}

// ── animals ────────────────────────────────────────────────────────────────
export const ANIMALS: Record<string, Shape[]> = {
  dog: [
    rect(-90, -110, 150, 62, 30), line([[-70, -60], [-74, -10]], 18), line([[-40, -60], [-38, -10]], 18),
    line([[30, -60], [26, -10]], 18), line([[50, -60], [56, -10]], 18), line([[-86, -96], [-126, -132]], 14),
    circle(76, -128, 38), poly([[56, -158], [44, -196], [80, -164]]), rect(92, -124, 44, 26, 13),
    circle(86, -138, 5, "hole"),
  ],
  cat: [
    rect(-70, -96, 120, 54, 27), line([[-56, -50], [-58, -10]], 14), line([[34, -50], [36, -10]], 14),
    line([[-66, -78], [-110, -96], [-120, -150]], 12), circle(62, -120, 34),
    poly([[38, -142], [36, -186], [64, -152]]), poly([[74, -152], [96, -184], [92, -138]]), circle(74, -124, 4, "hole"),
  ],
  bear: [
    rect(-130, -190, 230, 130, 60), line([[-104, -80], [-106, -12]], 40), line([[-40, -80], [-38, -12]], 40),
    line([[40, -80], [42, -12]], 40), line([[80, -90], [84, -12]], 40), circle(118, -186, 58),
    circle(92, -238, 20), circle(150, -236, 20), rect(150, -184, 44, 34, 17), circle(126, -200, 6, "hole"),
  ],
  bird: [
    rect(-44, -70, 88, 46, 23), circle(34, -82, 20), poly([[50, -86], [76, -80], [50, -74]], "grey"),
    poly([[-20, -66], [-70, -100], [-10, -54]]), line([[-6, -26], [-8, -6]], 6), line([[10, -26], [12, -6]], 6),
    circle(38, -88, 3, "hole"),
  ],
};

// ── objects ────────────────────────────────────────────────────────────────
export const OBJECTS: Record<string, Shape[]> = {
  door: [rect(-80, -264, 160, 264, 0, "ink"), rect(-60, -244, 120, 92, 6, "dim"), circle(56, -124, 9, "hole")],
  doorway: [rect(-85, -264, 170, 264, 0, "hole"), line([[-85, 0], [-85, -264], [85, -264], [85, 0]], 10)],
  window: [rect(-90, -330, 180, 200, 8, "grey"), rect(-78, -318, 72, 84, 4, "hole"), rect(6, -318, 72, 84, 4, "hole"),
    rect(-78, -226, 72, 84, 4, "hole"), rect(6, -226, 72, 84, 4, "hole")],
  house: [poly([[-160, -200], [0, -330], [160, -200]]), rect(-130, -210, 260, 210, 6), rect(-34, -110, 68, 110, 4, "hole"),
    rect(-104, -170, 52, 48, 4, "hole"), rect(52, -170, 52, 48, 4, "hole")],
  car: [rect(-180, -96, 360, 66, 26), poly([[-110, -96], [-70, -158], [70, -158], [120, -96]]), poly([[-86, -100], [-58, -144], [-4, -144], [-4, -100]], "hole"),
    poly([[10, -100], [10, -144], [60, -144], [96, -100]], "hole"), circle(-104, -30, 32, "hole"), circle(-104, -30, 22), circle(104, -30, 32, "hole"), circle(104, -30, 22)],
  phone: [rect(-60, -220, 120, 220, 20), rect(-48, -204, 96, 180, 8, "hole"), rect(-20, -214, 40, 6, 3, "hole")],
  laptop: [rect(-120, -176, 240, 150, 10), rect(-106, -164, 212, 126, 6, "hole"), poly([[-150, -26], [150, -26], [168, 0], [-168, 0]])],
  qr: [],
  envelope: [rect(-110, -150, 220, 150, 10), poly([[-104, -144], [0, -64], [104, -144]], "hole"), poly([[-90, -144], [0, -78], [90, -144]])],
  wallet: [rect(-110, -130, 220, 130, 22), rect(40, -92, 80, 54, 18, "grey"), circle(80, -65, 9, "hole")],
  card: [rect(-130, -160, 260, 160, 18), rect(-130, -130, 260, 28, 0, "hole"), rect(-100, -60, 70, 40, 6, "grey")],
  lock: [line([[-44, -150], [-44, -200], [0, -236], [44, -200], [44, -150]], 22), rect(-74, -156, 148, 156, 22), circle(0, -92, 18, "hole"), rect(-7, -92, 14, 40, 6, "hole")],
  key: [circle(-70, -60, 46), circle(-70, -60, 18, "hole"), line([[-26, -60], [110, -60]], 22), line([[78, -60], [78, -24]], 18), line([[104, -60], [104, -32]], 18)],
  lamp: [line([[0, 0], [0, -392]], 12, "grey"), line([[0, -388], [0, -410], [-28, -410], [-50, -410]], 12, "grey"), rect(-66, -414, 34, 14, 6, "core")],
  tree: [line([[0, 0], [0, -150]], 26), circle(0, -210, 92), circle(-62, -170, 56), circle(62, -170, 56)],
  bed: [rect(-190, -78, 380, 46, 10), rect(-190, -150, 30, 150, 8), rect(160, -110, 30, 110, 8), rect(-160, -110, 90, 34, 16, "grey")],
  table: [rect(-200, -132, 400, 22, 8), line([[-170, -110], [-170, 0]], 18, "grey"), line([[170, -110], [170, 0]], 18, "grey")],
  atm: [rect(-90, -300, 180, 300, 14), rect(-70, -276, 140, 100, 8, "hole"), rect(-50, -150, 100, 12, 6, "hole"), rect(-56, -120, 112, 70, 6, "grey")],
  parcel: [rect(-100, -160, 200, 160, 8), rect(-16, -160, 32, 160, 0, "grey"), line([[-100, -120], [100, -120]], 8, "hole")],
  money: [rect(-120, -90, 240, 90, 10), circle(0, -45, 26, "hole"), circle(0, -45, 16), rect(-120, -110, 240, 14, 6, "grey")],
  camera: [rect(-70, -250, 140, 60, 16), circle(40, -220, 18, "hole"), circle(40, -220, 9, "red"), line([[-40, -194], [-40, -100]], 14, "grey"), line([[-80, -100], [0, -100]], 14, "grey")],
  router: [rect(-140, -70, 280, 70, 16), line([[-90, -70], [-110, -190]], 12), line([[90, -70], [110, -190]], 12), circle(-80, -36, 7, "hole"), circle(-50, -36, 7, "hole"), circle(-20, -36, 7, "hole")],
  moon: [circle(0, -360, 46), circle(-22, -376, 42, "hole")],
  chat: [rect(-130, -220, 260, 170, 34), poly([[-80, -54], [-110, -6], [-30, -54]]), rect(-90, -176, 180, 18, 9, "hole"), rect(-90, -134, 120, 18, 9, "hole")],
  warning: [poly([[0, -240], [130, 0], [-130, 0]]), rect(-12, -160, 24, 90, 10, "hole"), circle(0, -40, 14, "hole")],
  link: [rect(-130, -90, 140, 70, 35), rect(-112, -72, 104, 34, 17, "hole"), rect(-10, -90, 140, 70, 35), rect(8, -72, 104, 34, 17, "hole"), rect(-40, -64, 80, 18, 9)],
};

/** The shapes of a library part by name (people, animals, objects), or null. */
export function libraryShapes(what: string): Shape[] | null {
  if (what === "person") return personShapes("stand");
  if (what.startsWith("person_")) return POSES[what.slice(7)] ? personShapes(what.slice(7)) : null;
  return ANIMALS[what] ?? OBJECTS[what] ?? null;
}

/** [minX, minY, maxX, maxY] of a list of shapes, lines widened by half their width. */
export function shapesBox(shapes: Shape[]): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const add = (x: number, y: number, pad = 0) => {
    x0 = Math.min(x0, x - pad); y0 = Math.min(y0, y - pad); x1 = Math.max(x1, x + pad); y1 = Math.max(y1, y + pad);
  };
  for (const s of shapes) {
    if (s.shape === "circle") add(s.cx, s.cy, s.r);
    else if (s.shape === "rect") { add(s.x, s.y); add(s.x + s.w, s.y + s.h); }
    else if (s.shape === "line") for (const p of s.points) add(p[0], p[1], s.width / 2);
    else for (const p of s.points) add(p[0], p[1]);
  }
  return Number.isFinite(x0) ? [x0, y0, x1, y1] : [-100, -200, 100, 0];
}
