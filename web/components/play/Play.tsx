"use client";

// The chart player: a library of chart folders from the visitor's device, the play screen (watch with auto play, play, or practise
// a loop at a slower speed), video export with the music, and the result.  The rules are the game's own (lib/chart).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Ring } from "@/components/Ring";
import { MastheadNav } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { STATUS_URL } from "@/components/Contact";
import slideData from "@/lib/chart/slides.json";
import { buildChart } from "@/lib/chart/build.mjs";
import { K, BOX, convertJudge } from "@/lib/chart/engine/timing.mjs";
import { COMBO_NAMES } from "@/lib/chart/engine/score.mjs";
import { NOTE_SPEED, TOUCH_SPEED, achieveText, playResult } from "@/lib/chart/rules.mjs";
import type { PlayResult } from "@/lib/chart/types";
import { songsFromFiles, filesFromDrop, filesFromInput, levelValue, type Song } from "@/lib/chart/library";
import { Field, preloadSkin } from "./field";
import { SongClock, limiter } from "./audio";
import { InputController, DEFAULT_KEYS } from "./input";
import { encodeVideo, canExport, VIDEO_FPS, AUDIO_RATE } from "./export";
import { Sfx, GameSe, type SeTable } from "./sfx";
import { advance, lostSoFar, sessionAt, NOTE_CLOCK_MS, TICK_MS, type Center, type Live, type View } from "./run";

type Mode = "watch" | "play" | "practice";
const CENTERS: Center[] = ["off", "combo", "achievement", "achievementDown", "dx"];
// the game's ring (judgement line) designs, OptionGameoutline 0..17, in its own names
const OUTLINES = ["Blind", "No line", "Simple", "Sensor", "maimai", "GreeN", "ORANGE", "PiNK", "MURASAKi", "MiLK", "FiNALE", "DX", "Splash", "UNiVERSE", "FESTiVAL", "BUDDiES", "PRiSM", "CiRCLE"];
type Sort = "title" | "level" | "bpm" | "recent";
type Pick = { song: Song; slot: number };

const LEVELS = ["all", "10", "10+", "11", "11+", "12", "12+", "13", "13+", "14", "14+", "15"];
const diffClass = (name: string) => "diff d-" + name.toLowerCase().replace(/[^a-z]/g, "");
const fmt = (ms: number) => { const s = Math.max(0, ms) / 1000; return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}.${Math.floor((s % 1) * 10)}`; };

/** A silent WAV of the chart's length, so a song folder without audio still plays on the same clock. */
function silence(ms: number): Blob {
  const rate = 8000, n = Math.ceil((ms / 1000) * rate), buf = new ArrayBuffer(44 + n), v = new DataView(buf);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + n, true); str(8, "WAVE"); str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true); str(36, "data"); v.setUint32(40, n, true);
  new Uint8Array(buf, 44).fill(128);
  return new Blob([buf], { type: "audio/wav" });
}

export function Play() {
  const t = useTranslations("play");
  const f = useTranslations("footer");
  const [songs, setSongs] = useState<Song[]>([]);
  const [reading, setReading] = useState(0);
  const [pick, setPick] = useState<Pick | null>(null);
  const [result, setResult] = useState<PlayResult | null>(null);
  const urls = useRef(new Map<File, string>());
  const url = useCallback((file: File | null) => {
    if (!file) return null;
    let u = urls.current.get(file);
    if (!u) { u = URL.createObjectURL(file); urls.current.set(file, u); }
    return u;
  }, []);
  useEffect(() => () => { for (const u of urls.current.values()) URL.revokeObjectURL(u); }, []);
  useEffect(() => { preloadSkin(); }, []);   // the sprites are ready before the first chart opens

  const importFiles = useCallback(async (files: { file: File; path: string }[]) => {
    setReading(files.length);
    try { setSongs(await songsFromFiles(files)); } finally { setReading(0); }
    setPick(null); setResult(null);
  }, []);

  return (
    <div className="frame play-frame">
      <header className="masthead">
        <a className="home" href="/"><Ring lit={0} size={34} /></a>
        <div className="wordmark">Ras<span>mai</span></div>
        <MastheadNav current="play" />
        <ThemeToggle />
      </header>
      {result && pick ? (
        <Result result={result} pick={pick} url={url} onAgain={(mode) => { setResult(null); setPick({ ...pick, ...(mode === "watch" ? { watch: true } : {}) }); }} onLibrary={() => { setResult(null); setPick(null); }} />
      ) : pick ? (
        <Player key={`${pick.song.id}#${pick.slot}`} pick={pick} url={url} onResult={setResult} onLibrary={() => setPick(null)} />
      ) : (
        <Library songs={songs} reading={reading} url={url} onImport={importFiles} onPick={(song, slot) => setPick({ song, slot })} />
      )}
      <footer className="foot">
        <span>
          {f.rich("createdBy", { b: (c) => <b>{c}</b> })} · {f("notAffiliated")} · {t("privacy")} · <a href="/privacy/">{f("privacy")}</a> · <a href="/terms/">{f("terms")}</a> · <a href="/support">{f("support")}</a> · <a href={STATUS_URL} target="_blank" rel="noopener noreferrer">{f("status")}</a>
        </span>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------- library ----------------------------------------------------------------
