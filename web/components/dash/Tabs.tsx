"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { type RefreshStatus } from "./api";

export type Tab = "overview" | "picks" | "new" | "traits" | "best50" | "charts" | "recent" | "chart" | "areas" | "account" | "admin";

// what to play, then how you play, then your scores, then the reference tabs; their names are in the translation files
const TABS: Tab[] = ["overview", "picks", "new", "traits", "best50", "charts", "recent", "chart", "areas", "account"];

// the developer tab is only ever added for the one account the internal API answers the developer route for
export function tabsFor(admin?: boolean): Tab[] {
  return admin ? [...TABS, "admin"] : TABS;
}

// the SWIPE hint is for somebody who has not swiped yet: once they have, on this device, it stays away
const SWIPED = "rasmai.swiped";
const NUDGED = "rasmai.nudged";

/** The section strip. It scrolls sideways on a phone; the edges fade where there is more, and the chosen tab is kept in view. */
export function Tabs({ current, onPick, admin }: { current: Tab; onPick: (t: Tab) => void; admin?: boolean }) {
  const t = useTranslations("dash");
  const shown = tabsFor(admin);
  const strip = useRef<HTMLElement>(null);
  const [more, setMore] = useState("none");
  const [swiped, setSwiped] = useState(false);
  const learn = useCallback(() => {
    setSwiped(true);
    try {
      localStorage.setItem(SWIPED, "1");
    } catch {
      // private window or blocked storage: the hint just comes back next visit
    }
  }, []);
  useEffect(() => {
    try {
      if (localStorage.getItem(SWIPED)) setSwiped(true);
    } catch {
      // nothing remembered
    }
  }, []);
  // once a session, on a phone, the strip leans toward the next tabs and settles back, so it shows it moves before anyone is told to
  useEffect(() => {
    const el = strip.current;
    if (!el || swiped || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !window.matchMedia("(max-width: 860px)").matches) return;
    try {
      if (sessionStorage.getItem(NUDGED)) return;
      sessionStorage.setItem(NUDGED, "1");
    } catch {
      return;
    }
    if (el.scrollWidth <= el.clientWidth + 8) return;
    const lean = setTimeout(() => el.scrollTo({ left: 52, behavior: "smooth" }), 700);
    const back = setTimeout(() => el.scrollTo({ left: 0, behavior: "smooth" }), 1300);
    return () => {
      clearTimeout(lean);
      clearTimeout(back);
    };
  }, [swiped]);
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
    el?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [current]);
  return (
    <div className="tabs-wrap" data-more={more} data-swiped={swiped ? "" : undefined}>
      <nav className="tabs" aria-label={t("sections")} ref={strip} data-more={more} onScroll={measure} onTouchMove={learn}>
        {shown.map((id) => (
          <button key={id} type="button" className={id === current ? "on" : ""} aria-current={id === current ? "true" : undefined} onClick={() => onPick(id)}>
            {t(`tabs.${id}`)}
          </button>
        ))}
      </nav>
      <span className="tabs-hint" aria-hidden="true">
        <span className="tabs-hint-label">SWIPE</span>
        <span className="tabs-hint-arrow"><i>›</i><i>›</i><i>›</i></span>
      </span>
    </div>
  );
}

export function RefreshBar({ status }: { status: RefreshStatus }) {
  const t = useTranslations("dash");
  const total = status.total ?? 0;
  const done = status.done ?? 0;
  const stage = status.stage ?? "";
  const label = stage && t.has(`stages.${stage}` as never) ? t(`stages.${stage}` as never) : stage;
  return (
    <div className="refresh-bar" role="status">
      <span className="lamp wait" />
      <span>
        {t("readingScores", { what: status.detail || label })}
        {total > 1 ? ` ${done}/${total}` : ""}
      </span>
    </div>
  );
}
