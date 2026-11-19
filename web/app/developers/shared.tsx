"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

export type Review = "none" | "pending" | "verified" | "rejected";
export type App = {
  id: string;
  name: string;
  description: string;
  website: string;
  privacy: string;
  redirects: string[];
  hasSecret: boolean;
  review: Review;
  icon: string;
  blocked: boolean;
  createdAt: string;
};
type Answer = { ok?: boolean; error?: string; apps?: App[]; max?: number; maxRedirects?: number; reviews?: boolean; donePage?: string; app?: App; secret?: string };

/** The site itself, where the sign-in and the OAuth endpoints are: this host without the portal's "developers." */
export const site = () => window.location.origin.replace("//developers.", "//");
/** Where the portal's pages start: the root on its own host, /developers on the site's (next.config.ts). */
export const home = () => (window.location.hostname.startsWith("developers.") ? "" : "/developers");

/** The signed-in developer's apps, and `call` for everything that changes them. */
export function useApps() {
  const t = useTranslations("developers");
  const [apps, setApps] = useState<App[] | null>(null);
  const [max, setMax] = useState(10);
  const [maxRedirects, setMaxRedirects] = useState(10);
  // whether Rasmai reviews apps at all: with it off, nothing about review is shown
  const [reviews, setReviews] = useState(false);
  // Rasmai's own page a player ends on: the redirect of an app with no website
  const [donePage, setDonePage] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  /** One call under /api/me/apps: the answer when it went well; otherwise nothing, with the problem said. */
  const call = useCallback(async (path = "", body?: unknown): Promise<Answer | undefined> => {
    setBusy(true);
    setProblem("");
    try {
      const response = await fetch(`/api/me/apps${path}`, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const answer = (await response.json().catch(() => ({}))) as Answer;
      if (response.status === 401) {
        setSignedOut(true);
        return;
      }
      if (response.ok && answer.ok) {
        const { app } = answer;
        if (answer.apps) {
          setApps(answer.apps);
          setMax(answer.max ?? 10);
          setMaxRedirects(answer.maxRedirects ?? 10);
          setReviews(answer.reviews === true);
          setDonePage(answer.donePage ?? "");
        }
        if (app) setApps((old) => old && old.map((one) => (one.id === app.id ? app : one)));
        return answer;
      }
      const known = `problems.${answer.error}` as never;
      setProblem(t.has(known) ? t(known) : t("problems.other"));
    } catch {
      setProblem(t("problems.offline"));
    } finally {
      setBusy(false);
    }
  }, [t]);

  useEffect(() => {
    call();
  }, [call]);

  return { apps, max, maxRedirects, reviews, donePage, signedOut, busy, problem, setProblem, call };
}

/** What stands in for a page until the apps are read, and when nobody is signed in. */
export function Gate({ state, children }: { state: ReturnType<typeof useApps>; children: React.ReactNode }) {
  const t = useTranslations("developers");
  if (state.signedOut) {
    return (
      <section className="dp-gate">
        <h1>{t("signedOutTitle")}</h1>
        <p className="dp-note">{t("signedOut")}</p>
        <div className="btn-row">
          <a className="button" href="/auth/portal">{t("signIn")}</a>
        </div>
      </section>
    );
  }
  if (!state.apps) return <p className={`hint${state.problem ? " bad" : ""}`} role="status">{state.problem || t("loading")}</p>;
  return children;
}

/** An app's picture, or its first letter until it has one. */
export function Icon({ app, size = 28 }: { app: Pick<App, "name" | "icon">; size?: number }) {
  const style = { "--s": `${size}px` } as React.CSSProperties;
  return app.icon ? <img className="dp-icon" src={app.icon} alt="" width={size} height={size} style={style} /> : <span className="dp-icon" style={style} aria-hidden="true">{[...app.name][0]}</span>;
}

/** The review state as the site's status lamp: unlit, pink while it waits, gold once verified, dark when rejected. */
export function Lamp({ review }: { review: Review }) {
  return <span className="dp-lamp" data-review={review} aria-hidden="true" />;
}

/** The portal's session is its own host's, so it is ended here and not on the site. */
export function SignOut() {
  const t = useTranslations("developers");
  const out = () => fetch("/auth/logout", { method: "POST" }).finally(() => window.location.reload());
  return (
    <button type="button" className="button ghost dp-mini" onClick={out}>
      {t("signOut")}
    </button>
  );
}

export function Copy({ text }: { text: string }) {
  const t = useTranslations("developers");
  const [copied, setCopied] = useState(false);
  const copy = () =>
    navigator.clipboard.writeText(text).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => undefined, // refused: the value is on the page to copy by hand
    );
  return (
    <button type="button" className="button ghost dp-mini" onClick={copy}>
      {copied ? t("copied") : t("copy")}
    </button>
  );
}
