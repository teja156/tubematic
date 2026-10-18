// Stick figure for the Stick Explainer register (TMDEV-101) — a white canvas,
// black line art, discrete-pose visual style. A component, not a scene: it has
// no AbsoluteFill and paints no background, so place it inside a scene you
// author (usually on top of StickScene).
//
//   <StickFigure pose="type" expression="angry" attire="suit" x={540} y={1150} />
//
// DISCRETE POSING IS THE POINT. This component never interpolates. A pose
// change is a prop change on a frame boundary — exactly the 1-frame swap the
// register calls for — so drive it from a frame threshold, not from a spring:
//
//   const pose = frame < 90 ? "stand" : "point";
//
// Tweening the limbs would produce the smooth character animation this register
// deliberately does not have, and would cost far more to get right.
//
// Geometry is a joint table, not hand-drawn paths: every pose is a set of
// elbow/hand/knee/foot coordinates in the same local box, so two poses always
// share a head, a torso and a stroke weight. That is what makes a swap read as
// the same character moving rather than as two different drawings.
//
// The figure has a real torso with separate left/right shoulder and hip
// anchors, rather than a bare spine with both arms hung off one point. That is
// not decoration: with a single shoulder vertex, "shrug" and "panic" read as a
// chevron sitting on the neck instead of as two arms, which is what the first
// cut of this component actually rendered.

/** A point in the figure's own 220x460 local box. */
interface Point {
  x: number;
  y: number;
}

export type StickPose =
  | "stand"
  | "point"
  | "raise"
  | "wave"
  | "hands-hips"
  | "arms-crossed"
  | "shrug"
  | "think"
  | "reach"
  | "panic"
  | "walk"
  | "sit"
  | "type";

export type StickExpression =
  | "neutral"
  | "happy"
  | "shocked"
  | "angry"
  | "worried"
  | "sad"
  | "thinking";

export type StickAttire = "none" | "labcoat" | "suit" | "hoodie" | "dress";

export type StickHeadwear = "none" | "cap" | "hardhat" | "hair";

/**
 * Which canvas the figure is drawn on (TMDEV-101).
 *
 * The figure's geometry, poses and expressions are identical either way — only
 * the stroke and fill invert. That separation is what lets one video mix
 * figures with full-bleed imagery: the canvas is the thing that cannot vary
 * within a video, the line colour is not.
 *
 * `fill` matters as much as `color`. It is the head's and torso's interior, so
 * it has to match the canvas or the figure reads as a white cut-out floating on
 * a dark ground rather than as an outline drawn on it.
 */
export type StickTheme = "light" | "dark";

const THEMES: Record<StickTheme, { color: string; fill: string }> = {
  light: { color: "#000000", fill: "#ffffff" },
  dark: { color: "#ffffff", fill: "#0f0f0f" },
};

interface Props {
  /** Which static pose to hold. Change it on a frame boundary to "animate". */
  pose?: StickPose;
  /** Face template — eyebrow angle, eye shape and mouth curve together. */
  expression?: StickExpression;
  /** Garment overlay drawn over the torso. */
  attire?: StickAttire;
  /** Colour of the garment. Ignored when `attire` is "none". */
  attireColor?: string;
  /** Headwear overlay drawn over the head. */
  headwear?: StickHeadwear;
  /** Colour of the headwear. */
  headwearColor?: string;
  /** Centre of the figure, in 1080x1920 frame coordinates. */
  x: number;
  y: number;
  /** 1 renders the figure 460px tall. Stroke scales with it. */
  scale?: number;
  /** Mirror horizontally — the poses below all face or gesture to the right. */
  flip?: boolean;
  /** Line weight in local units. The register's spec is 4-6px at full size. */
  stroke?: number;
  /**
   * Which canvas this figure sits on. Sets `color` and `fill` together; pass
   * the one matching the video's canvas. Either can still be overridden.
   */
  theme?: StickTheme;
  /** Line colour. Defaults from `theme`. */
  color?: string;
  /** Head and torso fill. Defaults from `theme`; must match the canvas. */
  fill?: string;
}

const BOX_W = 220;
const BOX_H = 460;

const HEAD: Point = { x: 110, y: 68 };
const HEAD_R = 52;
const NECK_TOP: Point = { x: 110, y: 112 };
const NECK_BOTTOM: Point = { x: 110, y: 138 };

