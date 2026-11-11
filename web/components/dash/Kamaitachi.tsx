"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Support } from "@/components/Support";
import { ApiError, postJSON, type Overview } from "./api";
import { Label } from "./bits";
import "./kamaitachi.css";

type Counts = { bests: number; plays: number; unmatched: number; seen: number };

// the same rule the bot applies, so an obvious typo never costs one of the five tries a quarter hour
const USERNAME = /^[A-Za-z0-9_-]{2,30}$/;

/** What to tell the person after a read of Kamaitachi failed, and whether the support line belongs under it; "" for a signed-out answer, which the page handles. */
function problem(e: Error, t: ReturnType<typeof useTranslations>): [string, boolean] {
  const code = e instanceof ApiError ? e.code : "";
  if (code === "bad_username") return [t("badUsername"), false];
  if (code === "no_such_user") return [t("noSuchUser"), false];
  if (code === "rate_limited") return [t("rateLimited"), false];
  if (code === "kamaitachi") return [t("unreachable"), true];
  if (e instanceof ApiError && e.status === 401) return ["", false];
  return [e.message, true];
}

/** The username field with its button beside it. */
function UsernameRow({ field, name, setName, busy, invalid, go, going, onSubmit }: {
  field: string; name: string; setName: (name: string) => void; busy: boolean; invalid: boolean; go: string; going: string;
  onSubmit: (event: React.FormEvent) => void;
}) {
  const t = useTranslations("kamaitachi");
  return (
    <form className="kamai-form" onSubmit={onSubmit} noValidate>
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
          aria-invalid={invalid ? true : undefined}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" className="button" disabled={busy || !name.trim()}>
          {busy ? going : go}
        </button>
      </div>
    </form>
  );
}

/** Follows a Kamaitachi profile by its username, for an account with no maimai DX NET sign-in to read, or whose sign-in has expired:
 * the profile's public scores are what the account shows from then on. */
export function LinkKamaitachi() {
  const t = useTranslations("kamaitachi");
  const field = useId();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stuck, setStuck] = useState(false);
  const send = (event: React.FormEvent) => {
    event.preventDefault();
    const username = name.trim();
    setError("");
    setStuck(false);
    if (!USERNAME.test(username)) return setError(t("badUsername"));
    setBusy(true);
    postJSON("/api/me/kamaitachi/import", { username })
      // the dashboard is read again: it is a linked account's now
      .then(() => window.location.reload())
      .catch((e: Error) => {
        const [text, help] = problem(e, t);
        setError(text);
        setStuck(help);
        setBusy(false);
      });
  };
  return (
    <div className="kamai-link">
      <UsernameRow field={field} name={name} setName={setName} busy={busy} invalid={error === t("badUsername")} go={t("link")} going={t("linking")} onSubmit={send} />
      <p className="hint" id={`${field}-hint`}>{t("linkHint")}</p>
      <div className="kamai-result" aria-live="polite">
        {error && <p className="hint bad">{error}</p>}
        {error && stuck && <Support />}
      </div>
    </div>
  );
}

/** Moves scores to and from Kamaitachi: a file to upload there, and a profile's public scores to read in here.
 * A profile read in is followed from then on: every refresh reads it again, until the person stops it. */
export function Kamaitachi({ me }: { me: Overview }) {
  const t = useTranslations("kamaitachi");
  const field = useId();
  const [name, setName] = useState(me.kamaitachi ?? "");
  const [following, setFollowing] = useState(me.kamaitachi ?? "");
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
        setFollowing(username);
        // new scores change every number on the dashboard, so it is read again, like after importing a Rasmai export
        if (r.bests || r.plays) setTimeout(() => window.location.reload(), 1500);
      })
      .catch((e: Error) => fail(...problem(e, t)))
      .finally(() => setBusy(false));
  };
  const stop = () => {
    fail("");
    postJSON("/api/me/kamaitachi/unfollow")
      .then(() => setFollowing(""))
      .catch((e: Error) => fail(...problem(e, t)));
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
      <UsernameRow field={field} name={name} setName={setName} busy={busy} invalid={error === t("badUsername")} go={t("import")} going={t("importing")} onSubmit={send} />
      <p className="hint" id={`${field}-hint`}>{t("importHint")}</p>
      {following && (
        <p className="hint">
          {t.rich("following", { name: following, b: (c) => <b>{c}</b> })}
          {/* only beside a maimai sign-in: with none, the profile is all the account has to read */}
          {me.maimai && (
            <>
              {" "}
              <button type="button" className="linkish" onClick={stop}>
                {t("stop")}
              </button>
            </>
          )}
        </p>
      )}

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
