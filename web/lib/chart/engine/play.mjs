// A play session: feeds sensor/button input into the notes and judges them with the game's rules.
// Ported from NoteBase / HoldNote / BreakHoldNote / TouchNoteB / TouchHoldC / SlideRoot / NotesReader touch chains / GameScoreList.
//
// Chart notes (see lib/library.mjs buildChart):
//   {k:'tap',   t, l, b?, x?, s?}                   tap / break / EX / star head (s)
//   {k:'hold',  t, d, l, b?, x?}                    hold
//   {k:'touch', t, a:'A'..'E', l, f}                touch
//   {k:'thold', t, d, a, l, f}                      touch hold
//   {k:'slide', t, l, w, d, b?, segs:[{ty,f,e,t0,t1}]}
import { T, J, K, FRAME, HOLD_HEAD_MS, HOLD_TAIL_MS, TOUCH_HOLD_HEAD_MS, TOUCH_HOLD_TAIL_MS, checkStart, getJudgeTiming, judgeHoldTotal } from './timing.mjs';
import { ScoreKeeper } from './score.mjs';
import { SlideTracker } from './slides.mjs';
import { AREA_COUNT, areaIndex, laneArea, isCArea } from './areas.mjs';

const LEAD = 1500;                          // notes join the live list this long before their time

// NotesReader.IsTouchNext: is `temp` a neighbour of `link` (offsets are lane offsets from link's lane)
const NEXT = {
  B: { B: [1, 7], E: [0, 1], A: [0], C: [0, 1, 2, 3, 4, 5, 6, 7] },
  E: { B: [0, 7], A: [0, 7], D: [0] },
  A: { B: [0], E: [0, 1], D: [0, 1] },
  D: { A: [0, 7], E: [0] },
  C: { B: [0, 1, 2, 3, 4, 5, 6, 7] },
};
const isTouchNext = (temp, link) => (NEXT[link.a]?.[temp.a] ?? []).some((o) => temp.l === (o + link.l) % 8);

export class Session {
  constructor(chart, slideData, opts = {}) {
    this.opt = opts.judgeFrames ?? 0;                      // the player's judge-timing option, in frames
    // Every game note time sits `adjustMs` after its chart time: a fresh player's AdjustTiming option is Normal (20), which is +60 ms
    // (UserOption.GetAdjustMSec); test/oracle.mjs checks this against the game's own NotesReader.
    this.adjustMs = opts.adjustMs ?? 60;
    const A = this.adjustMs;
    const notes = chart.notes.map((n, i) => ({ ...n, i, t: n.t + A, segs: n.segs?.map((s) => ({ ...s, t0: s.t0 + A, t1: s.t1 + A })) })).sort((a, b) => a.t - b.t || a.i - b.i);
    this.notes = notes.map((n, idx) => this._make(n, idx, slideData));
    this.score = new ScoreKeeper(this.notes.map((n) => n.scoreKind));
    this.events = [];
    this.heads = [];                                       // hold / touch-hold heads as they are judged (the game plays a sound for the head and another for the tail)
    this.chartEnd = chart.endMs + A;
    this.cursor = 0;                                       // first note not yet taken into `live`
    this.live = [];
    this.lastNow = null;
    // lane queues (IsJudgeNote): the earliest unfinished tap/hold of a lane is the only one that can be judged
    this.laneQueue = Array.from({ length: 8 }, () => []);
    for (const n of this.notes) if (n.k === 'tap' || n.k === 'hold') this.laneQueue[n.l & 7].push(n);
    this.laneHead = new Array(8).fill(0);
    this._groupTouch();
    this._markEach();
  }

  _make(n, idx, slideData) {
    const o = { ...n, idx, ended: false, result: T.End, diff: 0 };
    switch (n.k) {
      case 'tap': o.scoreKind = n.b ? K.Break : K.Tap; o.judgeType = n.x ? J.ExTap : n.b ? J.Break : J.Tap; break;
      case 'hold': o.scoreKind = n.b ? K.Break : K.Hold; o.judgeType = n.x ? J.ExTap : n.b ? J.Break : J.Tap; o.tail = n.t + n.d; o.headResult = T.End; o.headJudged = false; o.bodyOn = false; o.released = 0; break;
      case 'touch': o.scoreKind = K.Touch; o.judgeType = J.Touch; o.sensor = laneArea(n.a, n.l); break;
      case 'thold': o.scoreKind = K.Hold; o.judgeType = J.Touch; o.sensor = laneArea(n.a, n.l); o.tail = n.t + n.d; o.headResult = T.End; o.headJudged = false; o.bodyOn = false; o.released = 0; break;
      case 'slide': o.scoreKind = n.b ? K.Break : K.Slide; o.tracker = new SlideTracker(n, slideData); break;
      default: throw new Error(`unknown note kind ${n.k}`);
    }
    return o;
  }

