// Slide judging: a port of SlideRoot (hit-area progression + end judgment) and SlideManager.GetSlideHitArea / GetSlideTypeLength.
import { T, J, FRAME, JUDGE_ADJUST_MS, checkStart, getSlideJudgeTiming } from './timing.mjs';
import { areaIndex, rotateArea, isCArea } from './areas.mjs';

// SlideType numbers used by slides.json (Manager/SlideType.cs); *_R types count their length the other way round
export const SLIDE = Object.freeze({ Straight: 1, CircleL: 2, CircleR: 3, CurveL: 4, CurveR: 5, ThunderL: 6, ThunderR: 7, Corner: 8, BendL: 9, BendR: 10, SkipL: 11, SkipR: 12, Fan: 13 });
const RIGHT_HANDED = new Set([SLIDE.BendR, SLIDE.CircleR, SLIDE.CurveR, SLIDE.SkipR, SLIDE.ThunderR]);
// ma2 slide record code -> SlideType (Manager/Ma2fileRecordID.cs)
export const SLIDE_CODE = { SI_: 1, SCL: 2, SCR: 3, SUL: 4, SUR: 5, SSL: 6, SSR: 7, SV_: 8, SXL: 9, SXR: 10, SLL: 11, SLR: 12, SF_: 13 };

// SlideManager.GetSlideTypeLength
export function slideTypeLength(type, start, end) {
  let n = end < start ? 8 + end - start : end - start;
  if (RIGHT_HANDED.has(type)) n = (8 - n) % 8;
  return n;
}

// slides.json: { types: [ { paths: [len][point [x,y,dist,heading]], hit: [start][len][ {push, release, points:[names]} ] } ] }
export function hitAreasFor(slideData, type, start, end, starLane) {
  const startRel = (start - starLane + 8) % 8;
  const list = slideData.types[type]?.hit?.[startRel]?.[slideTypeLength(type, start, end)];
  return list ?? [];
}

// pieces: [{ty, f, e, t0, t1}] (a plain slide is one piece; chained slides have several, each starting where the last arrived)
export class SlideTracker {
  constructor(note, slideData) {
    this.note = note;
    this.lane = note.l;                             // ButtonId
    this.appear = note.t;                           // the star's note time
    const pieces = note.segs;
    this.launch = pieces[0].t0;                     // StarLaunchMsec
    this.arrive = pieces[pieces.length - 1].t1;     // StarArriveMsec
    this.tail = this.arrive;                        // TailMsec
    // _hitAreaList: the first piece's areas, then each later piece's areas minus its first (that one is kept as the junction "sub" area)
    this.areas = hitAreasFor(slideData, pieces[0].ty, pieces[0].f, pieces[0].e, this.lane).map((a) => ({ ...a, points: a.points.map((n) => areaIndex[n]) }));
    for (let i = 1; i < pieces.length; i++) {
      const next = hitAreasFor(slideData, pieces[i].ty, pieces[i].f, pieces[i].e, this.lane);
      next.slice(1).forEach((a) => this.areas.push({ ...a, points: a.points.map((n) => areaIndex[n]) }));
    }
    this.playable = this.areas.length > 0;
    this.hitIndex = 0; this.hitSubIndex = 0; this.hitIn = false;
    this.result = T.End;
    const total = this.areas.reduce((s, a) => s + a.push + a.release, 0);
    const last = this.areas[this.areas.length - 1];
    this.lastWait = total > 0 ? (this.arrive - this.launch) * (last.push / total) : 0;   // lastWaitTime
    this.lastWaitForJudge = this.lastWait;
    this.ended = false;
    this.progress = 0;                              // for drawing: how far along the sensors the player is (0..1)
    this.lastNow = null;
    // special-cased "skip" slides may skip over one sensor (IsExtraSlideForNextCheck): types SkipL / SkipR
    this.skipType = pieces[0].ty === SLIDE.SkipL || pieces[0].ty === SLIDE.SkipR;
    this.skipLen = slideTypeLength(pieces[0].ty, pieces[0].f, pieces[0].e);
  }

  _pushed(area, sensors) {                          // InputManager.ConvertTouchPanelRotatePush: rotate by the star's lane
    if (isCArea(area)) return sensors[areaIndex.C1] || sensors[areaIndex.C2];
    return sensors[rotateArea(area, this.lane)];
  }
  _checkTouch(index, isIn, sensors) {
    const a = this.areas[index];
    if (!isIn) {
      for (let n = 0; n < a.points.length; n++) {
        if (this._pushed(a.points[n], sensors)) {
          this.hitIndex = index; this.hitSubIndex = n; this.hitIn = true;
          if (index === this.areas.length - 1) this.hitIndex = index + 1;
          return true;
        }
      }
      return false;
    }
    if (!this._pushed(a.points[this.hitSubIndex], sensors)) { this.hitIndex = index + 1; this.hitSubIndex = 0; this.hitIn = false; return true; }
    return false;
  }
  // NextCheck / IsUnderThreePointSlideCheck / IsExtraSlideCheck: may the player skip a sensor?
  _nextCheck() {
    if (this.skipType) {
      const len = this.skipLen;
      const extra = (n) => (this.hitIndex === n ? this.hitIn : true);
      if (len >= 1 && len <= 3) return extra(1);
      if (len === 4) return extra(1) && extra(3);
      return true;
    }
    const n = this.areas.length;
    if (n > 3) return true;
    if (n <= 3 && n - 1 !== this.hitIndex + 1) return true;
    if (n <= 3 && n - 1 === this.hitIndex + 1 && this.hitIn) return true;
    return false;
  }

  _judge(now, opt) {                                // SlideRoot.Judge
    if (now - opt * FRAME >= this.launch + checkStart(J.SlideOut)) {
      const [r] = getSlideJudgeTiming(now - this.tail + this.lastWait, opt, this.lastWaitForJudge);
      this.result = r === T.TooFast ? T.FastGood : r;
    }
  }
  _tooLate(now, opt) {                              // SlideRoot.JudgeToolate
    if (this.result === T.TooLate) return true;
    if (this.result !== T.End) return false;
    const [r] = getSlideJudgeTiming(now - this.tail, opt, this.lastWait);
    if (r === T.TooLate) this.result = T.TooLate;
    return this.result === T.TooLate;
  }

  // returns the final timing once the slide has finished (including its trailing wait), else null
  update(now, sensors, opt = 0) {
    if (this.ended) return null;
    const dt = this.lastNow === null ? 0 : Math.max(0, now - this.lastNow);
    this.lastNow = now;
    if (now + JUDGE_ADJUST_MS >= this.appear && this.hitIndex < this.areas.length) {
      let flag;
      do {
        flag = this._checkTouch(this.hitIndex, this.hitIn, sensors);
        if (!flag && this._nextCheck()) {
          const n = this.hitIndex + 1;
          if (n < this.areas.length) flag = this._checkTouch(n, false, sensors);
        }
        if (this.hitIndex >= this.areas.length) flag = false;
      } while (flag);
    }
    this.progress = this.areas.length ? Math.min(1, (this.hitIndex + (this.hitIn ? 0.5 : 0)) / this.areas.length) : 0;
    if (this.hitIndex >= this.areas.length) this._judge(now, opt);
    if (this.result === T.End && !this._tooLate(now, opt)) return null;
    if (this.lastWait <= 0 || this.result === T.TooLate) {
      if (this.result === T.TooLate && this.hitIndex >= this.areas.length - 1) this.result = T.LateGood;
      this.ended = true;
      return this.result;
    }
    this.lastWait -= dt;
    return null;
  }
}
