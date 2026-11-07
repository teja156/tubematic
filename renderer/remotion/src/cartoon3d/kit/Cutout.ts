// Flat 2D character on a camera-facing plane, lit by the scene (with a fixed
// "lit normal", see below), receiving and casting the silhouette's shadow,
// with a soft contact shadow under the feet. The old back-light "rim" (a
// second silhouette card shifted sideways) is gone: in close shots it read as
// a grey ghost duplicate of the body.
//
// SPIKE 2: the drawing is now REDRAWN EVERY FRAME from continuous parameters
// (walk phase, bob, lean, eyelid, head tilt) instead of swapping between a
// handful of pre-baked pose pictures. One canvas + one texture per character,
// re-uploaded per frame. That is what lets a character be animated "on ones"
// the way the reference does, rather than flip-booking between two poses.
//
// Cost: one 2D canvas redraw (~50 path ops, well under a millisecond) plus one
// texture upload per character per frame. Baking a cache keyed on quantised
// parameters was rejected: at 1024x2048 RGBA each cached state is 8 MB, so a
// few dozen states would exhaust the GTX 1650's 4 GB.
import * as THREE from "three";
import { cutoutNormalMaterial } from "./InkPipeline";

export type DrawFn = (ctx: CanvasRenderingContext2D, w: number, h: number) => void;

export class Cutout {
  readonly mesh: THREE.Mesh;
  readonly width: number;
  readonly height: number;
  private ctx: CanvasRenderingContext2D;
  private tex: THREE.CanvasTexture;
  private mat: THREE.MeshLambertMaterial;
  private depthMat: THREE.MeshDepthMaterial;
  private px: number;
  /** world-space normal the card is LIT with (see litNormal below) */
  private litNormal = new THREE.Vector3(0, 1, 0);
  /** soft contact shadow under the feet */
  private contact: THREE.Mesh;

