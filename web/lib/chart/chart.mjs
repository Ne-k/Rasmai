// Parse a Simai maidata.txt (AstroDX / MajdataEdit chart folder) into metadata + one inote text per difficulty.
//
// File shape:   &key=value   (a value runs until the next line that starts with '&', so inote bodies span many lines)
//   &title= &artist= &wholebpm= &first=<offset seconds> &lv_N= &des_N= &inote_N= ...
// Difficulty slots (N): 1 Easy, 2 Basic, 3 Advanced, 4 Expert, 5 Master, 6 Re:Master, 7 original. maimai DX has no Easy,
// so slots 2..6 become game difficulties 0..4 (Basic .. Re:Master); slot 1 and 7 are reported as skipped.

export const DIFFICULTY_NAMES = ['Basic', 'Advanced', 'Expert', 'Master', 'Re:Master'];

export function parseMaidata(text) {
  text = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n');
  const fields = {};
  // split on newline + '&' so '&' inside a value (e.g. a title) is safe as long as it is not at the start of a line
  const parts = ('\n' + text).split(/\n(?=&[A-Za-z_0-9]+=)/).filter((p) => p.trim());
  for (const p of parts) {
    const m = p.match(/^\s*&([A-Za-z_0-9]+)=([\s\S]*)$/);
    if (m) fields[m[1]] = m[2].replace(/\s+$/, '');
  }
  const meta = {
    title: fields.title ?? '',
    artist: fields.artist ?? '',
    wholebpm: fields.wholebpm !== undefined ? parseFloat(fields.wholebpm) : null,
    first: fields.first !== undefined ? parseFloat(fields.first) || 0 : 0,
  };
  const charts = {};
  for (const [k, v] of Object.entries(fields)) {
    const m = k.match(/^inote_(\d+)$/);
    if (!m) continue;
    const n = Number(m[1]);
    charts[n] = {
      slot: n,
      inote: v,
      level: fields['lv_' + n] ?? null,
      designer: fields['des_' + n] ?? fields.des ?? null,
    };
  }
  return { meta, charts, fields };
}

// "10", "10+", "13.7", "7.2" -> {level: 13, decimal: 7, plus: true, musicLevelId}
// maimai shows "+" from decimal .6 upward. musicLevelID is the index into the game's musicLevel table:
// 1..7 -> 1..7, then 7+ = 8, 8 = 9, 8+ = 10, ... 15 = 23, 15+ = 24.
export function parseLevel(raw) {
  if (raw === null || raw === undefined || String(raw).trim() === '') return null;
  const s = String(raw).trim();
  let level, decimal = 0, plus = false;
  const m = s.match(/^(\d+)(?:\.(\d))?(\+)?/);
  if (!m) return null;
  level = parseInt(m[1], 10);
  if (m[2] !== undefined) decimal = parseInt(m[2], 10);
  if (m[3]) { plus = true; if (m[2] === undefined) decimal = 7; }
  else if (decimal >= 6) plus = true;
  return { level, decimal, plus, musicLevelId: musicLevelId(level, plus) };
}

export function musicLevelId(level, plus) {
  if (level <= 7) return plus && level === 7 ? 8 : Math.max(level, 0);
  const id = 9 + (level - 8) * 2 + (plus ? 1 : 0);
  return Math.min(id, 24);
}
