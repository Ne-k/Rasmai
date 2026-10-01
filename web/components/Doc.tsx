import { Children, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
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
export const EFFECTIVE_DATE = "30 September 2026";

type DocProps = { tag: string; title: React.ReactNode; intro: string; dated?: boolean; children: React.ReactNode };

type Section = { heading: ReactNode | null; body: ReactNode[]; size: "half" | "wide" | "solo" };

function isTag(node: ReactNode, tag: string): node is ReactElement<{ children?: ReactNode; className?: string }> {
  return isValidElement(node) && node.type === tag;
}

/** The words in a piece of the page, to tell a long paragraph from a short one. */
function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

// past this many characters a paragraph across a whole row runs too long, so it is set in two columns
const SPLIT_PARAGRAPH = 480;

/**
 * The page's flat run of headings, paragraphs and lists, cut into one section per heading so the
 * sections can sit side by side as panels across the whole width, the way the dashboard's do. A
 * section with a long list takes the full width and sets the list in two columns; two short sections
 * in a row share a row; a short section with no short neighbour takes the full width on its own.
 */
function toSections(children: ReactNode): Section[] {
  const sections: Section[] = [];
  for (const child of Children.toArray(children)) {
    if (isTag(child, "h2")) sections.push({ heading: child, body: [], size: "half" });
    else {
      if (!sections.length) sections.push({ heading: null, body: [], size: "wide" });
      sections[sections.length - 1].body.push(child);
    }
  }
  for (const section of sections) {
    const long = section.body.some(
      (node) =>
        (isValidElement<{ className?: string }>(node) && String(node.props.className ?? "").includes("cmds")) ||
        (isTag(node, "ul") && Children.count(node.props.children) >= 4),
    );
    if (long || section.body.length > 3) section.size = "wide";
  }
  // a short section only sits at half width beside another short one, so no half-row is left empty
  for (let i = 0; i < sections.length; i++) {
    if (sections[i].size !== "half") continue;
    if (sections[i + 1]?.size === "half") i++;
    else sections[i].size = "solo";
  }
  // across a whole row, a long paragraph is set in two columns; a short one just runs across
  for (const section of sections) {
    if (section.size === "half") continue;
    section.body = section.body.map((node) =>
      isTag(node, "p") && textOf(node).length > SPLIT_PARAGRAPH
        ? cloneElement(node, { className: [node.props.className, "doc-split"].filter(Boolean).join(" ") })
        : node,
    );
  }
  return sections;
}

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
        <div className="doc-grid">
          {toSections(children).map((section, i) => (
            <section key={i} className={`doc-section ${section.size}`}>
              {section.heading}
              {section.body}
            </section>
          ))}
        </div>
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
