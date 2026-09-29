"use client";

import { useRef, useState } from "react";
import { InstallHint } from "@/components/Pwa";
import { postJSON, type Overview, type RefreshStatus } from "./api";
import { Ago, Label, when } from "./bits";
import { Beta } from "./Beta";
import { Sharing } from "./Sharing";

export function Account({ me, refresh, onRefresh }: { me: Overview; refresh: RefreshStatus | null; onRefresh: (s: RefreshStatus) => void }) {
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState("");
  // the same shape the bot sends, for the moment before it has said anything
  const [sharing, setSharing] = useState(me.sharing ?? {
    on: false, url: "",
    sections: { best50: true, traits: false, recent: false, areas: false },
    card: { on: true, chart: true, gain: true, charts: true, plays: false },
    embed: { region: true, charts: true },
    colour: "#ff3d8f", colours: ["#ff3d8f"],
    visual: "curve", visuals: [{ key: "curve", needs: "", ready: true }],
  });
  const [beta, setBeta] = useState(me.beta ?? { on: {}, features: [] });
  const start = () => {
    setBusy(true);
    postJSON<RefreshStatus>("/api/me/refresh")
      .then((s) => onRefresh(s))
      .catch((e: Error) => setNote(e.message))
      .finally(() => setBusy(false));
  };
  const unlink = () => {
    setBusy(true);
    postJSON("/api/me/unlink")
      .then(() => window.location.reload())
      .catch((e: Error) => setNote(e.message))
      .finally(() => setBusy(false));
  };
  const picker = useRef<HTMLInputElement>(null);
  const importFile = (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    file
      .text()
      .then((text) => postJSON<{ bests: number; plays: number; ratingPoints: number; playCounts: number }>("/api/me/import", JSON.parse(text)))
      .then((r) => {
        setNote(`Imported ${r.plays} plays, ${r.bests} bests, ${r.ratingPoints} rating points and ${r.playCounts} play counts. Reloading…`);
        setTimeout(() => window.location.reload(), 1500);
      })
      .catch((e: Error) => setNote(e instanceof SyntaxError ? "That file isn't JSON." : e.message))
      .finally(() => {
        setBusy(false);
        if (picker.current) picker.current.value = "";
      });
  };
  const s = me.settings ?? {};
  const label = (v: unknown, map: Record<string, string>) => map[String(v)] ?? String(v);
  return (
    <div className="two-up">
      <section className="ledger">
        <div className="ledger-head">
          <Label info="The maimai DX NET account linked to your Discord. History points are the saved ratings behind the graph on Overview.">maimai account</Label>
        </div>
        <dl className="facts">
          <dt>player</dt>
          <dd>{me.profile?.name}</dd>
          <dt>region</dt>
          <dd className="mono">{me.region?.toUpperCase()}</dd>
          <dt>last read</dt>
          <dd className="mono">{when(me.profile?.updatedAt)}</dd>
          <dt>history points</dt>
          <dd className="mono">{me.history?.length ?? 0}</dd>
        </dl>
        <div className="btn-row">
          <button type="button" className="button" onClick={start} disabled={busy || Boolean(refresh?.running)}>
            {refresh?.running ? "refreshing…" : "refresh scores"}
          </button>
          <a className="button ghost" href="/api/me/export">
            download JSON
          </a>
          <button type="button" className="button ghost" onClick={() => picker.current?.click()} disabled={busy}>
            import JSON
          </button>
          <input ref={picker} type="file" accept="application/json,.json" hidden onChange={(e) => importFile(e.target.files?.[0])} />
        </div>
        {refresh?.stage === "failed" && <p className="hint">Refresh failed: {refresh.error}</p>}
        {refresh?.stage === "done" && !refresh.running && (
          <p className="hint ok">
            Refreshed <Ago iso={refresh.finishedAt} />.
          </p>
        )}
        {note && <p className="hint">{note}</p>}
        <p className="hint">Takes about a minute. It&apos;s the same refresh the Discord commands do, and your picks update after.</p>
        <p className="hint">
          You can import an export back in. It won&apos;t overwrite anything. Import your oldest file first so each best keeps the date you set it.
        </p>
        <InstallHint />
      </section>
      <section className="ledger">
        <div className="ledger-head">
          <Label info="Your defaults for the Discord commands.">bot settings</Label>
        </div>
        <dl className="facts">
          <dt>default layout</dt>
          <dd>{label(s.layout, { both: "image and text", embed: "text only", image: "image only" })}</dd>
          <dt>default targets</dt>
          <dd>{label(s.challenge, { easy: "easier", balanced: "balanced", hard: "challenging", extreme: "long shots" })}</dd>
          <dt>default /new difficulty</dt>
          <dd>{label(s.new_difficulty, { any: "any" })}</dd>
          <dt>open to /compare</dt>
          <dd>{s.compare ? "on" : "off"}</dd>
          <dt>server leaderboards</dt>
          <dd>{s.leaderboard ? "on" : "off"}</dd>
          <dt>daily history read</dt>
          <dd>{s.history ? "on" : "off"}</dd>
          <dt>daily note by DM</dt>
          <dd>{s.notify ? "on" : "off"}</dd>
        </dl>
        <p className="hint">
          Change these with <code>/settings</code> in Discord.
        </p>
        </section>

      {me.sharing && <Sharing state={sharing} onChange={setSharing} />}

      {beta.features.length > 0 && <Beta state={beta} onChange={setBeta} />}

      <section className="ledger">
        <div className="ledger-head">
          <Label>unlink</Label>
        </div>
        <p className="hint">Deletes your maimai session, scores, history and play counts. You stay signed in with Discord here.</p>
        {confirm ? (
          <div className="btn-row">
            <button type="button" className="button pink" onClick={unlink} disabled={busy}>
              yes, unlink and delete
            </button>
            <button type="button" className="button ghost" onClick={() => setConfirm(false)}>
              keep it
            </button>
          </div>
        ) : (
          <button type="button" className="button ghost" onClick={() => setConfirm(true)}>
            unlink maimai account…
          </button>
        )}
      </section>
    </div>
  );
}
