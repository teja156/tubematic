/*
 * Isometric Infographic's pin layout. A pin is a dot on a prop, a leader going
 * up and a rule with a label (and a big number) at its top. Two props that
 * stand close on the board would put their labels on top of each other, so each
 * board's pins are laid out once, for the whole board in view, in the order the
 * config lists them: a pin keeps the side its `side` or the default gives it
 * while that is free, then tries the other side, then rises one label height at
 * a time. The layout does not depend on the frame, so a label never jumps when
 * another pin builds or the camera moves; the whole view is the closest the
 * props ever stand on screen (a zoom only spreads them), so what is clear there
 * stays clear.
 */
import { GEOMETRY, W, type Board, type IsometricData } from "./contract";
import { propDef } from "./draw";
import { project } from "./kit";
import { WHOLE, projAt } from "./stage";

/** Where a pin's rule and label sit relative to its default place. */
export interface PinSlot {
  right: boolean;
  /** How many label heights the rule rises above its default height. */
  lane: number;
}

export const PIN = { up: 150, rule: 220, laneStep: 122, maxLane: 3, gap: 8, vgap: 20, labelPx: 32, valuePx: 36, unitPx: 24 } as const;

interface Rect { x0: number; y0: number; x1: number; y1: number; line?: true }

// the vertical gap is wider: a lifted prop carries its pin about 18 px higher than the layout assumes
// two thin lines (leaders, rules) crossing or running together are not a clash; a line through a label is
const overlaps = (a: Rect, b: Rect) =>
  !(a.line && b.line) && a.x0 < b.x1 + PIN.gap && b.x0 < a.x1 + PIN.gap && a.y0 < b.y1 + PIN.vgap && b.y0 < a.y1 + PIN.vgap;

/** The title and the readout (with its row of cubes) over the left of the frame: a label there is kept for last. */
const KEEP_OUT: Rect = { x0: 60, y0: GEOMETRY.titleTop, x1: 640, y1: GEOMETRY.bandTop + 30 };
const inFrame = (r: Rect) => r.x0 >= GEOMETRY.safeLeft && r.x1 <= GEOMETRY.safeRight;

/** The label's estimated width: caps at 40 px with letter spacing, the number at 64 px, its unit at 40 px. */
export function labelWidth(label: string, value?: string, unit?: string): number {
  const l = label.length * PIN.labelPx;
  const v = value ? value.length * PIN.valuePx + (unit ? unit.length * PIN.unitPx + 8 : 0) : 0;
  return Math.max(l, v);
}

/** The rects a pin takes at a slot: the label, the leader (thin) and the rule (thin). */
function rects(ax: number, ay: number, w: number, hasValue: boolean, slot: PinSlot): Rect[] {
  const top = ay - PIN.up - slot.lane * PIN.laneStep;
  const left = slot.right ? ax + 14 : ax - PIN.rule;
  const h = 48 + (hasValue ? 70 : 0);
  return [
    { x0: left, y0: top + 4, x1: left + w, y1: top + 4 + h },
    { x0: ax - 2, y0: top, x1: ax + 2, y1: ay, line: true },
    { x0: slot.right ? ax : ax - PIN.rule, y0: top - 2, x1: slot.right ? ax + PIN.rule : ax, y1: top + 2, line: true },
  ];
}

/** One slot per pin of the board, in the pins' order. */
export function pinLayout(data: IsometricData, b: Board): PinSlot[] {
  const pr = projAt(WHOLE);
  const placed: Rect[] = [];
  return (b.pins ?? []).map((pin) => {
    const prop = b.props.find((p) => p.id === pin.on);
    const def = prop ? propDef(prop.what, data.customProps ?? []) : null;
    const fallback: PinSlot = { right: pin.side ? pin.side === "right" : true, lane: 0 };
    if (!prop) return fallback;
    const [ax, ay] = project(pr, prop.at[0], prop.at[1], (def?.height ?? 1) * (prop.scale ?? 1) + 0.15);
    const dflt = pin.side ? pin.side === "right" : !(ax > W * 0.62);
    const sides = pin.side ? [dflt] : [dflt, !dflt];
    const w = labelWidth(pin.label, pin.value, pin.unit);
    // Three passes, each looser: clear of the other pins, inside the frame and off the title and readout;
    // then clear of the other pins and inside the frame; then clear of the other pins only.
    const tests: ((rs: Rect[]) => boolean)[] = [
      (rs) => !rs.some((r) => placed.some((q) => overlaps(r, q))) && rs.every(inFrame) && !rs.some((r) => overlaps(r, KEEP_OUT)),
      (rs) => !rs.some((r) => placed.some((q) => overlaps(r, q))) && rs.every(inFrame),
      (rs) => !rs.some((r) => placed.some((q) => overlaps(r, q))),
    ];
    let chosen: PinSlot | null = null;
    search: for (const ok of tests) {
      for (let lane = 0; lane <= PIN.maxLane; lane++) {
        for (const right of sides) {
          const slot = { right, lane };
          if (ok(rects(ax, ay, w, !!pin.value, slot))) {
            chosen = slot;
            break search;
          }
        }
      }
    }
    // nothing clear within the lanes: keep it at the top lane on its default side
    const slot = chosen ?? { right: dflt, lane: PIN.maxLane };
    placed.push(...rects(ax, ay, w, !!pin.value, slot));
    return slot;
  });
}
