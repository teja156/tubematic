/*
 * The shape of a Storybook Atlas prop: one object drawn in the book's ink, in
 * one or more states, cached as a bitmap per state (../bitmap.tsx).
 *
 * A prop draws itself with its base at the origin: (0, 0) is the middle of the
 * line it stands on (a floor prop) or hangs from the middle of its bottom edge
 * (a wall prop); x runs -w/2..w/2 and y runs -h..0. The box must hold every
 * pixel of every state, outline included, because the bitmap is cut to it: an
 * outline is centred on its path, so a drawing ends 3 px inside the box (its
 * base at y = -3). The model sheet's box check reports any overflow.
 */
import type React from "react";

/** What a prop can do when the agent fires an `act` on it. */
export const ACTS = ["wobble", "bounce", "shake", "spin", "swing", "pulse", "glow", "switch", "cycle"] as const;
export type Act = (typeof ACTS)[number];

/**
 * - floor: stands on the floor line.
 * - wall: hangs on the wall or floats in the scene band, above the floor line.
 */
export type Place = "floor" | "wall";

export type PropSpec = {
  /** Its box in px: [width, height]. */
  box: [number, number];
  place: Place;
  /** How many drawings it has. State 0 is the resting look; `switch` goes to 1, `cycle` loops 1..states-1. */
  states: number;
  acts: Act[];
  /**
   * For a door, a porthole or anything the camera can push through into the
   * next chapter: the point it pushes towards, in prop coordinates (origin at
   * the base, y up is negative).
   */
  portal?: [number, number];
};

/** A prop's drawing: `state` picks which look. */
export type PropDrawing = React.FC<{ state: number }>;

export type PropEntry = PropSpec & { label: string; draw: PropDrawing };
