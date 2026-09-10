import { Ring } from "./Ring";
import { ThemeToggle } from "./Theme";
import { ServersNotice } from "./Servers";

const STEPS = ["Get your link", "Sign in", "Connect"];

const NAV: [string, string][] = [
  ["home", "/"],
  ["link", "/link/"],
  ["dashboard", "/me/"],
  ["invite", "/invite"],
];

export function MastheadNav({ current }: { current: string }) {
  return (
    <nav className="masthead-nav">
      {NAV.map(([label, href]) =>
        label === current ? (
          <span key={label} className="tag">
            {label}
          </span>
        ) : (
          <a key={label} className="tag" href={href}>
            {label}
          </a>
        ),
      )}
    </nav>
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
            {STEPS.map((label, i) => {
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
          Created by <b>nek_ng</b> ·{" "}
          {footLeft}
          {footLeft ? " · " : ""}
          <a href="/privacy/">privacy</a> · <a href="/terms/">terms</a> · <a href="/invite">invite the bot</a>
        </span>
        <span>{footRight}</span>
      </footer>
    </div>
  );
}
