"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Support } from "@/components/Support";
import { Turnstile } from "@/components/Turnstile";
import { errorCopy } from "@/components/copy";
import { useTranslations } from "next-intl";

type ConnectInfo = {
  method?: "bookmark" | "segaid";
  loginLink: string;
  bookmarklet: string;
  expiresDisplay: string;
  region: string;
  turnstile: string;
  verified: boolean;
};

type Platform = "desktop" | "ios" | "android";

// the tags the flow messages use; the glyphs are the Share and Bookmarks icons in Safari
const tags = {
  b: (c: React.ReactNode) => <b>{c}</b>,
  em: (c: React.ReactNode) => <em>{c}</em>,
  code: (c: React.ReactNode) => <code>{c}</code>,
  glyph: (c: React.ReactNode) => <span className="glyph">{c}</span>,
  jp: (c: React.ReactNode) => (
    <a href="https://maimaidx.jp/maimai-mobile/" target="_blank" rel="noopener noreferrer">
      {c}
    </a>
  ),
};

function detectPlatform(): Platform {
  const ua = navigator.userAgent;
  const iPadOS = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  if (/iPhone|iPad|iPod/.test(ua) || iPadOS) return "ios";
  if (/Android/.test(ua)) return "android";
  if (window.matchMedia("(pointer: coarse)").matches && !window.matchMedia("(pointer: fine)").matches) return "android";
  return "desktop";
}

export default function ConnectPage() {
  const t = useTranslations("flow");
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{t("loading")}</p></div>}>
      <Connect />
    </Suspense>
  );
}

