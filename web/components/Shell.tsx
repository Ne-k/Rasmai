"use client";

import { Ring } from "./Ring";
import { ThemeToggle } from "./Theme";
import { ServersNotice } from "./Servers";
import { LangToggle, useM } from "./I18n";

// the keys are what a page passes as `current`; the words come from the reader's language
const NAV = [
  ["home", "/"],
  ["link", "/link/"],
  ["commands", "/commands/"],
  ["dashboard", "/me/"],
  ["invite", "/invite"],
] as const;

// The language switch is a sibling of the nav, not one of its links: on a phone the nav takes a row
// of its own, and the switch stays up in the top row beside the theme switch.
export function MastheadNav({ current }: { current: string }) {
  const m = useM();
  return (
    <>
      <nav className="masthead-nav">
        {NAV.map(([key, href]) =>
          key === current ? (
            <span key={key} className="tag">
              {m.nav[key]}
            </span>
          ) : (
            <a key={key} className="tag" href={href}>
              {m.nav[key]}
            </a>
          ),
        )}
      </nav>
      <LangToggle />
    </>
  );
}

type ShellProps = {
  tag: string;
  lit: number;
  done?: boolean;
  footLeft?: string;
  footRight?: string;
  children: React.ReactNode;
};

export function Shell({ tag, lit, done = false, footLeft = "", footRight = "", children }: ShellProps) {
  const m = useM();
  return (
    <div className="frame">
      <header className="masthead">
        <Ring lit={lit} size={34} done={done} />
        <div className="wordmark">
          Ras<span>mai</span>
        </div>
        <MastheadNav current={tag === "link" || tag.startsWith("step") || tag === "done" || tag === "error" ? "link" : tag} />
        <ThemeToggle />
      </header>
      <ServersNotice />
      <div className="stage">
        <aside className="rail">
          <Ring lit={lit} size={200} done={done} />
          <ol className="rail-steps">
            {m.shell.steps.map((label, i) => {
              const n = i + 1;
              const cls = done || n < lit ? "did" : n === lit ? "on" : "";
              return (
                <li key={label} className={cls}>
                  <b>0{n}</b>
                  {label}
                </li>
              );
            })}
          </ol>
        </aside>
        <main>{children}</main>
      </div>
      <footer className="foot">
        <span>
          {m.footer.createdBy} ·{" "}
          {footLeft}
          {footLeft ? " · " : ""}
          <a href="/privacy/">{m.footer.privacy}</a> · <a href="/terms/">{m.footer.terms}</a> · <a href="/invite">{m.footer.invite}</a>
        </span>
        <span>{footRight}</span>
      </footer>
    </div>
  );
}
