"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Support } from "@/components/Support";
import { Turnstile } from "@/components/Turnstile";
import { Tutorial } from "@/components/Tutorial";
import { GATEWAY_HOST } from "@/lib/gateway";
import { errorCopy } from "@/components/copy";
import { useTranslations } from "next-intl";

type ConnectInfo = {
  method?: "cookie" | "segaid";
  loginLink: string;
  expiresDisplay: string;
  region: string;
  turnstile: string;
  verified: boolean;
  grant?: string;
};

// a page on the gateway that does not send a signed-in browser on to maimai DX NET, so its cookies can be looked at there
const GATEWAY_PAGE = `https://${GATEWAY_HOST}/common_auth/`;

const tags = {
  chrome: (c: React.ReactNode) => (
    <a href="/chromeextension" target="_blank" rel="noopener noreferrer">
      {c}
    </a>
  ),
  firefox: (c: React.ReactNode) => (
    <a href="/firefoxextension" target="_blank" rel="noopener noreferrer">
      {c}
    </a>
  ),
  b: (c: React.ReactNode) => <b>{c}</b>,
  em: (c: React.ReactNode) => <em>{c}</em>,
  code: (c: React.ReactNode) => <code>{c}</code>,
  jp: (c: React.ReactNode) => (
    <a href="https://maimaidx.jp/maimai-mobile/" target="_blank" rel="noopener noreferrer">
      {c}
    </a>
  ),
};

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
  // the /login card's buttons name the way of linking to open on: "extension" also starts it, "paste" and "hand" open their cards
  const way = params.get("way") ?? "";
  const [info, setInfo] = useState<ConnectInfo | null>(null);
  const [errorKind, setErrorKind] = useState<string | null>(null);
  const [checkFailed, setCheckFailed] = useState("");

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

  if (!info) {
    return (
      <Shell tag="step 2 of 3" lit={2} footLeft={t("neverSeesPassword")}>
        <p className="hint" style={{ padding: "60px 0" }}>{t("loading")}</p>
      </Shell>
    );
  }
  const onExpired = () => setErrorKind("expired");
  return japan ? <JapanConnect info={info} code={code} user={user} onExpired={onExpired} /> : <CookieConnect info={info} code={code} user={user} onExpired={onExpired} way={way} />;
}

/** What a sign-in refusal from the bot says on this page, where the login link is still good. */
function useProblemCopy() {
  const t = useTranslations("flow");
  const e = useTranslations("errors");
  return (data: { kind?: string; error?: unknown }, refused: string, unreachable: string): string => {
    if (data.kind === "credentials" || data.kind === "upstream") return refused;
    if (data.kind === "unknown" || !data.kind) return data.error ? String(data.error) : unreachable;
    if (e.has(`${data.kind}.headline` as never)) {
      const copy = errorCopy(data.kind, e);
      return `${copy.detail} ${copy.hint}`;
    }
    return String(data.error ?? t("failed"));
  };
}

