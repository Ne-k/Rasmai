"use client";

import { useEffect, useState } from "react";

type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

let pendingPrompt: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    pendingPrompt = event as InstallPromptEvent;
    listeners.forEach((fn) => fn());
  });
  window.addEventListener("appinstalled", () => {
    pendingPrompt = null;
    listeners.forEach((fn) => fn());
  });
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(display-mode: standalone)").matches || Boolean((navigator as { standalone?: boolean }).standalone);
}

const BUILD = process.env.NEXT_PUBLIC_BUILD_ID ?? "dev";

/** Registers the service worker, marks the document when the site runs as a home-screen app, and offers a reload when a newer build has taken over. */
export function Pwa() {
  const [updated, setUpdated] = useState(false);
  useEffect(() => {
    const mark = () => document.documentElement.toggleAttribute("data-standalone", isStandalone());
    mark();
    const media = window.matchMedia("(display-mode: standalone)");
    media.addEventListener("change", mark);
    if ("serviceWorker" in navigator) {
      // the build id in the address makes every deploy a new worker script, so its cache is versioned with the build
      navigator.serviceWorker
        .register(`/sw.js?v=${encodeURIComponent(BUILD)}`)
        .then((registration) => {
          registration.addEventListener("updatefound", () => {
            const worker = registration.installing;
            if (!worker || !navigator.serviceWorker.controller) return; // the first install is not an update
            worker.addEventListener("statechange", () => {
              if (worker.state === "activated") setUpdated(true);
            });
          });
        })
        .catch(() => undefined);
    }
    return () => media.removeEventListener("change", mark);
  }, []);
  if (!updated) return null;
  return (
    <div className="toast" role="status">
      <span>A newer version of the site is ready.</span>
      <button type="button" className="button pink" onClick={() => window.location.reload()}>
        reload
      </button>
      <button type="button" className="linkish" onClick={() => setUpdated(false)} aria-label="Dismiss">
        later
      </button>
    </div>
  );
}

const HINT_KEY = "rasmai-install-hint";

function hintDismissed(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) === "no";
  } catch {
    return false;
  }
}

type Platform = "ios" | "android" | "other";

function platform(): Platform {
  const ua = navigator.userAgent;
  const iPadOS = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  if (/iPhone|iPad|iPod/.test(ua) || iPadOS) return "ios";
  if (/Android/.test(ua)) return "android";
  return "other";
}

/** How to put Rasmai on the home screen, for the device at hand. Renders nothing once it is installed. */
export function InstallHint() {
  const [state, setState] = useState<{ standalone: boolean; platform: Platform; canPrompt: boolean; touch: boolean } | null>(null);
  const [dismissed, setDismissed] = useState(true); // assume dismissed until the browser says otherwise, so nothing flashes
  useEffect(() => {
    setDismissed(hintDismissed());
    const read = () =>
      setState({
        standalone: isStandalone(),
        platform: platform(),
        canPrompt: pendingPrompt !== null,
        touch: window.matchMedia("(pointer: coarse)").matches,
      });
    read();
    listeners.add(read);
    return () => {
      listeners.delete(read);
    };
  }, []);
  if (!state || dismissed || state.standalone || (!state.touch && !state.canPrompt)) return null;
  const dismiss = () => {
    try {
      localStorage.setItem(HINT_KEY, "no");
    } catch {
      /* private mode: the hint goes for this page only */
    }
    setDismissed(true);
  };

  const install = () => {
    const prompt = pendingPrompt;
    if (!prompt) return;
    prompt.prompt().catch(() => undefined);
  };
  return (
    <div className="install" role="note">
      <button type="button" className="install-close" onClick={dismiss} aria-label="Don't show this again">
        ×
      </button>
      <div className="install-icon" aria-hidden="true">
        <img src="/app/icon-192.png" alt="" width={44} height={44} />
      </div>
      <div className="install-body">
        <b>Rasmai on your home screen.</b>{" "}
        {state.canPrompt ? (
          <>
            The dashboard opens like an app, full screen, straight to your scores.
            <div className="btn-row">
              <button type="button" className="button pink" onClick={install}>
                install the app
              </button>
            </div>
          </>
        ) : state.platform === "ios" ? (
          <>
            In Safari tap <b>Share</b> <span className="glyph">⎙</span>, then <b>Add to Home Screen</b>. It opens full screen, straight to your scores.
          </>
        ) : state.platform === "android" ? (
          <>
            In Chrome open the <b>⋮</b> menu and choose <b>Install app</b> or <b>Add to Home screen</b>. It opens full screen, straight to your scores.
          </>
        ) : (
          <>Your browser can install this page as an app from its menu. It opens full screen, straight to your scores.</>
        )}
      </div>
    </div>
  );
}