function Library({ songs, reading, url, onImport, onPick }: { songs: Song[]; reading: number; url: (f: File | null) => string | null; onImport: (files: { file: File; path: string }[]) => void; onPick: (song: Song, slot: number) => void }) {
  const t = useTranslations("play");
  const [sort, setSort] = useState<Sort>("title");
  const [level, setLevel] = useState("all");
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const shown = useMemo(() => {
    const want = level === "all" ? null : levelValue(level);
    const list = songs.map((s) => ({ s, charts: s.charts.filter((c) => want === null || (() => { const v = levelValue(c.level); return v !== null && Math.floor(v) === Math.floor(want) && (v >= want ? want % 1 >= 0.6 || v % 1 < 0.6 : false); })()) })).filter((x) => x.charts.length);
    const top = (x: { charts: Song["charts"] }) => Math.max(...x.charts.map((c) => levelValue(c.level) ?? 0));
    list.sort((a, b) => sort === "title" ? a.s.title.localeCompare(b.s.title) : sort === "level" ? top(b) - top(a) || a.s.title.localeCompare(b.s.title) : sort === "bpm" ? (b.s.bpm ?? 0) - (a.s.bpm ?? 0) : b.s.added - a.s.added);
    return list;
  }, [songs, sort, level]);
  const sorts: [Sort, string][] = [["title", t("sortTitle")], ["level", t("sortLevel")], ["bpm", t("sortBpm")], ["recent", t("sortRecent")]];
  return (
    <>
      <div className="play-head">
        <h1>{t.rich("title", { em: (c) => <span>{c}</span> })}</h1>
        {songs.length > 0 && <span className="count">{t("songs", { n: songs.length })}</span>}
      </div>
      <div className={over ? "drop over" : "drop"} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={async (e) => { e.preventDefault(); setOver(false); onImport(await filesFromDrop(e.dataTransfer.items)); }}>
        <p>{t("intro")}</p>
        <button type="button" className="button pink" onClick={() => input.current?.click()} disabled={reading > 0}>{reading ? t("reading", { n: reading }) : t("open")}</button>
        <p className="hint">{t("dropHere")}</p>
        {/* webkitdirectory is what every browser calls the folder picker; React has no prop for it */}
        <input ref={input} type="file" multiple hidden {...({ webkitdirectory: "" } as object)} onChange={(e) => { if (e.target.files?.length) onImport(filesFromInput(e.target.files)); e.target.value = ""; }} />
      </div>
      {songs.length > 0 && (
        <div className="library" style={{ marginTop: 24 }}>
          <aside>
            <div>
              <p className="filter-title">{t("sortBy")}</p>
              <div className="sorts">{sorts.map(([k, label]) => <button key={k} type="button" className={sort === k ? "on" : ""} onClick={() => setSort(k)}>{label}</button>)}</div>
            </div>
            <div>
              <p className="filter-title">{t("level")}</p>
              <div className="levels">{LEVELS.map((l) => <button key={l} type="button" className={level === l ? "on" : ""} onClick={() => setLevel(l)}>{l === "all" ? t("all") : l}</button>)}</div>
            </div>
          </aside>
          <main>
            <div className="songs">
              <div className="songs-head"><span /><span>{t("colChart")}</span><span style={{ textAlign: "right" }}>{t("colBpm")}</span><span>{t("colLevels")}</span></div>
              {shown.length === 0 && <div className="empty">{t("noSongs")}</div>}
              {shown.map(({ s, charts }) => (
                <div key={s.id} className="song-row">
                  {s.image ? <img className="jacket" src={url(s.image) ?? ""} alt="" /> : <div className="jacket blank">{[...s.title][0]?.toUpperCase()}</div>}
                  <div style={{ minWidth: 0 }}><div className="title">{s.title}</div><div className="artist">{s.artist}{s.group ? ` · ${s.group}` : ""}</div></div>
                  <div className="bpm">{s.bpm ?? ""}</div>
                  <div className="diffs">{charts.map((c) => <button key={c.slot} type="button" className={diffClass(c.name)} onClick={() => onPick(s, c.slot)}>{c.name} {c.level}</button>)}</div>
                </div>
              ))}
            </div>
          </main>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- player ----------------------------------------------------------------
const themeColors = () => { const cs = getComputedStyle(document.documentElement); return { screen: cs.getPropertyValue("--ring-screen").trim() || "#1d1a2f", ring: "#6a6a7c", button: "#8f8fa3" }; };

function Player({ pick, url, onResult, onLibrary }: { pick: Pick & { watch?: boolean }; url: (f: File | null) => string | null; onResult: (r: PlayResult) => void; onLibrary: () => void }) {
  const t = useTranslations("play");
  const { song, slot } = pick;
  const chart = useMemo(() => buildChart(song.maidata, slot), [song, slot]);
  const chartInfo = song.charts.find((c) => c.slot === slot)!;
  const canvas = useRef<HTMLCanvasElement>(null);
  const field = useRef<Field | null>(null);
  const clock = useRef<SongClock | null>(null);
  const control = useRef<InputController | null>(null);
  const live = useRef<Live | null>(null);
  const gameSe = useRef<GameSe | null>(null);
  const sfx = useRef<Sfx | null>(null);
  const seTable = useRef<SeTable | null>(null);
  const [mode, setMode] = useState<Mode>(pick.watch === false ? "play" : "watch");
  const modeRef = useRef(mode); modeRef.current = mode;
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [stats, setStats] = useState({ ach: "  0.0000%", dx: 0, combo: 0 });
  const [speed, setSpeed] = useState(14);       // NOTE_SPEED index: 4.5
  const [touchSpeed, setTouchSpeed] = useState(14);
  const [offset, setOffset] = useState(0);
  const [sensors, setSensors] = useState(false);
  const [fastLate, setFastLate] = useState(true);
  const [center, setCenter] = useState<Center>("combo");
  const [useSkin, setUseSkin] = useState(true);
  const [outline, setOutline] = useState(17);
  const [starPink, setStarPink] = useState(false);
  const [rate, setRate] = useState(1);
  const [loop, setLoop] = useState<{ a: number | null; b: number | null }>({ a: null, b: null });
  const [exporting, setExporting] = useState<null | number | "done" | "unsupported" | "failed">(null);   // a number: the share encoded so far
  const busy = typeof exporting === "number";
  const cancelExport = useRef<AbortController | null>(null);
  useEffect(() => () => cancelExport.current?.abort(), []);
  const opts = useRef<View>({ noteSpeed: NOTE_SPEED[speed], touchSpeed: TOUCH_SPEED[touchSpeed], showSensors: sensors, dispJudge: fastLate ? 1 : 0, offset, rate, center, useSkin, outline, starPink });
  opts.current = { noteSpeed: NOTE_SPEED[speed], touchSpeed: TOUCH_SPEED[touchSpeed], showSensors: sensors, dispJudge: fastLate ? 1 : 0, offset, rate, center, useSkin, outline, starPink };
  const finished = useRef(false);
  const duration = clock.current?.durationMs ?? chart.endMs;

  const rebuild = useCallback((audioMs: number) => { live.current = sessionAt(chart, audioMs); field.current?.reset(); gameSe.current?.setNotes(live.current.session.notes, audioMs + NOTE_CLOCK_MS); finished.current = false; }, [chart]);

  // set up: audio, the field, input, the frame loop
  useEffect(() => {
    const cv = canvas.current!;
    const fld = new Field(cv, slideData);
    fld.setChart(chart);
    field.current = fld;
    const ck = new SongClock();
    clock.current = ck;
    const ctl = new InputController(cv, (x, y) => fld.clientToField(x, y));
    ctl.setKeys(DEFAULT_KEYS);
    ctl.onEscape = () => { ck.pause(); sfx.current?.stopAll(); setPlaying(false); };
    ctl.attach();
    control.current = ctl;
    rebuild(0);
    let alive = true;
    // the song and the game's sprites (web/scripts/play-assets.mjs; plain shapes without them) must both be in before Play is offered
    Promise.all([ck.load(song.audio ?? silence(chart.endMs + 3000)), fld.loadSkin("/play/skin")]).then(() => { if (alive) setReady(true); });
    // the game's own sound effects, when the site has them; silence otherwise
    fetch("/play/se/seoptions.json").then(async (r) => {
      if (!r.ok || !alive) return;
      const table = (await r.json()) as SeTable, fx = new Sfx(ck), se = new GameSe(fx, table);
      await fx.preload(se.names);
      if (!alive) return;
      sfx.current = fx; gameSe.current = se; seTable.current = table;
      if (live.current) se.setNotes(live.current.session.notes, ck.nowMs() + NOTE_CLOCK_MS);
    }).catch(() => {});
    const offEnded = ck.on("ended", () => { setPlaying(false); finished.current = true; setStats((s) => ({ ...s })); });
    const offLoop = ck.on("loop", () => { const a = ck.nowMs(); rebuild(a); });
    const ro = new ResizeObserver(() => fld.resize());
    ro.observe(cv);
    fld.resize();
    let theme = themeColors();
    const mo = new MutationObserver(() => { theme = themeColors(); });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    let lastUi = 0, raf = 0;
    const frame = () => {
      if (!alive) return;
      raf = requestAnimationFrame(frame);
      const L = live.current;
      if (!L) return;
      const o = opts.current;
      const audio = ck.nowMs();
      const now = audio + NOTE_CLOCK_MS + o.offset;
      if (modeRef.current === "watch") { ctl.drain(); L.bot.step(now, L.input); }
      else {
        const perf = performance.now();
        for (const ev of ctl.drain()) {
          const at = now - (perf - ev.perf) * o.rate;
          if (ev.kind === "area") L.input.setArea(ev.idx, ev.on); else { L.input.setButton(ev.idx, ev.on); if (ev.on) fld.flash(ev.idx, at); }
          L.session.tick(at, L.input.snapshot());
        }
      }
      advance(L, fld, ck.playing ? gameSe.current : null, now, o, theme);
      if (perfNow() - lastUi > 100) {
        lastUi = perfNow();
        const sc = L.session.score;
        setPos(audio);
        setStats({ ach: achieveText(sc.achievement), dx: sc.dxScore, combo: sc.combo });
      }
    };
    const perfNow = () => performance.now();
    raf = requestAnimationFrame(frame);
    return () => { alive = false; cancelAnimationFrame(raf); ro.disconnect(); mo.disconnect(); offEnded(); offLoop(); ctl.detach(); ck.close(); };
  }, [chart, song.audio, rebuild]);

  const seek = useCallback((ms: number) => { const ck = clock.current!; ms = Math.max(0, Math.min(duration, ms)); ck.seek(ms); sfx.current?.stopAll(); rebuild(ms); setPos(ms); }, [duration, rebuild]);
  const togglePlay = useCallback(async () => {
    const ck = clock.current!;
    if (ck.playing) { ck.pause(); sfx.current?.stopAll(); setPlaying(false); return; }
    if (finished.current || ck.nowMs() >= duration - 1) seek(0);
    await ck.play();
    setPlaying(true);
  }, [duration, seek]);
  useEffect(() => { clock.current?.setRate(rate); }, [rate]);
  useEffect(() => { clock.current?.setLoop(loop.a, loop.b); }, [loop]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.code === "Space" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement)) { e.preventDefault(); togglePlay(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay]);
  const changeMode = (m: Mode) => { setMode(m); if (m !== "practice") { setLoop({ a: null, b: null }); setRate(1); } rebuild(clock.current?.nowMs() ?? 0); };

  const toResult = () => {
    const L = live.current!;
    // notes still pending at the end count as missed: the engine judges them as the clock passes their window, so run it past the end
    for (let now = clock.current!.nowMs() + NOTE_CLOCK_MS; !L.session.score.done && now < chart.endMs + 5000; now += TICK_MS) L.session.tick(now, L.input.snapshot());
    onResult(playResult(L.session.score, { song: song.id, slot, title: song.title, level: chartInfo.level, autoplay: mode === "watch" }));
  };

  // the whole chart drawn offscreen and encoded faster than real time, in watch mode at full speed, with the song and the note sounds
  const exportVideo = async () => {
    const ck = clock.current!;
    if (!(await canExport())) { setExporting("unsupported"); return; }
    ck.pause(); sfx.current?.stopAll(); setPlaying(false);
    const abort = new AbortController();
    cancelExport.current = abort;
    setExporting(0);
    try {
      const o = opts.current, colors = themeColors(), sec = ck.durationMs / 1000, frames = Math.ceil(sec * VIDEO_FPS);
      // play the chart through once without drawing, writing down every note sound at the frame that sets it off, as live
      const fx = sfx.current?.recorder(), se = fx && seTable.current ? new GameSe(fx, seTable.current) : null;
      if (fx && se) {
        const L = sessionAt(chart, 0);
        se.setNotes(L.session.notes, NOTE_CLOCK_MS);
        for (let i = 0; i < frames; i++) {
          const now = (i * 1000) / VIDEO_FPS + NOTE_CLOCK_MS + o.offset;
          fx.at = i / VIDEO_FPS;
          L.bot.step(now, L.input);
          advance(L, null, se, now, o, colors);
        }
      }
      const mix = new OfflineAudioContext(2, Math.ceil(sec * AUDIO_RATE), AUDIO_RATE), out = limiter(mix);
      out.connect(mix.destination);
      for (const buf of [ck.song, fx?.mixdown(sec)]) {
        if (!buf) continue;
        const src = mix.createBufferSource();
        src.buffer = buf; src.connect(out); src.start();
      }
      const blob = await encodeVideo({ maidata: song.maidata, slot, view: o, colors, frames }, mix.startRendering(), setExporting, abort.signal);
      if (!blob) { setExporting(null); return; }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${song.title} ${chartInfo.name}.mp4`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      setExporting("done");
    } catch {
      setExporting(abort.signal.aborted ? null : "failed");
    }
  };

  const keys = DEFAULT_KEYS;
  return (
    <>
      <div className="play-head">
        <h1>{t.rich("title", { em: (c) => <span>{c}</span> })}</h1>
        <button type="button" className="linkish" onClick={onLibrary}>{t("backToLibrary")}</button>
      </div>
      <div className="player">
        <div className="screen-wrap">
          <canvas ref={canvas} className="screen" aria-label={`${song.title} ${chartInfo.name}`} />
          {!song.audio && <div className="screen-note">{t("noAudio")}</div>}
        </div>
        <aside className="panel">
          <div className="song-card">
            {song.image ? <img src={url(song.image) ?? ""} alt="" /> : <div className="jacket blank">{[...song.title][0]?.toUpperCase()}</div>}
            <div style={{ minWidth: 0 }}>
              <div className="title">{song.title}</div>
              <div className="artist">{song.artist}</div>
              <div className="meta"><span className={diffClass(chartInfo.name)}>{chartInfo.name} {chartInfo.level}</span>{chartInfo.designer && <span>{chartInfo.designer}</span>}{song.bpm && <span>BPM {song.bpm}</span>}</div>
            </div>
          </div>
          <div className="modes" role="tablist">
            {(["watch", "play", "practice"] as Mode[]).map((m) => <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "on" : ""} onClick={() => changeMode(m)} disabled={busy}>{t(m === "watch" ? "modeWatch" : m === "play" ? "modePlay" : "modePractice")}</button>)}
          </div>
          <div className="transport">
            <div className="times"><span>{fmt(pos)}</span><span>{fmt(duration)}</span></div>
            <input type="range" min={0} max={Math.ceil(duration)} value={Math.floor(pos)} onChange={(e) => seek(Number(e.target.value))} disabled={busy} aria-label={t("playBtn")} />
            <div className="row">
              <button type="button" className="button ghost narrow" onClick={() => seek(pos - 5000)} aria-label={t("back5")} disabled={busy}>‹‹</button>
              <button type="button" className="button pink" onClick={togglePlay} disabled={!ready || busy}>{playing ? t("pause") : t("playBtn")}</button>
              <button type="button" className="button ghost narrow" onClick={() => seek(pos + 5000)} aria-label={t("fwd5")} disabled={busy}>››</button>
            </div>
          </div>
          <div className="tiles">
            <div className="tile"><div className="k">{t("achievement")}</div><div className="v">{stats.ach.trim()}</div></div>
            <div className="tile"><div className="k">{t("dxScore")}</div><div className="v">{stats.dx} / {chart.notes.length * 3}</div></div>
          </div>
          {mode === "practice" && (
            <div className="loop">
              <button type="button" className="button ghost small" onClick={() => setLoop((l) => ({ a: pos, b: l.b !== null && l.b > pos ? l.b : null }))}>{t("loopA")}</button>
              <button type="button" className="button ghost small" onClick={() => setLoop((l) => ({ a: l.a !== null && l.a < pos ? l.a : 0, b: pos }))}>{t("loopB")}</button>
              <button type="button" className="button ghost small" onClick={() => setLoop({ a: null, b: null })}>{t("loopClear")}</button>
              <span className="ab">{loop.a !== null && loop.b !== null ? `${fmt(loop.a)} – ${fmt(loop.b)}` : t("loopNone")}</span>
              <label style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>{t("speed")}
                <select value={rate} onChange={(e) => setRate(Number(e.target.value))}>{[0.5, 0.6, 0.7, 0.8, 0.9, 1].map((r) => <option key={r} value={r}>{Math.round(r * 100)}%</option>)}</select>
              </label>
            </div>
          )}
          <div className="opts">
            <label><span>{t("noteSpeed")}</span><span><input type="range" min={0} max={NOTE_SPEED.length - 2} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /><span className="num">{(1 + speed * 0.25).toFixed(2)}</span></span></label>
            <label><span>{t("touchSpeed")}</span><span><input type="range" min={0} max={TOUCH_SPEED.length - 2} value={touchSpeed} onChange={(e) => setTouchSpeed(Number(e.target.value))} /><span className="num">{touchSpeed + 1}</span></span></label>
            <label><span>{t("offset")}</span><input type="number" step={5} value={offset} onChange={(e) => setOffset(Number(e.target.value) || 0)} style={{ width: 70 }} /></label>
            <label><span>{t("showSensors")}</span><input type="checkbox" checked={sensors} onChange={(e) => setSensors(e.target.checked)} /></label>
            <label><span>{t("judgeDisplay")}</span><input type="checkbox" checked={fastLate} onChange={(e) => setFastLate(e.target.checked)} /></label>
            <label><span>{t("look")}</span><select value={useSkin ? "game" : "plain"} onChange={(e) => setUseSkin(e.target.value === "game")}><option value="game">{t("lookGame")}</option><option value="plain">{t("lookPlain")}</option></select></label>
            <label><span>{t("ringDesign")}</span><select value={outline} onChange={(e) => setOutline(Number(e.target.value))} disabled={!useSkin}>{OUTLINES.map((name, i) => <option key={name} value={i}>{name}</option>)}</select></label>
            <label><span>{t("starColor")}</span><select value={starPink ? "pink" : "blue"} onChange={(e) => setStarPink(e.target.value === "pink")} disabled={!useSkin}><option value="blue">{t("starBlue")}</option><option value="pink">{t("starPink")}</option></select></label>
            <label><span>{t("centerDisplay")}</span><select value={center} onChange={(e) => setCenter(e.target.value as Center)}>{CENTERS.map((c) => <option key={c} value={c}>{t(c === "off" ? "centerOff" : c === "combo" ? "centerCombo" : c === "achievement" ? "centerAchievement" : c === "achievementDown" ? "centerAchievementDown" : "centerDx")}</option>)}</select></label>
          </div>
          <div>
            <div className="keys">{keys.map((k, i) => <span key={k}>{k.toUpperCase()}<b>{i + 1}</b></span>)}</div>
            <p className="hint" style={{ marginTop: 6 }}>{t("keysHint")}</p>
          </div>
          <div className="export-row">
            {busy ? (
              <button type="button" className="button ghost" onClick={() => cancelExport.current?.abort()}>{t("exportCancel")}</button>
            ) : <button type="button" className="button" onClick={exportVideo} disabled={!ready}>{t("exportVideo")}</button>}
            {busy && <><progress value={exporting} max={1} /><p className="hint">{t("exporting", { pct: Math.floor(exporting * 100) })}</p></>}
            {exporting === "done" && <p className="hint ok">{t("exportDone")}</p>}
            {exporting === "unsupported" && <p className="hint">{t("exportUnsupported")}</p>}
            {exporting === "failed" && <p className="hint">{t("exportFailed")}</p>}
          </div>
          <button type="button" className="button pink" onClick={toResult} disabled={busy}>{t("toResult")}</button>
        </aside>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- result ----------------------------------------------------------------
const KINDS = [["kindTap", K.Tap], ["kindHold", K.Hold], ["kindSlide", K.Slide], ["kindTouch", K.Touch], ["kindBreak", K.Break]] as const;

function Result({ result, pick, url, onAgain, onLibrary }: { result: PlayResult; pick: Pick; url: (f: File | null) => string | null; onAgain: (mode: "watch" | "play") => void; onLibrary: () => void }) {
  const t = useTranslations("play");
  const { song } = pick;
  const chartInfo = song.charts.find((c) => c.slot === pick.slot)!;
  const C = 2 * Math.PI * 104, arc = (C * Math.min(1, result.achievement / 101)).toFixed(1);
  const ticks = Array.from({ length: 8 }, (_, i) => { const a = (i * 45 * Math.PI) / 180; return [120 + 96 * Math.cos(a), 120 + 96 * Math.sin(a), 120 + 112 * Math.cos(a), 120 + 112 * Math.sin(a)]; });
  // per kind: the five judgement boxes from the engine's [EScoreType][ETiming] counts
  const rows = KINDS.map(([key, kind]) => { const box = [0, 0, 0, 0, 0]; result.byKind[kind].forEach((n, timing) => { if (n) box[convertJudge(timing)] += n; }); return { key, box, total: box.reduce((a, b) => a + b, 0) }; }).filter((r) => r.total);
  const all = [0, 0, 0, 0, 0]; rows.forEach((r) => r.box.forEach((n, i) => { all[i] += n; }));
  const cell = (n: number, i: number) => <td key={i} className={i === BOX.Miss && n ? "miss" : n ? "" : "zero"}>{n}</td>;
  const order = [BOX.Critical, BOX.Perfect, BOX.Great, BOX.Good, BOX.Miss];
  return (
    <>
      <div className="play-head">
        <h1>{t.rich("title", { em: (c) => <span>{c}</span> })}</h1>
        <span className="count">{song.title} · {chartInfo.name} {chartInfo.level}{result.autoplay ? ` · ${t("autoplayNote")}` : ""}</span>
      </div>
      <div className="result">
        <div className="result-card">
          <svg className="gauge" viewBox="0 0 240 240" role="img" aria-label={`${t("rank")} ${result.rank}`}>
            <circle className="track" cx="120" cy="120" r="104" />
            <circle className="arc" cx="120" cy="120" r="104" strokeDasharray={`${arc} ${C.toFixed(1)}`} transform="rotate(-90 120 120)" />
            {ticks.map(([x1, y1, x2, y2], i) => <line key={i} className="tick" x1={x1} y1={y1} x2={x2} y2={y2} />)}
            <text x="120" y="112" fontSize="48" textAnchor="middle">{result.rank}</text>
            <text x="120" y="142" fontSize="13" textAnchor="middle" letterSpacing="2" opacity=".6">{t("rank").toUpperCase()}</text>
          </svg>
          <div className="big">{achieveText(result.achievement).trim().replace("%", "")}<span>%</span></div>
          <div className="sub">{t("achievement")}</div>
          {result.comboType > 0 && <span className="medal">{COMBO_NAMES[result.comboType]}</span>}
          <div className="tiles">
            <div className="tile"><div className="k">{t("dxScore")}</div><div className="v">{result.dx} / {result.dxMax}</div></div>
            <div className="tile"><div className="k">{t("maxCombo")}</div><div className="v">{result.maxCombo} / {result.theoryCombo}</div></div>
            <div className="tile"><div className="k">{t("fast")} / {t("late")}</div><div className="v">{result.fast} / {result.late}</div></div>
          </div>
        </div>
        <main>
          <h2>{t("judgements")}</h2>
          <table className="judge-table">
            <thead><tr><th /><th>{t("critical")}</th><th>{t("perfect")}</th><th>{t("great")}</th><th>{t("good")}</th><th>{t("miss")}</th></tr></thead>
            <tbody>
              {rows.map((r) => <tr key={r.key}><td>{t(r.key)}</td>{order.map((b) => cell(r.box[b], b))}</tr>)}
              <tr><td>{t("allNotes")}</td>{order.map((b) => cell(all[b], b))}</tr>
            </tbody>
          </table>
          <div className="btn-row" style={{ marginTop: 22 }}>
            <button type="button" className="button pink" onClick={() => onAgain("play")}>{t("playAgain")}</button>
            <button type="button" className="button ghost" onClick={() => onAgain("watch")}>{t("watchAgain")}</button>
            <button type="button" className="button ghost" onClick={onLibrary}>{t("backToLibrary")}</button>
          </div>
        </main>
      </div>
    </>
  );
}
