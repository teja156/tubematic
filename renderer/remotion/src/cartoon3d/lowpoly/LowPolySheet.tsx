// The Low-Poly Skit figure sheet (TMDEV-250), for a person to approve the house figure. One page per frame:
// page 0 the figure from the front, the side and three quarters, then three colourways; page 1 the face set and a
// crowd of seeded random figures. Orthographic, so a person judges proportions without perspective. No video uses it.
import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { buildFigure, HOUSE, mulberry, randomOutfit, type Figure, type Outfit } from "./figure";
import { FACE_NAMES, setFace, type FaceName } from "./faces";
import { applyPose, POSES, type Pose, type PoseName } from "./poses";
import { dancePose, walkPose } from "./cycles";

export const SHEET_PAGES = 3;
const ZOOM = 600;
const wx = (px: number) => (px - 540) / ZOOM;
const wy = (py: number) => (960 - py) / ZOOM;

const place = (f: Figure, px: number, feetPy: number, scale = 1, yaw = 0, z = 0) => {
  f.root.scale.setScalar(scale);
  f.root.position.set(wx(px), wy(feetPy), z);
  f.root.rotation.y = yaw;
  return f;
};
const bust = (f: Figure) => {
  f.body.children[0].visible = false; // pelvis
  f.joints.spine.children[0].visible = false; // torso
  for (const j of [f.joints.shoulderL, f.joints.shoulderR, f.joints.hipL, f.joints.hipR]) j.visible = false;
};
const relax = (f: Figure, rnd: () => number) => {
  f.joints.shoulderL.rotation.set((rnd() - 0.5) * 0.3, 0, 0.12);
  f.joints.shoulderR.rotation.set((rnd() - 0.5) * 0.3, 0, -0.12);
  f.joints.elbowL.rotation.x = -0.15 - rnd() * 0.2;
  f.joints.elbowR.rotation.x = -0.15 - rnd() * 0.2;
  f.joints.neck.rotation.y = (rnd() - 0.5) * 0.5;
};

const POSE_NAMES = Object.keys(POSES) as PoseName[];
const POSE_SCALE = 0.36;
/** poses that read from the side */
const SIDE_VIEW = new Set<PoseName>(["sit", "lie", "fall", "hold", "point", "stomp"]);
const poseSlot = (i: number) => ({ px: 135 + (i % 4) * 270, feet: 260 + Math.floor(i / 4) * 270 });
const STRIPS: { name: string; y: number; poses: Pose[] }[] = [
  { name: "WALK: a step every 11 frames", y: 1380, poses: [0, 3, 6, 9].map((f) => walkPose(f)) },
  { name: "JIG: a knee lift every 5 frames", y: 1680, poses: [1, 3, 6, 8].map((f) => dancePose(f)) },
];

const COLOURWAYS: { name: string; o: Outfit }[] = [
  { name: "teal", o: HOUSE },
  { name: "coral", o: { skin: "#a8683c", hair: "#16161c", hairStyle: "tuft", shirt: "#ef6a4a", trousers: "#3a3a40", boots: "#e9e6df", sole: "#33333b", stubble: true } },
  { name: "mustard", o: { skin: "#f6cba3", hair: "#f2f0ea", hairStyle: "bob", shirt: "#e7b53c", trousers: "#2c4a3e", boots: "#4b3a2e", sole: "#33333b" } },
];

const Page0: React.FC = () => {
  const figs = useMemo(() => {
    const r = mulberry(3);
    const mk = (o: Outfit, px: number, feet: number, s: number, yaw: number) => {
      const f = buildFigure(o); setFace(f.headMount, "smile"); relax(f, r); return place(f, px, feet, s, yaw);
    };
    return [
      mk(HOUSE, 190, 800, 1, 0), mk(HOUSE, 540, 800, 1, Math.PI / 2), mk(HOUSE, 890, 800, 1, Math.PI / 5),
      ...COLOURWAYS.map((c, i) => mk(c.o, 200 + i * 340, 1660, 0.85, 0.35)),
    ];
  }, []);
  return <>{figs.map((f, i) => <primitive key={i} object={f.root} />)}</>;
};

