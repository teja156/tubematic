// A custom Terminal Doc move: a Caesar shift. Each letter of `text` rolls
// forward through the alphabet by SHIFT places, one after another from the
// left, like an odometer, and lands on its shifted letter.
//
// Saved with write_scene_file as generated/<video_id>/move-caesar.tsx and
// listed in customMoves as {"id": "caesar", "src": "<video_id>/move-caesar",
// "frames": 60, "text": 12}. A move draws from the `t` it is given (0 at its
// event, `frames` at its end and after), inside `box`, and imports only react,
// remotion and the kit.
import { Glyph, cellX, clamp01, ease, type MoveProps } from "../../installed/terminalDoc/kit";

const SHIFT = 3;
const A = "A".charCodeAt(0);
const shifted = (ch: string, by: number) =>
  ch >= "A" && ch <= "Z" ? String.fromCharCode(A + ((ch.charCodeAt(0) - A + by) % 26)) : ch;

export default function Caesar({ t, frames, text, box, skin }: MoveProps) {
  const size = 96;
  const y = box.y + box.h / 2;
  const n = text.length;
  return (
    <>
      {Array.from(text).map((ch, i) => {
        // Each letter starts a little after its left neighbour and rolls for
        // half the move; the last one lands at `frames`.
        const start = (i / Math.max(1, n)) * frames * 0.5;
        const p = ease.arc(clamp01((t - start) / (frames * 0.5)));
        const step = Math.floor(p * SHIFT + 1e-6);
        const done = p >= 1;
        return (
          <Glyph
            key={i}
            x={cellX(i, n, size)}
            y={y}
            size={size}
            ch={shifted(ch, step)}
            color={done ? skin.tones.red : step > 0 ? skin.tones.white : skin.tones.grey}
            skin={skin}
          />
        );
      })}
    </>
  );
}
