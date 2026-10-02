import { getTranslations } from "next-intl/server";
import { Cmd } from "./Cmd";
import { CONTACT_DISCORD, CONTACT_EMAIL, SITE_URL } from "./Contact";
import { Term } from "./Term";

// each page is an ordered list of sections, each an ordered list of blocks: pNN a paragraph,
// uNN a bullet list, cNN a command list. The words live in messages/*.json under docs.<page>.<section>.
const PAGES = {
  commands: {
    start: ["c01"],
    play: ["p01", "c01"],
    scores: ["c01"],
    how: ["c01"],
    share: ["c01"],
    data: ["c01"],
    website: ["p01", "u01", "p02"],
    good: ["u01"],
  },
  privacy: {
    about: ["p01"],
    stored: ["p01", "u01", "p02"],
    profile: ["p01"],
    website: ["u01"],
    notStored: ["u01"],
    whoElse: ["u01"],
    kept: ["p01", "u01", "p02"],
    security: ["u01"],
    age: ["p01"],
    changes: ["p01"],
  },
  terms: {
    about: ["p01"],
    what: ["p01", "p02"],
    account: ["u01"],
    share: ["u01"],
    fairUse: ["u01"],
    noGuarantees: ["u01"],
    stopping: ["p01"],
    changes: ["p01"],
  },
} as const;

const TERMS = [
  "rating", "odds", "constant", "trait", "newpool", "oldpool", "judgement",
  "dxscore", "curve", "confirmed", "mainotes", "notation", "region", "sss",
] as const;

/** The body of a document page as a flat run of h2 / p / ul / div.cmds, which Doc cuts into sections. */
export async function docBody(page: keyof typeof PAGES) {
  const t = await getTranslations("docs");
  const has = (key: string) => t.has(key as never);
  const raw = (key: string) => t.raw(key as never) as Record<string, unknown>;
  const ids = (key: string) => Object.keys(raw(key)).sort();

  const contact = t.rich("contact", {
    mail: (c) => <a href={`mailto:${CONTACT_EMAIL}`}>{c}</a>,
    b: (c) => <b>{c}</b>,
    email: CONTACT_EMAIL,
    discord: CONTACT_DISCORD,
  });
  const tags = {
    code: (c: React.ReactNode) => <code>{c}</code>,
    b: (c: React.ReactNode) => <b>{c}</b>,
    me: (c: React.ReactNode) => <a href="/me/">{c}</a>,
    privacy: (c: React.ReactNode) => <a href="/privacy/">{c}</a>,
    cloudflare: (c: React.ReactNode) => <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener noreferrer">{c}</a>,
    discord: (c: React.ReactNode) => <a href="https://discord.com/privacy" rel="noopener noreferrer">{c}</a>,
    google: (c: React.ReactNode) => <a href="https://policies.google.com/privacy" rel="noopener noreferrer">{c}</a>,
    ...Object.fromEntries(TERMS.map((term) => [term, (c: React.ReactNode) => <Term word={c} means={t(`glossary.${term}`)} />])),
  };
  const values = { ...tags, contact, site: SITE_URL.replace("https://", "") };
  // the keys are built from the page structure above, so they cannot be checked against the message types
  const rich = (key: string) => (t.rich as unknown as (key: string, values: object) => React.ReactNode)(key, values);

  return Object.entries(PAGES[page]).flatMap(([id, blocks]) => {
    const section = `${page}.${id}`;
    if (!has(`${section}.title`)) return [];
    return [
      <h2 key={id}>{t(`${section}.title` as never)}</h2>,
      ...(blocks as readonly string[]).map((block) => {
        const key = `${section}.${block}`;
        if (block.startsWith("p")) return <p key={key}>{rich(key)}</p>;
        if (block.startsWith("u")) return <ul key={key}>{ids(key).map((i) => <li key={i}>{rich(`${key}.${i}`)}</li>)}</ul>;
        return (
          <div key={key} className="cmds">
            {ids(key).map((c) => (
              <Cmd key={c} name={t(`${key}.${c}.name` as never)} args={has(`${key}.${c}.args`) ? t(`${key}.${c}.args` as never) : undefined}>
                {rich(`${key}.${c}.what`)}
              </Cmd>
            ))}
          </div>
        );
      }),
    ];
  });
}
