import { Children, Fragment, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { Ring } from "./Ring";
import { MastheadNav } from "./Shell";
import { ThemeToggle } from "./Theme";
import type { Locale } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n/server";
import { getTranslations } from "next-intl/server";
import { TRANSLATE_URL } from "./Contact";

export { CONTACT_DISCORD, CONTACT_EMAIL, SITE_URL } from "./Contact";

// written once, shown the way each language writes a date
export const EFFECTIVE_DATE = "2026-10-02";

export function effectiveDate(locale: Locale): string {
  const [year, month, day] = EFFECTIVE_DATE.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return locale === "ja"
    ? `${year}年${month}月${day}日`
    : date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

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

// past this many characters a paragraph across a whole row runs too long, so it is set in two columns.
// Japanese carries about twice as much in a character, so its bar is half as many.
const SPLIT_PARAGRAPH: Record<Locale, number> = { en: 480, ja: 240 };

/** The children with fragments opened up, so a page body written as one fragment per language still splits by heading. */
function flat(children: ReactNode): ReactNode[] {
  return Children.toArray(children).flatMap((child) =>
    isValidElement<{ children?: ReactNode }>(child) && child.type === Fragment ? flat(child.props.children) : [child],
  );
}

/**
 * The page's flat run of headings, paragraphs and lists, cut into one section per heading so the
 * sections can sit side by side as panels across the whole width, the way the dashboard's do. A
 * section with a long list takes the full width and sets the list in two columns; two short sections
 * in a row share a row; a short section with no short neighbour takes the full width on its own.
 */
function toSections(children: ReactNode, locale: Locale): Section[] {
  const sections: Section[] = [];
  for (const child of flat(children)) {
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
      isTag(node, "p") && textOf(node).length > SPLIT_PARAGRAPH[locale]
        ? cloneElement(node, { className: [node.props.className, "doc-split"].filter(Boolean).join(" ") })
        : node,
    );
  }
  return sections;
}

export async function Doc({ tag, title, intro, dated = true, children }: DocProps) {
  const locale = await getLocale();
  const doc = await getTranslations("doc");
  const footer = await getTranslations("footer");
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
        {dated ? <p className="doc-date">{doc("effective", { date: effectiveDate(locale) })}</p> : null}
        <div className="doc-grid">
          {toSections(children, locale).map((section, i) => (
            <section key={i} className={`doc-section ${section.size}`}>
              {section.heading}
              {section.body}
            </section>
          ))}
        </div>
      </main>
      <footer className="foot">
        <span>
          {footer.rich("createdBy", { b: (c) => <b>{c}</b> })} · {footer("notAffiliated")}
        </span>
        <span>
          <a href="/privacy/">{footer("privacy")}</a> · <a href="/terms/">{footer("terms")}</a> · <a href="/support">{footer("support")}</a> · <a href={TRANSLATE_URL} target="_blank" rel="noopener noreferrer">{footer("translate")}</a>
        </span>
      </footer>
    </div>
  );
}
