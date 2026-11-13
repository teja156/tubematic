/*
 * Screens and inputs: phone, laptop, window, qr, keypad, password, toggle,
 * button, app. Each is centred on (0, 0) inside its OBJECTS box (../contract.ts).
 */
import React from "react";
import { rng } from "../../characterKit/geometry";
import {
  ALFA, BLUE, CORAL, CREAM, Cel, INK, JOST, MUSTARD, OLIVE, PAPER, TEAL, actProgress, ellP, fitFont, mix, polyP, rectP,
  type ObjectDrawProps,
} from "../cel";
import { screenLines } from "../contract";

const DOTS = [BLUE, MUSTARD, OLIVE, CORAL];

/** A screen's content: a title, up to three rows, the pressed row in teal, "done" turning it teal with a check. */
const ScreenContent: React.FC<{ x: number; y: number; w: number; h: number; p: ObjectDrawProps; seed: number }> = ({ x, y, w, h, p, seed }) => {
  const lines = screenLines(p.text);
  const title = lines[0] ?? "";
  const rows = lines.slice(1, 4);
  const rowH = Math.min(92, (h - 110) / 3.3);
  const on = /^row([1-3])$/.exec(p.act);
  const onRow = on && p.actT >= 0 ? Number(on[1]) - 1 : -1;
  const done = p.act === "done" ? actProgress(p.actT, 8) : 0;
  return (
    <g>
      {title && (
        <text x={x + 26} y={y + 62} fontFamily={JOST} fontWeight={600} fontSize={fitFont(title, w - 52, 44)} fill={INK}>
          {title}
        </text>
      )}
      {rows.map((r, i) => {
        const ry = y + 96 + i * (rowH + 16);
        const hot = i === onRow;
        return (
          <g key={i}>
            <Cel d={rectP(x + 18, ry, w - 36, rowH, 16)} fill={hot ? TEAL : CREAM} phase={p.phase} seed={seed + i} sw={3.5} broken={false} />
            <Cel d={ellP(x + 58, ry + rowH / 2, 20, 20)} fill={DOTS[i % DOTS.length]} phase={p.phase} seed={seed + 5 + i} sw={3.5} broken={false} />
            <text x={x + 92} y={ry + rowH / 2 + 14} fontFamily={JOST} fontWeight={600} fontSize={fitFont(r, w - 140, 40)} fill={hot ? CREAM : INK}>
              {r}
            </text>
          </g>
        );
      })}
      {done > 0 && (
        <g>
          <rect x={x} y={y + (h * (1 - done))} width={w} height={h * done} rx={16} fill={TEAL} />
          {done >= 1 && (
            <g transform={`translate(${x + w / 2} ${y + h / 2})`}>
              <path d="M-60 0 L-18 42 L66 -48" stroke={CREAM} strokeWidth={30} fill="none" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M-60 0 L-18 42 L66 -48" stroke={INK} strokeWidth={5} fill="none" strokeLinecap="round" strokeLinejoin="round" transform="translate(-6 -5)" strokeDasharray="90 9 140 8" />
            </g>
          )}
        </g>
      )}
    </g>
  );
};

export const Phone: React.FC<ObjectDrawProps> = (p) => (
  <g>
    <ellipse cx={8} cy={276} rx={150} ry={12} fill={INK} opacity={0.14} />
    <Cel d={rectP(-152, -272, 304, 540, 48)} fill={CREAM} phase={p.phase} seed={80} sw={5} />
    <Cel d={rectP(-128, -222, 256, 446, 16)} fill={PAPER} phase={p.phase} seed={81} sw={4} />
    <rect x={-36} y={-252} width={72} height={11} rx={5} fill={INK} />
    <ScreenContent x={-128} y={-222} w={256} h={446} p={p} seed={90} />
  </g>
);

export const Laptop: React.FC<ObjectDrawProps> = (p) => (
  <g>
    <ellipse cx={8} cy={202} rx={250} ry={12} fill={INK} opacity={0.14} />
    <Cel d={rectP(-230, -200, 460, 330, 18)} fill={INK} phase={p.phase} seed={113} />
    <Cel d={rectP(-210, -180, 420, 290, 8)} fill={CREAM} phase={p.phase} seed={114} sw={3} broken={false} />
    <ScreenContent x={-210} y={-180} w={420} h={290} p={p} seed={120} />
    <Cel d={polyP([[-252, 132], [252, 132], [262, 182], [-262, 182]])} fill={mix(PAPER, INK, 0.2)} phase={p.phase} seed={115} broken={false} />
    <rect x={-50} y={146} width={100} height={12} rx={6} fill={INK} opacity={0.5} />
  </g>
);

