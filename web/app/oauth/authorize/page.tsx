"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { useTranslations } from "next-intl";

type Begin =
  | { ok: true; ticket: string; app: { name: string; by: string; website: string; privacy: string; verified: boolean; icon: string }; redirectHost: string; reviews: boolean; for?: string; cancel: string }
  | { ok: false; error?: string; description?: string; redirect?: string };

// an app's developer typed these addresses: only an http(s) one is ever made a link
const web = (url?: string) => (url && /^https?:\/\//i.test(url) ? url : "");

// Where an app sends a player to ask for their maimai sign-in (OAuth's authorize step). The page only names the app and
// carries the ticket: the Aime sign-in helper marks <html> when it is installed, opens its own approval window on a real
// press of the button, and sends the tab on to the app itself. Nothing of the player's passes through this page.
export default function AuthorizePage() {
  const t = useTranslations("flow");
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{t("loading")}</p></div>}>
      <Authorize />
    </Suspense>
  );
}

function Authorize() {
  const t = useTranslations("oauth");
  const flow = useTranslations("flow");
  const query = useSearchParams().toString();
  const [begin, setBegin] = useState<Begin | null>(null);
  const [helper, setHelper] = useState(false);
  const [opened, setOpened] = useState(false);

  useEffect(() => {
    fetch(`/api/oauth/begin?${query}`)
      .then(async (response) => setBegin((await response.json()) as Begin))
      .catch(() => setBegin({ ok: false }));
  }, [query]);

  useEffect(() => {
    const found = () => setHelper(document.documentElement.hasAttribute("data-aime-helper"));
    const waiting = () => setOpened(true);
    found();
    document.addEventListener("aime-helper", found);
    document.addEventListener("aime-opened", waiting);
    return () => {
      document.removeEventListener("aime-helper", found);
      document.removeEventListener("aime-opened", waiting);
    };
  }, []);

  const shell = (children: React.ReactNode) => (
    <Shell tag="authorize" lit={opened ? 2 : 1} steps={[t("steps.check"), t("steps.approve"), t("steps.return")]} footLeft={flow("neverSeesPassword")}>
      {children}
    </Shell>
  );

  if (!begin) return shell(<p className="hint" style={{ padding: "60px 0" }}>{flow("loading")}</p>);

  if (!begin.ok) {
    return shell(
      <>
        <h1>{t("failedTitle")}</h1>
        <p className="lede">{begin.description || t("unreachable")}</p>
        {web(begin.redirect) && (
          <div className="btn-row">
            <a className="button ghost" href={web(begin.redirect)}>{t("back")}</a>
          </div>
        )}
      </>,
    );
  }

  const { app } = begin;
  return shell(
    <>
      {app.icon && <img src={app.icon} alt="" width={64} height={64} style={{ display: "block", marginBottom: 14, border: "2px solid var(--edge)", borderRadius: 16 }} />}
      <h1 style={{ textWrap: "balance" }}>{t("title", { name: app.name })}</h1>
      <p className="lede">{t("by", { by: app.by, host: begin.redirectHost })}</p>
      {begin.for && <p>{t("for", { who: begin.for })}</p>}
      {(web(app.website) || web(app.privacy)) && (
        <p>
          {web(app.website) && <a href={web(app.website)} target="_blank" rel="noopener noreferrer">{t("website")}</a>}
          {web(app.website) && web(app.privacy) && " · "}
          {web(app.privacy) && <a href={web(app.privacy)} target="_blank" rel="noopener noreferrer">{t("privacy")}</a>}
        </p>
      )}
      <p>{t("receives")}</p>
      {!app.verified && <p className="hint bad" style={{ fontSize: 15, margin: "0 0 16px" }}>{t(begin.reviews ? "unverified" : "trust")}</p>}

      {helper ? (
        <>
          <div className="btn-row">
            <button type="button" className="button pink" data-aime-oauth="" data-aime-ticket={begin.ticket}>
              {t("continue")}
            </button>
          </div>
          <div className="status" role="status">
            {opened && (
              <>
                <span className="lamp wait" />
                <span>{t("waiting")}</span>
              </>
            )}
          </div>
        </>
      ) : (
        <>
          <p>{t("needHelper")}</p>
          <div className="btn-row">
            <a className="button" href="/chromeextension" target="_blank" rel="noopener noreferrer">{t("addChrome")}</a>
            <button type="button" className="button ghost" onClick={() => window.location.reload()}>{t("added")}</button>
          </div>
          <p className="hint">{t("firefoxSoon")}</p>
        </>
      )}
      {web(begin.cancel) && (
        <p style={{ marginTop: 18 }}>
          <a href={web(begin.cancel)}>{t("cancel", { name: app.name })}</a>
        </p>
      )}
    </>,
  );
}
