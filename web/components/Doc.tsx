import { Ring } from "./Ring";
import { MastheadNav } from "./Shell";
import { ThemeToggle } from "./Theme";

export const SITE_URL = "https://rasmai.lol";
export const CONTACT_EMAIL = "cardin@nguyen.ink";
export const CONTACT_DISCORD = "nek_ng";

export function Contact() {
  return (
    <>
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>, or <b>{CONTACT_DISCORD}</b> on Discord
    </>
  );
}
export const EFFECTIVE_DATE = "5 September 2026";

type DocProps = { tag: string; title: React.ReactNode; intro: string; dated?: boolean; children: React.ReactNode };

export function Doc({ tag, title, intro, dated = true, children }: DocProps) {
  return (
    <div className="frame">
      <header className="masthead">
        <Ring lit={0} size={34} />
        <div className="wordmark">
          <a href="/" style={{ color: "inherit", textDecoration: "none" }}>
            Ras<span>mai</span>
          </a>
        </div>
        <MastheadNav current={tag} />
        <ThemeToggle />
      </header>
      <main className="doc">
        <h1>{title}</h1>
        <p className="lede">{intro}</p>
        {dated ? <p className="doc-date">Effective {EFFECTIVE_DATE}</p> : null}
        {children}
      </main>
      <footer className="foot">
        <span>
          Created by <b>nek_ng</b> · not affiliated with SEGA
        </span>
        <span>
          <a href="/privacy/">privacy</a> · <a href="/terms/">terms</a>
        </span>
      </footer>
    </div>
  );
}
