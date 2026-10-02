"use client";

import { Ring } from "./Ring";
import { ThemeToggle } from "./Theme";
import { ServersNotice } from "./Servers";
import { useTranslations } from "next-intl";
import { LangToggle, useSignedIn } from "./I18n";
import { TRANSLATE_URL } from "./Contact";

// the keys are what a page passes as `current`; the words come from the reader's language
const NAV = [
  ["home", "/"],
  ["link", "/link/"],
  ["commands", "/commands/"],
  ["dashboard", "/me/"],
  ["invite", "/invite"],
  ["support", "/support"],
] as const;

// these leave for another site, so they open in a tab of their own
const EXTERNAL = new Set(["support"]);

/** The way in for someone who is not signed in: the dashboard page offers Discord and Google, and a first sign-in there makes the account. */
function SignInButton() {
  const t = useTranslations("nav");
  if (useSignedIn()) return null;
  return (
    <a className="signin-pill" href="/me/" title={t("signInTitle")}>
      {t("signIn")}
    </a>
  );
}

// The language switch is a sibling of the nav, not one of its links: on a phone the nav takes a row
// of its own, and the switch stays up in the top row beside the theme switch.
export function MastheadNav({ current }: { current: string }) {
  const t = useTranslations("nav");
  const signedIn = useSignedIn();
  return (
    <>
      <nav className="masthead-nav">
        {NAV.filter(([key]) => signedIn || key !== "dashboard").map(([key, href]) =>
          key === current ? (
            <span key={key} className="tag">
              {t(key)}
            </span>
          ) : (
            <a key={key} className="tag" href={href} {...(EXTERNAL.has(key) ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
              {t(key)}
            </a>
          ),
        )}
      </nav>
      <SignInButton />
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

const STEPS = ["link", "signIn", "connect"] as const;

export function Shell({ tag, lit, done = false, footLeft = "", footRight = "", children }: ShellProps) {
  const steps = useTranslations("shell.steps");
  const footer = useTranslations("footer");
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
            {STEPS.map((step, i) => {
              const n = i + 1;
              const label = steps(step);
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
          {footer.rich("createdBy", { b: (c) => <b>{c}</b> })} ·{" "}
          {footLeft}
          {footLeft ? " · " : ""}
          <a href="/privacy/">{footer("privacy")}</a> · <a href="/terms/">{footer("terms")}</a> · <a href="/invite">{footer("invite")}</a> · <a href="/support">{footer("support")}</a> · <a href={TRANSLATE_URL} target="_blank" rel="noopener noreferrer">{footer("translate")}</a>
        </span>
        <span>{footRight}</span>
      </footer>
    </div>
  );
}
