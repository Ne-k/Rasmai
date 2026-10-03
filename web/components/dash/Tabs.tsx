"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { type RefreshStatus } from "./api";

export type Tab = "overview" | "picks" | "players" | "new" | "traits" | "best50" | "charts" | "recent" | "chart" | "areas" | "account" | "admin";

// what to play, then how you play, then your scores, then the reference tabs; their names are in the translation files
const TABS: Tab[] = ["overview", "picks", "players", "new", "traits", "best50", "charts", "recent", "chart", "areas", "account"];

// the developer tab is only ever added for the one account the internal API answers the developer route for;
// the players tab only while one of the two beta features that fill it is on
export function tabsFor(admin?: boolean, players?: boolean): Tab[] {
  const tabs = TABS.filter((t) => t !== "players" || players);
  return admin ? [...tabs, "admin"] : tabs;
}

/** The section strip. It scrolls sideways on a phone; the edges fade where there is more, and the chosen tab is kept in view. */
export function Tabs({ current, onPick, admin, players }: { current: Tab; onPick: (t: Tab) => void; admin?: boolean; players?: boolean }) {
  const t = useTranslations("dash");
  const shown = tabsFor(admin, players);
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
      <nav className="tabs" aria-label={t("sections")} ref={strip} data-more={more} onScroll={measure}>
        {shown.map((id) => (
          <button key={id} type="button" className={id === current ? "on" : ""} aria-current={id === current ? "true" : undefined} onClick={() => onPick(id)}>
            {t(`tabs.${id}`)}
          </button>
        ))}
      </nav>
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
