// Judgment windows, hold totals and score tables.  Every number here is copied from the decompiled game:
//   NoteJudge.cs (windows in 60 fps frames, JudgeAdjustMs, GetJudgeTiming, GetSlideJudgeTiming, JudgeHoldTotal)
//   NoteScore.cs (score per judgment and note kind)
// test/rules.test.mjs re-reads those .cs files and fails if any table here drifts from them.

export const FRAME = 16.666666;            // NoteJudge uses 16.666666f, not 1000/60
export const JUDGE_ADJUST_MS = 50;         // NoteJudge.JudgeAdjustMs: every window is shifted +50 ms (the arcade's display lag)

// ETiming
export const T = Object.freeze({
  TooFast: 0, FastGood: 1, FastGreat3rd: 2, FastGreat2nd: 3, FastGreat: 4, FastPerfect2nd: 5, FastPerfect: 6, Critical: 7,
  LatePerfect: 8, LatePerfect2nd: 9, LateGreat: 10, LateGreat2nd: 11, LateGreat3rd: 12, LateGood: 13, TooLate: 14, End: 15,
});
export const TIMING_NAMES = Object.keys(T);

// EJudgeType
export const J = Object.freeze({ Tap: 0, HoldOut: 1, SlideOut: 2, Touch: 3, ExTap: 4, Break: 5 });

// frames, per EJudgeType, 15 boundaries each
export const WINDOW_FRAMES = [
  [-9, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 9],                       // Tap
  [-9, -6, -5, -4, -3, -2, -1, 0, 1, 4, 8, 9, 10, 11, 14],                    // HoldOut
  [-36, -26, -22, -18, -14, -14, -14, 0, 14, 14, 14, 16, 22, 26, 36],         // SlideOut
  [-9, -9, -9, -9, -9, -9, -9, 0, 9, 10.5, 12, 13, 14, 15, 18],               // Touch
  [-9, -9, -9, -9, -9, -9, -9, 0, 9, 9, 9, 9, 9, 9, 9],                       // ExTap
  [-9, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 9],                       // Break
];
const TBL = WINDOW_FRAMES.map((row) => row.map((f) => f * FRAME + JUDGE_ADJUST_MS));

export const HOLD_HEAD_MS = 50 + JUDGE_ADJUST_MS;          // JudgeHoldHeadFrame
export const HOLD_TAIL_MS = 150 + JUDGE_ADJUST_MS;         // JudgeHoldTailFrame
export const TOUCH_HOLD_HEAD_MS = 200 + JUDGE_ADJUST_MS;   // JudgeTouchHoldHeadFrame
export const TOUCH_HOLD_TAIL_MS = 150 + JUDGE_ADJUST_MS;   // JudgeTouchHoldTailFrame

export const checkStart = (type) => TBL[type][0];
export const checkEnd = (type) => TBL[type][14];

// diffMs = current time - note time.  optionFrames = the player's judge-timing option (in frames).
// Returns [timing, diff with the +50 ms adjust removed again] like the game's `ref float`.
export function getJudgeTiming(diffMs, optionFrames, type) {
  const t = TBL[type];
  let m = diffMs - optionFrames * FRAME;
  if (type === J.SlideOut) m += JUDGE_ADJUST_MS;
  const r = m < t[0] ? T.TooFast : m < t[1] ? T.FastGood : m < t[2] ? T.FastGreat3rd : m < t[3] ? T.FastGreat2nd : m < t[4] ? T.FastGreat
    : m < t[5] ? T.FastPerfect2nd : m < t[6] ? T.FastPerfect : m <= t[8] ? T.Critical : m <= t[9] ? T.LatePerfect : m <= t[10] ? T.LatePerfect2nd
    : m <= t[11] ? T.LateGreat : m <= t[12] ? T.LateGreat2nd : m <= t[13] ? T.LateGreat3rd : m <= t[14] ? T.LateGood : T.TooLate;
  return [r, m - JUDGE_ADJUST_MS];
}

