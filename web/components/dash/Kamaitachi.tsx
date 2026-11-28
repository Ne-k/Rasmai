"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Support } from "@/components/Support";
import { ApiError, postJSON, type Overview } from "./api";
import { Label } from "./bits";
import "./kamaitachi.css";

const CONNECT = "/auth/kamaitachi/";

/** Connects Kamaitachi for an account with no maimai DX NET sign-in to read, or whose sign-in has expired:
 * its scores are what the account shows from then on. */
export function LinkKamaitachi() {
  const t = useTranslations("kamaitachi");
  return (
    <div className="kamai-link">
      <div className="btn-row">
        <a className="button" href={CONNECT}>
          {t("connect")}
        </a>
      </div>
      <p className="hint">{t("linkHint")}</p>
    </div>
  );
}

/** Moves scores to and from Kamaitachi: a file to upload there, and a connected account's scores to read in here.
 * A connected account is followed from then on: every refresh reads it again, until the person stops it. */
export function Kamaitachi({ me }: { me: Overview }) {
  const t = useTranslations("kamaitachi");
  const [following, setFollowing] = useState(me.kamaitachi ?? "");
  const [error, setError] = useState("");
  // a profile followed by its name, from before Kamaitachi's sign-in was used: read without a key until connected again
  const byName = Boolean(following) && !me.kamaitachiKeyed;
  const name = { name: following, b: (c: React.ReactNode) => <b>{c}</b> };

  const stop = () => {
    setError("");
    postJSON("/api/me/kamaitachi/unfollow")
      .then(() => setFollowing(""))
      // a signed-out answer is the page's to handle
      .catch((e: Error) => setError(e instanceof ApiError && e.status === 401 ? "" : e.message));
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
      {following && !byName && (
        <p className="kamai-state">
          <span>{t.rich("following", name)}</span>
          <span className="ok-badge">{t("linkedBadge")}</span>
        </p>
      )}
      {byName && (
        <p className="notice kamai-old">
          <span>{t.rich("byName", name)}</span>
        </p>
      )}
      <div className="btn-row">
        <a className={following && !byName ? "button ghost" : "button"} href={CONNECT}>
          {t(following ? "reconnect" : "connect")}
        </a>
        {/* only beside a maimai sign-in: with none, the profile is all the account has to read */}
        {following && me.maimai && (
          <button type="button" className="linkish" onClick={stop}>
            {t("stop")}
          </button>
        )}
      </div>
      {!byName && <p className="hint">{t(following ? "followingHint" : "connectHint")}</p>}

      <div className="kamai-result" aria-live="polite">
        {error && <p className="hint bad">{error}</p>}
        {error && <Support />}
      </div>
    </section>
  );
}