export const Window: React.FC<ObjectDrawProps> = (p) => (
  <g>
    <Cel d={rectP(-290, -210, 580, 420, 22)} fill={CREAM} phase={p.phase} seed={130} sw={5} />
    <Cel d={rectP(-290, -210, 580, 62, 22)} fill={mix(PAPER, INK, 0.12)} phase={p.phase} seed={131} sw={4} broken={false} />
    {[CORAL, MUSTARD, TEAL].map((c, i) => (
      <circle key={i} cx={-252 + i * 34} cy={-179} r={10} fill={c} stroke={INK} strokeWidth={3} />
    ))}
    <ScreenContent x={-270} y={-140} w={540} h={340} p={p} seed={135} />
  </g>
);

export const Qr: React.FC<ObjectDrawProps> = (p) => {
  const n = 21;
  const size = 220;
  const c = size / n;
  const r = rng(77);
  const x0 = -size / 2;
  let d = "";
  const finder = (i: number, j: number) => {
    for (const [fi, fj] of [[0, 0], [0, n - 7], [n - 7, 0]]) {
      const a = i - fi;
      const b = j - fj;
      if (a >= -1 && a <= 7 && b >= -1 && b <= 7) {
        if (a < 0 || b < 0 || a > 6 || b > 6) return 0;
        if (a === 0 || b === 0 || a === 6 || b === 6) return 1;
        return a >= 2 && a <= 4 && b >= 2 && b <= 4 ? 1 : 0;
      }
    }
    return -1;
  };
  for (let i = 0; i < n; i++)
    for (let j = 0; j < n; j++) {
      const fz = finder(i, j);
      if (fz === -1 ? r() < 0.48 : fz === 1) d += `M${(x0 + j * c).toFixed(1)} ${(x0 + i * c).toFixed(1)}h${c.toFixed(2)}v${c.toFixed(2)}h${(-c).toFixed(2)}Z`;
    }
  const scan = p.act === "scan" ? actProgress(p.actT) : 0;
  const done = p.act === "done" ? actProgress(p.actT, 8) : 0;
  return (
    <g>
      <Cel d={rectP(-132, -132, 264, 264, 14)} fill={CREAM} phase={p.phase} seed={140} sw={5} />
      <path d={d} fill={INK} />
      {scan > 0 && scan < 1 && (
        <g>
          <rect x={-124} y={x0 + scan * size - 5} width={248} height={10} rx={5} fill={CORAL} />
          <rect x={x0} y={x0} width={size} height={scan * size} fill={CORAL} opacity={0.18} />
        </g>
      )}
      {done > 0 && (
        <g transform={`scale(${done})`}>
          <Cel d={ellP(0, 0, 70, 70)} fill={TEAL} phase={p.phase} seed={141} sw={5} />
          <path d="M-30 2 L-8 24 L32 -22" stroke={CREAM} strokeWidth={15} fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      )}
    </g>
  );
};

export const Keypad: React.FC<ObjectDrawProps> = (p) => {
  const code = p.text.slice(0, 8);
  const typed = p.act === "type" ? Math.ceil(actProgress(p.actT) * code.length) : p.act === "done" ? code.length : 0;
  const done = p.act === "done" ? actProgress(p.actT, 8) : 0;
  const slots = Math.max(code.length, 4);
  const sw = Math.min(42, 300 / slots - 6);
  const keys = [1, 2, 3, 4, 5, 6, 7, 8, 9];
  const lastKey = typed > 0 ? Number(code[typed - 1]) : -1;
  return (
    <g>
      <Cel d={rectP(-184, -228, 368, 456, 30)} fill={CREAM} phase={p.phase} seed={150} sw={5} />
      {Array.from({ length: slots }, (_, i) => {
        const x = -((slots * (sw + 6)) / 2) + i * (sw + 6);
        return (
          <g key={i}>
            <Cel d={rectP(x, -200, sw, 58, 8)} fill={i < typed ? (done ? TEAL : MUSTARD) : PAPER} phase={p.phase} seed={151 + i} sw={3.5} broken={false} />
            {i < typed && code[i] && (
              <text x={x + sw / 2} y={-157} textAnchor="middle" fontFamily={ALFA} fontSize={Math.min(40, sw)} fill={INK}>{code[i]}</text>
            )}
          </g>
        );
      })}
      {keys.map((k, i) => {
        const kx = -104 + (i % 3) * 104;
        const ky = -60 + Math.floor(i / 3) * 96;
        const down = p.act === "type" && p.actT >= 0 && p.actT < 20 && k === lastKey;
        return (
          <g key={k}>
            <Cel d={ellP(kx, ky, 38, 38)} fill={down ? CORAL : mix(PAPER, TEAL, 0.28)} phase={p.phase} seed={160 + k} sw={3.5} broken={false} />
            <text x={kx} y={ky + 14} textAnchor="middle" fontFamily={JOST} fontWeight={600} fontSize={40} fill={down ? CREAM : INK}>{k}</text>
          </g>
        );
      })}
    </g>
  );
};

