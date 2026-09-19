"use client";

import { useEffect, useRef, useState } from "react";
import type { Sharing as SharingState } from "./api";

type Toggle<G extends "card" | "embed"> = { key: keyof SharingState[G]; label: string; note: string };

// the name and the rating are the card, so they are not here. Everything else is the owner's.
const PICTURE: Toggle<"card">[] = [
  { key: "chart", label: "Rating over time", note: "the curve across the bottom" },
  { key: "gain", label: "What it moved", note: "how far the rating has come, and since when" },
  { key: "charts", label: "Charts scored", note: "how many charts you have a score on" },
  { key: "plays", label: "Play count", note: "how many credits you have put in" },
];

// what the picture can be a picture of. Two of them need a section the profile may not be sharing.
const VISUALS: Record<string, { label: string; note: string }> = {
  curve: { label: "Rating over time", note: "where your rating has been going" },
  best50: { label: "Your best 50", note: "the fifty charts it is made of, tallest first" },
  traits: { label: "How you play", note: "the wheel of what each part of your play asks" },
  figures: { label: "Just the figures", note: "no chart, the numbers on their own" },
};

const TEXT: Toggle<"embed">[] = [
  { key: "region", label: "Region", note: "international or Japan, beside the rating" },
  { key: "charts", label: "Charts scored", note: "the count, beside the rating" },
];

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

  const rows = <G extends "card" | "embed">(group: G, list: Toggle<G>[]) => (
    <ul className="share-toggles">
      {list.map((row) => (
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
    <dialog className="sheet" ref={box} aria-label="the card your link shows in Discord">
      <div className="sheet-head">
        <b>The card in Discord</b>
        <button type="button" className="sheet-shut" onClick={() => box.current?.close()} aria-label="close">
          ×
        </button>
      </div>

      <div className="sheet-body">
        <p className="hint">
          What Discord shows when somebody pastes your link. Your name and rating are always on it. Everything else
          here is yours.
        </p>

        <div className="embed-preview" style={{ borderLeftColor: colour }} aria-label="what the card looks like">
          {state.card.on && !failed ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={picture} alt="the picture above your card" onError={() => setFailed(true)} />
          ) : null}
          <div className="embed-body">
            <b className="embed-title" style={{ color: colour }}>
              your name
            </b>
            <span className="embed-line">{bits.join(" · ")}</span>
            <span className="embed-btn">See the profile</span>
          </div>
        </div>
        {failed && <p className="hint">The picture is not ready yet. It will be there when Discord reads the card.</p>}

        <p className="embed-group">the picture</p>
        <ul className="visuals">
          {state.visuals.map((option) => {
            const about = VISUALS[option.key];
            if (!about) return null;
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
                      {option.ready ? about.note : `turn ${option.needs === "best50" ? "Best 50" : "Traits"} on above first`}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>

        <p className="embed-group">colour</p>
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
            <span>your own</span>
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
            <b>Show a picture</b>
            <span className="dim">off leaves the name, the rating and the button</span>
          </span>
        </label>

        {state.card.on && (
          <>
            <p className="embed-group">on the picture</p>
            {rows("card", PICTURE)}
          </>
        )}

        <p className="embed-group">under your name</p>
        {rows("embed", TEXT)}

        <p className="hint">
          Discord holds on to a card for about half an hour after it first reads it, so a change shows up on the next
          link you post rather than on one already sent.
        </p>
      </div>
    </dialog>
  );
}
