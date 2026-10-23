// Simai note-text parser.  Input: the body of one &inote_N=... field.  Output: a flat list of notes with absolute tick times.
//
// Time model.  A "measure" is one 4/4 bar = RES (384) ticks, exactly like .ma2 (RESOLUTION 384, a quarter note = 96 ticks).
// {n} makes each comma worth 1/n of a measure, {#s} makes each comma worth s seconds (converted with the current BPM).
// Positions are tracked as floating point measures and rounded to the tick grid per note, never accumulated in ticks, so odd
// divisions such as {577} or {251} do not drift.
//
// Supported: taps, break (b), EX (x), star-shaped tap ($), holds (h[len]), touch A1..E8 / C (+ f, + hold), slides with every
// shape, chained slides (a-b-c), "same star, several slides" (*), each notes (/ and `), BPM changes ( ), || comments.
// Not interpreted (parsed and ignored): @ m ? ! are treated as flags only where noted in the code.

export const RES = 384;
const SHAPES = '-^<>vpqszwV';

const tickOf = (posMeasures) => Math.round(posMeasures * RES + 1e-7);

export function parseSimai(body, { initialBpm = null, warn = () => {}, onGroup = null } = {}) {
  const src = body.replace(/\|\|[^\n]*/g, '').replace(/\s+/g, '');
  let pos = 0;                 // measures
  let bpm = initialBpm ?? 120;
  let unit = 1 / 4;            // measures per comma
  let secPerComma = null;      // when {#s} is used
  const notes = [];
  const bpms = [];             // {tick, bpm}
  let group = '';
  let ended = false;
  let sawBpm = false;

  const addBpm = (b) => {
    const t = tickOf(pos);
    const last = bpms[bpms.length - 1];
    if (last && last.tick === t) last.bpm = b; else if (!last || last.bpm !== b) bpms.push({ tick: t, bpm: b });
    bpm = b;
    sawBpm = true;
  };

  const flush = () => {
    if (!group) return;
    if (onGroup) onGroup(pos, group);
    const tokens = group.split(/[\/`]/).filter(Boolean);
    for (const tok of tokens) {
      try {
        for (const n of parseToken(tok, bpm, warn)) { n.tick = tickOf(pos); n.exact = pos * RES; notes.push(n); }
      } catch (e) {
        warn(`skipped note "${tok}" at measure ${pos.toFixed(3)}: ${e.message}`);
      }
    }
    group = '';
  };

  let i = 0;
  while (i < src.length && !ended) {
    const c = src[i];
    if (c === '(') {
      const j = src.indexOf(')', i);
      if (j < 0) throw new Error('unterminated "(" BPM marker');
      const b = parseFloat(src.slice(i + 1, j));
      if (!(b > 0)) throw new Error(`bad BPM "${src.slice(i, j + 1)}"`);
      if (!sawBpm && pos === 0 && bpms.length === 0) { bpm = b; }
      addBpm(b);
      i = j + 1;
    } else if (c === '{') {
      const j = src.indexOf('}', i);
      if (j < 0) throw new Error('unterminated "{" division');
      const v = src.slice(i + 1, j);
      if (v.startsWith('#')) { secPerComma = parseFloat(v.slice(1)); unit = null; }
      else { const n = parseFloat(v); if (!(n > 0)) throw new Error(`bad division "{${v}}"`); unit = 1 / n; secPerComma = null; }
      i = j + 1;
    } else if (c === ',') {
      flush();
      pos += secPerComma !== null ? secPerComma * bpm / 240 : unit;
      i++;
    } else if (c === 'E' && !/[1-8]/.test(src[i + 1] ?? '')) {
      ended = true;
    } else if (c === '[') {                       // length specs may contain characters like '#'; copy through verbatim
      const j = src.indexOf(']', i);
      if (j < 0) throw new Error('unterminated "["');
      group += src.slice(i, j + 1);
      i = j + 1;
    } else {
      group += c;
      i++;
    }
  }
  flush();
  if (!bpms.length || bpms[0].tick !== 0) bpms.unshift({ tick: 0, bpm: initialBpm ?? bpm });
  return { notes, bpms, endMeasure: pos, ended };
}

// ---- one note token ("1", "2b", "3h[4:1]", "A4f", "1-5[4:1]", "1-3[8:1]*-6[8:1]") -------------------------------------------

function parseToken(tok, bpm, warn) {
  const out = [];
  const parts = tok.split('*');
  // The head part may hold several notes written without "/" ("12" = "1/2", "1b2b" = "1b/2b").
  const heads = splitNotes(parts[0]);
  let first = null;
  for (const h of heads) {
    first = parseOne(h, bpm, warn);
    out.push(...first.notes);
  }
  // "*": extra slides that share the head's star
  for (const extra of parts.slice(1)) {
    if (!first || !first.slideStart) throw new Error('"*" used on a note without a slide');
    const m = parseOne(first.slideStart + extra, bpm, warn, { shared: true });
    out.push(...m.notes);
  }
  return out;
}

// Cut a string into single notes.  A note is: a lane (1-8) or touch area (A1..E8, C), modifiers (b x f $ ? ! @ m), an optional
// hold "h[len]", and any number of slide pieces (shape + lane(s) + optional b + optional [len]).  A digit/touch letter after a
// finished note starts the next one.
function splitNotes(s) {
  const out = [];
  let i = 0;
  while (i < s.length) {
    const start = i;
    if (/[ABDE]/.test(s[i]) && /[1-8]/.test(s[i + 1] ?? '')) i += 2;
    else if (s[i] === 'C') { i++; if (/[12]/.test(s[i] ?? '')) i++; }
    else if (/[1-8]/.test(s[i])) i++;
    else throw new Error(`unexpected "${s[i]}"`);
    for (;;) {
      const ch = s[i];
      if (ch === undefined) break;
      if ('bxf$@?!m'.includes(ch)) i++;
      else if (ch === 'h') { i++; if (s[i] === '[') i = s.indexOf(']', i) + 1; }
      else if (ch === '[') { const e = s.indexOf(']', i); if (e < 0) throw new Error('unterminated "["'); i = e + 1; }
      else if (SHAPES.includes(ch)) {
        i++;
        if ((ch === 'p' || ch === 'q') && s[i] === ch) i++;          // pp / qq
        i += ch === 'V' ? 2 : 1;                                       // V has a pivot lane and an end lane
      } else break;
    }
    out.push(s.slice(start, i));
  }
  return out;
}

function parseOne(tok, bpm, warn, opts = {}) {
  let m;
  // touch notes: A1..A8, B1..B8, D1..D8, E1..E8, C / C1 / C2
  if ((m = tok.match(/^([ABDE])([1-8])(.*)$/)) || (m = tok.match(/^(C)([12]?)(.*)$/))) {
    const area = m[1];
    const lane = area === 'C' ? 0 : parseInt(m[2], 10) - 1;
    const rest = m[3];
    const flagsOnly = rest.replace(/\[[^\]]*\]/g, '');          // modifiers outside the [length]: "hf[1:1]" = hold + firework
    const lm = rest.match(/\[([^\]]*)\]/);
    const eff = /f/.test(flagsOnly) ? 1 : 0;
    if (/h/.test(flagsOnly)) {
      if (!lm) throw new Error('touch hold without a length');
      return { notes: [{ kind: 'touchhold', area, lane, eff, lenSpec: parseLenSpec(lm[1]), bpm }] };
    }
    return { notes: [{ kind: 'touch', area, lane, eff }] };
  }
  m = tok.match(/^([1-8])(.*)$/);
  if (!m) throw new Error('unrecognized note');
  const lane = parseInt(m[1], 10) - 1;
  let rest = m[2];
  const flags = { brk: false, ex: false, star: false, noHead: false };
  let hold = null;
  let j = 0;
  // modifiers up to the first slide shape
  for (; j < rest.length; j++) {
    const ch = rest[j];
    if (SHAPES.includes(ch)) break;
    if (ch === 'b') flags.brk = true;
    else if (ch === 'x') flags.ex = true;
    else if (ch === '$') flags.star = true;
    else if (ch === '?' || ch === '!') flags.noHead = true;
    else if (ch === 'h') {
      let spec = null;
      if (rest[j + 1] === '[') { const e = rest.indexOf(']', j); spec = rest.slice(j + 2, e); j = e; }
      hold = { spec: spec ? parseLenSpec(spec) : null };
    } else if (ch === '@' || ch === 'm' || ch === 'f') { /* visual-only flags */ }
    else if (ch === '[') { const e = rest.indexOf(']', j); j = e; }
    else throw new Error(`unknown modifier "${ch}"`);
  }
  const shapePart = rest.slice(j);
  if (!shapePart) {
    if (hold) {
      if (!hold.spec) return { notes: [{ kind: 'tap', lane, ...flags }] };   // "1h" without a length is a tap
      return { notes: [{ kind: 'hold', lane, ...flags, lenSpec: hold.spec, bpm }] };
    }
    if (flags.star) return { notes: [{ kind: 'star', lane, ...flags }] };
    return { notes: [{ kind: 'tap', lane, ...flags }] };
  }
  // slide chain
  const segs = [];
  let k = 0;
  let from = lane;
  while (k < shapePart.length) {
    let shape = shapePart[k++];
    if (!SHAPES.includes(shape)) throw new Error(`unexpected "${shape}" in slide`);
    if ((shape === 'p' || shape === 'q') && shapePart[k] === shape) { shape += shape; k++; }   // pp / qq
    let pivot = null, end;
    if (shape === 'V') {
      pivot = parseInt(shapePart[k++], 10) - 1;
      end = parseInt(shapePart[k++], 10) - 1;
    } else {
      end = parseInt(shapePart[k++], 10) - 1;
    }
    if (!(end >= 0 && end <= 7) || (pivot !== null && !(pivot >= 0 && pivot <= 7))) throw new Error('slide lane out of range');
    let segBreak = false, lenSpec = null;
    while (k < shapePart.length && !SHAPES.includes(shapePart[k])) {   // note: 'p'/'q' start the next shape, handled at loop top
      const ch = shapePart[k];
      if (ch === 'b') { segBreak = true; k++; }
      else if (ch === 'x' || ch === '$' || ch === '?' || ch === '!' || ch === '@' || ch === 'm' || ch === 'f') k++;
      else if (ch === '[') { const e = shapePart.indexOf(']', k); lenSpec = parseLenSpec(shapePart.slice(k + 1, e)); k = e + 1; }
      else throw new Error(`unexpected "${ch}" in slide`);
    }
    segs.push({ shape, from, pivot, end, brk: segBreak, lenSpec });
    from = end;
  }
  const note = { kind: 'slide', lane, ...flags, segs, bpm, shared: !!opts.shared };
  return { notes: [note], slideStart: String(lane + 1) };
}

// "4:1" | "#1.5" | "160#4:1" | "3##4:1" | "3##160#4:1"
export function parseLenSpec(s) {
  let wait = null, bpmOv = null;
  if (s.includes('##')) { const [w, r] = s.split('##'); wait = parseFloat(w); s = r; }
  if (s.startsWith('#')) return { wait, sec: parseFloat(s.slice(1)) };
  if (s.includes('#')) { const [b, r] = s.split('#'); bpmOv = parseFloat(b); s = r; }
  const m = s.match(/^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/);
  if (m) return { wait, a: parseFloat(m[1]), b: parseFloat(m[2]), bpmOv };
  const n = parseFloat(s);
  if (!isNaN(n)) return { wait, sec: n };
  throw new Error(`bad length "[${s}]"`);
}

// length spec -> ticks at the given tempo
export function lenToTicks(spec, bpm) {
  if (spec.sec !== undefined) return spec.sec * bpm / 240 * RES;
  const base = RES * spec.b / spec.a;
  return spec.bpmOv ? base * bpm / spec.bpmOv : base;
}

export function waitToTicks(spec, bpm) {
  return spec && spec.wait !== null && spec.wait !== undefined ? spec.wait * bpm / 240 * RES : 96;   // default: one beat
}
