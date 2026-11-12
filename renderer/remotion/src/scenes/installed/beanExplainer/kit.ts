/*
 * Where a prop's drawing and box come from: the library, or the props the
 * video's agent drew for it (loaded by the scene from generated/<video_id>/).
 * Everything that draws or places a prop asks a kit, so a custom prop behaves
 * exactly like a library one once it is loaded.
 */
import type React from "react";
import { PROPS, propSize, type BECustomProp, type PropId } from "./contract";
import { DRAWINGS } from "./props";
import type { PropDrawProps } from "./props/common";

export type Drawing = React.FC<PropDrawProps>;

export type PropKit = {
  draw: (id: string) => Drawing | undefined;
  size: (id: string) => { w: number; h: number };
  acts: (id: string) => readonly string[];
};

export function makeKit(custom: BECustomProp[] = [], drawings: Record<string, Drawing> = {}): PropKit {
  return {
    draw: (id) => (id in DRAWINGS ? DRAWINGS[id as PropId] : drawings[id]),
    size: (id) => propSize(id, custom),
    acts: (id) => (id in PROPS ? PROPS[id as PropId].acts : custom.find((c) => c.id === id)?.acts ?? []),
  };
}

export const LIBRARY_KIT = makeKit();
