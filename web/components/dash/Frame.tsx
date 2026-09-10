"use client";

import { Ring } from "@/components/Ring";
import { MastheadNav } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ServersNotice } from "@/components/Servers";
import { type Overview } from "./api";

export function Frame({ children, user, onSignOut }: { children: React.ReactNode; user?: Overview["user"]; onSignOut?: () => void }) {
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
              sign out
            </button>
          </div>
        )}
      </header>
      <ServersNotice />
      {children}
      <footer className="foot">
        <span>
          Created by <b>nek_ng</b> · not affiliated with SEGA · <a href="/privacy/">privacy</a> ·{" "}
          <a href="/terms/">terms</a>
        </span>
        <span>scores are read from maimai DX NET when you run a command or refresh here</span>
      </footer>
    </div>
  );
}
