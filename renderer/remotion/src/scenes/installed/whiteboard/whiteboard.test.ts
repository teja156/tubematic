// Whiteboard's contract, layout, schedule and camera: the facts the MCP
// validator and the render rely on. The shared cases are the ones
// mcp/tests/test_whiteboard.py runs against mcp/whiteboard.py.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { BOARD, FLOOR, LAYOUTS, TIMING, doodleShare, itemFloor, itemNatural, textWidth, wrapText, type DoodleItem, type Layout, type PlacedItem, type WBItem, type WhiteboardData } from "./contract";
import { arrowEnds, fitProblem, placeItem, regionOrigin, type Pt } from "./layout";
import { schedule } from "./schedule";
import { DOODLES, DOODLE_NAMES, LIBRARY_DEFS, expandDoodle, type DoodleDef } from "./doodles";
import { W, cameraAt, mapView, onScreen, toScreen } from "./camera";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/whiteboard_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/whiteboard.json"), "utf8"));

const close = (a: number, b: number) => expect(Math.abs(a - b)).toBeLessThan(0.002);

describe("the shared contract cases", () => {
  it("wraps text the way the validator does", () => {
    for (const c of CASES.wrap) expect(wrapText(c.text, c.size, c.width), c.text).toEqual(c.lines);
  });

  it("measures text the way the validator does", () => {
    for (const c of CASES.text_width) close(textWidth(c.text, c.size), c.width);
  });

  it("times items the way the validator does", () => {
    for (const c of CASES.timing) {
      expect(itemNatural(c.item as WBItem), c.item.id).toBe(c.natural);
      expect(itemFloor(c.item as WBItem), c.item.id).toBe(c.floor);
    }
  });

  it("places items and judges their fit the way the validator does", () => {
    for (const c of CASES.place) {
      const slot = LAYOUTS[c.layout as Layout][c.slot];
      const it = c.item as PlacedItem;
      expect(fitProblem(it, slot) === "", `${c.layout}/${c.slot} ${JSON.stringify(it)}`).toBe(c.fits);
      if (!c.bbox) continue;
      const p = placeItem(it, slot);
      p.bbox.forEach((v, i) => close(v, c.bbox[i]));
      expect(p.lines.map((l) => l.text)).toEqual(c.lines);
      if (c.doodle) [p.doodle!.cx, p.doodle!.cy, p.doodle!.size].forEach((v, i) => close(v, c.doodle[i]));
      else expect(p.doodle).toBeUndefined();
    }
  });

  it("puts regions where the validator does", () => {
    for (const c of CASES.region_origin) expect(regionOrigin(c.i)).toEqual(c.xy);
  });

  it("ends arrows where the validator does", () => {
    for (const c of CASES.arrow) {
      const ends = arrowEnds(c.a, c.b);
      ends.forEach((pt: Pt, i: number) => pt.forEach((v, j) => close(v, c.ends[i][j])));
    }
  });

  it("schedules the marker the way the validator does", () => {
    const out = schedule(CASES.schedule.data as WhiteboardData).map((s) => ({ region: s.region, id: s.item.id, start: s.start, dur: s.dur }));
    expect(out).toEqual(CASES.schedule.out);
  });

  it("starts the item that opens the video before frame 0, so the first frame shows it", () => {
    const data = CASES.schedule_open.data as WhiteboardData;
    const out = schedule(data).map((s) => ({ region: s.region, id: s.item.id, start: s.start, dur: s.dur }));
    expect(out).toEqual(CASES.schedule_open.out);
    expect(out[0].start).toBe(-TIMING.openLead);
  });
});

describe("a labelled doodle's time", () => {
  it("keeps the label's floor when the doodle is squeezed to its own floor", () => {
    const it: DoodleItem = { id: "c", kind: "doodle", slot: "1", doodle: "coin", label: "coin", at: 0 };
    const floor = itemFloor(it);
    const labelFloor = floor - FLOOR.doodle;
    for (let dur = floor; dur <= itemNatural(it) + 5; dur++) {
      const share = doodleShare(it, dur);
      expect(dur * share, `dur ${dur}`).toBeGreaterThanOrEqual(FLOOR.doodle - 1e-9);
      expect(dur * (1 - share), `dur ${dur}`).toBeGreaterThanOrEqual(labelFloor - 1e-9);
    }
  });
});

