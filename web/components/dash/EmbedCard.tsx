"use client";

import { useEffect, useRef, useState } from "react";
import { useM } from "@/components/I18n";
import type { Sharing as SharingState } from "./api";

// the words for each switch are in the translation files, under the same key
// the name and the rating are the card, so they are not here. Everything else is the owner's.
const PICTURE: (keyof SharingState["card"])[] = ["chart", "gain", "charts", "plays"];

// what the picture can be a picture of (embedCard.visuals). Two of them need a section the profile may not be sharing.

const TEXT: (keyof SharingState["embed"])[] = ["region", "charts"];

/**
 * What a shared link turns into in Discord, and the switches for it, in a window of its own.
 *
 * The preview is the real picture from the real address rather than a drawing of one, so what is on
 * screen is what gets posted. It is asked for on this site's own address rather than the one the
 * bot publishes: the two can differ, and the page only allows pictures from itself.
 */
export function EmbedCard({ state, onSave, busy, onClose }: {
  state: SharingState;
  onSave: (body: Record<string, unknown>) => void;
  busy: boolean;
  onClose: () => void;
}) {
  const m = useM();
  const t = m.embedCard;
  const box = useRef<HTMLDialogElement>(null);
  const [drawn, setDrawn] = useState(0);
  const [failed, setFailed] = useState(false);
  const [colour, setColour] = useState(state.colour);
  const settled = useRef<number | null>(null);

  // opened once, on the way in. The caller usually passes a fresh arrow every render, and running
  // this again would reopen the window the moment somebody closed it.
  const shut = useRef(onClose);
  shut.current = onClose;
  useEffect(() => {
    const dialog = box.current;
    if (!dialog) return;
    dialog.showModal();
    const closed = () => shut.current();
    dialog.addEventListener("close", closed);
    return () => dialog.removeEventListener("close", closed);
  }, []);

  // a save lands as new state, and the picture is drawn from what was saved
  const drawnFrom = JSON.stringify([state.card, state.embed, state.colour, state.visual]);
  useEffect(() => {
    setDrawn((n) => n + 1);
    setFailed(false);
    setColour(state.colour);
  }, [drawnFrom, state.colour]);

  // the colour well fires on every drag, so it is saved once the hand stops moving
  const pick = (next: string) => {
    setColour(next);
    if (settled.current) window.clearTimeout(settled.current);
    settled.current = window.setTimeout(() => onSave({ colour: next }), 320);
  };

  const slug = state.url.split("/p/")[1] ?? "";
  const picture = `/p/${slug}/card.png?p=${drawn}`;
  const bits = ["13,551 rating"];
  if (state.embed.region) bits.push("international");
  if (state.embed.charts) bits.push("551 charts scored");

  const rows = <G extends "card" | "embed">(group: G, list: (keyof SharingState[G])[], words: Record<string, [string, string]>) => (
    <ul className="share-toggles">
      {list.map((key) => ({ key, label: words[key as string][0], note: words[key as string][1] })).map((row) => (
        <li key={String(row.key)}>
          <label>
            <input
              type="checkbox"
              checked={Boolean((state[group] as Record<string, boolean>)[row.key as string])}
              disabled={busy}
              onChange={(e) => onSave({ [group]: { [row.key]: e.target.checked } })}
            />
            <span>
              <b>{row.label}</b>
              <span className="dim">{row.note}</span>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );

  return (
    <dialog className="sheet" ref={box} aria-label={t.label}>
      <div className="sheet-head">
        <b>{t.title}</b>
        <button type="button" className="sheet-shut" onClick={() => box.current?.close()} aria-label={t.close}>
          ×
        </button>
      </div>

      <div className="sheet-body">
        <p className="hint">{t.intro}</p>

        <div className="embed-preview" style={{ borderLeftColor: colour }} aria-label={t.looks}>
          {state.card.on && !failed ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={picture} alt={t.imageAlt} onError={() => setFailed(true)} />
          ) : null}
          <div className="embed-body">
            <b className="embed-title" style={{ color: colour }}>
              your name
            </b>
            <span className="embed-line">{bits.join(" · ")}</span>
            <span className="embed-btn">See the profile</span>
          </div>
        </div>
        {failed && <p className="hint">{t.notReady}</p>}

        <p className="embed-group">{t.image}</p>
        <ul className="visuals">
          {state.visuals.map((option) => {
            const words = t.visuals[option.key];
            if (!words) return null;
            const about = { label: words[0], note: words[1] };
            return (
              <li key={option.key}>
                <label className={option.ready ? "" : "off"}>
                  <input
                    type="radio"
                    name="visual"
                    checked={state.visual === option.key}
                    disabled={busy || !option.ready}
                    onChange={() => onSave({ visual: option.key })}
                  />
                  <span>
                    <b>{about.label}</b>
                    <span className="dim">
                      {option.ready ? about.note : t.needs(m.sharing.sections[option.needs === "best50" ? "best50" : "traits"][0])}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>

        <p className="embed-group">{t.colour}</p>
        <div className="swatches">
          {state.colours.map((option) => (
            <button
              key={option}
              type="button"
              className={`swatch${option.toLowerCase() === colour.toLowerCase() ? " on" : ""}`}
              style={{ background: option }}
              aria-label={option}
              aria-pressed={option.toLowerCase() === colour.toLowerCase()}
              disabled={busy}
              onClick={() => pick(option)}
            />
          ))}
          <label className="swatch-own">
            <input type="color" value={colour} disabled={busy} onChange={(e) => pick(e.target.value)} />
            <span>{t.custom}</span>
          </label>
        </div>

        <label className="embed-main">
          <input
            type="checkbox"
            checked={state.card.on}
            disabled={busy}
            onChange={(e) => onSave({ card: { on: e.target.checked } })}
          />
          <span>
            <b>{t.showImage}</b>
            <span className="dim">{t.showImageNote}</span>
          </span>
        </label>

        {state.card.on && (
          <>
            <p className="embed-group">{t.onImage}</p>
            {rows("card", PICTURE, t.picture)}
          </>
        )}

        <p className="embed-group">{t.underName}</p>
        {rows("embed", TEXT, t.text)}

        <p className="hint">{t.cache}</p>
      </div>
    </dialog>
  );
}