  // NotesReader: simultaneous touch notes that sit next to each other form a chain; the first result is shared by all of them
  _groupTouch() {
    for (const kind of ['touch', 'thold']) {
      const all = this.notes.filter((n) => n.k === kind);
      for (const root of all) {
        if (root.group) continue;
        const cand = all.filter((n) => n.t === root.t && !n.group);
        const link = [root];
        for (let check = 0; check < link.length; check++) for (const c of cand) if (!link.includes(c) && isTouchNext(c, link[check])) link.push(c);
        if (link.length > 1) { const g = { members: link, done: false, timing: T.End }; link.forEach((m) => { m.group = g; }); }
      }
    }
  }

  // EACH notes (drawn yellow): two or more taps / holds / slide stars at the same instant, or touches at the same instant
  _markEach() {
    const byT = new Map();
    for (const n of this.notes) {
      const key = (n.k === 'touch' || n.k === 'thold' ? 'T' : 'L') + Math.round(n.t * 2);
      (byT.get(key) ?? byT.set(key, []).get(key)).push(n);
    }
    for (const group of byT.values()) if (group.length > 1) for (const n of group) n.each = true;
  }

  _emit(note, timing, diff) {
    if (this.score.setResult(note.idx, note.scoreKind, timing)) this.events.push({ note, timing, diff, kind: note.scoreKind, combo: this.score.combo });
  }

  // one step of the game loop.  inp = {buttonDown[8], buttonPush[8], areaDown[34], areaPush[34]}
  tick(now, inp) {
    const dt = this.lastNow === null ? 0 : Math.max(0, now - this.lastNow);
    this.lastNow = now;
    while (this.cursor < this.notes.length && this.notes[this.cursor].t - LEAD <= now) this.live.push(this.notes[this.cursor++]);
    const used = new Set();
    for (const n of this.live) {
      if (n.ended) continue;
      switch (n.k) {
        case 'tap': this._tap(n, now, inp, used); break;
        case 'hold': this._hold(n, now, dt, inp, used); break;
        case 'touch': this._touch(n, now, inp, used); break;
        case 'thold': this._touchHold(n, now, dt, inp, used); break;
        case 'slide': this._slide(n, now, inp); break;
      }
    }
    this._chains();
    if (this.live.some((n) => n.ended)) this.live = this.live.filter((n) => !n.ended);
    return this.score;
  }

  // IsJudgeNote
  _isHead(n) {
    const q = this.laneQueue[n.l & 7];
    let h = this.laneHead[n.l & 7];
    while (h < q.length && q[h].ended) h++;
    this.laneHead[n.l & 7] = h;
    return q[h] === n;
  }
  _started(n, type, now) { return now - this.opt * FRAME >= n.t + checkStart(type); }       // IsNoteCheckTimeStart

  _tap(n, now, inp, used) {
    const a = laneArea('A', n.l);
    if ((inp.buttonDown[n.l & 7] || inp.areaDown[a]) && this._isHead(n) && !used.has(a) && this._started(n, n.judgeType, now)) {
      const [r, diff] = getJudgeTiming(now - n.t, this.opt, n.judgeType);
      n.result = r; n.diff = diff;
      if (r !== T.TooLate) used.add(a);
    }
    if (n.result === T.End) {                                                               // JudgeToolate
      const [r, diff] = getJudgeTiming(now - n.t, this.opt, n.judgeType);
      if (r === T.TooLate) { n.result = T.TooLate; n.diff = diff; }
    }
    if (n.result !== T.End) { n.ended = true; this._emit(n, n.result, n.diff); }
  }

  _hold(n, now, dt, inp, used) {
    const a = laneArea('A', n.l);
    if (this._started(n, n.judgeType, now)) {
      if ((inp.buttonDown[n.l & 7] || inp.areaDown[a]) && this._isHead(n) && n.headResult === T.End && !used.has(a)) {
        const [r, diff] = getJudgeTiming(now - n.t, this.opt, n.judgeType);
        n.headResult = r; n.diff = diff; n.headJudged = true; n.bodyOn = true; this.heads.push({ note: n, timing: r });
        if (r !== T.TooLate) used.add(a);
      }
      if (n.headResult === T.End) {
        const [r, diff] = getJudgeTiming(now - n.t, this.opt, n.judgeType);
        if (r === T.TooLate) { n.headResult = T.TooLate; n.diff = diff; }
      }
      if (n.headResult === T.TooLate && !n.headJudged) n.headJudged = true;
    }
    if (now >= n.t + HOLD_HEAD_MS && now <= n.tail - HOLD_TAIL_MS) {
      const held = n.headJudged && (inp.buttonPush[n.l & 7] || inp.areaPush[a]);
      if (!held) n.released += dt; else n.bodyOn = true;
    }
    if (now >= n.tail && n.headJudged) {
      n.ended = true;
      const r = judgeHoldTotal(n.tail - n.t, n.released, n.headResult, n.bodyOn, false);
      n.result = r;
      this._emit(n, r, n.diff);
    }
  }

