"use client";

import { useEffect, useRef } from "react";

type RenderOptions = {
  sitekey: string;
  action?: string;
  theme?: "auto" | "light" | "dark";
  size?: "normal" | "flexible" | "compact";
  callback?: (token: string) => void;
  "error-callback"?: () => void;
  "expired-callback"?: () => void;
};

type TurnstileApi = {
  render: (container: HTMLElement, options: RenderOptions) => string;
  remove: (widgetId: string) => void;
  reset: (widgetId?: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => {
        loading = null;
        reject(new Error("turnstile script failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

type Props = {
  siteKey: string;
  action: string;
  onToken: (token: string) => void;
  onError?: () => void;
};

/** One Cloudflare Turnstile widget. Calls onToken with the token, and with "" when it expires. */
export function Turnstile({ siteKey, action, onToken, onError }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const tokenRef = useRef(onToken);
  const errorRef = useRef(onError);
  tokenRef.current = onToken;
  errorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    let widgetId: string | undefined;
    loadScript()
      .then(() => {
        if (cancelled || !host.current || !window.turnstile) return;
        widgetId = window.turnstile.render(host.current, {
          sitekey: siteKey,
          action,
          theme: "auto",
          size: "flexible",
          callback: (token) => tokenRef.current(token),
          "expired-callback": () => tokenRef.current(""),
          "error-callback": () => errorRef.current?.(),
        });
      })
      .catch(() => errorRef.current?.());
    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [siteKey, action]);

  return <div ref={host} className="turnstile" />;
}
