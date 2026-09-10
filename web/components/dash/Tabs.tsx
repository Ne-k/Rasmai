"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type RefreshStatus } from "./api";

export type Tab = "overview" | "picks" | "new" | "traits" | "best50" | "charts" | "recent" | "chart" | "areas" | "account";

// what to play, then how you play, then your scores, then the reference tabs
export const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "picks", label: "What to play" },
  { key: "new", label: "New charts" },
  { key: "traits", label: "Traits" },
  { key: "best50", label: "Best 50" },
  { key: "charts", label: "All charts" },
  { key: "recent", label: "Recent" },
  { key: "chart", label: "Look up" },
  { key: "areas", label: "Areas" },
  { key: "account", label: "Account" },
];

const STAGE_LABEL: Record<string, string> = {
  queued: "Waiting for a free slot",
  login: "Signing in to maimai DX NET",
  scores: "Reading score pages",
  recent: "Recent plays",
  extras: "Albums and events",
  plays: "Play counts",
  analysis: "Working out what to play",
  done: "Done",
  failed: "Failed",
};

/** The section strip. It scrolls sideways on a phone; the edges fade where there is more, and the chosen tab is kept in view. */
export function Tabs({ current, onPick }: { current: Tab; onPick: (t: Tab) => void }) {
  const strip = useRef<HTMLElement>(null);
  const [more, setMore] = useState("none");
  const measure = useCallback(() => {
    const el = strip.current;
    if (!el) return;
    const left = el.scrollLeft > 4;
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
    setMore(left && right ? "both" : left ? "left" : right ? "right" : "none");
  }, []);
  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);
  useEffect(() => {
    const el = strip.current?.querySelector<HTMLButtonElement>("button.on");
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [current]);
  return (
    <div className="tabs-wrap">
      <nav className="tabs" aria-label="Sections" ref={strip} data-more={more} onScroll={measure}>
        {TABS.map((t) => (
          <button key={t.key} type="button" className={t.key === current ? "on" : ""} aria-current={t.key === current ? "true" : undefined} onClick={() => onPick(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  );
}

export function RefreshBar({ status }: { status: RefreshStatus }) {
  const total = status.total ?? 0;
  const done = status.done ?? 0;
  const label = STAGE_LABEL[status.stage ?? ""] ?? status.stage ?? "";
  return (
    <div className="refresh-bar" role="status">
      <span className="lamp wait" />
      <span>
        Reading your scores from maimai · {status.detail || label}
        {total > 1 ? ` ${done}/${total}` : ""}
      </span>
    </div>
  );
}
