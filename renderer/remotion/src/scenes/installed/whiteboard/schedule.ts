/**
 * When the marker draws each item. One marker, so items draw one after the
 * other in the order they are listed. Each starts TIMING.lag frames after its
 * word and takes its natural time, cut short (never below its floor) so it
 * finishes before the next item starts, or before the camera leaves the region
 * with time left to read it. The validator refuses data whose floors do not fit.
 * The one exception is the item that opens the video (opensVideo).
 *
 * Keep in sync: mcp/whiteboard.py's schedule mirrors this function.
 */
import { TIMING, itemFloor, itemNatural, type WBItem, type WhiteboardData } from "./contract";

export type Scheduled = { item: WBItem; region: number; start: number; dur: number };

/** The frame the camera leaves region i: the next region's start, or the recap. */
export function regionLeave(data: WhiteboardData, i: number): number {
  return i + 1 < data.regions.length ? data.regions[i + 1].startFrame : data.recapFrame;
}

/** The board's first item at frame 0 opens the video: it is already being
 *  drawn on the first frame instead of waiting TIMING.lag frames. */
export function opensVideo(ri: number, k: number, item: WBItem): boolean {
  return ri === 0 && k === 0 && item.at === 0;
}

export function schedule(data: WhiteboardData): Scheduled[] {
  const out: Scheduled[] = [];
  data.regions.forEach((region, ri) => {
    const leave = regionLeave(data, ri);
    region.items.forEach((item, k) => {
      const start = opensVideo(ri, k, item) ? -TIMING.openLead : item.at + TIMING.lag;
      const next = region.items[k + 1];
      const deadline = next ? next.at + TIMING.lag - TIMING.gap : leave - TIMING.read;
      const dur = Math.max(1, Math.min(itemNatural(item), Math.max(itemFloor(item), deadline - start)));
      out.push({ item, region: ri, start, dur });
    });
  });
  return out;
}
