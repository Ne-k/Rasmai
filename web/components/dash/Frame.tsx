"use client";

import { Ring } from "@/components/Ring";
import { MastheadNav } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ServersNotice } from "@/components/Servers";
import { useM } from "@/components/I18n";
import { type Overview } from "./api";

export function Frame({ children, user, onSignOut }: { children: React.ReactNode; user?: Overview["user"]; onSignOut?: () => void }) {
  const m = useM();
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
              {m.dash.signOut}
            </button>
          </div>
        )}
      </header>
      <ServersNotice />
      {children}
      <footer className="foot">
        <span>
          {m.footer.createdBy} · {m.footer.notAffiliated} · <a href="/privacy/">{m.footer.privacy}</a> ·{" "}
          <a href="/terms/">{m.footer.terms}</a>
        </span>
        <span>{m.dash.footRight}</span>
      </footer>
    </div>
  );
}
