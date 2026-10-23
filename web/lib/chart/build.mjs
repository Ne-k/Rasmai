// A maidata.txt chart -> the note list the engine plays and the field draws.  Same output as the maimai-dx port's
// lib/library.mjs buildChart, but from text rather than a folder, so it runs in the browser.
//
// Notes: {k:'tap'|'hold'|'touch'|'thold'|'slide', t: ms in the audio, l: lane 0-7, ...}; b = break, x = EX, s = star head,
// d = duration ms, a = touch group 'A'..'E', f = firework, segs = slide pieces {ty, f, e, t0, t1} (type code, from, end, ms).
import { parseSimai, lenToTicks, waitToTicks } from './simai.mjs';
import { SLIDE_CODE } from './engine/slides.mjs';

export const SLOT_NAMES = { 1: 'Easy', 2: 'Basic', 3: 'Advanced', 4: 'Expert', 5: 'Master', 6: 'Re:Master', 7: 'Utage' };
const TOP_HALF = new Set([0, 1, 6, 7]);               // lanes 1,2,7,8 on screen

// Simai slide shape -> ma2 record code; the direction conventions were checked against official charts (simai2ma2).
export function slideCode(seg) {
  const { shape, from, end, pivot } = seg;
  const cw = (end - from + 8) % 8;
  switch (shape) {
    case '-': return 'SI_';
    case '^': return cw < 4 ? 'SCR' : cw > 4 ? 'SCL' : TOP_HALF.has(from) ? 'SCR' : 'SCL';
    case '>': return TOP_HALF.has(from) ? 'SCR' : 'SCL';
    case '<': return TOP_HALF.has(from) ? 'SCL' : 'SCR';
    case 'v': return 'SV_';
    case 'p': return 'SUL';
    case 'q': return 'SUR';
    case 's': return 'SSL';
    case 'z': return 'SSR';
    case 'w': return 'SF_';
    case 'pp': return 'SXL';
    case 'qq': return 'SXR';
    case 'V': return pivot === (from + 2) % 8 ? 'SLR' : 'SLL';
    default: return 'SI_';
  }
}

// ticks (384 per measure, 96 per quarter) -> milliseconds, following the chart's BPM changes
function timeline(bpms) {
  const list = bpms.length ? bpms.map((b) => ({ ...b })) : [{ tick: 0, bpm: 120 }];
  if (list[0].tick > 0) list.unshift({ tick: 0, bpm: list[0].bpm });
  let ms = 0;
  const segs = list.map((b, i) => { const s = { tick: b.tick, ms, bpm: b.bpm }; if (list[i + 1]) ms += ((list[i + 1].tick - b.tick) * 60000) / (b.bpm * 96); return s; });
  return (tick) => { let s = segs[0]; for (const x of segs) if (x.tick <= tick) s = x; return s.ms + ((tick - s.tick) * 60000) / (s.bpm * 96); };
}

/** md = parseMaidata(text); slot = 1..7 */
export function buildChart(md, slot) {
  const ch = md.charts[slot];
  if (!ch) throw new Error(`no chart ${slot}`);
  const warns = [];
  const p = parseSimai(ch.inote, { initialBpm: md.meta.wholebpm, warn: (w) => warns.push(w) });
  const ms = timeline(p.bpms);
  const offset = (md.meta.first || 0) * 1000;             // the chart's measure 0 sits this far into the audio
  const at = (tick) => Math.round((ms(tick) + offset) * 10) / 10;
  const dur = (tick, ticks) => Math.round((ms(tick + ticks) - ms(tick)) * 10) / 10;
  const ticksOf = (spec, bpm) => Math.max(1, Math.round(lenToTicks(spec, bpm)));
  const notes = [];
  for (const n of p.notes) {
    const base = { t: at(n.tick), l: n.lane };
    if (n.brk) base.b = 1;
    if (n.ex) base.x = 1;
    switch (n.kind) {
      case 'tap': notes.push({ k: 'tap', ...base }); break;
      case 'star': notes.push({ k: 'tap', ...base, s: 1 }); break;
      case 'hold': notes.push({ k: 'hold', ...base, d: dur(n.tick, ticksOf(n.lenSpec, n.bpm)) }); break;
      case 'touch': notes.push({ k: 'touch', t: base.t, l: n.lane, a: n.area, f: n.eff ? 1 : 0 }); break;
      case 'touchhold': notes.push({ k: 'thold', t: base.t, l: n.lane, a: n.area, f: n.eff ? 1 : 0, d: dur(n.tick, ticksOf(n.lenSpec, n.bpm)) }); break;
      case 'slide': {
        if (!n.noHead && !n.shared) notes.push({ k: 'tap', ...base, s: 1 });
        const specs = n.segs.filter((s) => s.lenSpec);
        const total = specs.length ? ticksOf(specs[specs.length - 1].lenSpec, n.bpm) : 96;
        const shoots = n.segs.map((s, k) => (s.lenSpec && specs.length === n.segs.length ? ticksOf(s.lenSpec, n.bpm) : Math.max(1, Math.round(total / n.segs.length))));
        const wait = Math.max(0, Math.round(waitToTicks(specs[0]?.lenSpec, n.bpm)));
        let cursor = n.tick + wait;
        const segs = n.segs.map((s, k) => { const t0 = at(cursor); cursor += shoots[k]; return { ty: SLIDE_CODE[slideCode(s)] ?? 1, f: s.from, e: s.end, t0, t1: at(cursor) }; });
        notes.push({ k: 'slide', t: base.t, l: n.lane, b: n.segs.some((s) => s.brk) ? 1 : 0, segs });
        break;
      }
      default: break;
    }
  }
  notes.sort((a, b) => a.t - b.t);
  const endMs = notes.reduce((m, n) => Math.max(m, n.t + (n.d ?? 0), n.segs ? n.segs[n.segs.length - 1].t1 : 0), 0) + 2000;
  const bars = [];
  for (let k = 0; bars.length < 10000; k += 384) { const t = at(k); if (!(t <= endMs)) break; bars.push(t); }
  return { title: md.meta.title, artist: md.meta.artist, slot, name: SLOT_NAMES[slot] ?? `#${slot}`, level: ch.level, designer: ch.designer, bpm: md.meta.wholebpm, endMs, notes, bars, warnings: warns.length };
}
