"use client";

import { Ring } from "@/components/Ring";
import { MastheadNav } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ServersNotice } from "@/components/Servers";
import { useTranslations } from "next-intl";
import { STATUS_URL, TRANSLATE_URL } from "@/components/Contact";
import { type Overview } from "./api";

export function Frame({ children, user, onSignOut }: { children: React.ReactNode; user?: Overview["user"]; onSignOut?: () => void }) {
  const t = useTranslations("dash");
  const f = useTranslations("footer");
  return (
    <div className="frame dash">
      <header className="masthead">
        <a className="home" href="/">
          <Ring lit={0} size={34} />
        </a>
        <div className="wordmark">
          Ras<span>mai</span>
        </div>
        <MastheadNav current="dashboard" />
        <ThemeToggle />
        {user && (
          <div className="who-discord">
            {user.avatar ? <img src={user.avatar} alt="" width={28} height={28} /> : <Ring lit={0} size={28} />}
            <span>{user.name}</span>
            <button type="button" className="linkish" onClick={onSignOut}>
              {t("signOut")}
            </button>
          </div>
        )}
      </header>
      <ServersNotice />
      {children}
      <footer className="foot">
        <span>
          {f.rich("createdBy", { b: (c) => <b>{c}</b> })} · {f("notAffiliated")} · <a href="/privacy/">{f("privacy")}</a> ·{" "}
          <a href="/terms/">{f("terms")}</a> · <a href="/support">{f("support")}</a> · <a href={STATUS_URL} target="_blank" rel="noopener noreferrer">{f("status")}</a> ·{" "}
          <a href={TRANSLATE_URL} target="_blank" rel="noopener noreferrer">{f("translate")}</a>
        </span>
        <span>{t("footRight")}</span>
      </footer>
    </div>
  );
}
