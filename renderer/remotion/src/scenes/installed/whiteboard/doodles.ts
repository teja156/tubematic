/**
 * The doodle library: every drawing the marker can make, hand-built here
 * once. The agent picks doodles by name and never draws, because agent-drawn
 * shapes and people read as weak clip art (TMDEV-194's finding), and nothing
 * can check a drawing's quality before a render.
 *
 * Each doodle is a list of strokes in a 100 x 100 box, y pointing down, drawn
 * in the order listed, the way a person would draw it (outline first, then
 * details). The renderer scales a doodle to its slot and adds a seeded hand
 * wobble.
 *
 * Keep in sync: the names are the pack's extra.doodles list
 * (tubematic_core/style_packs/whiteboard.json), which the validator and the
 * skill read. tests/unit and mcp/tests pin that the three agree.
 */
export type P = [number, number];
type Stroke = P[];

const rad = (d: number) => (d * Math.PI) / 180;

/** Ellipse arc, angles in degrees (0 = right, 90 = down). */
function arc(cx: number, cy: number, rx: number, ry: number, a0: number, a1: number): Stroke {
  const n = Math.max(6, Math.ceil(Math.abs(a1 - a0) / 8));
  const out: Stroke = [];
  for (let i = 0; i <= n; i++) {
    const a = rad(a0 + ((a1 - a0) * i) / n);
    out.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
  }
  return out;
}
const circle = (cx: number, cy: number, r: number, from = -100): Stroke => arc(cx, cy, r, r, from, from + 365);
const ellipse = (cx: number, cy: number, rx: number, ry: number, from = -100): Stroke => arc(cx, cy, rx, ry, from, from + 365);

/** Rounded rectangle as one stroke from its top-left, closing with a small overlap. */
function rrect(x: number, y: number, w: number, h: number, r: number): Stroke {
  return [
    ...arc(x + r, y + r, r, r, 180, 270),
    ...arc(x + w - r, y + r, r, r, 270, 360),
    ...arc(x + w - r, y + h - r, r, r, 0, 90),
    ...arc(x + r, y + h - r, r, r, 90, 180),
    [x, y + r * 0.5],
  ];
}
const rect = (x: number, y: number, w: number, h: number): Stroke => [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y - 1]];
const line = (...pts: P[]): Stroke => pts;
function quad(a: P, c: P, b: P, n = 12): Stroke {
  const out: Stroke = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    out.push([u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]]);
  }
  return out;
}
/** Closed polygon through the points. */
const poly = (...pts: P[]): Stroke => [...pts, pts[0]];
/** A star or a gear's teeth: points alternating between two radii. */
function radial(cx: number, cy: number, r0: number, r1: number, n: number, rot = -90): Stroke {
  const out: Stroke = [];
  for (let i = 0; i <= n * 2; i++) {
    const a = rad(rot + (i * 180) / n);
    const r = i % 2 === 0 ? r1 : r0;
    out.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]);
  }
  return out;
}
function gearTeeth(cx: number, cy: number, r0: number, r1: number, n: number): Stroke {
  const out: Stroke = [];
  const step = 360 / n;
  for (let i = 0; i <= n; i++) {
    const a = -90 + i * step;
    for (const [da, r] of [[-step * 0.32, r0], [-step * 0.2, r1], [step * 0.2, r1], [step * 0.32, r0]] as [number, number][]) {
      out.push([cx + Math.cos(rad(a + da)) * r, cy + Math.sin(rad(a + da)) * r]);
    }
  }
  return out;
}