const Page2: React.FC = () => {
  const figs = useMemo(() => {
    const out: Figure[] = [];
    POSE_NAMES.forEach((n, i) => {
      const f = buildFigure({ ...HOUSE, shirt: ["#2f9aa8", "#ef6a4a", "#e7b53c", "#6d5bc9"][i % 4] }); setFace(f.headMount, n === "fall" || n === "flinch" ? "shock" : n === "bang" ? "shout" : "smile");
      applyPose(f, POSES[n]); const { px, feet } = poseSlot(i); place(f, px, feet, POSE_SCALE, SIDE_VIEW.has(n) ? 1.2 : 0.25); out.push(f);
    });
    STRIPS.forEach((st) => st.poses.forEach((p, i) => { const f = buildFigure(HOUSE); setFace(f.headMount, "neutral"); applyPose(f, p); place(f, 135 + i * 270, st.y, POSE_SCALE, 0.4); out.push(f); }));
    return out;
  }, []);
  return <>{figs.map((f, i) => <primitive key={i} object={f.root} />)}</>;
};

const Page1: React.FC = () => {
  const figs = useMemo(() => {
    const out: Figure[] = [];
    const r = mulberry(11);
    FACE_NAMES.forEach((name: FaceName, i) => {
      const f = buildFigure({ ...HOUSE, hairStyle: i % 3 === 1 ? "tuft" : "cap", hair: i % 2 ? "#3a2616" : "#d8a23a", shirt: ["#2f9aa8", "#ef6a4a", "#e7b53c", "#6d5bc9"][i % 4] });
      setFace(f.headMount, name); bust(f);
      const s = 1.55, tx = 135 + (i % 4) * 270, ty = i < 4 ? 250 : 600;
      f.root.scale.setScalar(s); f.root.position.set(wx(tx), wy(ty) - 0.825 * s, 0);
      out.push(f);
    });
    const faces: FaceName[] = ["neutral", "smile", "grin", "blank", "smug", "worry"];
    for (let row = 0; row < 5; row++) {
      for (let c = 0; c < 11; c++) {
        const f = buildFigure(randomOutfit(r)); setFace(f.headMount, faces[Math.floor(r() * faces.length)]); relax(f, r);
        place(f, 60 + c * 96 + (row % 2) * 48, 1760 - row * 125, 0.5, (r() - 0.5) * 0.5, -row * 0.05);
        out.push(f);
      }
    }
    return out;
  }, []);
  return <>{figs.map((f, i) => <primitive key={i} object={f.root} />)}</>;
};

const cap: React.CSSProperties = { position: "absolute", font: "600 24px system-ui, sans-serif", whiteSpace: "nowrap", color: "#3b3a36", textAlign: "center", transform: "translateX(-50%)", letterSpacing: 1 };
const Label: React.FC<{ x: number; y: number; children: React.ReactNode; big?: boolean }> = ({ x, y, children, big }) => (
  <div style={{ ...cap, left: x, top: y, ...(big ? { font: "700 34px system-ui, sans-serif" } : {}) }}>{children}</div>
);

export const LowPolySheet: React.FC = () => {
  const page = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: "#ece6d9" }}>
      <ThreeCanvas width={1080} height={1920} orthographic camera={{ zoom: ZOOM, position: [0, 0, 20], near: 0.1, far: 100 }} gl={{ antialias: true }}>
        <ambientLight intensity={1.15} />
        <directionalLight position={[2, 4, 6]} intensity={1.5} />
        <directionalLight position={[-3, 1, 2]} intensity={0.35} color="#bcd0ff" />
        {page === 0 ? <Page0 /> : page === 1 ? <Page1 /> : <Page2 />}
      </ThreeCanvas>
      {page === 0 ? (<>
        <Label x={540} y={40} big>Low-Poly Skit: the house figure</Label>
        <Label x={190} y={830}>FRONT</Label><Label x={540} y={830}>SIDE</Label><Label x={890} y={830}>THREE QUARTERS</Label>
        <Label x={540} y={900}>1.0 tall, about 4 heads, 18 flat-shaded parts</Label>
        {COLOURWAYS.map((c, i) => <Label key={c.name} x={200 + i * 340} y={1700}>{c.name.toUpperCase()}</Label>)}
      </>) : page === 2 ? (<>
        <Label x={540} y={40} big>poses and cycles</Label>
        {POSE_NAMES.map((n, i) => <Label key={n} x={poseSlot(i).px} y={poseSlot(i).feet + 18}>{n.toUpperCase()}</Label>)}
        {STRIPS.map((st) => <Label key={st.name} x={540} y={st.y + 24}>{st.name}</Label>)}
      </>) : (<>
        <Label x={540} y={40} big>faces swap on a frame; mouths never move</Label>
        {FACE_NAMES.map((n, i) => <Label key={n} x={135 + (i % 4) * 270} y={(i < 4 ? 250 : 600) + 135}>{n.toUpperCase()}</Label>)}
        <Label x={540} y={760}>crowd: one figure, seeded colours (instanced in a video)</Label>
      </>)}
    </AbsoluteFill>
  );
};
