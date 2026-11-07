// The ROBERT E. LEE, 1870: a full-size sidewheel packet as a code part (shared builder: steamboatKit.ts, KIT_REV 7).
// Red trim, her name on the texas board and round both paddle boxes. 38 m, bow toward +x.
import { makeSteamboat } from "./steamboatKit";

export const LEE_BOAT = makeSteamboat({
  name: "ROBERT E. LEE",
  arc: "ROBT. E. LEE",
  trim: "#c63b2c",
  trimDark: "#6e1a14",
  blurb: "the Robert E. Lee, an 1870 Mississippi sidewheel steamboat at full size (38 m, bow toward +x): white decks, red trim, two crowned black chimneys, painted paddle boxes with turning wheels",
});
