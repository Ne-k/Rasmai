"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A word with its meaning a hover away.
 *
 * Hover is not a thing on a phone, so a tap opens it too, and it is a button rather than a span so
 * a keyboard reaches it and a screen reader says there is something to open. The text is carried in
 * the markup rather than fetched, because there are a dozen of these on the page and none of them
 * change.
 */
export function Term({ word, means }: { word: string; means: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  return (
    <span className="term" ref={box}>
      <button
        type="button"
        className="term-word"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        // a tap fires the pointer events as well as the click, so hovering is left to real mice:
        // otherwise a phone opens it on touch and the click that follows closes it again
        onPointerEnter={(event) => event.pointerType === "mouse" && setOpen(true)}
        onPointerLeave={(event) => event.pointerType === "mouse" && setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        {word}
      </button>
      <span className={`term-pop${open ? " on" : ""}`} role="tooltip" aria-hidden={!open}>
        {means}
      </span>
    </span>
  );
}
