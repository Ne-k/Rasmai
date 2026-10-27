"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import slideData from "@/lib/chart/slides.json";
import { buildChart } from "@/lib/chart/build.mjs";
import { parseMaidata } from "@/lib/chart/chart.mjs";
import type { Chart } from "@/lib/chart/types";
import { Field } from "./field";
import { SongClock } from "./audio";
import { Sfx, GameSe, type SeTable } from "./sfx";
import { advance, sessionAt, NOTE_CLOCK_MS, type Live, type View } from "./run";
import "./viewer.css";

export const themeColors = () => { const cs = getComputedStyle(document.documentElement); return { screen: cs.getPropertyValue("--ring-screen").trim() || "#1d1a2f", ring: "#6a6a7c", button: "#8f8fa3" }; };
export const fmt = (ms: number) => { const s = Math.max(0, ms) / 1000; return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}.${Math.floor((s % 1) * 10)}`; };

/** A silent WAV of the chart's length, so a song folder without audio still plays on the same clock. */
function silence(ms: number): Blob {
  const rate = 8000, n = Math.ceil((ms / 1000) * rate), buf = new ArrayBuffer(44 + n), v = new DataView(buf);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + n, true); str(8, "WAVE"); str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true); str(36, "data"); v.setUint32(40, n, true);
  new Uint8Array(buf, 44).fill(128);
  return new Blob([buf], { type: "audio/wav" });
}

// what the page using the screen adds each frame: `step` judges the frame's input (auto play when absent), `ui` reads the score
export type ScreenHooks = { step?: (L: Live, now: number) => void; ui?: (L: Live) => void };

/** The play screen: the field on a canvas, the song's clock and the note sounds, judged and drawn every frame. */
export function useScreen(chart: Chart, audio: Blob | string | null, opts: { current: View }, hooks: { current: ScreenHooks }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const field = useRef<Field | null>(null);
  const clock = useRef<SongClock | null>(null);
  const live = useRef<Live | null>(null);
  const gameSe = useRef<GameSe | null>(null);
  const sfx = useRef<Sfx | null>(null);
  const seTable = useRef<SeTable | null>(null);
  const finished = useRef(false);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const duration = clock.current?.durationMs ?? chart.endMs;

  const rebuild = useCallback((audioMs: number) => { live.current = sessionAt(chart, audioMs); field.current?.reset(); gameSe.current?.setNotes(live.current.session.notes, audioMs + NOTE_CLOCK_MS); finished.current = false; }, [chart]);

  useEffect(() => {
    const cv = canvas.current!;
    const fld = new Field(cv, slideData);
    fld.setChart(chart);
    field.current = fld;
    const ck = new SongClock();
    clock.current = ck;
    rebuild(0);
    let alive = true;
    // a song from the server comes by its address; one that is not there plays the chart in silence
    const song = typeof audio === "string" ? fetch(audio).then((r) => (r.ok ? r.blob() : null)).catch(() => null) : Promise.resolve(audio);
    // the song and the game's sprites (web/scripts/play-assets.mjs; plain shapes without them) must both be in before Play is offered
    Promise.all([song.then((b) => ck.load(b ?? silence(chart.endMs + 3000))), fld.loadSkin("/play/skin")]).then(() => { if (alive) setReady(true); });
    // the game's own sound effects, when the site has them; silence otherwise
    fetch("/play/se/seoptions.json").then(async (r) => {
      if (!r.ok || !alive) return;
      const table = (await r.json()) as SeTable, fx = new Sfx(ck), se = new GameSe(fx, table);
      await fx.preload(se.names);
      if (!alive) return;
      sfx.current = fx; gameSe.current = se; seTable.current = table;
      if (live.current) se.setNotes(live.current.session.notes, ck.nowMs() + NOTE_CLOCK_MS);
    }).catch(() => {});
    const offEnded = ck.on("ended", () => { setPlaying(false); finished.current = true; if (live.current) hooks.current.ui?.(live.current); });
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
      const o = opts.current, h = hooks.current;
      const audioMs = ck.nowMs();
      const now = audioMs + NOTE_CLOCK_MS + o.offset;
      if (h.step) h.step(L, now); else L.bot.step(now, L.input);
      advance(L, fld, ck.playing ? gameSe.current : null, now, o, theme);
      if (performance.now() - lastUi > 100) {
        lastUi = performance.now();
        setPos(audioMs);
        h.ui?.(L);
      }
    };
    raf = requestAnimationFrame(frame);
    return () => { alive = false; cancelAnimationFrame(raf); ro.disconnect(); mo.disconnect(); offEnded(); offLoop(); ck.close(); };
  }, [chart, audio, rebuild, opts, hooks]);

  const seek = useCallback((ms: number) => { const ck = clock.current!; ms = Math.max(0, Math.min(duration, ms)); ck.seek(ms); sfx.current?.stopAll(); rebuild(ms); setPos(ms); }, [duration, rebuild]);
  const togglePlay = useCallback(async () => {
    const ck = clock.current!;
    if (ck.playing) { ck.pause(); sfx.current?.stopAll(); setPlaying(false); return; }
    if (finished.current || ck.nowMs() >= duration - 1) seek(0);
    await ck.play();
    setPlaying(true);
  }, [duration, seek]);

  return { canvas, field, clock, live, sfx, seTable, ready, playing, setPlaying, pos, duration, rebuild, seek, togglePlay };
}

/** A chart played by auto play with its song and note sounds, at the given speeds (NOTE_SPEED / TOUCH_SPEED values). */
export function Viewer({ maidata, slot, audio, noteSpeed, touchSpeed, label }: { maidata: string; slot: number; audio: string | null; noteSpeed: number; touchSpeed: number; label: string }) {
  const t = useTranslations("play");
  const chart = useMemo(() => buildChart(parseMaidata(maidata), slot), [maidata, slot]);
  const opts = useRef<View>({ noteSpeed, touchSpeed, showSensors: false, dispJudge: 1, offset: 0, rate: 1, center: "combo", useSkin: true, outline: 17, starPink: false });
  opts.current = { ...opts.current, noteSpeed, touchSpeed };
  const hooks = useRef<ScreenHooks>({});
  const { canvas, ready, playing, pos, duration, seek, togglePlay } = useScreen(chart, audio, opts, hooks);
  return (
    <div className="viewer">
      <canvas ref={canvas} className="screen" aria-label={label} />
      <div className="transport">
        <div className="times"><span>{fmt(pos)}</span><span>{fmt(duration)}</span></div>
        <input type="range" min={0} max={Math.ceil(duration)} value={Math.floor(pos)} onChange={(e) => seek(Number(e.target.value))} aria-label={t("playBtn")} />
        <div className="row">
          <button type="button" className="button ghost narrow" onClick={() => seek(pos - 5000)} aria-label={t("back5")}>‹‹</button>
          <button type="button" className="button pink" onClick={togglePlay} disabled={!ready}>{playing ? t("pause") : t("playBtn")}</button>
          <button type="button" className="button ghost narrow" onClick={() => seek(pos + 5000)} aria-label={t("fwd5")}>››</button>
        </div>
      </div>
    </div>
  );
}
