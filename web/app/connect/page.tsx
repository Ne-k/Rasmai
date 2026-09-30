"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Turnstile } from "@/components/Turnstile";
import { errorCopy } from "@/components/copy";

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

function detectPlatform(): Platform {
  const ua = navigator.userAgent;
  const iPadOS = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  if (/iPhone|iPad|iPod/.test(ua) || iPadOS) return "ios";
  if (/Android/.test(ua)) return "android";
  if (window.matchMedia("(pointer: coarse)").matches && !window.matchMedia("(pointer: fine)").matches) return "android";
  return "desktop";
}

export default function ConnectPage() {
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>Loading…</p></div>}>
      <Connect />
    </Suspense>
  );
}

function Connect() {
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
    const copy = errorCopy(errorKind);
    return (
      <Shell tag="error" lit={2} footLeft="nothing was saved">
        <h1>
          {copy.headline[0]}
          <em>{copy.headline[1]}</em>.
        </h1>
        <p className="lede">{copy.detail}</p>
        <div className="aside">{copy.hint}</div>
      </Shell>
    );
  }

  const japan = info?.method === "segaid";

  if (info && !info.verified) {
    return (
      <Shell
        tag="step 2 of 3"
        lit={2}
        footLeft={japan ? "your SEGA ID is stored encrypted" : "Rasmai never sees your password"}
        footRight={`link valid until ${info.expiresDisplay}`}
      >
        <h1>
          One quick <em>check</em>.
        </h1>
        <p className="lede">
          {japan ? "Pass the human check to get the sign-in form." : "Pass the human check to get your link and the connect bookmark."}
        </p>
        <div className="check">
          <Turnstile siteKey={info.turnstile} action="connect" onToken={passCheck} onError={() => setCheckFailed("failed")} />
          {checkFailed === "failed" && <p className="hint">The check failed. Reload the page and try again.</p>}
        </div>
        <div className="aside">
          <b>Why?</b> The next screen gives Rasmai {japan ? "your maimaidx.jp sign-in" : "your maimai session"}, and the check
          stops bots from grabbing it.
        </div>
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
    <div className="seg" role="group" aria-label="Your device">
      {(["desktop", "ios", "android"] as Platform[]).map((p) => (
        <button key={p} type="button" className={platform === p ? "on" : ""} onClick={() => setPlatform(p)}>
          {p === "desktop" ? "Computer" : p === "ios" ? "iPhone / iPad" : "Android"}
        </button>
      ))}
    </div>
  );

  return (
    <Shell
      tag="step 2 of 3"
      lit={done ? 3 : 2}
      done={done}
      footLeft="Rasmai never sees your password"
      footRight={info ? `link valid until ${info.expiresDisplay}` : ""}
    >
      <h1>
        {mobile ? (
          <>
            Set up the <em>bookmark</em>, then sign in.
          </>
        ) : (
          <>
            Drag in the <em>bookmark</em>, then sign in.
          </>
        )}
      </h1>
      <p className="lede">
        {mobile
          ? "Set up the bookmark, sign in at my-aime and open the Aime authentication. Then run the bookmark there. This page updates when you're connected."
          : "Keep this tab open. It updates when you're connected."}
      </p>
      {platformPicker}

      <section className="step">
        <div className="n">1</div>
        <div>
          {platform === "desktop" && (
            <>
              <h2>Drag this to your bookmarks bar</h2>
              <p>
                Grab the pink button and drop it on your browser&apos;s bookmarks bar. If the bar is hidden, press{" "}
                <code>Ctrl+Shift+B</code> (<code>⌘+Shift+B</code> on a Mac) first.
              </p>
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
                  copy instead
                </button>
              </div>
              {copied && <p className="hint ok">Copied. Paste it as a bookmark&apos;s address.</p>}
            </>
          )}

          {platform === "ios" && (
            <>
              <h2>Make the connect bookmark</h2>
              <p>Copy the bookmark code, then save it as a bookmark like this.</p>
              <div className="btn-row">
                <button className="button pink" type="button" onClick={copyBookmarklet} disabled={!info}>
                  {copied ? "✓ copied" : "copy bookmark code"}
                </button>
              </div>
              <ol className="howto">
                <li>
                  Tap <b>Share</b> <span className="glyph">⎙</span> → <b>Add Bookmark</b> → <b>Save</b>. Name it{" "}
                  <b>maimai connect</b>.
                </li>
                <li>
                  Open <b>Bookmarks</b> <span className="glyph">📖</span> → <b>Edit</b> → tap the new bookmark.
                </li>
                <li>
                  Replace its <b>address</b> with what you copied → <b>Done</b>.
                </li>
              </ol>
            </>
          )}

          {platform === "android" && (
            <>
              <h2>Make the connect bookmark</h2>
              <p>Copy the bookmark code, then save it as a bookmark like this.</p>
              <div className="btn-row">
                <button className="button pink" type="button" onClick={copyBookmarklet} disabled={!info}>
                  {copied ? "✓ copied" : "copy bookmark code"}
                </button>
              </div>
              <ol className="howto">
                <li>
                  Tap <b>⋮</b> → <b>☆</b> to bookmark this page.
                </li>
                <li>
                  Tap <b>⋮</b> → <b>Bookmarks</b>, then <b>⋮</b> on the new bookmark → <b>Edit</b>.
                </li>
                <li>
                  Name it <b>maimai connect</b>, replace the <b>URL</b> with what you copied, and go back to save.
                </li>
              </ol>
            </>
          )}
        </div>
      </section>

      <section className="step">
        <div className="n">2</div>
        <div>
          <h2>Sign in at my-aime, then authenticate</h2>
          <p>
            First sign in at my-aime.net with the account you play on{mobile ? "" : " (opens in a new tab)"}. Then open the Aime
            authentication, which takes you to the gateway page.
          </p>
          <div className="btn-row">
            <a className="button ghost" href="https://my-aime.net/en/" target="_blank" rel="noopener noreferrer">
              1 · sign in at my-aime →
            </a>
            {info?.loginLink ? (
              <a className="button" href={info.loginLink} target="_blank" rel="noopener noreferrer">
                2 · open the Aime authentication →
              </a>
            ) : (
              <span className="button disabled" aria-disabled="true">
                2 · open the Aime authentication →
              </span>
            )}
          </div>
          <div className="readout">
            <span className="lbl">link valid until</span>
            <span className="val">{info?.expiresDisplay ?? "…"}</span>
            <span className="lbl">region</span>
            <span className="val">{info?.region.toUpperCase() ?? "…"}</span>
          </div>
        </div>
      </section>

      <section className="step">
        <div className="n">3</div>
        <div>
          <h2>Run the bookmark on the AIME page</h2>
          {platform === "desktop" && (
            <p>
              When you&apos;re on the gateway page, click the <b>maimai connect</b> bookmark. This page updates once
              it&apos;s done.
            </p>
          )}
          {platform === "ios" && (
            <p>
              When you&apos;re on the gateway page, open <b>Bookmarks</b> <span className="glyph">📖</span> and tap{" "}
              <b>maimai connect</b>. Then come back to this tab.
            </p>
          )}
          {platform === "android" && (
            <p>
              When you&apos;re on the gateway page, tap the <b>address bar</b>, type <b>maimai connect</b> and pick the
              bookmark from the suggestions. Pasting the code into the address bar won&apos;t work in Chrome. Then come
              back to this tab.
            </p>
          )}
          <div className="status">
            <span className={`lamp ${done ? "done" : status === "waiting" ? "wait" : ""}`} />
            <span>
              {done
                ? player
                  ? `Connected as ${player}.`
                  : "Connected."
                : status === "stopped"
                  ? "Stopped checking. Reload to keep waiting."
                  : "Waiting for the sign-in…"}
            </span>
          </div>
        </div>
      </section>

      <div className="aside">
        <b>Stuck?</b> If the bookmark says it can&apos;t read your login, sign out of the gateway, sign in again, then
        run it again. If the link expired, run <code>/login</code> in Discord for a new one. This bookmark is for
        International accounts. A Japan account links with its SEGA ID instead: run <code>/login region:Japan</code>.
        Accounts from the Chinese version can&apos;t be linked yet.
      </div>
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
          const copy = errorCopy("credentials");
          setProblem(`${copy.detail} ${copy.hint}`);
          return;
        }
        setProblem(String(data.error ?? "The sign-in didn't work. Try again in a moment."));
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
      setProblem("Couldn't reach Rasmai. Check your connection and try again.");
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
      footLeft="your SEGA ID is stored encrypted"
      footRight={`link valid until ${info.expiresDisplay}`}
    >
      <h1>
        Sign in with your <em>SEGA ID</em>.
      </h1>
      <p className="lede">
        maimaidx.jp has no sign-in Rasmai can borrow the way the international site does, so Rasmai signs in there with
        your SEGA ID whenever it reads your scores.
      </p>

      <section className="step">
        <div className="n">1</div>
        <div>
          <h2>Your maimaidx.jp sign-in</h2>
          <p>
            The SEGA ID and password you use on{" "}
            <a href="https://maimaidx.jp/maimai-mobile/" target="_blank" rel="noopener noreferrer">
              maimaidx.jp
            </a>
            .
          </p>
          <form className="signin" onSubmit={submit}>
            <label>
              <span>SEGA ID</span>
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
              <span>Password</span>
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
              <span>Aime card</span>
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
            <p className="hint">
              One SEGA ID can hold several Aime cards, each its own player. Leave this at 1 unless yours has more than one.
            </p>
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
                Save my login for next time
                <small>
                  Remembers your SEGA ID and card on this device only. Your password is never saved here; your browser can
                  offer to save it.
                </small>
              </span>
            </label>
            <div className="btn-row">
              <button className="button pink" type="submit" disabled={busy || done || !segaId || !password}>
                {busy ? "signing in…" : "sign in and link"}
              </button>
            </div>
            {problem && (
              <p className="hint bad" role="alert">
                {problem}
              </p>
            )}
          </form>
          <div className="readout">
            <span className="lbl">link valid until</span>
            <span className="val">{info.expiresDisplay}</span>
            <span className="lbl">region</span>
            <span className="val">JP</span>
          </div>
          <div className="status">
            <span className={`lamp ${done ? "done" : "wait"}`} />
            <span>{done ? (player ? `Connected as ${player}.` : "Connected.") : busy ? "Signing in to maimaidx.jp…" : "Waiting for the sign-in…"}</span>
          </div>
        </div>
      </section>

      <div className="aside">
        <b>What Rasmai keeps.</b> Your SEGA ID and password are encrypted before they&apos;re stored, and they&apos;re
        used only to sign in to maimaidx.jp and read your scores. They&apos;re deleted when you run{" "}
        <code>/logout</code> or <code>/delete-account</code>. If you change the password, run <code>/login</code> again.
      </div>
    </Shell>
  );
}