  _touch(n, now, inp, used) {
    const down = isCArea(n.sensor) ? inp.areaDown[areaIndex.C1] || inp.areaDown[areaIndex.C2] : inp.areaDown[n.sensor];
    const key = isCArea(n.sensor) ? areaIndex.C1 : n.sensor;
    if (down && !used.has(key) && this._started(n, J.Touch, now)) {
      const [r, diff] = getJudgeTiming(now - n.t, this.opt, J.Touch);
      n.result = r; n.diff = diff;
      used.add(key); if (isCArea(n.sensor)) used.add(areaIndex.C2);
    }
    if (n.result === T.End) {
      const [r, diff] = getJudgeTiming(now - n.t, this.opt, J.Touch);
      if (r === T.TooLate) { n.result = T.TooLate; n.diff = diff; }
    }
    if (n.result !== T.End) this._finishTouch(n);
  }
  _finishTouch(n) {
    n.ended = true;
    this._emit(n, n.result, n.diff);
    if (n.group && !n.group.done) { n.group.done = true; n.group.timing = n.result; n.group.diff = n.diff; }
  }

  _touchHold(n, now, dt, inp, used) {
    const down = isCArea(n.sensor) ? inp.areaDown[areaIndex.C1] || inp.areaDown[areaIndex.C2] : inp.areaDown[n.sensor];
    const push = isCArea(n.sensor) ? inp.areaPush[areaIndex.C1] || inp.areaPush[areaIndex.C2] : inp.areaPush[n.sensor];
    const key = isCArea(n.sensor) ? areaIndex.C1 : n.sensor;
    if (this._started(n, J.Touch, now)) {
      if (down && n.headResult === T.End && !used.has(key)) {
        const [r, diff] = getJudgeTiming(now - n.t, this.opt, J.Touch);
        n.headResult = r; n.diff = diff; n.headJudged = true; n.bodyOn = true; this.heads.push({ note: n, timing: r });
        used.add(key); if (isCArea(n.sensor)) used.add(areaIndex.C2);
      }
      if (n.headResult === T.End) {
        const [r, diff] = getJudgeTiming(now - n.t, this.opt, J.Touch);
        if (r === T.TooLate) { n.headResult = T.TooLate; n.diff = diff; }
      }
      if (n.headResult === T.TooLate && !n.headJudged) n.headJudged = true;
    }
    if (now >= n.t + TOUCH_HOLD_HEAD_MS && now <= n.tail - TOUCH_HOLD_TAIL_MS) {
      if (!(n.headJudged && push)) n.released += dt; else n.bodyOn = true;
    }
    if (now >= n.tail && n.headJudged) {
      n.ended = true;
      n.result = judgeHoldTotal(n.tail - n.t, n.released, n.headResult, n.bodyOn, true);
      this._emit(n, n.result, n.diff);
      if (n.group && !n.group.done) { n.group.done = true; n.group.timing = n.result; }
    }
  }

  _slide(n, now, inp) {
    const r = n.tracker.update(now, inp.areaPush, this.opt);
    if (r !== null) { n.ended = true; n.result = r; this._emit(n, r, 0); }
  }

  // GameCtrl: once one touch of a chain has a result, the rest take the same one
  _chains() {
    for (const n of this.live) {
      if (n.ended || !n.group || !n.group.done || (n.k !== 'touch' && n.k !== 'thold')) continue;
      if (n.k === 'touch') { n.result = n.group.timing; n.diff = n.group.diff ?? 0; this._finishTouch(n); }
      else if (!n.headJudged) { n.headResult = n.group.timing; n.headJudged = true; n.bodyOn = true; this.heads.push({ note: n, timing: n.headResult }); }
    }
  }
}

// ---- input helper: turns time-stamped pushes/releases into the per-tick arrays Session.tick wants ----
export class InputState {
  constructor() { this.buttonPush = new Array(8).fill(false); this.areaPush = new Array(AREA_COUNT).fill(false); this._reset(); }
  _reset() { this.buttonDown = new Array(8).fill(false); this.areaDown = new Array(AREA_COUNT).fill(false); }
  setButton(i, on) { if (on && !this.buttonPush[i]) this.buttonDown[i] = true; this.buttonPush[i] = on; }
  setArea(i, on) { if (on && !this.areaPush[i]) this.areaDown[i] = true; this.areaPush[i] = on; }
  // returns the arrays for this tick and clears the one-tick "down" edges
  snapshot() { const s = { buttonDown: this.buttonDown, buttonPush: this.buttonPush.slice(), areaDown: this.areaDown, areaPush: this.areaPush.slice() }; this._reset(); return s; }
}
