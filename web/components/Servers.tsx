"use client";

import { useEffect, useState } from "react";

type Servers = { maintenance: boolean; reachable: boolean; until: string | null; next: string | null; checkedAt: string | null };

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function inMinutes(iso: string): string {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (Number.isNaN(minutes)) return "";
  if (minutes <= 1) return "any minute now";
  if (minutes < 90) return `in ${minutes} min`;
  return `in ${Math.round(minutes / 60)} h`;
}

/** A band across the top when maimai DX NET is down: the page keeps working from the last read, but nothing new can be read. */
export function ServersNotice() {
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
  const back = state.maintenance && state.until ? ` Back ${inMinutes(state.until)}, at ${clock(state.until)} your time.` : "";
  return (
    <div className="notice" role="status">
      <span className="notice-lamp" aria-hidden="true" />
      <span>
        <b>{state.maintenance ? "maimai DX NET is in maintenance." : "maimai DX NET is not answering right now."}</b>
        {back} Everything here is from the last read. A new read, and linking an account, cannot happen until it is back.
      </span>
    </div>
  );
}