// The torso is a shallow trapezoid; the arms hang from its top corners and the
// legs from its bottom corners.
const SHOULDER_L: Point = { x: 86, y: 146 };
const SHOULDER_R: Point = { x: 134, y: 146 };
const HIP_L: Point = { x: 96, y: 288 };
const HIP_R: Point = { x: 124, y: 288 };
const TORSO = "M 84 134 L 136 134 L 128 290 L 92 290 Z";

interface PoseGeometry {
  /** Elbow then hand. */
  armL: [Point, Point];
  armR: [Point, Point];
  /** Knee then foot. */
  legL: [Point, Point];
  legR: [Point, Point];
}

const ARMS_DOWN: Pick<PoseGeometry, "armL" | "armR"> = {
  armL: [{ x: 66, y: 206 }, { x: 62, y: 268 }],
  armR: [{ x: 154, y: 206 }, { x: 158, y: 268 }],
};

const LEGS_STAND: Pick<PoseGeometry, "legL" | "legR"> = {
  legL: [{ x: 90, y: 370 }, { x: 86, y: 446 }],
  legR: [{ x: 130, y: 370 }, { x: 134, y: 446 }],
};

// Seated, facing right: thighs run forward from the hip, shins drop to the
// floor. Place the figure so its hip lands on the chair.
const LEGS_SIT: Pick<PoseGeometry, "legL" | "legR"> = {
  legL: [{ x: 180, y: 298 }, { x: 186, y: 398 }],
  legR: [{ x: 172, y: 310 }, { x: 178, y: 406 }],
};

const POSES: Record<StickPose, PoseGeometry> = {
  stand: { ...ARMS_DOWN, ...LEGS_STAND },
  point: {
    armL: ARMS_DOWN.armL,
    armR: [{ x: 176, y: 166 }, { x: 214, y: 138 }],
    ...LEGS_STAND,
  },
  raise: {
    armL: [{ x: 62, y: 106 }, { x: 46, y: 36 }],
    armR: [{ x: 158, y: 106 }, { x: 174, y: 36 }],
    ...LEGS_STAND,
  },
  wave: {
    armL: ARMS_DOWN.armL,
    armR: [{ x: 172, y: 130 }, { x: 192, y: 66 }],
    ...LEGS_STAND,
  },
  "hands-hips": {
    armL: [{ x: 50, y: 224 }, { x: 92, y: 282 }],
    armR: [{ x: 170, y: 224 }, { x: 128, y: 282 }],
    ...LEGS_STAND,
  },
  // The two forearms cross at different heights on purpose: level with each
  // other they merge into a single bar and the pose reads as a bowtie.
  "arms-crossed": {
    armL: [{ x: 58, y: 240 }, { x: 148, y: 196 }],
    armR: [{ x: 162, y: 248 }, { x: 78, y: 214 }],
    ...LEGS_STAND,
  },
  shrug: {
    armL: [{ x: 58, y: 204 }, { x: 42, y: 150 }],
    armR: [{ x: 162, y: 204 }, { x: 178, y: 150 }],
    ...LEGS_STAND,
  },
  // Elbow low and wide so the forearm running back up to the chin does not
  // lie on top of its own upper arm, which reads as a scribble, not an arm.
  think: {
    armL: ARMS_DOWN.armL,
    armR: [{ x: 188, y: 244 }, { x: 146, y: 128 }],
    ...LEGS_STAND,
  },
  reach: {
    armL: ARMS_DOWN.armL,
    armR: [{ x: 176, y: 170 }, { x: 218, y: 168 }],
    ...LEGS_STAND,
  },
  // Elbows wide at chest height, hands up and clear of the head — the sharp
  // bend is what separates this from `raise`, where the arms go straight up.
  // The hands must stay outside the head circle: the head is filled and drawn
  // after the arms, so one tucked behind it reads as a severed forearm.
  panic: {
    armL: [{ x: 30, y: 176 }, { x: 16, y: 86 }],
    armR: [{ x: 190, y: 176 }, { x: 204, y: 86 }],
    ...LEGS_STAND,
  },
  // One arm back, one forward. Both angled inward — the obvious symmetric
  // choice — closes a diamond against the torso between them.
  walk: {
    armL: [{ x: 62, y: 212 }, { x: 54, y: 272 }],
    armR: [{ x: 154, y: 206 }, { x: 178, y: 250 }],
    legL: [{ x: 78, y: 362 }, { x: 56, y: 442 }],
    legR: [{ x: 142, y: 356 }, { x: 164, y: 438 }],
  },
  sit: {
    armL: [{ x: 94, y: 216 }, { x: 152, y: 250 }],
    armR: [{ x: 146, y: 216 }, { x: 194, y: 242 }],
    ...LEGS_SIT,
  },
  type: {
    armL: [{ x: 86, y: 218 }, { x: 170, y: 228 }],
    armR: [{ x: 142, y: 220 }, { x: 196, y: 226 }],
    ...LEGS_SIT,
  },
};