export const Password: React.FC<ObjectDrawProps> = (p) => {
  const text = p.text.slice(0, 18) || "••••••••";
  const typed = p.act === "type" ? Math.ceil(actProgress(p.actT) * text.length) : p.act === "done" || p.act === "" ? text.length : text.length;
  const done = p.act === "done";
  const shown = p.act === "type" || done ? text.slice(0, typed) : text;
  return (
    <g>
      <Cel d={rectP(-272, -70, 544, 140, 24)} fill={done ? mix(TEAL, CREAM, 0.4) : CREAM} phase={p.phase} seed={170} sw={5} />
      <g transform="translate(-220 0)">
        <Cel d={rectP(-18, -6, 36, 30, 5)} fill={MUSTARD} phase={p.phase} seed={171} sw={3.5} broken={false} />
        <path d="M-11 -6 V-16 A11 11 0 0 1 11 -16 V-6" stroke={INK} strokeWidth={4.5} fill="none" />
      </g>
      <text x={-180} y={18} fontFamily={JOST} fontWeight={600} fontSize={fitFont(shown || " ", 420, 50)} fill={INK} letterSpacing={2}>{shown}</text>
      {done && <path d="M196 0 L214 18 L246 -18" stroke={TEAL} strokeWidth={10} fill="none" strokeLinecap="round" strokeLinejoin="round" />}
    </g>
  );
};

export const Toggle: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "flip" ? actProgress(p.actT, 6) : 0;
  return (
    <g>
      <Cel d={rectP(-130, -66, 260, 132, 66)} fill={k >= 0.5 ? TEAL : mix(PAPER, INK, 0.15)} phase={p.phase} seed={180} sw={5} broken={false} />
      <circle cx={-64 + k * 128} cy={0} r={50} fill={CREAM} stroke={INK} strokeWidth={5} />
    </g>
  );
};

export const Button: React.FC<ObjectDrawProps> = (p) => {
  const lit = p.act === "light" && p.actT >= 0;
  const text = p.text.slice(0, 14);
  return (
    <g>
      <Cel d={rectP(-170, -58, 340, 128, 40)} fill={mix(CORAL, INK, 0.35)} phase={p.phase} seed={190} sw={0} />
      <Cel d={rectP(-170, -70, 340, 124, 40)} fill={lit ? TEAL : CORAL} phase={p.phase} seed={191} sw={5} broken={false} />
      {text && <text x={0} y={10} textAnchor="middle" fontFamily={ALFA} fontSize={fitFont(text, 280, 54, true)} fill={CREAM}>{text}</text>}
    </g>
  );
};

export const App: React.FC<ObjectDrawProps> = (p) => {
  const b = p.act === "bounce" && p.actT >= 0 && p.actT < 12 ? Math.sin((p.actT / 12) * Math.PI) * -24 : 0;
  const text = p.text.slice(0, 10);
  return (
    <g transform={`translate(0 ${b})`}>
      <Cel d={rectP(-100, -130, 200, 200, 46)} fill={TEAL} phase={p.phase} seed={200} sw={5} />
      <Cel d={ellP(0, -30, 48, 48)} fill={CREAM} phase={p.phase} seed={201} sw={4} broken={false} />
      <Cel d={ellP(0, -30, 20, 20)} fill={CORAL} phase={p.phase} seed={202} sw={3.5} broken={false} />
      {text && <text x={0} y={122} textAnchor="middle" fontFamily={JOST} fontWeight={600} fontSize={fitFont(text, 230, 40)} fill={INK}>{text}</text>}
    </g>
  );
};