function Connect() {
  const t = useTranslations("flow");
  const e = useTranslations("errors");
  const params = useSearchParams();
  const code = params.get("code") ?? "";
  const user = params.get("user") ?? "";
  const [info, setInfo] = useState<ConnectInfo | null>(null);
  const [errorKind, setErrorKind] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [status, setStatus] = useState<"waiting" | "done" | "stopped">("waiting");
  const [player, setPlayer] = useState("");
  const [platform, setPlatform] = useState<Platform>("desktop");
  const [checkFailed, setCheckFailed] = useState("");
  const bookmarkRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    setPlatform(detectPlatform());
  }, []);

  const loadInfo = useCallback(() => {
    if (!code || !user) {
      setErrorKind("invalid_user");
      return;
    }
    fetch(`/api/connect-info?code=${encodeURIComponent(code)}&user=${encodeURIComponent(user)}`)
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.kind ?? "unknown");
        setInfo(data as ConnectInfo);
      })
      .catch((e: Error) => setErrorKind(e.message || "unknown"));
  }, [code, user]);

  useEffect(() => {
    loadInfo();
  }, [loadInfo]);

  // the widget's token goes to the server, which remembers the verdict on the login code
  const passCheck = (token: string) => {
    if (!token) return;
    setCheckFailed("");
    fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, user, token }),
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? "unknown");
        loadInfo();
      })
      .catch((e: Error) => (e.message === "expired" ? setErrorKind("expired") : setCheckFailed("failed")));
  };

  // React refuses to render javascript: URLs; the bookmarklet is exactly that, so set it on the node directly.
  useEffect(() => {
    if (info && bookmarkRef.current) bookmarkRef.current.setAttribute("href", info.bookmarklet);
  }, [info]);

  useEffect(() => {
    if (!info?.verified) return;
    let stopped = false;
    let tries = 0;
    const poll = async () => {
      if (stopped) return;
      if (tries++ > 600) {
        setStatus("stopped");
        return;
      }
      try {
        const r = await fetch(`/api/status?user=${encodeURIComponent(user)}&code=${encodeURIComponent(code)}`);
        const data = await r.json();
        if (data?.connected) {
          setStatus("done");
          setPlayer(data.player ?? "");
          const q = new URLSearchParams({ player: data.player ?? "", region: data.region ?? "" });
          setTimeout(() => {
            window.location.href = `/connected/?${q.toString()}`;
          }, 900);
          return;
        }
      } catch {
        /* keep polling */
      }
      setTimeout(poll, 2000);
    };
    poll();
    return () => {
      stopped = true;
    };
  }, [info, user, code]);

  if (errorKind) {
    const copy = errorCopy(errorKind, e);
    return (
      <Shell tag="error" lit={2} footLeft={t("nothingSaved")}>
        <h1>
          {copy.headline}
          {t("period")}
        </h1>
        <p className="lede">{copy.detail}</p>
        <div className="aside">{copy.hint}</div>
        <Support />
      </Shell>
    );
  }

  const japan = info?.method === "segaid";

  if (info && !info.verified) {
    return (
      <Shell
        tag="step 2 of 3"
        lit={2}
        footLeft={japan ? t("segaIdEncrypted") : t("neverSeesPassword")}
        footRight={t("validUntil", { time: info.expiresDisplay })}
      >
        <h1>{t.rich("checkTitle", tags)}</h1>
        <p className="lede">{japan ? t("checkLedeJapan") : t("checkLede")}</p>
        <div className="check">
          <Turnstile siteKey={info.turnstile} action="connect" onToken={passCheck} onError={() => setCheckFailed("failed")} />
          {checkFailed === "failed" && <p className="hint">{t("checkFailed")}</p>}
        </div>
        <div className="aside">{t.rich("checkWhy", { ...tags, japan: String(japan) })}</div>
      </Shell>
    );
  }

  if (info && japan) {
    return <JapanConnect info={info} code={code} user={user} onExpired={() => setErrorKind("expired")} />;
  }

  const done = status === "done";
  const mobile = platform !== "desktop";
  const copyBookmarklet = () => {
    if (!info) return;
    navigator.clipboard.writeText(info.bookmarklet).then(() => setCopied(true));
  };

  const platformPicker = (
    <div className="seg" role="group" aria-label={t("device")}>
      {(["desktop", "ios", "android"] as Platform[]).map((p) => (
        <button key={p} type="button" className={platform === p ? "on" : ""} onClick={() => setPlatform(p)}>
          {t(`devices.${p}`)}
        </button>
      ))}
    </div>
  );

  return (
    <Shell
      tag="step 2 of 3"
      lit={done ? 3 : 2}
      done={done}
      footLeft={t("neverSeesPassword")}
      footRight={info ? t("validUntil", { time: info.expiresDisplay }) : ""}
    >
      <h1>{t.rich(mobile ? "titleMobile" : "titleDesktop", tags)}</h1>
      <p className="lede">{mobile ? t("ledeMobile") : t("ledeDesktop")}</p>
      {platformPicker}

      <section className="step">
        <div className="n">1</div>
        <div>
          {platform === "desktop" && (
            <>
              <h2>{t("dragTitle")}</h2>
              <p>{t.rich("drag", tags)}</p>
              <div className="btn-row">
                <a
                  ref={bookmarkRef}
                  className="button pink bookmarklet"
                  href="#"
                  title="maimai connect"
                  draggable
                  onClick={(e) => e.preventDefault()}
                  onDragStart={(e) => {
                    if (!info) return;
                    e.dataTransfer.effectAllowed = "copyLink";
                    e.dataTransfer.setData("text/uri-list", info.bookmarklet);
                    e.dataTransfer.setData("text/plain", info.bookmarklet);
                    bookmarkRef.current?.classList.add("dragging");
                  }}
                  onDragEnd={() => bookmarkRef.current?.classList.remove("dragging")}
                >
                  ◯ maimai connect
                </a>
                <button className="button ghost" type="button" onClick={copyBookmarklet} disabled={!info}>
                  {t("copyInstead")}
                </button>
              </div>
              {copied && <p className="hint ok">{t("copiedHint")}</p>}
            </>
          )}

          {platform === "ios" && (
            <>
              <h2>{t("makeTitle")}</h2>
              <p>{t("makeBody")}</p>
              <div className="btn-row">
                <button className="button pink" type="button" onClick={copyBookmarklet} disabled={!info}>
                  {copied ? t("copied") : t("copyCode")}
                </button>
              </div>
              <ol className="howto">
                {(["step1", "step2", "step3"] as const).map((step) => (
                  <li key={step}>{t.rich(`ios.${step}`, tags)}</li>
                ))}
              </ol>
            </>
          )}

          {platform === "android" && (
            <>
              <h2>{t("makeTitle")}</h2>
              <p>{t("makeBody")}</p>
              <div className="btn-row">
                <button className="button pink" type="button" onClick={copyBookmarklet} disabled={!info}>
                  {copied ? t("copied") : t("copyCode")}
                </button>
              </div>
              <ol className="howto">
                {(["step1", "step2", "step3"] as const).map((step) => (
                  <li key={step}>{t.rich(`android.${step}`, tags)}</li>
                ))}
              </ol>
            </>
          )}
        </div>
      </section>

      <section className="step">
        <div className="n">2</div>
        <div>
          <h2>{t("signInTitle")}</h2>
          <p>{t("signIn", { mobile: String(mobile) })}</p>
          <div className="btn-row">
            <a className="button ghost" href="https://my-aime.net/en/" target="_blank" rel="noopener noreferrer">
              {t("signInButton")}
            </a>
            {info?.loginLink ? (
              <a className="button" href={info.loginLink} target="_blank" rel="noopener noreferrer">
                {t("authButton")}
              </a>
            ) : (
              <span className="button disabled" aria-disabled="true">
                {t("authButton")}
              </span>
            )}
          </div>
          <div className="readout">
            <span className="lbl">{t("labelValidUntil")}</span>
            <span className="val">{info?.expiresDisplay ?? "…"}</span>
            <span className="lbl">{t("labelRegion")}</span>
            <span className="val">{info?.region.toUpperCase() ?? "…"}</span>
          </div>
        </div>
      </section>

      <section className="step">
        <div className="n">3</div>
        <div>
          <h2>{t("runTitle")}</h2>
          {platform === "desktop" && <p>{t.rich("runDesktop", tags)}</p>}
          {platform === "ios" && <p>{t.rich("runIos", tags)}</p>}
          {platform === "android" && <p>{t.rich("runAndroid", tags)}</p>}
          <div className="status">
            <span className={`lamp ${done ? "done" : status === "waiting" ? "wait" : ""}`} />
            <span>
              {done ? (player ? t("connectedAs", { name: player }) : t("connected")) : status === "stopped" ? t("stopped") : t("waiting")}
            </span>
          </div>
        </div>
      </section>

      <div className="aside">{t.rich("stuck", tags)}</div>
    </Shell>
  );
}