/** Shoulder/hip -> joint -> end, as one polyline. */
function limb(root: Point, joint: Point, end: Point): string {
  return `M ${root.x} ${root.y} L ${joint.x} ${joint.y} L ${end.x} ${end.y}`;
}

const EYE_L: Point = { x: 90, y: 62 };
const EYE_R: Point = { x: 130, y: 62 };

/**
 * Face templates. Each is eyebrow angle + eye shape + mouth curve together —
 * changing one in isolation is how a "shocked" face ends up reading as mildly
 * surprised. Keep them as whole templates.
 */
function Face({
  expression,
  color,
  paper,
}: {
  expression: StickExpression;
  color: string;
  /** The canvas colour — the whites of a shocked eye are the ground showing
   *  through, so hardcoding white here leaves two glowing discs on dark. */
  paper: string;
}) {
  const dot = (p: Point, key: string) => (
    <ellipse key={key} cx={p.x} cy={p.y} rx={4.5} ry={7.5} fill={color} stroke="none" />
  );
  const brow = (from: Point, to: Point, key: string) => (
    <line key={key} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
  );

  switch (expression) {
    case "happy":
      return (
        <>
          {dot(EYE_L, "el")}
          {dot(EYE_R, "er")}
          <path d="M 90 88 Q 110 110 130 88" fill="none" />
        </>
      );
    case "shocked":
      return (
        <>
          <circle cx={EYE_L.x} cy={EYE_L.y} r={11} fill={paper} />
          <circle cx={EYE_R.x} cy={EYE_R.y} r={11} fill={paper} />
          <circle cx={EYE_L.x} cy={EYE_L.y} r={4.5} fill={color} stroke="none" />
          <circle cx={EYE_R.x} cy={EYE_R.y} r={4.5} fill={color} stroke="none" />
          {brow({ x: 78, y: 34 }, { x: 102, y: 28 }, "bl")}
          {brow({ x: 142, y: 34 }, { x: 118, y: 28 }, "br")}
          <ellipse cx={110} cy={100} rx={8} ry={12} fill={color} stroke="none" />
        </>
      );
    case "angry":
      return (
        <>
          {dot(EYE_L, "el")}
          {dot(EYE_R, "er")}
          {brow({ x: 78, y: 38 }, { x: 102, y: 50 }, "bl")}
          {brow({ x: 142, y: 38 }, { x: 118, y: 50 }, "br")}
          <path d="M 92 100 Q 101 91 110 98 Q 119 105 128 96" fill="none" />
        </>
      );
    case "worried":
      return (
        <>
          {dot(EYE_L, "el")}
          {dot(EYE_R, "er")}
          {brow({ x: 78, y: 50 }, { x: 102, y: 38 }, "bl")}
          {brow({ x: 142, y: 50 }, { x: 118, y: 38 }, "br")}
          <path d="M 94 102 Q 110 93 126 102" fill="none" />
        </>
      );
    case "sad":
      return (
        <>
          {dot(EYE_L, "el")}
          {dot(EYE_R, "er")}
          {brow({ x: 78, y: 48 }, { x: 102, y: 38 }, "bl")}
          {brow({ x: 142, y: 48 }, { x: 118, y: 38 }, "br")}
          <path d="M 90 108 Q 110 86 130 108" fill="none" />
        </>
      );
    case "thinking":
      return (
        <>
          {dot(EYE_L, "el")}
          {dot(EYE_R, "er")}
          {brow({ x: 78, y: 44 }, { x: 102, y: 34 }, "bl")}
          {brow({ x: 142, y: 40 }, { x: 118, y: 42 }, "br")}
          <line x1={98} y1={98} x2={126} y2={92} />
        </>
      );
    case "neutral":
    default:
      return (
        <>
          {dot(EYE_L, "el")}
          {dot(EYE_R, "er")}
          <line x1={94} y1={96} x2={126} y2={96} />
        </>
      );
  }
}

/**
 * Garment overlays, drawn over the torso and under the arms, so the silhouette
 * reads as a costume on a stick body rather than as a redrawn character — which
 * is what keeps a role recognisable across poses without a character sheet.
 */
