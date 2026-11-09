// timeline.js: standalone loops for the model sheets, and the per-frame hook.
//
// Standalone loops (model sheets, tests): window.LOOP = LOOPS[name] swaps the whole frame for that function, called with
// loop time. Give each a length: LOOPS.x = t => { ... }; LOOPS.x.len = 4;
// Every frame is a pure function of t: frames render in parallel and out of order, so nothing may carry over.
const LOOPS = {};

function drawWorld(t) {
  if (window.LOOP) window.LOOP(t);
  flushLetters();
}
