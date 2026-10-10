"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { RelinkNotice, useNeedsRelink } from "@/components/RelinkNotice";

type Notice = { text: string; tone: string; link: string; id: string; hideOnHost?: string; at?: string };

const KEY = "rasmai-notice-seen";
const TONES = new Set(["info", "notice", "warning"]);
const MAX = 300;
// the bot sanitises what it stores, and the browser trusts none of it a second time: an https address
// with nothing clever in it, or no link at all. React escapes the words, so they need no scrubbing.
const SAFE_LINK = /^https:\/\/[^\s<>'"]{1,300}$/;

function onHost(host: string): boolean {
  if (!host) return false;
  return location.hostname === host || location.hostname.endsWith(`.${host}`);
}

// a planned maintenance sends the time it starts or ends, written here in the reader's own time zone
function when(at: string | undefined): string {
  const moment = at ? new Date(at) : null;
  if (!moment || Number.isNaN(moment.getTime())) return "";
  return ` ${moment.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}.`;
}

function dismissed(id: string): boolean {
  try {
    return localStorage.getItem(KEY) === id;
  } catch {
    return false; // private mode: the band shows each visit rather than never
  }
}

/** Whatever the site has been told to say, across the top of every page. Set from Discord, dismissed per reader.
 *  An account that needs linking again is told that instead: it matters more to them than any notice. */
export function SiteNotice() {
  const t = useTranslations("common");
  const relink = useNeedsRelink();
  const path = usePathname() ?? "";
  // nothing until the browser has fetched one, so no band flashes on a page that should not carry it
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/notice", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? (r.json() as Promise<Notice>) : null))
      .then((next) => {
        if (!alive || typeof next?.text !== "string" || !next.text || !next.id) return;
        // a notice can name the address it is about, and stands down for anyone already there
        if (onHost(next.hideOnHost ?? "") || dismissed(next.id)) return;
        setNotice(next);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  // the dashboard says it itself, with the buttons to relink, so the band would only say it twice there
  if (relink) return path.startsWith("/me") ? null : <RelinkNotice />;
  if (!notice) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(KEY, notice.id);
    } catch {
      /* private mode: dismissed for this page only */
    }
    setNotice(null);
  };

  const tone = TONES.has(notice.tone) ? notice.tone : "notice";
  const link = SAFE_LINK.test(notice.link ?? "") ? notice.link : "";
  return (
    <div className={`movebar tone-${tone}`} role="status">
      <span className="movebar-lamp" aria-hidden="true" />
      <span className="movebar-text">
        {notice.text.slice(0, MAX)}
        {when(notice.at)}
        {link ? (
          <>
            {" "}
            <a href={link} rel="noopener noreferrer nofollow ugc">
              {t("more")}
            </a>
          </>
        ) : null}
      </span>
      <button type="button" className="movebar-close" onClick={dismiss} aria-label={t("dismiss")}>
        ×
      </button>
    </div>
  );
}