function Attire({ attire, color }: { attire: StickAttire; color: string }) {
  switch (attire) {
    case "labcoat":
      return (
        <>
          <path d="M 84 134 L 136 134 L 150 350 L 70 350 Z" fill={color} />
          <line x1={110} y1={168} x2={110} y2={350} />
          <path d="M 94 134 L 110 172 L 126 134" fill="none" />
        </>
      );
    case "suit":
      return (
        <>
          <path d="M 84 134 L 136 134 L 142 292 L 78 292 Z" fill={color} />
          <path d="M 94 134 L 110 168 L 126 134" fill="none" />
          <path d="M 110 168 L 118 216 L 110 232 L 102 216 Z" fill="#c62828" />
        </>
      );
    case "hoodie":
      return (
        <>
          <path d="M 84 142 Q 110 128 136 142 L 148 302 Q 110 314 72 302 Z" fill={color} />
          <path d="M 90 134 Q 110 166 130 134" fill="none" />
          <line x1={110} y1={170} x2={110} y2={206} />
        </>
      );
    case "dress":
      return <path d="M 86 134 L 134 134 L 166 332 L 54 332 Z" fill={color} />;
    case "none":
    default:
      return null;
  }
}

/** Headwear overlays, drawn over the head circle and under the face. */
function Headwear({ headwear, color }: { headwear: StickHeadwear; color: string }) {
  switch (headwear) {
    case "cap":
      return (
        <>
          <path d="M 58 44 Q 110 2 162 44 Z" fill={color} />
          <path d="M 162 44 Q 196 46 198 58 L 148 56 Z" fill={color} />
        </>
      );
    case "hardhat":
      return (
        <>
          <path d="M 62 40 Q 110 -2 158 40 Z" fill={color} />
          <rect x={44} y={40} width={132} height={12} rx={6} fill={color} />
          <line x1={110} y1={6} x2={110} y2={40} />
        </>
      );
    case "hair":
      return (
        <path
          d="M 56 64 Q 54 8 110 10 Q 166 8 164 64 Q 152 40 110 40 Q 68 40 56 64 Z"
          fill={color}
        />
      );
    case "none":
    default:
      return null;
  }
}

export default function StickFigure({
  pose = "stand",
  expression = "neutral",
  attire = "none",
  attireColor = "#9aa4b2",
  headwear = "none",
  headwearColor = "#2b2b2b",
  x,
  y,
  scale = 1,
  flip = false,
  stroke = 6,
  theme = "light",
  color,
  fill,
}: Props) {
  const palette = THEMES[theme] ?? THEMES.light;
  const ink = color ?? palette.color;
  const paper = fill ?? palette.fill;
  const g = POSES[pose] ?? POSES.stand;
  const w = BOX_W * scale;
  const h = BOX_H * scale;

  return (
    <svg
      viewBox={`0 0 ${BOX_W} ${BOX_H}`}
      width={w}
      height={h}
      style={{
        position: "absolute",
        left: x - w / 2,
        top: y - h / 2,
        overflow: "visible",
        transform: flip ? "scaleX(-1)" : undefined,
      }}
    >
      <g
        stroke={ink}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      >
        {/* Legs first, then the torso over them, so the hip reads as solid. */}
        <path d={limb(HIP_L, g.legL[0], g.legL[1])} />
        <path d={limb(HIP_R, g.legR[0], g.legR[1])} />
        <line x1={NECK_TOP.x} y1={NECK_TOP.y} x2={NECK_BOTTOM.x} y2={NECK_BOTTOM.y} />
        <path d={TORSO} fill={paper} />

        <Attire attire={attire} color={attireColor} />

        {/* Arms over the garment — bare stick arms are the register's look. */}
        <path d={limb(SHOULDER_L, g.armL[0], g.armL[1])} />
        <path d={limb(SHOULDER_R, g.armR[0], g.armR[1])} />

        <circle cx={HEAD.x} cy={HEAD.y} r={HEAD_R} fill={paper} />
        <Headwear headwear={headwear} color={headwearColor} />

        {/* The face is mirrored back when the figure is flipped, so an
            asymmetric expression stays the expression it was authored as. */}
        <g
          transform={flip ? `translate(${BOX_W} 0) scale(-1 1)` : undefined}
          strokeWidth={stroke * 0.8}
        >
          <Face expression={expression} color={ink} paper={paper} />
        </g>
      </g>
    </svg>
  );
}
