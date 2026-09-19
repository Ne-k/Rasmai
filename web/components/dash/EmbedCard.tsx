"use client";

import { useEffect, useRef, useState } from "react";
import type { Sharing as SharingState } from "./api";
import { Label } from "./bits";

type Toggle<G extends "card" | "embed"> = { group: G; key: keyof SharingState[G]; label: string; note: string };

// the name and the rating are the card, so they are not here. Everything else is the owner's.
const PICTURE: Toggle<"card">[] = [
  { group: "card", key: "chart", label: "Rating over time", note: "the curve across the bottom" },
  { group: "card", key: "gain", label: "What it moved", note: "how far the rating has come, and since when" },
  { group: "card", key: "charts", label: "Charts scored", note: "how many charts you have a score on" },
  { group: "card", key: "plays", label: "Play count", note: "how many credits you have put in" },
];

const TEXT: Toggle<"embed">[] = [
  { group: "embed", key: "region", label: "Region", note: "international or Japan, beside the rating" },
  { group: "embed", key: "charts", label: "Charts scored", note: "the count, beside the rating" },
];

/**
 * What a shared link turns into in Discord, and the switches for it.
 *
 * The preview is the real picture from the real address, not a drawing of one, so what you are
 * looking at is what gets posted. Discord keeps its own copy of a picture for a long while, so the
 * address carries the moment the profile last changed; here it carries a counter as well, because
 * a toggle changes the picture without changing the profile.
 */
export function EmbedCard({ state, onSave, busy }: {
  state: SharingState;
  onSave: (body: Record<string, unknown>) => void;
  busy: boolean;
}) {
  const [drawn, setDrawn] = useState(0);
  const [failed, setFailed] = useState(false);
  const first = useRef(true);

  // the saved state is what the picture is drawn from, so it is redrawn once a save lands
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setDrawn((n) => n + 1);
    setFailed(false);
  }, [state.card, state.embed]);

  if (!state.on || !state.url) return null;
  const picture = `${state.url}/card.png?p=${drawn}`;
  const bits = [`13,551 rating`];
  if (state.embed.region) bits.push("international");
  if (state.embed.charts) bits.push("551 charts scored");

  return (
    <div className="embed-card">
      <div className="ledger-head">
        <Label info="Discord reads this off the page when somebody pastes your link. The picture and the line under your name are yours to set; your name and rating are always on it, because without them it is not your profile.">
          the card in Discord
        </Label>
      </div>

      <div className="embed-preview" aria-label="what the card looks like">
        {state.card.on && !failed ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={picture} alt="the picture above your card" onError={() => setFailed(true)} />
        ) : null}
        <div className="embed-body">
          <b className="embed-title">your name</b>
          <span className="embed-line">{bits.join(" · ")}</span>
          <span className="embed-btn">See the profile</span>
        </div>
      </div>
      {failed && <p className="hint">The picture could not be drawn just now. It will be there when the card is read.</p>}

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
          <ul className="share-toggles">
            {PICTURE.map((row) => (
              <li key={row.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={Boolean(state.card[row.key])}
                    disabled={busy}
                    onChange={(e) => onSave({ card: { [row.key]: e.target.checked } })}
                  />
                  <span>
                    <b>{row.label}</b>
                    <span className="dim">{row.note}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="embed-group">under your name</p>
      <ul className="share-toggles">
        {TEXT.map((row) => (
          <li key={row.key}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(state.embed[row.key])}
                disabled={busy}
                onChange={(e) => onSave({ embed: { [row.key]: e.target.checked } })}
              />
              <span>
                <b>{row.label}</b>
                <span className="dim">{row.note}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>

      <p className="hint">
        Discord holds on to a card for about half an hour after it first reads it, so a change shows up on the next link
        you post rather than on one already sent.
      </p>
    </div>
  );
}
