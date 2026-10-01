"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

type Servers = { maintenance: boolean; reachable: boolean; until: string | null; next: string | null; checkedAt: string | null };

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function inMinutes(iso: string, t: ReturnType<typeof useTranslations<"servers">>): string {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (Number.isNaN(minutes)) return "";
  if (minutes <= 1) return t("anyMinute");
  if (minutes < 90) return t("inMinutes", { n: minutes });
  return t("inHours", { n: Math.round(minutes / 60) });
}

/** A band across the top when maimai DX NET is down: the page keeps working from the last read, but nothing new can be read. */
export function ServersNotice() {
  const t = useTranslations("servers");
  const [state, setState] = useState<Servers | null>(null);
  useEffect(() => {
    let alive = true;
    const read = () =>
      fetch("/api/servers", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then((r) => (r.ok ? (r.json() as Promise<Servers>) : null))
        .then((s) => {
          if (alive && s) setState(s);
        })
        .catch(() => undefined);
    read();
    const timer = setInterval(read, 3 * 60 * 1000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  if (!state || (!state.maintenance && state.reachable)) return null;
  const back = state.maintenance && state.until ? t("back", { when: inMinutes(state.until, t), clock: clock(state.until) }) : "";
  return (
    <div className="notice" role="status">
      <span className="notice-lamp" aria-hidden="true" />
      <span>
        <b>{state.maintenance ? t("maintenance") : t("down")}</b>
        {back}
        {t("rest")}
      </span>
    </div>
  );
}