// what "Save my login" keeps, on this device only: the SEGA ID and card, never the password, which is
// left to the browser's own password manager
const SAVED_LOGIN_KEY = "rasmai.jp.savedLogin";

function readSavedLogin(): { segaId: string; aime: string } | null {
  try {
    const raw = window.localStorage.getItem(SAVED_LOGIN_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { segaId?: unknown; aime?: unknown };
    return typeof saved.segaId === "string" && saved.segaId
      ? { segaId: saved.segaId, aime: typeof saved.aime === "string" && saved.aime ? saved.aime : "1" }
      : null;
  } catch {
    return null;
  }
}

function writeSavedLogin(saved: { segaId: string; aime: string } | null) {
  try {
    if (saved) window.localStorage.setItem(SAVED_LOGIN_KEY, JSON.stringify(saved));
    else window.localStorage.removeItem(SAVED_LOGIN_KEY);
  } catch {
    /* storage blocked: nothing is remembered, which is the safe outcome */
  }
}

/** Japan's maimai DX NET has no session Rasmai can borrow, so the account is linked with its SEGA ID. */
function JapanConnect({
  info,
  code,
  user,
  onExpired,
}: {
  info: ConnectInfo;
  code: string;
  user: string;
  onExpired: () => void;
}) {
  const t = useTranslations("flow");
  const e = useTranslations("errors");
  const [segaId, setSegaId] = useState("");
  const [password, setPassword] = useState("");
  const [aime, setAime] = useState("1");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [player, setPlayer] = useState<string | null>(null);
  const [remember, setRemember] = useState(false);

  useEffect(() => {
    const saved = readSavedLogin();
    if (!saved) return;
    setSegaId(saved.segaId);
    setAime(saved.aime);
    setRemember(true);
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setProblem("");
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ code, user, region: "jp", segaId, password, aime }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.ok) {
        if (data.kind === "expired" || data.kind === "invalid_user") {
          onExpired();
          return;
        }
        if (data.kind === "credentials") {
          // the bot's own words say to run /login again, but on this page the link still works
          const copy = errorCopy("credentials", e);
          setProblem(`${copy.detail} ${copy.hint}`);
          return;
        }
        if (data.kind === "upstream") {
          // maimaidx.jp could not be reached or answered with something unexpected; the link is not spent
          setProblem(t("unreachableJp"));
          return;
        }
        if (data.kind && e.has(`${data.kind}.headline` as never) && data.kind !== "unknown") {
          const copy = errorCopy(data.kind, e);
          setProblem(`${copy.detail} ${copy.hint}`);
          return;
        }
        setProblem(String(data.error ?? t("failed")));
        return;
      }
      setPassword("");
      writeSavedLogin(remember ? { segaId: segaId.trim(), aime } : null);
      const name = String(data.player?.name ?? "");
      setPlayer(name);
      const q = new URLSearchParams({ player: name, region: "jp", rating: String(data.player?.rating ?? "") });
      setTimeout(() => {
        window.location.href = `/connected/?${q.toString()}`;
      }, 900);
    } catch {
      setProblem(t("offline"));
    } finally {
      setBusy(false);
    }
  };

  const done = player !== null;
  return (
    <Shell
      tag="step 2 of 3"
      lit={done ? 3 : 2}
      done={done}
      footLeft={t("segaIdEncrypted")}
      footRight={t("validUntil", { time: info.expiresDisplay })}
    >
      <h1>{t.rich("jpTitle", tags)}</h1>
      <p className="lede">{t("jpLede")}</p>

      <section className="step">
        <div className="n">1</div>
        <div>
          <h2>{t("jpStepTitle")}</h2>
          <p>{t.rich("jpStep", tags)}</p>
          <form className="signin" onSubmit={submit}>
            <label>
              <span>{t("segaId")}</span>
              <input
                type="text"
                name="segaId"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                maxLength={256}
                value={segaId}
                onChange={(e) => setSegaId(e.target.value)}
                disabled={busy || done}
              />
            </label>
            <label>
              <span>{t("password")}</span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
                maxLength={256}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy || done}
              />
            </label>
            <label className="narrow">
              <span>{t("aimeCard")}</span>
              <input
                type="number"
                name="aime"
                inputMode="numeric"
                min={1}
                max={20}
                required
                value={aime}
                onChange={(e) => setAime(e.target.value)}
                disabled={busy || done}
              />
            </label>
            <p className="hint">{t("aimeHint")}</p>
            <label className="remember">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => {
                  setRemember(e.target.checked);
                  if (!e.target.checked) writeSavedLogin(null);
                }}
                disabled={busy || done}
              />
              <span>
                {t("remember")}
                <small>{t("rememberHint")}</small>
              </span>
            </label>
            <div className="btn-row">
              <button className="button pink" type="submit" disabled={busy || done || !segaId || !password}>
                {busy ? t("signingIn") : t("signInAndLink")}
              </button>
            </div>
            {problem && (
              <>
                <p className="hint bad" role="alert">
                  {problem}
                </p>
                <Support />
              </>
            )}
          </form>
          <div className="readout">
            <span className="lbl">{t("labelValidUntil")}</span>
            <span className="val">{info.expiresDisplay}</span>
            <span className="lbl">{t("labelRegion")}</span>
            <span className="val">JP</span>
          </div>
          <div className="status">
            <span className={`lamp ${done ? "done" : "wait"}`} />
            <span>{done ? (player ? t("connectedAs", { name: player }) : t("connected")) : busy ? t("signingInJp") : t("waiting")}</span>
          </div>
        </div>
      </section>

      <div className="aside">{t.rich("keeps", tags)}</div>
    </Shell>
  );
}
