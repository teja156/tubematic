// The NATCHEZ, 1870: a full-size sidewheel packet as a code part (shared builder: steamboatKit.ts, KIT_REV 7).
// Blue trim, her name on the texas board and round both paddle boxes. 38 m, bow toward +x.
import { makeSteamboat } from "./steamboatKit";

export const NATCHEZ_BOAT = makeSteamboat({
  name: "NATCHEZ",
  arc: "NATCHEZ",
  trim: "#2f63b3",
  trimDark: "#16346c",
  blurb: "the Natchez, an 1870 Mississippi sidewheel steamboat at full size (38 m, bow toward +x): white decks, blue trim, two crowned black chimneys, painted paddle boxes with turning wheels",
});
