// A scripted player (the game's "auto play"): presses every note the way a perfect player would.  Used by the tests, and by the demo mode in the app.
import { laneArea, areaIndex, rotateArea, isCArea } from './areas.mjs';

export class AutoPlayer {
  // offset: ms after the note time at which taps are pressed (50 is the middle of the Critical window); hold: how long a tap stays down
  constructor(session, { offset = 50, hold = 20, tapOffsets = null, skipSlides = false } = {}) {
    this.refs = new Array(40).fill(0);               // two fingers on one sensor keep it down until both lift
    const plan = [];
    for (const n of session.notes) {
      const off = tapOffsets ? tapOffsets(n) : offset;
      const press = (area, upAt) => plan.push({ at: n.t + off, area, on: true }, { at: Math.max(upAt, n.t + off + hold), area, on: false });
      if (n.k === 'tap') press(laneArea('A', n.l), n.t + off + hold);
      else if (n.k === 'hold') press(laneArea('A', n.l), n.tail + 5);
      else if (n.k === 'touch') press(n.sensor, n.t + off + hold);
      else if (n.k === 'thold') press(n.sensor, n.tail + 5);
    }
    plan.sort((a, b) => a.at - b.at);
    this.plan = plan; this.p = 0;
    // slides: walk the sensors in order, entering each at the time the star reaches it
    this.slides = (skipSlides ? [] : session.notes.filter((n) => n.k === 'slide' && n.tracker.playable)).map((n) => {
      const tr = n.tracker, total = tr.areas.reduce((a, x) => a + x.push + x.release, 0);
      let cum = 0;
      const enter = tr.areas.map((a) => { const t0 = tr.launch + ((tr.arrive - tr.launch) * cum) / total; cum += a.push + a.release; return t0; });
      return { tr, enter, current: -1, done: false };
    });
  }
  _set(inp, area, on) { this.refs[area] += on ? 1 : -1; inp.setArea(area, this.refs[area] > 0); }
  _sensor(tr, idx) { const a = tr.areas[idx].points[0]; return isCArea(a) ? areaIndex.C1 : rotateArea(a, tr.lane); }

  // apply everything due by `now` to the InputState
  step(now, inp) {
    while (this.p < this.plan.length && this.plan[this.p].at <= now) { const e = this.plan[this.p++]; this._set(inp, e.area, e.on); }
    for (const st of this.slides) {
      if (st.done) continue;
      const tr = st.tr;
      if (tr.hitIndex >= tr.areas.length || tr.ended) { if (st.current >= 0) this._set(inp, this._sensor(tr, st.current), false); st.done = true; continue; }
      let idx = -1;
      for (let i = 0; i < st.enter.length; i++) if (st.enter[i] <= now) idx = i;
      if (idx !== st.current) {
        if (st.current >= 0) this._set(inp, this._sensor(tr, st.current), false);
        if (idx >= 0) this._set(inp, this._sensor(tr, idx), true);
        st.current = idx;
      }
    }
  }
}
