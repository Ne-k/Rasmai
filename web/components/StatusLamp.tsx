"use client";

import { useEffect, useState } from "react";

type Reading = "checking" | "up" | "down";

const KEY = "rasmai-health";
const KEEP_MS = 60_000;

const WORDS: Record<Reading, string> = {
  checking: "Checking status",
  up: "Rasmai is up",
  down: "Rasmai is having trouble",
};

/** A lamp in the masthead: green when the bot answers, pink when it does not, grey until it is known.
 *  The answer is kept for a minute in the tab so moving between pages does not ask again.
 *  It links to the status page when there is one. */
export function StatusLamp() {
  const [reading, setReading] = useState<Reading>("checking");
  const [href, setHref] = useState("");

  useEffect(() => {
    try {
      const held = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
      if (held && Date.now() - held.at < KEEP_MS) {
        setReading(held.reading);
        setHref(held.href ?? "");
        return;
      }
    } catch {
      /* private mode: it asks every time */
    }
    let live = true;
    fetch("/api/health", { cache: "no-store" })
      .then((response) => response.json())
      .then((body) => {
        const next: Reading = body.bot ? "up" : "down";
        if (live) {
          setReading(next);
          setHref(String(body.statusUrl ?? ""));
        }
        try {
          sessionStorage.setItem(KEY, JSON.stringify({ reading: next, href: String(body.statusUrl ?? ""), at: Date.now() }));
        } catch {
          /* nothing to keep it in */
        }
      })
      .catch(() => {
        /* the visitor's own network failing says nothing about the bot: stay grey */
      });
    return () => {
      live = false;
    };
  }, []);

  const inside = (
    <>
      <span className={`status-lamp-dot ${reading}`} aria-hidden="true" /> status
    </>
  );
  return href ? (
    <a className="tag status-lamp" href={href} title={WORDS[reading]} aria-label={`${WORDS[reading]}. Open the status page`}>
      {inside}
    </a>
  ) : (
    <span className="tag status-lamp" title={WORDS[reading]} aria-label={WORDS[reading]}>
      {inside}
    </span>
  );
}
