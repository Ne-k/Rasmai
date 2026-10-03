"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Support } from "@/components/Support";
import { ApiError, postJSON } from "./api";
import { Label } from "./bits";
import "./kamaitachi.css";

type Counts = { bests: number; plays: number; unmatched: number; seen: number };

// the same rule the bot applies, so an obvious typo never costs one of the five tries a quarter hour
const USERNAME = /^[A-Za-z0-9_-]{2,30}$/;

/** Moves scores to and from Kamaitachi: a file to upload there, and a profile's public scores to read in here. */
export function Kamaitachi() {
  const t = useTranslations("kamaitachi");
  const field = useId();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Counts | null>(null);
  const [error, setError] = useState("");
  // generic failures get the support line under them; the ones a person can fix themselves do not
  const [stuck, setStuck] = useState(false);

  const fail = (message: string, help = false) => {
    setError(message);
    setStuck(help);
  };
  const send = (event: React.FormEvent) => {
    event.preventDefault();
    const username = name.trim();
    setDone(null);
    fail("");
    if (!USERNAME.test(username)) return fail(t("badUsername"));
    setBusy(true);
    postJSON<Counts>("/api/me/kamaitachi/import", { username })
      .then((r) => {
        setDone(r);
        // new scores change every number on the dashboard, so it is read again, like after importing a Rasmai export
        if (r.bests || r.plays) setTimeout(() => window.location.reload(), 1500);
      })
      .catch((e: Error) => {
        const code = e instanceof ApiError ? e.code : "";
        if (code === "bad_username") fail(t("badUsername"));
        else if (code === "no_such_user") fail(t("noSuchUser"));
        else if (code === "rate_limited") fail(t("rateLimited"));
        else if (code === "kamaitachi") fail(t("unreachable"), true);
        else if (e instanceof ApiError && e.status === 401) fail("");
        else fail(e.message, true);
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="ledger kamai">
      <div className="ledger-head">
        <Label info={t("info")}>{t("title")}</Label>
      </div>

      <h3 className="kamai-sub">{t("toSub")}</h3>
      <div className="btn-row">
        <a className="button ghost" href="/api/me/kamaitachi" download>
          {t("download")}
        </a>
      </div>
      <p className="hint">{t("downloadHint")}</p>

      <h3 className="kamai-sub">{t("fromSub")}</h3>
      <form className="kamai-form" onSubmit={send} noValidate>
        <label htmlFor={field}>{t("username")}</label>
        <div className="kamai-row">
          <input
            id={field}
            type="text"
            name="kamaitachi-username"
            value={name}
            maxLength={30}
            disabled={busy}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            aria-describedby={`${field}-hint`}
            aria-invalid={error === t("badUsername") ? true : undefined}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="submit" className="button" disabled={busy || !name.trim()}>
            {busy ? t("importing") : t("import")}
          </button>
        </div>
      </form>
      <p className="hint" id={`${field}-hint`}>{t("importHint")}</p>

      <div className="kamai-result" aria-live="polite">
        {done && (done.seen === 0 ? (
          <p className="hint">{t("empty")}</p>
        ) : done.bests || done.plays ? (
          <p className="hint ok">{t("added", { bests: done.bests, plays: done.plays })}</p>
        ) : (
          <p className="hint ok">{t("nothingNew", { seen: done.seen })}</p>
        ))}
        {done && done.unmatched > 0 && <p className="hint">{t("unmatched", { n: done.unmatched })}</p>}
        {error && <p className="hint bad">{error}</p>}
        {error && stuck && <Support />}
      </div>
    </section>
  );
}
