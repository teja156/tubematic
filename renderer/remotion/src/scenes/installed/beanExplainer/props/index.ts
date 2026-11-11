/*
 * The prop library by id. Every id in contract.ts's PROPS has exactly one
 * drawing here; beanExplainer.test.ts fails when the two lists differ.
 */
import type React from "react";
import type { PropId } from "../contract";
import type { PropDrawProps } from "./common";
import { Apple, Banknote, Bed, Brain, ChartDown, ChartUp, Coffee, Coins, CreditCard, Dumbbell, Heart, Pill, PiggyBank, Stomach, Wallet, Water } from "./lifeProps";
import { Browser, Calendar, Document, Envelope, Laptop, Note, Phone, PriceTag, Sign, Speech, Thought } from "./textProps";
import { Bomb, Bug, Bulb, Clock, Cloud, Cursor, Gears, Hourglass, Key, Lock, Magnifier, Server, Shield, Trophy, Wifi } from "./thingProps";

export const DRAWINGS: Record<PropId, React.FC<PropDrawProps>> = {
  phone: Phone, browser: Browser, laptop: Laptop, sign: Sign, document: Document, note: Note, speech: Speech,
  thought: Thought, pricetag: PriceTag, calendar: Calendar, envelope: Envelope,
  coins: Coins, banknote: Banknote, wallet: Wallet, piggybank: PiggyBank, creditcard: CreditCard, chartup: ChartUp, chartdown: ChartDown,
  brain: Brain, heart: Heart, stomach: Stomach, pill: Pill, coffee: Coffee, water: Water, bed: Bed, dumbbell: Dumbbell, apple: Apple,
  lock: Lock, key: Key, server: Server, wifi: Wifi, bug: Bug, shield: Shield, cursor: Cursor,
  clock: Clock, hourglass: Hourglass, gears: Gears, bulb: Bulb, cloud: Cloud, trophy: Trophy, bomb: Bomb, magnifier: Magnifier,
};

/*
 * Acts that move the whole prop, applied by the stage as a transform about the
 * prop's centre (swing: about its top edge). Every other act is drawn by the
 * prop itself from `actT`.
 */
export const WHOLE_PROP_ACTS = ["shake", "swing", "wobble", "spin", "beat", "buzz"] as const;

/** [dx, dy, rotateDeg, scale, pivotY] for a whole-prop act `t` frames after it started. */
export function wholePropMotion(act: string, t: number, h: number): [number, number, number, number, number] {
  if (t < 0) return [0, 0, 0, 1, 0];
  switch (act) {
    case "shake":
    case "buzz":
      return t < 18 ? [Math.sin(t * 2.7) * 9 * (1 - t / 18), Math.cos(t * 3.1) * 4 * (1 - t / 18), 0, 1, 0] : [0, 0, 0, 1, 0];
    case "swing":
      return [0, 0, 14 * Math.exp(-t / 14) * Math.sin(t / 3), 1, -h / 2];
    case "wobble":
      return t < 30 ? [0, 0, 8 * Math.sin(t / 2.4) * (1 - t / 30), 1, h / 2] : [0, 0, 0, 1, 0];
    case "spin":
      return t < 18 ? [0, 0, 360 * (1 - (1 - t / 18) ** 3), 1, 0] : [0, 0, 0, 1, 0];
    case "beat": {
      // two quick pulses, then a slow resting beat while on stage
      const k = t % 30;
      const pulse = k < 6 ? Math.sin((k / 6) * Math.PI) : k >= 8 && k < 14 ? 0.6 * Math.sin(((k - 8) / 6) * Math.PI) : 0;
      return [0, 0, 0, 1 + 0.09 * pulse, 0];
    }
    default:
      return [0, 0, 0, 1, 0];
  }
}
