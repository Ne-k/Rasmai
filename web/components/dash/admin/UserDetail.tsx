"use client";

import { useEffect } from "react";
import { Label, num, when } from "../bits";
import { Facts, Who } from "./bits";
import type { Detail } from "./types";

export function UserDetail({ detail, onClose }: { detail: Detail; onClose: () => void }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  const settings = Object.entries(detail.settings ?? {});
  const peak = Math.max(1, ...detail.activity.map((d) => d.plays));
  return (
    <div className="sheet-back" role="dialog" aria-modal="true" aria-label={`${detail.player || detail.userId} in full`} onClick={onClose}>
      <div className="sheet-card" onClick={(e) => e.stopPropagation()}>
        <div className="ledger-head">
          <Label>account</Label>
          <button type="button" className="linkish" onClick={onClose}>
            close
          </button>
        </div>
        <section className="ident">
          <div className="ident-who">
            <Who person={detail} id={detail.userId} />
            <h1>{detail.player || "not read yet"}</h1>
            <div className="ident-sub mono">
              {[detail.dan, detail.title].filter(Boolean).join(" · ") || "no title"} · {detail.region.toUpperCase()}
            </div>
          </div>
          <div className="readout big">
            <span className="lbl">rating</span>
            <span className="val">{num(detail.rating)}</span>
            <span className="lbl">charts</span>
            <span className="val">{num(detail.charts)}</span>
          </div>
        </section>

        {detail.expired && <p className="hint bad">Session expired {when(detail.expired)}; reads are stopped until they run /login.</p>}

        <div className="two-up">
          <section className="ledger">
            <div className="ledger-head">
              <Label>when</Label>
            </div>
            <Facts
              rows={[
                ["last used the app", detail.seenAt ? when(detail.seenAt) : "never"],
                ["last score read", when(detail.readAt)],
                ["linked", when(detail.linkedAt)],
                ["first play stored", String(detail.counts.firstPlay ?? "—").slice(0, 10)],
                ["latest play stored", String(detail.counts.lastPlay ?? "—").slice(0, 10)],
                ["daily read", detail.quietRead.error ? <span className="bad">{detail.quietRead.error}</span> : detail.quietRead.readAt ? `${when(detail.quietRead.readAt)} · +${num(detail.quietRead.added)}` : "never run"],
              ]}
            />
          </section>
          <section className="ledger">
            <div className="ledger-head">
              <Label>what is stored</Label>
            </div>
            <Facts
              rows={[
                ["plays", num(Number(detail.counts.plays ?? 0))],
                ["judgement pages", num(Number(detail.counts.judgements ?? 0))],
                ["rating points", num(Number(detail.counts.ratingPoints ?? 0))],
                ["play counts", num(Number(detail.counts.playCounts ?? 0))],
                ["area readings", num(Number(detail.counts.areaReadings ?? 0))],
                ["plays on the cabinet", num(detail.totalPlayCount)],
                ["public profile", detail.shared ? "shared" : "private"],
              ]}
            />
          </section>
        </div>

        {detail.activity.length > 0 && (
          <section className="ledger">
            <div className="ledger-head">
              <Label>their plays · last 30 days with any</Label>
              <span className="mono hint">peak {num(peak)} in a day</span>
            </div>
            <div className="admin-bars">
              {detail.activity.map((d) => (
                <span key={d.day} className="admin-bar" title={`${d.day}: ${d.plays} plays`}>
                  <span style={{ height: `${Math.max(3, (100 * d.plays) / peak)}%` }} />
                </span>
              ))}
            </div>
          </section>
        )}

        <section className="ledger">
          <div className="ledger-head">
            <Label>their settings</Label>
          </div>
          <Facts rows={settings.map(([key, value]) => [key.replace(/_/g, " "), String(value)])} />
        </section>
      </div>
    </div>
  );
}
