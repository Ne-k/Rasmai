"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { postJSON, type Sharing as SharingState } from "./api";
import { Label } from "./bits";
import { EmbedCard } from "./EmbedCard";

const SECTIONS: (keyof SharingState["sections"])[] = ["best50", "traits", "recent", "areas"];

/** The public profile: a link anyone can open, carrying only the sections that are switched on. */
export function Sharing({ state, onChange }: { state: SharingState; onChange: (next: SharingState) => void }) {
  const t = useTranslations("sharing");
  const [busy, setBusy] = useState(false);
  const [customising, setCustomising] = useState(false);
  const [copied, setCopied] = useState(false);
  const [note, setNote] = useState("");

  const save = (body: Record<string, unknown>) => {
    setBusy(true);
    setNote("");
    postJSON<SharingState>("/api/me/sharing", body)
      .then(onChange)
      .catch((e: Error) => setNote(e.message || t("couldntSave")))
      .finally(() => setBusy(false));
  };

  const copy = () => {
    navigator.clipboard
      .writeText(state.url)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => setNote(t("couldntCopy")));
  };

  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={t("info")}>{t("title")}</Label>
        <span className={`mono hint${state.on ? " ok" : ""}`}>{state.on ? t("shared") : t("private")}</span>
      </div>

      <p className="hint">{t("intro")}</p>

      <div className="btn-row">
        <button type="button" className={state.on ? "button ghost" : "button"} onClick={() => save({ on: !state.on })} disabled={busy}>
          {state.on ? t("stop") : t("create")}
        </button>
        {state.on && (
          <button type="button" className="button ghost" onClick={() => save({ on: true, rotate: true })} disabled={busy}>
            {t("newLink")}
          </button>
        )}
      </div>

      {state.on && state.url && (
        <div className="share-link">
          <code>{state.url}</code>
          <button type="button" className="button ghost" onClick={copy}>
            {copied ? t("copied") : t("copy")}
          </button>
        </div>
      )}

      {state.on && (
        <ul className="share-toggles">
          {SECTIONS.map((section) => (
            <li key={section}>
              <label>
                <input
                  type="checkbox"
                  checked={state.sections[section]}
                  disabled={busy}
                  onChange={(e) => save({ sections: { [section]: e.target.checked } })}
                />
                <span>
                  <b>{t(`sections.${section}.title`)}</b>
                  <span className="dim">{t(`sections.${section}.hint`)}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {state.on && (
        <div className="btn-row">
          <button type="button" className="button ghost" onClick={() => setCustomising(true)}>
            {t("customise")}
          </button>
        </div>
      )}
      {state.on && customising && (
        <EmbedCard state={state} onSave={save} busy={busy} onClose={() => setCustomising(false)} />
      )}

      {note && <p className="hint">{note}</p>}
      {state.on && <p className="hint">{t("breaks")}</p>}
    </section>
  );
}
