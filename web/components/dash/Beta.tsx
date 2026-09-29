"use client";

import { useEffect, useRef, useState } from "react";
import { getJSON, postJSON, type Beta as BetaState, type BetaFeature, type BetaVerdict } from "./api";
import { Label } from "./bits";

const POLL_MS = 4000;

/** "about 12 minutes left", from seconds. */
function left(seconds: number): string {
  if (seconds <= 0) return "";
  if (seconds < 60) return "less than a minute left";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `about ${minutes} minute${minutes === 1 ? "" : "s"} left`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `about ${hours}h${rest ? ` ${rest}m` : ""} left`;
}

/** How far a feature's groundwork has got, while it is still going. */
function Progress({ feature }: { feature: BetaFeature }) {
  const total = feature.total ?? 0;
  const done = feature.done ?? 0;
  if (!total || !feature.waiting) return null;
  const percent = Math.min(100, Math.max(0, feature.percent ?? 0));
  const eta = left(feature.eta ?? 0);
  return (
    <span className="crawl">
      <span
        className="crawl-bar"
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="charts read so far"
      >
        <span style={{ width: `${percent}%` }} />
      </span>
      <span className="crawl-said mono">
        {done.toLocaleString()} / {total.toLocaleString()} charts · {percent.toFixed(1)}%{eta ? ` · ${eta}` : ""}
      </span>
    </span>
  );
}

const VERDICTS: { key: BetaVerdict; label: string }[] = [
  { key: "better", label: "Better" },
  { key: "same", label: "No difference" },
  { key: "worse", label: "Worse" },
];

/** What one tester made of one feature: a verdict, and optionally why. Only shown once it is on. */
function Feedback({ feature, onSaved }: { feature: BetaFeature; onSaved: (next: BetaState) => void }) {
  const said = feature.said ?? null;
  const [note, setNote] = useState(said?.said ?? "");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const send = (verdict: BetaVerdict, text: string) => {
    setBusy(true);
    setError("");
    postJSON<BetaState>("/api/me/beta/feedback", { feature: feature.key, verdict, said: text })
      .then((next) => {
        onSaved(next);
        setOpen(false);
      })
      .catch((e: Error) => setError(e.message || "couldn't send that"))
      .finally(() => setBusy(false));
  };

  return (
    <span className="beta-say">
      <span className="beta-say-row">
        <span className="dim">Compared to having it off:</span>
        {VERDICTS.map((v) => (
          <button
            key={v.key}
            type="button"
            className={`beta-chip${said?.verdict === v.key ? " on" : ""}`}
            disabled={busy}
            aria-pressed={said?.verdict === v.key}
            onClick={() => send(v.key, note)}
          >
            {v.label}
          </button>
        ))}
        <button type="button" className="beta-chip quiet" disabled={busy} onClick={() => setOpen((was) => !was)}>
          {note ? "Edit note" : "Add a note"}
        </button>
      </span>
      {open && (
        <span className="beta-say-row">
          <input
            type="text"
            className="beta-note"
            maxLength={500}
            placeholder="What changed?"
            value={note}
            disabled={busy}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && said?.verdict) send(said.verdict, note);
            }}
          />
          {said?.verdict && (
            <button type="button" className="beta-chip" disabled={busy} onClick={() => send(said.verdict, note)}>
              Save
            </button>
          )}
          {!said?.verdict && <span className="mono hint">Pick an option first.</span>}
        </span>
      )}
      {said && !open && (
        <span className="mono hint ok">
          You said {said.verdict}
          {said.said ? ` · ${said.said}` : ""}
        </span>
      )}
      {error && <span className="mono hint">{error}</span>}
    </span>
  );
}

/** Features that work but are not finished. Each is off until its owner turns it on. */
export function Beta({ state, onChange }: { state: BetaState; onChange: (next: BetaState) => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const latest = useRef(onChange);
  latest.current = onChange;

  // while groundwork is still running, keep the bar moving without the person reloading the page
  const running = state.features.some((f) => (f.waiting ?? 0) > 0);
  useEffect(() => {
    if (!running) return;
    let alive = true;
    const timer = setInterval(() => {
      getJSON<BetaState>("/api/me/beta")
        .then((next) => {
          if (alive) latest.current(next);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [running]);

  const toggle = (key: string, on: boolean) => {
    setBusy(true);
    setNote("");
    postJSON<BetaState>("/api/me/beta", { on: { [key]: on } })
      .then((next) => {
        onChange(next);
        const feature = next.features.find((f) => f.key === key);
        setNote(
          !on
            ? "Turns off on your next refresh."
            : feature && feature.ready === false
              ? "Turned on, but the bot can't run it yet, so nothing changes for now."
              : "Turns on with your next refresh. Hit refresh above to see it now.",
        );
      })
      .catch((e: Error) => setNote(e.message || "couldn't save that"))
      .finally(() => setBusy(false));
  };

  const count = Object.values(state.on).filter(Boolean).length;

  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info="Features that work but aren't finished yet. Turning one off puts things back to normal.">
          beta
        </Label>
        <span className={`mono hint${count ? " ok" : ""}`}>{count ? `${count} on` : "none on"}</span>
      </div>

      <ul className="share-toggles">
        {state.features.map((feature) => (
          <li key={feature.key}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(state.on[feature.key])}
                disabled={busy}
                onChange={(e) => toggle(feature.key, e.target.checked)}
              />
              <span>
                <b>{feature.label}</b>
                <span className="dim">{feature.note}</span>
                <Progress feature={feature} />
                {feature.status && !feature.waiting && (
                  <span className={`mono hint${feature.ready === false ? "" : " ok"}`}>{feature.status}</span>
                )}
              </span>
            </label>
            {state.on[feature.key] && <Feedback feature={feature} onSaved={onChange} />}
          </li>
        ))}
      </ul>

      {note && <p className="hint">{note}</p>}
      <p className="hint">These can change your traits and picks. Tell us what you think so we know whether to keep them.</p>
    </section>
  );
}
