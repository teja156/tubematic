/*
 * The Paper Diorama prop sheet: props painted exactly as a video paints them,
 * twelve to a page (one page per frame), each with its name and size under
 * it, on the room cream.
 *
 * With `props` it shows those (render_paper_props passes a video's own
 * customProps, so the agent can look before it uses them). With no props it
 * shows the whole shipped library and then the critter's expressions, for a
 * person to approve the kit. No video uses this composition.
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, useCurrentFrame } from "remotion";
import { COLORS, CRITTER, type PropDef } from "./contract";
import { PAD, hashSeed, paintProp } from "./paint";
import { critterDef } from "./critter";
import { loadFonts } from "../paper/fonts";
import { PAPER_FONTS } from "../PaperDiorama";
import LIBRARY from "./props.json";

const PER_PAGE = 12;
const CELL_W = 360, CELL_H = 470, TOP = 60;

function entries(props?: Record<string, PropDef>): [string, PropDef][] {
  if (props) return Object.entries(props);
  const lib = Object.entries(LIBRARY as unknown as Record<string, PropDef>);
  const faces = CRITTER.expressions.map((ex) => [`critter: ${ex}`, critterDef("hero", "cap", ex)] as [string, PropDef]);
  return [...lib, ...faces];
}

export const sheetPages = (props?: Record<string, PropDef>) => Math.max(1, Math.ceil(entries(props).length / PER_PAGE));

export const PaperPropSheet: React.FC<{ props?: Record<string, PropDef> }> = ({ props }) => {
  const frame = useCurrentFrame();
  const all = entries(props);
  const page = all.slice(frame * PER_PAGE, frame * PER_PAGE + PER_PAGE);
  const [sprites, setSprites] = useState<string[] | null>(null);
  const [handle] = useState(() => delayRender("PaperPropSheet: painting"));
  useEffect(() => {
    loadFonts(PAPER_FONTS)
      .catch(() => undefined)
      .then(() => {
        setSprites(page.map(([name, def]) => paintProp(def, hashSeed(name.startsWith("critter") ? "critter" : name)).toDataURL()));
        continueRender(handle);
      });
    // one page per frame: repaint when the page changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, handle]);
  return (
    <AbsoluteFill style={{ background: COLORS.creamHi }}>
      {sprites && page.map(([name, def], i) => {
        const col = i % 3, row = Math.floor(i / 3);
        const fit = Math.min(1, (CELL_W - 40) / (def.w + 2 * PAD), (CELL_H - 90) / (def.h + 2 * PAD));
        const w = (def.w + 2 * PAD) * fit, h = (def.h + 2 * PAD) * fit;
        const x = col * CELL_W, y = TOP + row * CELL_H;
        return (
          <React.Fragment key={name}>
            <img src={sprites[i]} style={{ position: "absolute", left: x + (CELL_W - w) / 2, top: y + (CELL_H - 80 - h), width: w, height: h }} />
            <div style={{
              position: "absolute", left: x, width: CELL_W, top: y + CELL_H - 70, textAlign: "center",
              fontFamily: "Inter, Arial, sans-serif", fontWeight: 800, fontSize: 26, color: COLORS.ink,
            }}>
              {name}
              <div style={{ fontSize: 20, fontWeight: 800, opacity: 0.55 }}>{Math.round(def.w)} x {Math.round(def.h)}</div>
            </div>
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};
