"use client";

import { useRef, useState } from "react";
import { InstallHint } from "@/components/Pwa";
import { useTranslations } from "next-intl";
import { postJSON, type Overview, type RefreshStatus } from "./api";
import { Ago, Label, when } from "./bits";
import { Beta } from "./Beta";
import { Sharing } from "./Sharing";

export function Account({ me, refresh, onRefresh }: { me: Overview; refresh: RefreshStatus | null; onRefresh: (s: RefreshStatus) => void }) {
  const t = useTranslations("accountTab");
  const common = useTranslations("common");
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
        setNote(t("imported", { plays: r.plays, bests: r.bests, points: r.ratingPoints, counts: r.playCounts }));
        setTimeout(() => window.location.reload(), 1500);
      })
      .catch((e: Error) => setNote(e instanceof SyntaxError ? t("notJson") : e.message))
      .finally(() => {
        setBusy(false);
        if (picker.current) picker.current.value = "";
      });
  };
  const s = me.settings ?? {};
  const label = (v: unknown, map: "layouts" | "challenges" | "any") => (t.has(`${map}.${String(v)}` as never) ? t(`${map}.${String(v)}` as never) : String(v));
  return (
    <div className="two-up">
      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("accountInfo")}>{t("account")}</Label>
        </div>
        <dl className="facts">
          <dt>{t("player")}</dt>
          <dd>{me.profile?.name}</dd>
          <dt>{t("region")}</dt>
          <dd className="mono">{me.region?.toUpperCase()}</dd>
          <dt>{t("lastRead")}</dt>
          <dd className="mono">{when(me.profile?.updatedAt)}</dd>
          <dt>{t("historyPoints")}</dt>
          <dd className="mono">{me.history?.length ?? 0}</dd>
        </dl>
        <div className="btn-row">
          <button type="button" className="button" onClick={start} disabled={busy || Boolean(refresh?.running)}>
            {refresh?.running ? t("refreshing") : t("refresh")}
          </button>
          <a className="button ghost" href="/api/me/export">
            {t("download")}
          </a>
          <button type="button" className="button ghost" onClick={() => picker.current?.click()} disabled={busy}>
            {t("import")}
          </button>
          <input ref={picker} type="file" accept="application/json,.json" hidden onChange={(e) => importFile(e.target.files?.[0])} />
        </div>
        {refresh?.stage === "failed" && <p className="hint">{t("failed", { why: refresh.error ?? "" })}</p>}
        {refresh?.stage === "done" && !refresh.running && (
          <p className="hint ok">
            {t("refreshed")}<Ago iso={refresh.finishedAt} />{common("period")}
          </p>
        )}
        {note && <p className="hint">{note}</p>}
        <p className="hint">{t("takes")}</p>
        <p className="hint">{t("importHint")}</p>
        <InstallHint />
      </section>
      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("settingsInfo")}>{t("settings")}</Label>
        </div>
        <dl className="facts">
          <dt>{t("layout")}</dt>
          <dd>{label(s.layout, "layouts")}</dd>
          <dt>{t("targets")}</dt>
          <dd>{label(s.challenge, "challenges")}</dd>
          <dt>{t("newDifficulty")}</dt>
          <dd>{label(s.new_difficulty, "any")}</dd>
          <dt>{t("compare")}</dt>
          <dd>{s.compare ? t("on") : t("off")}</dd>
          <dt>{t("leaderboard")}</dt>
          <dd>{s.leaderboard ? t("on") : t("off")}</dd>
          <dt>{t("history")}</dt>
          <dd>{s.history ? t("on") : t("off")}</dd>
          <dt>{t("notify")}</dt>
          <dd>{s.notify ? t("on") : t("off")}</dd>
        </dl>
        <p className="hint">{t.rich("change", { code: (c) => <code>{c}</code> })}</p>
      </section>

      {me.sharing && <Sharing state={sharing} onChange={setSharing} />}

      {beta.features.length > 0 && <Beta state={beta} onChange={setBeta} />}

      <section className="ledger">
        <div className="ledger-head">
          <Label>{t("unlink")}</Label>
        </div>
        <p className="hint">{t("unlinkHint")}</p>
        {confirm ? (
          <div className="btn-row">
            <button type="button" className="button pink" onClick={unlink} disabled={busy}>
              {t("unlinkYes")}
            </button>
            <button type="button" className="button ghost" onClick={() => setConfirm(false)}>
              {t("keep")}
            </button>
          </div>
        ) : (
          <button type="button" className="button ghost" onClick={() => setConfirm(true)}>
            {t("unlinkAsk")}
          </button>
        )}
      </section>
    </div>
  );
}
