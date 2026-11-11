"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { type RefreshStatus } from "./api";

export type Tab = "overview" | "picks" | "new" | "traits" | "best50" | "charts" | "recent" | "chart" | "areas" | "account" | "admin";

export type Group = "overview" | "play" | "scores" | "lookup" | "account" | "admin";

// the strip holds five places to go, each with the tabs that belong together under it: you, what to play, your scores, the
// reference tabs, your account. An address still names a tab, so every link made before the groups lands where it did
const GROUPS: [Group, Tab[]][] = [
  ["overview", ["overview", "traits"]],
  ["play", ["picks", "new"]],
  ["scores", ["best50", "charts", "recent"]],
  ["lookup", ["chart", "areas"]],
  ["account", ["account"]],
];

/** The groups an account sees, without the tabs that have nothing to show for it. The developer tab is only ever added for the
 * one account the internal API answers the developer route for. */
export function groupsFor(admin?: boolean, hidden: Tab[] = []): [Group, Tab[]][] {
  const groups = GROUPS.map(([group, tabs]): [Group, Tab[]] => [group, tabs.filter((tab) => !hidden.includes(tab))]).filter(([, tabs]) => tabs.length > 0);
  return admin ? [...groups, ["admin", ["admin"]]] : groups;
}

export function tabsFor(admin?: boolean): Tab[] {
  return groupsFor(admin).flatMap(([, tabs]) => tabs);
}

const NUDGED = "rasmai.nudged";

/** The section strip, and under it the tabs of the group that is open. The strip scrolls sideways if a phone is too narrow for it;
 * the edges fade where there is more, and the chosen group is kept in view. */
export function Tabs({ current, onPick, admin, hidden }: { current: Tab; onPick: (t: Tab) => void; admin?: boolean; hidden?: Tab[] }) {
  const t = useTranslations("dash");
  const groups = groupsFor(admin, hidden);
  const [group, inside] = groups.find(([, tabs]) => tabs.includes(current)) ?? groups[0];
  // the tab last open in each group, so coming back to a group returns to where the person was in it
  const last = useRef<Partial<Record<Group, Tab>>>({});
  useEffect(() => {
    last.current[group] = current;
  }, [group, current]);
  const enter = (id: Group, tabs: Tab[]) => {
    const kept = last.current[id];
    onPick(kept && tabs.includes(kept) ? kept : tabs[0]);
  };
  const strip = useRef<HTMLElement>(null);
  const [more, setMore] = useState("none");
  // the SWIPE hint says it in words and motion until the first swipe, then goes quiet; it never goes away while there are more tabs to reach
  const [swiped, setSwiped] = useState(false);
  const learn = useCallback(() => setSwiped(true), []);
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
    // one block, so where the strip sticks to the top of the screen the open group's tabs stay under it
    <div className="tabs-top">
      <div className="tabs-wrap" data-more={more} data-swiped={swiped ? "" : undefined}>
        <nav className="tabs" aria-label={t("sections")} ref={strip} data-more={more} onScroll={measure} onTouchMove={learn}>
          {groups.map(([id, tabs]) => (
            <button key={id} type="button" className={id === group ? "on" : ""} aria-current={id === group ? "true" : undefined} onClick={() => enter(id, tabs)}>
              {t(`groups.${id}`)}
            </button>
          ))}
        </nav>
        <span className="tabs-hint-left" aria-hidden="true">‹</span>
        <span className="tabs-hint" aria-hidden="true">
          <span className="tabs-hint-label">SWIPE</span>
          <span className="tabs-hint-arrow"><i>›</i><i>›</i><i>›</i></span>
        </span>
      </div>
      {inside.length > 1 && (
        <nav className="subtabs" aria-label={t(`groups.${group}`)}>
          {inside.map((id) => (
            <button key={id} type="button" className={id === current ? "on" : ""} aria-current={id === current ? "true" : undefined} onClick={() => onPick(id)}>
              {/* a tab named like its group is renamed under it: Overview holds Summary, Look up holds Charts */}
              {t.has(`subtabs.${id}` as never) ? t(`subtabs.${id}` as never) : t(`tabs.${id}`)}
            </button>
          ))}
        </nav>
      )}
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