// slide ends are judged against the time their last sensor is reached; the Critical window grows by a quarter of that wait
export function getSlideJudgeTiming(diffMs, optionFrames, lastWaitMs) {
  const t2 = TBL[J.SlideOut];
  const q = lastWaitMs / 4;
  const lo = t2[6] - q, hi = t2[8] + q;
  const m = diffMs - optionFrames * FRAME;
  if (lo <= m && m <= hi && t2[0] <= m && m <= t2[14]) return [T.Critical, m];
  return getJudgeTiming(diffMs, optionFrames, J.SlideOut);
}

// JudgeBox
export const BOX = Object.freeze({ Miss: 0, Good: 1, Great: 2, Perfect: 3, Critical: 4 });
export function convertJudge(timing) {
  switch (timing) {
    case T.FastGood: case T.LateGood: return BOX.Good;
    case T.FastGreat3rd: case T.FastGreat2nd: case T.FastGreat: case T.LateGreat: case T.LateGreat2nd: case T.LateGreat3rd: return BOX.Great;
    case T.FastPerfect2nd: case T.FastPerfect: case T.LatePerfect: case T.LatePerfect2nd: return BOX.Perfect;
    case T.Critical: return BOX.Critical;
    default: return BOX.Miss;
  }
}
export const isFast = (timing) => timing >= T.FastGood && timing <= T.FastPerfect;
export const isLate = (timing) => timing >= T.LatePerfect && timing <= T.LateGood;

// hold body result by how much of the body was released (rows: 0-33 %, 34-67 %, 68-95 %, 96-100 %, never held)
const HOLD_PERCENT = [0, 33, 67, 95, 100];
const { FastGood: FG, FastGreat: FGr, FastPerfect: FP, Critical: C, LatePerfect: LP, LateGreat: LGr, LateGood: LG, TooFast: TF, TooLate: TL } = T;
const HOLD_PARAM = [
  [FG, FGr, FGr, FGr, FGr, FP, FP, C, LP, LP, LGr, LGr, LGr, LGr, LG],
  [FG, FGr, FGr, FGr, FGr, FP, FP, LP, LP, LP, LGr, LGr, LGr, LGr, LG],
  [FG, FG, FGr, FGr, FGr, FGr, FGr, LGr, LGr, LGr, LGr, LGr, LGr, LG, LG],
  [FG, FG, FG, FG, FG, FG, FG, LG, LG, LG, LG, LG, LG, LG, LG],
  [TF, FG, FG, FG, FG, FG, FG, LG, LG, LG, LG, LG, LG, LG, TL],
];
export function judgeHoldTotal(holdMs, releasedMs, headTiming, bodyOn, isTouchHold) {
  const head = isTouchHold ? TOUCH_HOLD_HEAD_MS : HOLD_HEAD_MS;
  if (holdMs <= head + HOLD_TAIL_MS) return headTiming;
  const body = holdMs - (head + HOLD_TAIL_MS);
  if (!bodyOn) return HOLD_PARAM[4][headTiming];
  const pct = Math.min(100, Math.ceil((releasedMs / body) * 100));
  for (let i = 0; i < HOLD_PERCENT.length; i++) if (HOLD_PERCENT[i] >= pct) return HOLD_PARAM[i][headTiming];
  return HOLD_PARAM[4][headTiming];
}

// EScoreType
export const K = Object.freeze({ Tap: 0, Hold: 1, Slide: 2, Break: 3, Touch: 4, BreakBonus: 5 });
// score per ETiming, per EScoreType
export const SCORE = [
  [0, 250, 400, 400, 400, 500, 500, 500, 500, 500, 400, 400, 400, 250, 0],
  [0, 500, 800, 800, 800, 1000, 1000, 1000, 1000, 1000, 800, 800, 800, 500, 0],
  [0, 750, 1200, 1200, 1200, 1500, 1500, 1500, 1500, 1500, 1200, 1200, 1200, 750, 0],
  [0, 1000, 1250, 1500, 2000, 2500, 2500, 2500, 2500, 2500, 2000, 1500, 1250, 1000, 0],
  [0, 250, 400, 400, 400, 500, 500, 500, 500, 500, 400, 400, 400, 250, 0],
  [0, 30, 40, 40, 40, 50, 75, 100, 75, 50, 40, 40, 40, 30, 0],
];
export const judgeScore = (timing, kind = K.Tap) => SCORE[kind][timing];
