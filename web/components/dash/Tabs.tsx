"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useM } from "@/components/I18n";
import { type RefreshStatus } from "./api";

export type Tab = "overview" | "picks" | "new" | "traits" | "best50" | "charts" | "recent" | "chart" | "areas" | "account" | "admin";

// what to play, then how you play, then your scores, then the reference tabs; their names are in the translation files
export const TABS: Tab[] = ["overview", "picks", "new", "traits", "best50", "charts", "recent", "chart", "areas", "account"];

// the developer tab is only ever added for the one account the internal API answers the developer route for
export function tabsFor(admin?: boolean): Tab[] {
  return admin ? [...TABS, "admin"] : TABS;
}

/** The section strip. It scrolls sideways on a phone; the edges fade where there is more, and the chosen tab is kept in view. */
export function Tabs({ current, onPick, admin }: { current: Tab; onPick: (t: Tab) => void; admin?: boolean }) {
  const m = useM();
  const shown = tabsFor(admin);
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
      <nav className="tabs" aria-label={m.dash.sections} ref={strip} data-more={more} onScroll={measure}>
        {shown.map((t) => (
          <button key={t} type="button" className={t === current ? "on" : ""} aria-current={t === current ? "true" : undefined} onClick={() => onPick(t)}>
            {m.dash.tabs[t]}
          </button>
        ))}
      </nav>
    </div>
  );
}

export function RefreshBar({ status }: { status: RefreshStatus }) {
  const m = useM();
  const total = status.total ?? 0;
  const done = status.done ?? 0;
  const label = m.dash.stages[status.stage ?? ""] ?? status.stage ?? "";
  return (
    <div className="refresh-bar" role="status">
      <span className="lamp wait" />
      <span>
        {m.dash.readingScores(status.detail || label)}
        {total > 1 ? ` ${done}/${total}` : ""}
      </span>
    </div>
  );
}