export const DOODLES: Record<string, Stroke[]> = {
  atom: [circle(50, 50, 7), ellipse(50, 50, 44, 16, 0), ...[60, 120].map((deg) => {
    const e = ellipse(0, 0, 44, 16, 0);
    const c = Math.cos(rad(deg));
    const s = Math.sin(rad(deg));
    return e.map(([x, y]) => [50 + x * c - y * s, 50 + x * s + y * c] as P);
  })],
  battery: [rrect(14, 30, 64, 40, 6), rect(78, 42, 8, 16), line([24, 40], [24, 60]), line([36, 40], [36, 60]), line([48, 40], [48, 60])],
  brain: [
    [...arc(38, 36, 18, 16, 160, 300), ...arc(58, 30, 18, 16, 220, 360), ...arc(70, 50, 16, 16, 280, 420), ...arc(56, 68, 18, 14, 0, 130), ...arc(34, 66, 18, 14, 40, 190), ...arc(26, 48, 14, 16, 100, 250)],
    quad([50, 22], [44, 46], [52, 74]),
    quad([34, 44], [42, 40], [42, 52]),
    quad([64, 40], [58, 48], [66, 56]),
  ],
  calendar: [rrect(16, 22, 68, 62, 6), line([16, 38], [84, 38]), line([32, 14], [32, 28]), line([68, 14], [68, 28]), line([30, 52], [36, 52]), line([47, 52], [53, 52]), line([64, 52], [70, 52]), line([30, 68], [36, 68]), line([47, 68], [53, 68])],
  car: [
    [[10, 64], [10, 50], [24, 46], [36, 30], [64, 30], [76, 46], [90, 50], [90, 64], [80, 64]],
    line([34, 64], [62, 64]),
    line([20, 64], [10, 64]),
    circle(27, 66, 8),
    circle(71, 66, 8),
    line([40, 34], [40, 46], [70, 46], [62, 34]),
  ],
  cart: [line([8, 22], [20, 22], [30, 64], [78, 64]), line([24, 32], [86, 32], [80, 54], [28, 54]), circle(36, 76, 6), circle(72, 76, 6)],
  chart_down: [line([14, 12], [14, 86], [90, 86]), line([22, 28], [40, 46], [54, 40], [80, 72]), line([66, 70], [80, 72], [80, 58])],
  chart_up: [line([14, 12], [14, 86], [90, 86]), line([22, 72], [40, 52], [54, 58], [80, 26]), line([66, 26], [80, 26], [80, 40])],
  check: [line([16, 52], [40, 76], [86, 22])],
  chip: [rrect(26, 26, 48, 48, 4), rect(40, 40, 20, 20), ...[34, 46, 58, 66].flatMap((v) => [line([v, 26], [v, 14]), line([v, 74], [v, 86]), line([26, v], [14, v]), line([74, v], [86, v])])],
  clock: [circle(50, 50, 38), line([50, 26], [50, 50], [66, 60]), line([50, 16], [50, 20]), line([84, 50], [80, 50]), line([50, 84], [50, 80]), line([16, 50], [20, 50])],
  cloud: [[...arc(30, 58, 16, 16, 90, 250), ...arc(46, 40, 20, 20, 190, 330), ...arc(68, 46, 16, 16, 240, 380), ...arc(74, 60, 12, 12, 290, 450), [30, 74]]],
  coin: [circle(50, 50, 36), circle(50, 50, 28, 80), line([56, 38], [46, 38], [42, 44], [46, 50], [54, 50], [58, 56], [54, 62], [42, 62]), line([50, 32], [50, 68])],
  cross: [line([20, 20], [80, 80]), line([80, 20], [20, 80])],
  database: [ellipse(50, 24, 32, 10, 180), line([18, 24], [18, 76]), quad([18, 76], [50, 96], [82, 76]), line([82, 76], [82, 24]), quad([18, 42], [50, 62], [82, 42]), quad([18, 59], [50, 79], [82, 59])],
  document: [line([62, 12], [24, 12], [24, 88], [76, 88], [76, 26], [62, 12], [62, 26], [76, 26]), line([34, 42], [66, 42]), line([34, 54], [66, 54]), line([34, 66], [58, 66])],
  drop: [[...quad([50, 10], [30, 38], [26, 62]), ...arc(50, 62, 24, 24, 180, 0), ...quad([74, 62], [70, 38], [50, 10])], quad([38, 66], [40, 76], [50, 78])],
  envelope: [rect(12, 26, 76, 50), line([12, 26], [50, 56], [88, 26])],
  factory: [line([10, 86], [10, 46], [30, 58], [30, 46], [50, 58], [50, 46], [70, 58], [70, 22], [84, 22], [84, 86], [8, 86]), rect(22, 68, 10, 10), rect(44, 68, 10, 10), quad([76, 18], [70, 6], [84, 6])],
  flame: [[[50, 88], ...quad([50, 88], [20, 82], [24, 56]), ...quad([24, 56], [30, 40], [44, 12]), ...quad([44, 12], [52, 34], [62, 36]), ...quad([62, 36], [66, 28], [66, 22]), ...quad([66, 22], [84, 46], [76, 70]), ...quad([76, 70], [70, 86], [50, 88])], [[50, 84], ...quad([50, 84], [38, 78], [42, 64]), ...quad([42, 64], [48, 52], [52, 46]), ...quad([52, 46], [62, 64], [58, 76]), [50, 84]]],
  gear: [gearTeeth(50, 50, 30, 40, 8), circle(50, 50, 12)],
  globe: [circle(50, 50, 38), ellipse(50, 50, 16, 38, -90), line([12, 50], [88, 50]), quad([18, 32], [50, 38], [82, 32]), quad([18, 68], [50, 62], [82, 68])],
  group: [circle(32, 38, 11), quad([12, 80], [14, 54], [32, 54]), quad([32, 54], [50, 54], [52, 80]), circle(68, 34, 11), quad([54, 52], [64, 48], [72, 50]), quad([72, 50], [88, 54], [90, 76])],
  heart: [[[50, 84], ...quad([50, 84], [12, 58], [14, 36]), ...arc(32, 34, 18, 18, 180, 330), ...quad([47, 25], [50, 28], [50, 32]), ...quad([50, 32], [52, 22], [64, 18]), ...arc(68, 34, 18, 18, 250, 360), ...quad([86, 36], [88, 58], [50, 84])]],
  hourglass: [line([24, 12], [76, 12]), line([24, 88], [76, 88]), line([30, 12], [30, 22], [50, 50], [30, 78], [30, 88]), line([70, 12], [70, 22], [50, 50], [70, 78], [70, 88]), line([38, 80], [62, 80], [50, 66], [38, 80])],
  house: [line([10, 48], [50, 14], [90, 48]), line([20, 40], [20, 86], [80, 86], [80, 40]), rect(42, 60, 16, 26), rect(28, 50, 10, 10)],
  key: [circle(26, 50, 16), circle(26, 50, 5), line([42, 50], [88, 50], [88, 62]), line([74, 50], [74, 60]), line([64, 50], [64, 58])],
  laptop: [rrect(20, 20, 60, 42, 4), rect(26, 26, 48, 30), line([20, 62], [10, 76], [90, 76], [80, 62]), line([42, 70], [58, 70])],
  lightbulb: [[...arc(50, 40, 26, 26, 140, 400), [38, 66]], line([38, 66], [62, 66]), line([40, 74], [60, 74]), line([43, 82], [57, 82]), line([44, 54], [50, 44], [56, 54])],
  magnet: [[[22, 80], [22, 46], ...arc(50, 46, 28, 28, 180, 360), [78, 80], [62, 80], [62, 46], ...arc(50, 46, 12, 12, 360, 180), [38, 80], [22, 80]], line([22, 68], [38, 68]), line([62, 68], [78, 68])],
  magnifier: [circle(42, 42, 26), line([60, 60], [86, 86]), quad([28, 38], [30, 28], [40, 26])],
  money_bag: [[[40, 26], ...quad([40, 26], [16, 46], [18, 70]), ...quad([18, 70], [22, 86], [50, 86]), ...quad([50, 86], [78, 86], [82, 70]), ...quad([82, 70], [84, 46], [60, 26]), [40, 26]], line([40, 26], [34, 14], [66, 14], [60, 26]), line([56, 50], [46, 50], [42, 56], [46, 62], [54, 62], [58, 68], [54, 74], [42, 74]), line([50, 44], [50, 80])],
  padlock: [rrect(22, 44, 56, 42, 6), [[34, 44], [34, 30], ...arc(50, 30, 16, 16, 180, 360), [66, 44]], circle(50, 60, 5), line([50, 65], [50, 74])],
  person: [circle(50, 30, 16), [[18, 88], ...quad([18, 88], [18, 54], [50, 54]), ...quad([50, 54], [82, 54], [82, 88])]],
  phone: [rrect(30, 10, 40, 80, 7), line([44, 18], [56, 18]), circle(50, 80, 3)],
  question: [[...arc(50, 34, 18, 18, 200, 400), ...quad([66, 42], [50, 50], [50, 62])], circle(50, 78, 2.5)],
  rocket: [[[50, 8], ...quad([50, 8], [32, 26], [36, 66]), [64, 66], ...quad([64, 66], [68, 26], [50, 8])], circle(50, 36, 7), line([36, 52], [24, 70], [38, 66]), line([64, 52], [76, 70], [62, 66]), line([44, 72], [50, 88], [56, 72])],
  scales: [line([50, 14], [50, 84]), line([34, 84], [66, 84]), line([16, 24], [84, 24]), line([16, 24], [8, 50]), line([16, 24], [24, 50]), quad([6, 50], [16, 62], [26, 50]), line([84, 24], [76, 50]), line([84, 24], [92, 50]), quad([74, 50], [84, 62], [94, 50])],
  server: [rrect(16, 12, 68, 22, 4), rrect(16, 39, 68, 22, 4), rrect(16, 66, 68, 22, 4), line([26, 23], [30, 23]), line([26, 50], [30, 50]), line([26, 77], [30, 77]), line([58, 23], [74, 23]), line([58, 50], [74, 50]), line([58, 77], [74, 77])],
  shield: [[[50, 10], [82, 22], ...quad([82, 22], [84, 66], [50, 90]), ...quad([50, 90], [16, 66], [18, 22]), [50, 10]], line([36, 50], [46, 60], [66, 38])],
  star: [radial(50, 52, 17, 40, 5)],
  sun: [circle(50, 50, 18), ...[0, 45, 90, 135, 180, 225, 270, 315].map((d) => line([50 + Math.cos(rad(d)) * 28, 50 + Math.sin(rad(d)) * 28], [50 + Math.cos(rad(d)) * 40, 50 + Math.sin(rad(d)) * 40]))],
  target: [circle(50, 50, 38), circle(50, 50, 24, 60), circle(50, 50, 9, 200), line([50, 50], [84, 16]), line([74, 16], [84, 16], [84, 26])],
  tree: [line([46, 88], [46, 60]), line([54, 88], [54, 60]), [[46, 62], ...arc(34, 50, 16, 16, 100, 250), ...arc(50, 30, 20, 20, 190, 340), ...arc(66, 50, 16, 16, 280, 440), [54, 62]]],
  warning: [poly([50, 12], [90, 84], [10, 84]), line([50, 36], [50, 62]), circle(50, 73, 2.5)],
  wifi: [arc(50, 70, 42, 42, 225, 315), arc(50, 70, 28, 28, 225, 315), arc(50, 70, 14, 14, 225, 315), circle(50, 72, 3)],
};

export const DOODLE_NAMES = Object.keys(DOODLES).sort();
