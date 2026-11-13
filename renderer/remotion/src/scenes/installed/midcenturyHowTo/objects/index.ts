/*
 * The object library's drawings, by id. Every id in OBJECTS (../contract.ts)
 * has a drawing here; midcenturyHowTo.test.ts checks it.
 */
import type React from "react";
import type { ObjectDrawProps } from "../cel";
import type { ObjectId } from "../contract";
import { App, Button, Keypad, Laptop, Password, Phone, Qr, Toggle, Window } from "./screens";
import { THINGS } from "./things";

export const DRAWINGS: Record<ObjectId, React.FC<ObjectDrawProps>> = {
  phone: Phone,
  laptop: Laptop,
  window: Window,
  qr: Qr,
  keypad: Keypad,
  password: Password,
  toggle: Toggle,
  button: Button,
  app: App,
  ...THINGS,
};
