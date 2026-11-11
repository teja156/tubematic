/*
 * A library prop as a cached drawing, and a check that its drawing fits its box.
 */
import React, { useLayoutEffect, useRef, useState } from "react";
import type { Drawing } from "../bitmap";
import { PROPS } from "./index";
import type { PropEntry } from "./types";

/** The prop in a state as a cached drawing, its base at (w/2, h) in the box; `density` above 1 for one shown enlarged. */
export function propDrawing(id: string, entry: PropEntry, state: number, density = 1): Drawing {
  const [w, h] = entry.box;
  const Draw = entry.draw;
  return {
    key: `prop:${id}:${state}@${density}`,
    width: w,
    height: h,
    density,
    render: () => (
      <g transform={`translate(${w / 2} ${h})`}>
        <Draw state={state} />
      </g>
    ),
  };
}

export function libraryDrawing(id: string, state: number): Drawing {
  return propDrawing(id, PROPS[id], state);
}

/** Outline strokes reach past getBBox (which ignores stroke width) by up to this much. */
const STROKE_MARGIN = 3;

/**
 * Draws every state of a prop live (unclipped, invisible) and reports where
 * its pixels reach against its box: "fits" or what overflows. For the model
 * sheet and whoever draws a prop.
 */
export const BoxCheck: React.FC<{ entry: PropEntry; x: number; y: number }> = ({ entry, x, y }) => {
  const ref = useRef<SVGGElement>(null);
  const [report, setReport] = useState("");
  const [w, h] = entry.box;
  const Draw = entry.draw;
  useLayoutEffect(() => {
    const g = ref.current;
    if (!g) return;
    const b = g.getBBox();
    const left = b.x - STROKE_MARGIN, right = b.x + b.width + STROKE_MARGIN;
    const top = b.y - STROKE_MARGIN, bottom = b.y + b.height + STROKE_MARGIN;
    const over: string[] = [];
    if (left < -w / 2) over.push(`left ${Math.ceil(-w / 2 - left)}`);
    if (right > w / 2) over.push(`right ${Math.ceil(right - w / 2)}`);
    if (top < -h) over.push(`top ${Math.ceil(-h - top)}`);
    if (bottom > 0) over.push(`bottom ${Math.ceil(bottom)}`);
    setReport(over.length ? `OVER: ${over.join(", ")}` : `fits (drawn ${Math.ceil(right - left)}x${Math.ceil(bottom - top)})`);
  }, [entry, w, h]);
  return (
    <>
      <svg width={1} height={1} style={{ position: "absolute", left: 0, top: 0, opacity: 0, overflow: "visible" }}>
        <g ref={ref}>
          {Array.from({ length: entry.states }, (_, s) => <Draw key={s} state={s} />)}
        </g>
      </svg>
      <div style={{ position: "absolute", left: x - 200, top: y, width: 400, textAlign: "center", fontSize: 22,
        fontFamily: "monospace", color: report.startsWith("OVER") ? "#B00020" : "#4E4136" }}>{report}</div>
    </>
  );
};
