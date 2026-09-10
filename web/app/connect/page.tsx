"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Turnstile } from "@/components/Turnstile";
import { errorCopy } from "@/components/copy";

type ConnectInfo = {
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

  if (info && !info.verified) {
    return (
      <Shell tag="step 2 of 3" lit={2} footLeft="your password never touches this page" footRight={`link valid until ${info.expiresDisplay}`}>
        <h1>
          One quick <em>check</em>.
        </h1>
        <p className="lede">
          A second to prove there is a person here. Then your link and the connect bookmark appear.
        </p>
        <div className="check">
          <Turnstile siteKey={info.turnstile} action="connect" onToken={passCheck} onError={() => setCheckFailed("failed")} />
          {checkFailed === "failed" && <p className="hint">The check did not pass. Reload the page and try again.</p>}
        </div>
        <div className="aside">
          <b>Why?</b> The link on the next screen hands your maimai session to the bot. The check keeps scripts from
          harvesting it.
        </div>
      </Shell>
    );
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
      footLeft="your password never touches this page"
      footRight={info ? `link valid until ${info.expiresDisplay}` : ""}
    >
      <h1>
        {mobile ? (
          <>
            One <em>bookmark</em>, then sign in.
          </>
        ) : (
          <>
            Two taps and a <em>bookmark</em>.
          </>
        )}
      </h1>
      <p className="lede">
        {mobile
          ? "Set the bookmark up once, sign in at my-aime, open the Aime authentication, then run the bookmark there. This page updates on its own when you're connected."
          : "Keep this tab open. It lights up on its own the moment you're connected."}
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
              <p>Copy the bookmark code, then turn any bookmark into the connect button:</p>
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
              <p>Copy the bookmark code, then turn any bookmark into the connect button:</p>
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
            authentication: it uses that sign-in and lands you on the gateway page.
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
              Once you&apos;re signed in and looking at the gateway page, click the <b>maimai connect</b> bookmark you
              saved. It hands your session to the bot and this page lights up.
            </p>
          )}
          {platform === "ios" && (
            <p>
              Once you&apos;re signed in and looking at the gateway page, open <b>Bookmarks</b>{" "}
              <span className="glyph">📖</span> and tap <b>maimai connect</b>. Then come back to this tab.
            </p>
          )}
          {platform === "android" && (
            <p>
              Once you&apos;re signed in and looking at the gateway page, tap the <b>address bar</b>, type{" "}
              <b>maimai connect</b> and pick the bookmark from the suggestions. That is how Chrome runs bookmark code;
              pasting it into the address bar does not work. Then come back to this tab.
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
        run it again. If the link expired, run <code>/login</code> in Discord for a new one.
      </div>
    </Shell>
  );
}
