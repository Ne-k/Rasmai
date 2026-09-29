"use client";

import { useState } from "react";
import { postJSON, type Sharing as SharingState } from "./api";
import { Label } from "./bits";
import { EmbedCard } from "./EmbedCard";

const SECTIONS: { key: keyof SharingState["sections"]; label: string; note: string }[] = [
  { key: "best50", label: "Best 50", note: "the 50 charts that make up your rating" },
  { key: "traits", label: "Traits", note: "your strengths and weak spots" },
  { key: "recent", label: "Recent plays", note: "your last 20 plays" },
  { key: "areas", label: "Areas", note: "your progress in each area" },
];

/** The public profile: a link anyone can open, carrying only the sections that are switched on. */
export function Sharing({ state, onChange }: { state: SharingState; onChange: (next: SharingState) => void }) {
  const [busy, setBusy] = useState(false);
  const [customising, setCustomising] = useState(false);
  const [copied, setCopied] = useState(false);
  const [note, setNote] = useState("");

  const save = (body: Record<string, unknown>) => {
    setBusy(true);
    setNote("");
    postJSON<SharingState>("/api/me/sharing", body)
      .then(onChange)
      .catch((e: Error) => setNote(e.message || "couldn't save that"))
      .finally(() => setBusy(false));
  };

  const copy = () => {
    navigator.clipboard
      .writeText(state.url)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => setNote("couldn't copy. Select the link and copy it yourself."));
  };

  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info="Anyone with the link can see it. Your Discord account isn't on it and search engines won't list it.">
          public profile
        </Label>
        <span className={`mono hint${state.on ? " ok" : ""}`}>{state.on ? "shared" : "private"}</span>
      </div>

      <p className="hint">
        Off by default. Shows your name, rating, play count and any sections you turn on.
      </p>

      <div className="btn-row">
        <button type="button" className={state.on ? "button ghost" : "button"} onClick={() => save({ on: !state.on })} disabled={busy}>
          {state.on ? "stop sharing" : "create a public link"}
        </button>
        {state.on && (
          <button type="button" className="button ghost" onClick={() => save({ on: true, rotate: true })} disabled={busy}>
            new link
          </button>
        )}
      </div>

      {state.on && state.url && (
        <div className="share-link">
          <code>{state.url}</code>
          <button type="button" className="button ghost" onClick={copy}>
            {copied ? "copied" : "copy"}
          </button>
        </div>
      )}

      {state.on && (
        <ul className="share-toggles">
          {SECTIONS.map((section) => (
            <li key={section.key}>
              <label>
                <input
                  type="checkbox"
                  checked={state.sections[section.key]}
                  disabled={busy}
                  onChange={(e) => save({ sections: { [section.key]: e.target.checked } })}
                />
                <span>
                  <b>{section.label}</b>
                  <span className="dim">{section.note}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {state.on && (
        <div className="btn-row">
          <button type="button" className="button ghost" onClick={() => setCustomising(true)}>
            customise the Discord card
          </button>
        </div>
      )}
      {state.on && customising && (
        <EmbedCard state={state} onSave={save} busy={busy} onClose={() => setCustomising(false)} />
      )}

      {note && <p className="hint">{note}</p>}
      {state.on && <p className="hint">Making a new link breaks the old one.</p>}
    </section>
  );
}