describe("the doodle expander", () => {
  it("expands every primitive the way the validator does", () => {
    for (const c of CASES.expand) {
      const got = expandDoodle(c.def as DoodleDef);
      expect(got.map((st) => st.length), c.name).toEqual(c.points.map((st: number[][]) => st.length));
      got.forEach((st, i) => st.forEach(([x, y], k) => {
        close(x, c.points[i][k][0]);
        close(y, c.points[i][k][1]);
      }));
    }
  });

  it("expands the whole shipped library the way the validator does", () => {
    for (const [name, def] of Object.entries(LIBRARY_DEFS)) {
      const e = expandDoodle(def);
      const want = CASES.library_digest[name];
      expect(e.map((st) => st.length), name).toEqual(want.counts);
      close(e.flat().reduce((a, [x, y]) => a + x + 2 * y, 0), want.sum);
    }
  });
});

describe("the doodle library", () => {
  it("is exactly the pack's list, so the agent can only pick what the renderer draws", () => {
    expect(DOODLE_NAMES).toEqual([...PACK.extra.doodles].sort());
  });

  it("keeps every stroke inside its 100 x 100 box", () => {
    for (const [name, strokes] of Object.entries(DOODLES)) {
      expect(strokes.length, name).toBeGreaterThan(0);
      for (const st of strokes) for (const [x, y] of st) {
        expect(x, name).toBeGreaterThanOrEqual(0);
        expect(x, name).toBeLessThanOrEqual(100);
        expect(y, name).toBeGreaterThanOrEqual(0);
        expect(y, name).toBeLessThanOrEqual(100);
      }
    }
  });
});

describe("layout", () => {
  it("keeps every slot inside its region", () => {
    for (const [layout, slots] of Object.entries(LAYOUTS)) {
      for (const [name, [x, y, w, h]] of Object.entries(slots)) {
        expect(x >= 0 && y >= 0 && x + w <= BOARD.regionW && y + h <= BOARD.regionH, `${layout}/${name}`).toBe(true);
      }
    }
  });

  it("never lets two slots of a layout overlap", () => {
    for (const [layout, slots] of Object.entries(LAYOUTS)) {
      const rects = Object.values(slots);
      for (let i = 0; i < rects.length; i++)
        for (let j = i + 1; j < rects.length; j++) {
          const [a, b] = [rects[i], rects[j]];
          const apart = a[0] + a[2] <= b[0] || b[0] + b[2] <= a[0] || a[1] + a[3] <= b[1] || b[1] + b[3] <= a[1];
          expect(apart, `${layout} ${i} ${j}`).toBe(true);
        }
    }
  });
});

describe("camera", () => {
  const data: WhiteboardData = CASES.schedule.data;

  it("rests on a region with its centre in the writing band, and keeps the neighbours out of frame", () => {
    const cam = cameraAt(data, 60);
    const [ox, oy] = regionOrigin(0);
    const [cx, cy] = toScreen(cam, ox + BOARD.regionW / 2, oy + BOARD.regionH / 2);
    close(cx, W / 2);
    close(cy, BOARD.bandCenterY);
    // The region to the right starts beyond the frame's right edge.
    const [nx] = toScreen(cam, regionOrigin(1)[0], 0);
    expect(nx).toBeGreaterThan(W);
  });

  it("keeps the whole board inside the safe zone at the recap, above the captions, for every region count", () => {
    for (let n = 2; n <= 6; n++) {
      const end = mapView(n);
      for (let i = 0; i < n; i++) {
        const [x, y] = regionOrigin(i);
        // The region and its circled number, which sits 70 px up and left of its corner.
        const [x0, y0] = toScreen(end, x - 132, y - 132);
        const [x1, y1] = toScreen(end, x + BOARD.regionW, y + BOARD.regionH);
        expect(x0, `${n}/${i}`).toBeGreaterThanOrEqual(60);
        expect(x1, `${n}/${i}`).toBeLessThanOrEqual(W - 60);
        expect(y0, `${n}/${i}`).toBeGreaterThanOrEqual(150);
        expect(y1, `${n}/${i}`).toBeLessThan(1340);
      }
    }
  });

  it("keeps a full-width line inside the side safe zone at the end of a region's creep", () => {
    const cam = cameraAt(data, data.regions[1].startFrame - 1);
    const [ox] = regionOrigin(0);
    const [left] = toScreen(cam, ox + 60 + BOARD.pad, 0);
    expect(left).toBeGreaterThanOrEqual(60);
  });

  it("counts writing of a region the camera has left as off screen, and the resting region's as on screen", () => {
    const cam = cameraAt(data, data.regions[1].startFrame + 60);
    const [ax, ay] = regionOrigin(0);
    const [bx, by] = regionOrigin(1);
    expect(onScreen(cam, ax + 70, ay + 100, 900, 80)).toBe(false);
    expect(onScreen(cam, bx + 70, by + 100, 900, 80)).toBe(true);
  });

  it("keeps moving through the recap, so the ending is never a still frame", () => {
    const a = cameraAt(data, data.recapFrame + 40);
    const b = cameraAt(data, data.recapFrame + 120);
    expect(b.z).toBeLessThan(a.z);
  });
});