/** The international gateway keeps its sign-in in a cookie no script may read any more, so the person copies it themselves. */
function CookieConnect({ info, code, user, onExpired, way = "" }: { info: ConnectInfo; code: string; user: string; onExpired: () => void; way?: string }) {
  const autoStart = way === "extension";
  const t = useTranslations("flow");
  const video = useTranslations("tutorial");
  const problemCopy = useProblemCopy();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [player, setPlayer] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState<"" | "copied" | "shown">("");
  const [opening, setOpening] = useState(false);
  const [extensionProblem, setExtensionProblem] = useState("");
  const rich = {
    ...tags,
    gw: (c: React.ReactNode) => (
      <a href={info.loginLink} target="_blank" rel="noopener noreferrer">
        {c}
      </a>
    ),
  };
  const helperLink = typeof window === "undefined" ? "" : `${window.location.origin}/api/link/${code}.${user}`;
  // the whole row copied, "clal=…", is as good as the value alone
  const token = value.trim().replace(/^clal=/, "");
  const valid = /^[A-Za-z0-9]{64}$/.test(token);

  // linked from outside this page, by the extension given the link: ask until the account turns up, then go on as a paste would
  useEffect(() => {
    if (player !== null) return;
    let tries = 0;
    const timer = setInterval(async () => {
      if (tries++ > 200) return clearInterval(timer);          // the link lasts ten minutes
      try {
        const data = await (await fetch(`/api/status?user=${encodeURIComponent(user)}&code=${encodeURIComponent(code)}`)).json();
        if (!data?.connected) return;
        clearInterval(timer);
        setPlayer(String(data.player ?? ""));
        window.location.href = `/connected/?${new URLSearchParams({ player: data.player ?? "", region: data.region ?? "intl" })}`;
      } catch {
        /* keep asking */
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [code, user, player]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setProblem("");
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ code, user, region: "intl", token }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.ok) {
        if (data.kind === "expired" || data.kind === "invalid_user") {
          onExpired();
          return;
        }
        setProblem(problemCopy(data, t("refusedIntl"), t("unreachableIntl")));
        return;
      }
      setValue("");
      const name = String(data.player?.name ?? "");
      setPlayer(name);
      const q = new URLSearchParams({ player: name, region: "intl", rating: String(data.player?.rating ?? "") });
      setTimeout(() => {
        window.location.href = `/connected/?${q.toString()}`;
      }, 900);
    } catch {
      setProblem(t("offline"));
    } finally {
      setBusy(false);
    }
  };

  // the site asks for the sign-in the way any app does: the answer is its own authorize page, where the extension takes over
  const viaExtension = async () => {
    if (opening) return;
    setOpening(true);
    setExtensionProblem("");
    try {
      const r = await fetch("/api/oauth/rasmai", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ code, user }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data.ok && typeof data.link === "string") {
        window.location.assign(data.link);
        return;
      }
      if (data.kind === "expired" || data.kind === "invalid_user") {
        onExpired();
        return;
      }
      setExtensionProblem(problemCopy(data, t("failed"), t("offline")));
    } catch {
      setExtensionProblem(t("offline"));
    } finally {
      setOpening(false);
    }
  };
  // once, even where React runs an effect twice in development
  const started = useRef(false);
  useEffect(() => {
    if (!autoStart || started.current) return;
    started.current = true;
    viaExtension();
  }, [autoStart]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = player !== null;
  return (
    <Shell
      tag="step 2 of 3"
      lit={done ? 3 : 2}
      done={done}
      footLeft={t("neverSeesPassword")}
      footRight={t("validUntil", { time: info.expiresDisplay })}
    >
      <h1>{t.rich("titleIntl", tags)}</h1>
      <p className="lede">{t("ledeIntl")}</p>

      <div className="ways">
        <details className="way first" open={way !== "paste" && way !== "hand"}>
          <summary>{t("wayOne")}</summary>
          <div className="way-body">
            <p>{t.rich("oneBody", rich)}</p>
            <div className="btn-row">
              <button type="button" className="button pink" onClick={viaExtension} disabled={opening || done}>
                {opening ? t("loading") : t("oneButton")}
              </button>
            </div>
            {extensionProblem && (
              <>
                <p className="hint bad" role="alert">
                  {extensionProblem}
                </p>
                <Support />
              </>
            )}
            <Tutorial clip="approve" label={video("approveLabel")} />
          </div>
        </details>

        {/* the same hand-off as the paste, as a link for the Aime sign-in helper extension: see app/api/link */}
        <details className="way" open={way === "paste"}>
          <summary>{t("wayTwo")}</summary>
          <div className="way-body">
            <p>{t.rich("twoBody", rich)}</p>
            <div className="btn-row">
              <button
                type="button"
                className="button ghost"
                onClick={() => navigator.clipboard.writeText(helperLink).then(() => setLinkCopied("copied"), () => setLinkCopied("shown"))}
              >
                {linkCopied === "copied" ? t("helperCopied") : t("helperCopy")}
              </button>
            </div>
            {/* the clipboard refused (blocked, or Firefox without the permission): the link itself, to copy by hand */}
            {linkCopied === "shown" && <code style={{ display: "block", marginTop: 8, overflowWrap: "anywhere" }}>{helperLink}</code>}
            <Tutorial clip="extension" label={video("helperLabel")} />
          </div>
        </details>

        <details className="way" open={way === "hand"}>
          <summary>{t("wayThree")}</summary>
          <div className="way-body">
            <section className="step">
              <div className="n">1</div>
              <div>
                <h2>{t("gwTitle")}</h2>
                <p>{t.rich("gwBody", tags)}</p>
                <div className="btn-row">
                  <a className="button" href={info.loginLink} target="_blank" rel="noopener noreferrer">
                    {t("gwButton")}
                  </a>
                </div>
              </div>
            </section>

            <section className="step">
              <div className="n">2</div>
              <div>
                <h2>{t("copyTitle")}</h2>
                <p>{t.rich("copyBody", tags)}</p>
                <div className="btn-row">
                  <a className="button ghost" href={GATEWAY_PAGE} target="_blank" rel="noopener noreferrer">
                    {t("gwPageButton")}
                  </a>
                </div>
                <ul className="howto">
                  <li>{t.rich("copyChrome", tags)}</li>
                  <li>{t.rich("copyFirefox", tags)}</li>
                </ul>
                <Tutorial label={video("label")} />
              </div>
            </section>

            <section className="step">
              <div className="n">3</div>
              <div>
                <h2>{t("pasteTitle")}</h2>
                <form className="signin" onSubmit={submit}>
                  <label>
                    <span>{t("pasteLabel")}</span>
                    <input
                      type="text"
                      name="clal"
                      data-aime-grant={info.grant || undefined}
                      autoComplete="off"
                      autoCapitalize="none"
                      spellCheck={false}
                      required
                      maxLength={80}
                      value={value}
                      onChange={(e) => {
                        setValue(e.target.value);
                        // the extension's popup fills this box from outside the page: its card opens so the value is seen
                        const card = e.target.closest("details");
                        if (card) card.open = true;
                      }}
                      disabled={busy || done}
                    />
                  </label>
                  <p className={`hint${value && !valid ? " bad" : ""}`}>{value && !valid ? t.rich("pasteBad", tags) : t("pasteHint")}</p>
                  <div className="btn-row">
                    <button className="button pink" type="submit" disabled={busy || done || !valid}>
                      {busy ? t("linking") : t("linkButton")}
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
              </div>
            </section>
          </div>
        </details>
      </div>

      {/* outside the cards: the account can turn up through any of the three, whichever card is open */}
      <div className="readout">
        <span className="lbl">{t("labelValidUntil")}</span>
        <span className="val">{info.expiresDisplay}</span>
        <span className="lbl">{t("labelRegion")}</span>
        <span className="val">{info.region.toUpperCase()}</span>
      </div>
      <div className="status" role="status">
        <span className={`lamp ${done ? "done" : "wait"}`} />
        <span>{done ? (player ? t("connectedAs", { name: player }) : t("connected")) : busy ? t("linking") : t("waiting")}</span>
      </div>

      <div className="aside">{t.rich("phones", tags)}</div>
      <div className="aside">{t.rich("keepsIntl", tags)}</div>
      <div className="aside">{t.rich("stuckIntl", tags)}</div>
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
  const problemCopy = useProblemCopy();
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
        // the bot's own words say to run /login again, but on this page the link still works
        const refused = errorCopy("credentials", e);
        setProblem(problemCopy(data, `${refused.detail} ${refused.hint}`, t("unreachableJp")));
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