  // height in metres; the canvas is drawn at 1:2 (w:h) in a 512x1024 design space
  constructor(height: number, px = 1024) {
    this.height = height;
    this.width = height / 2;
    this.px = px;
    const c = document.createElement("canvas");
    c.width = px;
    c.height = px * 2;
    const ctx = c.getContext("2d");
    if (!ctx) throw new Error("no 2d context");
    this.ctx = ctx;
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    this.tex = tex;
    this.mat = new THREE.MeshLambertMaterial({
      map: tex,
      alphaTest: 0.5,
      side: THREE.DoubleSide,
      emissiveMap: tex,
      emissive: new THREE.Color(0.12, 0.12, 0.12),
    });
    // LIT NORMAL. A camera-facing card's real normal points at the lens, so
    // its key-light term swings with every camera move and a character goes
    // flat or dark for no story reason. Instead the card is lit as if its
    // normal were `litNormal` (set per frame: toward the key, tilted up), so it
    // takes the same sun + sky as the props around it, receives the real
    // shadow map (a character standing in a building's shade goes into shade),
    // and never depends on where the camera is.
    const litNormal = { value: this.litNormal };
    this.mat.onBeforeCompile = (sh) => {
      sh.uniforms.uLitNormal = litNormal;
      sh.vertexShader = sh.vertexShader
        .replace("#include <common>", "#include <common>\nuniform vec3 uLitNormal;")
        .replace("#include <defaultnormal_vertex>", "vec3 transformedNormal = normalize((viewMatrix * vec4(uLitNormal, 0.0)).xyz);");
      sh.fragmentShader = sh.fragmentShader.replace(
        "#include <normal_fragment_begin>",
        "float faceDirection = 1.0; vec3 normal = normalize(vNormal); vec3 nonPerturbedNormal = normal;",
      );
    };
    this.mat.customProgramCacheKey = () => "cutout-litnormal";
    this.depthMat = new THREE.MeshDepthMaterial({
      depthPacking: THREE.RGBADepthPacking,
      map: tex,
      alphaTest: 0.5,
      side: THREE.DoubleSide,
    });
    const geo = new THREE.PlaneGeometry(this.width, height);
    geo.translate(0, height / 2, 0); // origin at the feet
    this.mesh = new THREE.Mesh(geo, this.mat);
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = true;
    this.mesh.customDepthMaterial = this.depthMat; // alpha-tested shadow: the shape, not the quad
    this.mesh.userData.normalMaterial = cutoutNormalMaterial(tex);

    // CONTACT SHADOW: a soft dark ellipse under the feet. The cast shadow
    // from the key already draws the silhouette on the ground; this is the
    // ambient-occlusion pool that glues the feet to the floor in every light,
    // including when the key is behind the camera and the cast shadow hides.
    const sc = document.createElement("canvas");
    sc.width = sc.height = 128;
    const sctx = sc.getContext("2d")!;
    const grad = sctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    // the reference's contact pool multiplies the ground by ~0.59 under the feet (0.52-0.74); measured at 0.98 here
    // with the old 0.55 x 0.55 stops, so the pool is denser and a touch wider
    // (drawn as an opaque grey ramp used as the ALPHA map of a flat dark colour: the old black-with-alpha canvas
    // uploaded with no alpha at all, so no card ever had a pool under its feet)
    grad.addColorStop(0, "rgb(230,230,230)");
    grad.addColorStop(0.5, "rgb(128,128,128)");
    grad.addColorStop(1, "rgb(0,0,0)");
    sctx.fillStyle = "#000";
    sctx.fillRect(0, 0, 128, 128);
    sctx.fillStyle = grad;
    sctx.fillRect(0, 0, 128, 128);
    const stex = new THREE.CanvasTexture(sc);
    const cgeo = new THREE.PlaneGeometry(this.width * 1.1, this.width * 0.5);
    cgeo.rotateX(-Math.PI / 2);
    this.contact = new THREE.Mesh(
      cgeo,
      new THREE.MeshBasicMaterial({ color: 0x0a0818, alphaMap: stex, transparent: true, depthWrite: false, fog: false }),
    );
    this.contact.position.set(0, 0.015, 0.02);
    this.contact.renderOrder = 1;
    this.contact.castShadow = false;
    this.contact.receiveShadow = false;
    this.contact.userData.noInk = true;
    this.mesh.add(this.contact);
  }

  /** the world-space direction the card is lit from (toward the key, tilted
   *  up so the sky term reads as sky). Set every frame by the scene. */
  setLitNormal(n: THREE.Vector3) {
    this.litNormal.copy(n).normalize();
  }

  /** contact-shadow strength 0..1 (less under a lamp-lit night figure) */
  setContact(amount: number) {
    (this.contact.material as THREE.MeshBasicMaterial).opacity = amount;
  }

  /** redraw the character for this frame in the 512x1024 design space */
  redraw(draw: DrawFn) {
    const ctx = this.ctx;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.px, this.px * 2);
    ctx.scale(this.px / 512, this.px / 512);
    draw(ctx, 512, 1024);
    ctx.restore();
    this.tex.needsUpdate = true;
  }

  // ambient colour the flat art picks up regardless of the key light (keeps a
  // 2D character readable when the key is behind it)
  setTint(c: THREE.Color, amount: number) {
    this.mat.emissive.copy(c).multiplyScalar(amount);
  }

  // yaw-only billboard toward the camera (stays upright, so its shadow stays a
  // standing figure)
  face(cam: THREE.Camera, blend = 1, baseYaw = 0) {
    const p = this.mesh.position;
    const yaw = Math.atan2(cam.position.x - p.x, cam.position.z - p.z);
    this.mesh.rotation.set(0, baseYaw + (yaw - baseYaw) * blend, 0);
  }

  // canvas coordinates (512x1024 space) -> world, for attaching 3D props to hands
  canvasToWorld(x: number, y: number) {
    const local = new THREE.Vector3(((x - 256) / 512) * this.width, (1 - y / 1024) * this.height, 0.02);
    this.mesh.updateMatrixWorld(true);
    return local.applyMatrix4(this.mesh.matrixWorld);
  }
}
