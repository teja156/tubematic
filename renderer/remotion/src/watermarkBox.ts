/*
 * Where the watermark sits on the 1080x1920 frame, and the line insert text
 * keeps to the left of. Watermark.tsx draws at these numbers; the insert
 * styles (Code Scenes, Format Packs) keep the right edge of every text in the
 * top rows of their layout at or left of KEEP_OUT_X, because an insert moves
 * up by as much as 120 px to clear the captions (mcp/inserts.py shift_for) and
 * its top row can then sit beside, and under, the mark.
 *
 * Keep in sync: mcp/tests/fixtures/*_contract.json hold KEEP_OUT_X, which
 * mcp/code_scenes.py and mcp/format_packs.py read.
 */

export const WATERMARK_WIDTH = 130;
export const WATERMARK_TOP = 32;
export const WATERMARK_RIGHT = 32;
/** The asset is 480x630, drawn at WATERMARK_WIDTH wide. */
export const WATERMARK_HEIGHT = Math.ceil((WATERMARK_WIDTH * 630) / 480);

export const FRAME_WIDTH = 1080;
export const WATERMARK_LEFT = FRAME_WIDTH - WATERMARK_RIGHT - WATERMARK_WIDTH;
export const WATERMARK_BOTTOM = WATERMARK_TOP + WATERMARK_HEIGHT;

/** Text in an insert's top rows ends at or before this x. */
export const KEEP_OUT_GAP = 18;
export const KEEP_OUT_X = WATERMARK_LEFT - KEEP_OUT_GAP;
