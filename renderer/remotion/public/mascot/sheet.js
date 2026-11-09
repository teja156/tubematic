// sheet.js: model sheets for ANY mascot (frame.html?code=<mascot.js>&sheet=turn|feels|act). The mascot file must set
// window.MASCOT = fn(x, y, u, o). The sheets are what a person reviews before a mascot is used: nothing here animates speech: the
// mouth only ever shows an emotion. window.renderSheet(name) draws one sheet into the page's #out canvas.
(() => {
  const M = (...a) => window.MASCOT(...a);
  const label = (txt, x, y, size = 22) => letter(txt, x, y, size, PAL.ink, { ink: false, alpha: .8 });
  const floor = (y, x0 = 0, x1 = W) => inkLine([[x0 + 40, y + 6], [W / 2, y + 4], [x1 - 40, y + 7]], .6, mixCol(PAL.paper, PAL.ink, .35), 'inkfine', .5);
  // Turnaround: the four drawn views, plus the 3/4 view flipped.
  LOOPS.turn = t => {
    const vs = [['front', false], ['q', false], ['side', false], ['back', false], ['q', true]];
    vs.forEach(([v, flip], i) => { const x = 210 + i * 375; M(x, 690, 21, { ...feel('neutral', t, { seed: i }), view: v, flip, boilKey: 'turn' + i }); label(flip ? 'q (flip)' : v, x, 760, 26); });
    floor(690);
  };
  LOOPS.turn.len = 4;
  // Ten emotions from the shared engine, front view.
  LOOPS.feels = t => {
    const names = ['neutral', 'happy', 'excited', 'thinking', 'idea', 'surprised', 'confused', 'sad', 'love', 'cool'];
    const cols = 5, cw = W / cols, ch = H / 2;
    names.forEach((n, i) => { const cx = cw * (i % cols) + cw / 2, gy = ch * Math.floor(i / cols) + ch - 70; M(cx, gy, 15, { ...feel(n, t, { seed: i }), emoteAge: 1, boilKey: 'feel' + i }); label(n, cx, gy + 42, 24); });
    floor(ch - 70); floor(H - 70);
  };
  LOOPS.feels.len = 4;
  // Acting: walk in, think, idea, excited with a jump, happy; arms raised along the way.
  LOOPS.act = t => {
    floor(840, 200, 1720);
    const walk = stroll(t, 0, 1.4, 420, 960, 24);
    const keys = [[0, 'neutral'], [1.6, 'thinking'], [3.0, 'idea'], [4.0, 'excited'], [5.6, 'happy']];
    const j = jump(t, 4.5, 5.15, 3.5), e = emotions(t, keys);
    M(walk.x, 840, 24, { ...e, ...(t < 1.4 ? { walk: walk.walk, view: walk.view, flip: walk.flip } : {}), dy: (e.dy || 0) + walk.dy + j.dy, sq: (e.sq || 0) + j.sq, boilKey: 'act' });
  };
  LOOPS.act.len = 7;

  // The act sheet is a contact sheet of eight moments; turn and feels are one frame.
  const ACT_TIMES = [.5, 1.0, 2.2, 3.3, 4.2, 4.8, 5.9, 6.5];
  window.renderSheet = async (name) => {
    if (!LOOPS[name]) throw new Error('unknown sheet: ' + name);
    window.LOOP = LOOPS[name];
    outC.width = W; outC.height = H;
    if (name === 'act') {
      const r = await window.renderContact(ACT_TIMES, 4, 480, [240, 420, 960, 540]);
      outC.width = r.canvas.width; outC.height = r.canvas.height; outX.drawImage(r.canvas, 0, 0);
    } else { T = 1.1; await redraw(); composite(T); }
  };
})();
