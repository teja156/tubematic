// System Flow's contract, layout and camera: the facts the MCP validator and
// the render rely on. The shared cases are the ones mcp/tests/test_system_flow.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { computeRows, wrapLabel, type SFBoard } from "./contract";
import { BAND, boardKeys, cameraAt, fit, toScreen } from "./camera";
import { LABEL_PX, layoutBoard, pointAlong, slotBox } from "./layout";

const CASES = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../../../../mcp/tests/fixtures/system_flow_contract.json"), "utf8"),
);

describe("the shared contract cases", () => {
  it("wraps labels the way the validator does", () => {
    for (const c of CASES.wrap_label) expect(wrapLabel(c.label), c.label).toEqual(c.lines);
  });

  it("assigns rows the way the validator does", () => {
    for (const c of CASES.rows) {
      const rows = computeRows(c.nodes.map((id: string) => ({ id })), c.edges.map(([from, to]: string[]) => ({ from, to })));
      expect(rows).toEqual(c.rows);
    }
  });
});

const board = (nodes: string[], edges: [string, string][], startFrame = 0): SFBoard => ({
  startFrame,
  headline: "h",
  nodes: nodes.map((id) => ({ id, label: id, icon: "server" })),
  edges: edges.map(([from, to]) => ({ from, to })),
  events: nodes.map((id, i) => ({ type: "node" as const, node: id, at: startFrame + 10 + i * 20 })),
});

describe("layout", () => {
  it("puts each node on the row computeRows gives it", () => {
    const b = board(["a", "b", "c", "d"], [["a", "b"], ["b", "c"], ["a", "c"], ["d", "c"]]);
    const lay = layoutBoard(b);
    const rows = computeRows(b.nodes, b.edges);
    const yByRow: Record<number, Set<number>> = {};
    for (const n of b.nodes) (yByRow[rows[n.id]] ??= new Set()).add(Math.round(lay.nodes[n.id].boxTop));
    // Same row, same box top; a lower row, lower on the page.
    expect(yByRow[0].size).toBe(1);
    expect([...yByRow[0]][0]).toBeLessThan([...yByRow[1]][0]);
    expect([...yByRow[1]][0]).toBeLessThan([...yByRow[2]][0]);
  });

  it("keeps the listed order within a row", () => {
    const lay = layoutBoard(board(["root", "x", "y", "z"], [["root", "x"], ["root", "y"], ["root", "z"]]));
    expect(lay.nodes.x.x).toBeLessThan(lay.nodes.y.x);
    expect(lay.nodes.y.x).toBeLessThan(lay.nodes.z.x);
    const rev = layoutBoard(board(["root", "z", "y", "x"], [["root", "z"], ["root", "y"], ["root", "x"]]));
    expect(rev.nodes.z.x).toBeLessThan(rev.nodes.x.x);
  });

  it("starts an edge below its source's label and ends it above the target's box", () => {
    const lay = layoutBoard(board(["a", "b"], [["a", "b"]]));
    const e = lay.edges["a>b"];
    expect(e.points[0].y).toBeGreaterThan(slotBox(lay.nodes.a).y1);
    expect(e.points[e.points.length - 1].y).toBeLessThan(lay.nodes.b.boxTop);
    expect(e.dots.length).toBeGreaterThan(2);
    expect(pointAlong(e.points, 0)).toMatchObject({ p: e.points[0] });
  });
});

describe("camera", () => {
  it("shows a full board of three rows of three with labels of 40 px or more", () => {
    const ids = ["a1", "a2", "a3", "b1", "b2", "b3", "c1", "c2", "c3"];
    const edges: [string, string][] = [["a1", "b1"], ["a2", "b2"], ["a3", "b3"], ["b1", "c1"], ["b2", "c2"], ["b3", "c3"]];
    const b = board(ids, edges);
    b.nodes = b.nodes.map((n) => ({ ...n, label: "Fourteen chars x" })); // wraps to two lines: the tallest slot
    const lay = layoutBoard(b);
    expect(LABEL_PX * fit(lay.bounds).s).toBeGreaterThanOrEqual(40);
  });

  it("keeps everything visible inside the band, a focus push included", () => {
    const b = board(["a", "b", "c"], [["a", "b"], ["a", "c"]]);
    b.events.push({ type: "focus", node: "b", at: 100 });
    const lay = layoutBoard(b);
    const keys = boardKeys(b, lay, 300);
    for (let f = 0; f < 300; f++) {
      const c = cameraAt(keys, f);
      for (const n of Object.values(lay.nodes)) {
        const entered = b.events.find((e) => e.type === "node" && e.node === n.id)!.at;
        if (f < entered + 4) continue; // not on screen yet, or a frame into its fade-in
        const box = slotBox(n);
        const tl = toScreen(c, box.x0, box.y0);
        const br = toScreen(c, box.x1, box.y1);
        expect(tl.y, `frame ${f} ${n.id}`).toBeGreaterThanOrEqual(BAND.y0 - 1);
        expect(br.y, `frame ${f} ${n.id}`).toBeLessThanOrEqual(BAND.y1 + 1);
        expect(tl.x).toBeGreaterThanOrEqual(BAND.x0 - 1);
        expect(br.x).toBeLessThanOrEqual(BAND.x1 + 1);
      }
    }
  });

  it("is a pure function of the frame", () => {
    const b = board(["a", "b"], [["a", "b"]]);
    const keys = boardKeys(b, layoutBoard(b), 200);
    expect(cameraAt(keys, 57)).toEqual(cameraAt(keys, 57));
  });
});
