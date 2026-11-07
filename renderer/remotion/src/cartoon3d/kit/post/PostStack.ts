// The ported post chain as one object the scene runner drives per frame:
//   RenderPass (MSAA 4, half float) -> InkPass (world ink, own pass) -> lens blur pre + main ->
//   [bloom (emissive only) + NEUTRAL tone map + colour grade] (one EffectPass).
// Same order and values as the bridge short's Bridge.tsx (mromidev/claude-animated-shorts, MIT), built here with the
// `postprocessing` composer directly instead of the R3F <EffectComposer> wrapper, because our runner owns the render
// call (useFrame priority 1) and the R3F wrapper would fight it.
// Colour convention [tubematic]: the scene is authored colour-unmanaged (R3F `linear`: hex colours are taken as-is),
// exactly like the old InkPipeline; the composer's final pass encodes to sRGB, so `outputColorSpace` is re-asserted
// per frame against R3F's configure() (the same reason the old pipeline re-asserts shadowMap.enabled).
import * as THREE from "three";
import { BlendFunction, BloomEffect, EffectComposer, EffectPass, RenderPass, ToneMappingEffect, ToneMappingMode } from "postprocessing";
import { InkPass, noInkFallback, type InkOptions } from "./ink";
import { LensBlur } from "./lensblur";
import { GradeEffect, GRADES } from "./grade";

/** Bloom for emissive sources only. Its MIP chain always starts at half of 1080x1920, whatever the output size, so
 *  the glow keeps the same size relative to the frame at 540, 1080 and 1440 widths. ADD blend: HDR-safe. */
const makeBloom = () => {
  const b = new BloomEffect({ blendFunction: BlendFunction.ADD, intensity: 0.5, luminanceThreshold: 1.0, luminanceSmoothing: 0.2, mipmapBlur: true, levels: 6, radius: 0.6 });
  const mip = b.mipmapBlurPass;
  const setSize = mip.setSize.bind(mip);
  mip.setSize = (w: number, h: number) => setSize(Math.round((1920 * w) / Math.max(h, 1)), 1920);
  return b;
};

export interface PostFrame {
  /** focus distance along the view axis (m) */
  focus: number;
  /** blur-disc radius at infinity, px at 1080x1920; 0 = sharp (wides, aerials) */
  cInf: number;
  /** 0 = day preset, 1 = golden preset (grade blends between them) */
  golden: number;
  /** ink in fog: lines stay black up to `start` m, then move `amount` (0..1) of the way to the fog colour when fully
   *  fogged; absent = the aerial-perspective default (60 m, 0.3). A beat's river fog wants (fog.near, ~0.85). */
  inkFog?: { start: number; amount: number };
}

export class PostStack {
  readonly composer: EffectComposer;
  readonly ink: InkPass;
  readonly lens: LensBlur;
  readonly bloom: BloomEffect;
  readonly tone: ToneMappingEffect;
  readonly grade: GradeEffect;
  readonly width: number;
  readonly height: number;
  private lastGolden = -1;

  constructor(gl: THREE.WebGLRenderer, scene: THREE.Scene, cam: THREE.PerspectiveCamera, ink: InkOptions = {}, on: { ink?: boolean; lens?: boolean; bloom?: boolean; tone?: boolean; grade?: boolean } = {}) {
    const size = gl.getDrawingBufferSize(new THREE.Vector2());
    this.width = size.x;
    this.height = size.y;
    gl.toneMapping = THREE.NoToneMapping;
    gl.outputColorSpace = THREE.SRGBColorSpace;
    this.composer = new EffectComposer(gl, { multisampling: 4, frameBufferType: THREE.HalfFloatType });
    this.composer.addPass(new RenderPass(scene, cam));
    this.ink = new InkPass(scene, cam, ink);
    if (on.ink !== false) this.composer.addPass(this.ink);
    this.lens = new LensBlur({ maxCoC: 24, nearScale: 1.2 });
    if (on.lens !== false) {
      this.composer.addPass(new EffectPass(cam, this.lens.pre));
      this.composer.addPass(new EffectPass(cam, this.lens.main));
    }
    this.bloom = makeBloom();
    this.tone = new ToneMappingEffect({ mode: ToneMappingMode.NEUTRAL });
    this.grade = new GradeEffect(GRADES.day, 1);
    const last = [on.bloom !== false ? this.bloom : null, on.tone !== false ? this.tone : null, on.grade !== false ? this.grade : null].filter((e): e is NonNullable<typeof e> => !!e);
    // with every effect off the final pass still has to encode to the screen: an empty EffectPass does that
    this.composer.addPass(new EffectPass(cam, ...last));
    this.composer.setSize(size.x, size.y, false);
  }

  /** once per frame, after the scene is posed; `root` is traversed for the NOINK safety net */
  render(gl: THREE.WebGLRenderer, root: THREE.Object3D, f: PostFrame) {
    gl.outputColorSpace = THREE.SRGBColorSpace;
    gl.toneMapping = THREE.NoToneMapping;
    noInkFallback(root);
    this.lens.focus = Math.max(0.3, f.focus);
    this.lens.cInf = f.cInf;
    this.ink.fogStart = f.inkFog?.start ?? 60;
    this.ink.fogInk = f.inkFog?.amount ?? 0.3;
    const g = Math.max(0, Math.min(1, f.golden));
    if (g !== this.lastGolden) {
      this.grade.set(GRADES.day, GRADES.golden, g);
      this.lastGolden = g;
    }
    this.composer.render();
  }

  dispose() {
    this.ink.dispose();
    this.lens.dispose();
    this.composer.dispose();
  }
}
