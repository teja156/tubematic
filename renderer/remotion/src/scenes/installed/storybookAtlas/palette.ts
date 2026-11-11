/*
 * Storybook Atlas: the frame, its bands and the house palette.
 * A vintage picture book on ivory paper; every colour on stage comes from here
 * so the guide, the people, the props and the backdrops read as one book.
 */
export const W = 1080;
export const H = 1920;

/** Bands of the frame, in pixels from the top (the plaque above, the caption label below the floor). */
export const BANDS = {
  frameInset: 26, // the thin grey rule inside the dark edge band
  plaqueTop: 210,
  plaqueBottom: 410,
  floor: 1344, // the floor line people, props and the guide stand on (70% H)
  captionTop: 1480,
  captionBottom: 1640,
} as const;

export const INK = "#2F2218"; // outlines and the dark edge band
export const RULE = "#7A756E"; // the thin inner frame rule
export const TEXT = "#2A2F33"; // plaque and caption text
export const IVORY = "#EBE5D2"; // paper and the caption label
export const CREAM = "#F2EDDF"; // plaque face, paper highlights
export const BEIGE = "#E4D9C3";
export const SAND = "#D7C8AA"; // floors
export const PINK = "#C5A694"; // the plaque's numeral cell, inner ears
export const SEAL = "#852B25"; // wax seal, the gauge's danger band
export const SEAL_DARK = "#5A1A15";
export const GOLD = "#B39151"; // brass
export const STARGOLD = "#F1DCA2"; // constellation strokes and stars
export const NAVY = "#262D3B"; // night
export const BLUEPRINT = "#3A5878";
export const SLATE = "#5E6F86";
export const SAGE = "#9AA88A";
export const WOOD = "#8A6446";
export const WOOD_DARK = "#5A4232";
export const MOUSE = "#A99F92";

/** The garment colours a person can wear. The last two are light, for chapters on a dark backdrop. */
export const GARMENT_COLORS = {
  ink: "#3B3A40",
  navy: "#34476A",
  brick: "#9A4A36",
  moss: "#5F7048",
  plum: "#6E4A63",
  ochre: "#B4893F",
  cream: "#E3D6B8",
  sky: "#9DB9D3",
} as const;

/** Skin tones: four flat picture-book tones. */
export const SKIN = {
  light: "#F0D2B6",
  tan: "#D9A77E",
  brown: "#A96F4A",
  deep: "#6E4630",
} as const;

/** The guide's waistcoat colours. */
export const COAT_COLORS = {
  blue: BLUEPRINT,
  sage: "#6F8360",
  brick: "#93452F",
  plum: "#6A4560",
  mustard: "#B98B3A",
} as const;

export const SERIF = "'EB Garamond', Garamond, 'Times New Roman', serif";
