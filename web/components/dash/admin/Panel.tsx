"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getJSON, postJSON } from "../api";
import { Empty, Label, num, when } from "../bits";
import { Activity, Composition, Facts, Gauge, Who, duration, size } from "./bits";
import { UserDetail } from "./UserDetail";
import type { AdminData, Detail } from "./types";

export function AdminPanel() {
  const [data, setData] = useState<AdminData | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Detail | null>(null);
  const [opening, setOpening] = useState("");
  const [asked, setAsked] = useState("");

  const openUser = (userId: string) => {
    setOpening(userId);
    getJSON<Detail>(`/api/me/admin?user=${encodeURIComponent(userId)}`)
      .then((d) => setOpen(d))
      .catch(() => undefined)
      .finally(() => setOpening(""));
  };

  // both chart databases refresh on their own, and neither had a way to say "now" short of a
  // restart. The bot refuses this to everyone but the one account, so nothing here checks.
  const update = (source: string) => {
    setAsked(source);
    postJSON("/api/me/admin/update", { source })
      .catch(() => undefined)
      .finally(() => {
        setAsked("");
        load();
      });
  };

  const load = useCallback(() => {
    getJSON<AdminData>("/api/me/admin")
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e: ApiError) => setError(e.status === 404 ? "no such page" : e.message));
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  // the route answers 404 to everyone but the one account, so the page says the same rather than hinting
  if (error) {
    return (
      <div className="gate">
        <h1>
          Nothing <em>here</em>.
        </h1>
        <p className="lede">This page does not exist.</p>
        <a className="button" href="/me/">
          back to your dashboard →
        </a>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="gate">
        <p className="hint">Loading…</p>
      </div>
    );
  }

  const live = data.live;
  const linked = data.accounts.reduce((sum, a) => sum + a.count, 0);
  const n = (key: string) => Number(live[key] ?? 0);
  const month = data.activity.reduce((sum, d) => sum + d.plays, 0);
  const attention = data.expired.length + data.failingReads.length;
  return (
    <>
      <main className="panel admin">
        <section className="ident">
          <div className="ident-who">
            <div className="label">developer</div>
            <h1>Rasmai</h1>
            <div className="ident-sub mono">
              {live.ready ? "connected" : "not ready"} · up {duration(n("uptimeSeconds"))} · read {when(data.generatedAt)}
            </div>
          </div>
          <div className="readout big">
            <span className="lbl">accounts</span>
            <span className="val">{num(linked)}</span>
            <span className="lbl">plays stored</span>
            <span className="val">{num(data.store.plays)}</span>
            <span className="lbl">database</span>
            <span className="val">{size(data.store.bytes)}</span>
          </div>
        </section>

        <section className="ledger">
          <div className="ledger-head">
            <Label>plays recorded · last 30 days</Label>
            <span className="mono hint">{num(month)} plays</span>
          </div>
          <Activity days={data.activity} />
        </section>

        <div className="two-up">
          <section className="ledger">
            <div className="ledger-head">
              <Label>load right now</Label>
              <span className="mono hint">{num(n("latencyMs"))} ms to the gateway</span>
            </div>
            <Gauge label="score reads in flight" used={n("scrapesMax") - n("scrapesFree")} total={n("scrapesMax")} />
            <Gauge label="image renders in flight" used={n("rendersMax") - n("rendersFree")} total={n("rendersMax")} />
            <Gauge label="analyses held in memory" used={n("analysesCached")} total={Math.max(n("analysesCached"), 20)} />
            <Facts
              rows={[
                ["servers", `${num(n("guilds"))} over ${num(n("shards") || 1)} shard${n("shards") === 1 ? "" : "s"}`],
                ["charts indexed", num(n("chartsIndexed"))],
                ["analysis lifetime", `${num(n("analysisTtlMinutes"))} min`],
                ["site reads running", num(n("refreshesRunning"))],
              ]}
            />
          </section>

          <section className="ledger">
            <div className="ledger-head">
              <Label>what is stored</Label>
              <span className="mono hint">
                {data.store.oldestPlay ? `since ${data.store.oldestPlay.slice(0, 10)}` : "nothing yet"}
              </span>
            </div>
            <Facts
              rows={[
                ["linked accounts", data.accounts.map((a) => `${num(a.count)} ${a.region.toUpperCase()}`).join(" · ") || "—"],
                ["plays", num(data.store.plays)],
                ["judgement pages", num(data.store.judgements)],
                ["rating points", num(data.store.ratingPoints)],
                ["play counts", num(data.store.playCounts)],
                ["free space in the file", size(data.store.freeBytes)],
                ["write-ahead log", data.store.walBytes ? size(data.store.walBytes) : "checkpointed"],
              ]}
            />
          </section>
        </div>

        <section className="ledger">
          <div className="ledger-head">
            <Label>what fills the database · {size(data.store.bytes)}</Label>
            <span className="mono hint">{size(data.store.freeBytes)} free</span>
          </div>
          <Composition tables={data.store.tables} total={data.store.bytes} />
        </section>

        <div className="two-up">
          <section className="ledger">
            <div className="ledger-head">
              <Label>busiest accounts</Label>
              <span className="mono hint">by plays recorded</span>
            </div>
            {data.busiest.length === 0 ? (
              <Empty>No plays recorded yet.</Empty>
            ) : (
              <ul className="people">
                {data.busiest.map((b) => (
                  <li key={b.userId}>
                    <Who person={b} id={b.userId} />
                    <span className="mono">{num(b.plays)} plays</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="ledger">
            <div className="ledger-head">
              <Label>needs attention</Label>
              <span className={`mono hint${attention ? " bad" : ""}`}>{attention ? `${attention} to look at` : "all clear"}</span>
            </div>
            {attention === 0 ? (
              <Empty>Every linked session is answering and the daily reads are landing.</Empty>
            ) : (
              <ul className="people">
                {data.expired.map((e) => (
                  <li key={`x${e.userId}`}>
                    <Who person={e} id={e.userId} />
                    <span className="mono bad">expired {when(e.since)}</span>
                  </li>
                ))}
                {data.failingReads.map((r) => (
                  <li key={`r${r.userId}`}>
                    <Who person={r} id={r.userId} />
                    <span className="mono bad">{r.error}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <section className="ledger">
          <div className="ledger-head">
            <Label>every server · {data.guilds_list?.length ?? 0}</Label>
            <span className="mono hint">
              {num((data.guilds_list ?? []).reduce((sum, g) => sum + g.members, 0))} members in reach · biggest first
            </span>
          </div>
          {!data.guilds_list?.length ? (
            <Empty>The bot is in no servers, or has not finished connecting.</Empty>
          ) : (
            <div className="scroll">
              <table className="tbl compact keep admin-users">
                <thead>
                  <tr>
                    <th>Server</th>
                    <th className="c-num">Members</th>
                    <th>Owner</th>
                    <th className="c-num">Added</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {data.guilds_list.map((g) => (
                    <tr key={g.id}>
                      <td>
                        <span className="who">
                          {g.icon ? <img src={g.icon} alt="" width={26} height={26} loading="lazy" /> : <span className="who-blank" />}
                          <span className="who-text">
                            <b>{g.name}</b>
                            <span className="mono dim">{g.id}</span>
                          </span>
                        </span>
                      </td>
                      <td className="c-num mono strong">{num(g.members)}</td>
                      <td className="mono">{g.owner || g.ownerId || "—"}</td>
                      <td className="c-num mono dim">{g.joinedAt ? when(g.joinedAt) : "—"}</td>
                      <td className="mono">
                        {g.configured ? <span className="dim">set up</span> : <span className="dim">defaults</span>}
                        <span className="dim"> · shard {g.shard}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="ledger">
          <div className="ledger-head">
            <Label>every account · {data.accounts_list?.length ?? 0}</Label>
            <span className="mono hint">most recently active first</span>
          </div>
          {!data.accounts_list?.length ? (
            <Empty>Nobody has linked an account yet.</Empty>
          ) : (
            <div className="scroll">
              <table className="tbl compact keep admin-users">
                <thead>
                  <tr>
                    <th>Who</th>
                    <th>Player</th>
                    <th className="c-num">Rating</th>
                    <th className="c-num">Plays</th>
                    <th className="c-num">Last seen</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {data.accounts_list.map((a) => (
                    <tr key={a.userId} className="clickable" onClick={() => openUser(a.userId)}>
                      <td>
                        <Who person={a} id={a.userId} />
                      </td>
                      <td className="mono">{a.player || "—"}</td>
                      <td className="c-num mono strong">{num(a.rating)}</td>
                      <td className="c-num mono">{num(a.plays)}</td>
                      <td className="c-num mono dim">{a.seenAt ? when(a.seenAt) : "never"}</td>
                      <td className="mono">
                        {a.expired ? <span className="bad">needs relinking</span> : <span className="dim">ok</span>}
                        {a.shared ? <span className="dim"> · shared</span> : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {opening && <p className="hint">Opening {opening}…</p>}
        </section>

        {open && <UserDetail detail={open} onClose={() => setOpen(null)} />}

        <section className="ledger">
          <div className="ledger-head">
            <Label>source caches</Label>
            <span className="mono hint">shared by everyone, and the same size whoever is linked</span>
          </div>
          {data.sources.length === 0 ? (
            <Empty>Nothing cached yet.</Empty>
          ) : (
            <div className="scroll">
              <table className="tbl compact keep">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th className="c-num">Size</th>
                    <th className="c-num">Last checked</th>
                    <th>Conditional</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sources.map((s) => (
                    <tr key={s.source}>
                      <td className="mono strong">{s.source}</td>
                      <td className="c-num mono">{size(s.bytes)}</td>
                      <td className="c-num mono dim">{s.checkedAt ? when(s.checkedAt) : "never"}</td>
                      <td className="mono dim">{s.etag ? "etag" : "full fetch"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="row-between">
            <span className="mono hint">update the chart databases by hand</span>
            <span className="seg">
              {[["simai", "simai charts"], ["otoge", "otoge-db"]].map(([key, label]) => {
                const state = data.updates?.[key];
                const running = Boolean(state?.running) || asked === key;
                return (
                  <button key={key} type="button" onClick={() => update(key)} disabled={running}>
                    {running ? `updating ${label}...` : `update ${label}`}
                  </button>
                );
              })}
            </span>
          </div>
          {["simai", "otoge"].map((key) => {
            const state = data.updates?.[key];
            if (!state || state.running || !state.said) return null;
            return (
              <p key={key} className={`hint ${state.ok ? "ok" : "bad"}`}>
                {key}: {state.said}
                {state.seconds ? ` · ${state.seconds}s` : ""}
                {state.at ? ` · ${when(state.at)}` : ""}
              </p>
            );
          })}
          {data.simai && data.simai.read + data.simai.waiting > 0 && (
            <p className="hint">
              Charts read note by note: <b>{data.simai.read.toLocaleString()}</b> trusted
              {data.simai.refused > 0 && <> · {data.simai.refused.toLocaleString()} read differently from maiノーツ and dropped</>}
              {data.simai.waiting > 0 ? <> · {data.simai.waiting.toLocaleString()} still to read</> : <> · nothing left to read</>}
              {data.simai.sheets ? <> · {data.simai.sheets.toLocaleString()} charts kept, {size(data.simai.sheetBytes ?? 0)}</> : null}
            </p>
          )}
        </section>

        <section className="ledger">
          <Label info="What the people running a beta feature made of it, against having it off. One verdict each, replaced whenever they change their mind.">
            beta feedback
          </Label>
          {Object.entries(data.betaTally ?? {}).map(([feature, counts]) => {
            const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
            return (
              <p key={feature} className="hint">
                <b>{feature}</b>: {total} said · better <b className="ok">{counts.better ?? 0}</b> · no difference{" "}
                <b>{counts.same ?? 0}</b> · worse <b className="bad">{counts.worse ?? 0}</b>
              </p>
            );
          })}
          {!(data.betaFeedback ?? []).length && <Empty>Nobody has said anything yet.</Empty>}
          <ul className="beta-said">
            {(data.betaFeedback ?? []).map((f) => (
              <li key={`${f.userId}-${f.feature}`}>
                <Who person={f} id={f.userId} />
                <span className="mono">{f.feature}</span>
                <span className={`mono ${f.verdict === "better" ? "ok" : f.verdict === "worse" ? "bad" : ""}`}>
                  {f.verdict}
                </span>
                <span className="dim">{f.said}</span>
                <span className="mono dim">{when(f.saidAt)}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}

/** One account in full, as a sheet over the page. Nothing here includes the stored maimai session. */
