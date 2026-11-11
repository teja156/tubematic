/*
 * The Under the Hood presenter's model sheet: every pose, plus the three mouth
 * shapes and a blink, on the style's canvas. A person approves the fixed
 * presenter from this; no video uses it.
 *
 *   npx remotion still src/index.ts PresenterSheet sheet.png --frame=0
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { POSES } from "./contract";
import { PresenterSvg } from "./presenter";

const BG = "#0E0F12";

export const PresenterSheet: React.FC = () => {
  const cells: { pose: (typeof POSES)[number]; mouth: 0 | 1 | 2; blink: boolean; label: string }[] = [
    ...POSES.map((pose) => ({ pose, mouth: 0 as const, blink: false, label: pose })),
    { pose: "idle", mouth: 1, blink: false, label: "mouth 1" },
    { pose: "idle", mouth: 2, blink: false, label: "mouth 2" },
    { pose: "idle", mouth: 0, blink: true, label: "blink" },
  ];
  const cols = 3, cw = 1080 / cols, ch = 1920 / 4;
  return (
    <AbsoluteFill style={{ background: BG }}>
      {cells.map((c, i) => {
        const x = (i % cols) * cw, y = Math.floor(i / cols) * ch;
        return (
          <div key={i} style={{ position: "absolute", left: x, top: y, width: cw, height: ch, overflow: "hidden", borderRight: "1px solid #24262C", borderBottom: "1px solid #24262C" }}>
            <div style={{ position: "absolute", left: 10, top: 6, width: 400, height: 560, transform: "scale(0.62)", transformOrigin: "0 0" }}>
              <PresenterSvg pose={c.pose} mouth={c.mouth} blink={c.blink} />
            </div>
            <div style={{ position: "absolute", left: 12, bottom: 10, color: "#9B9CA1", fontFamily: "monospace", fontSize: 26 }}>{c.label}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
