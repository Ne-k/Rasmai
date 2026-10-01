export type Locale = "en" | "ja";

// the reader's choice from the switch in the top bar; without it the browser's own languages decide
export const LANG_COOKIE = "rasmai-lang";

export function isLocale(value: unknown): value is Locale {
  return value === "en" || value === "ja";
}

/** The language to show: the saved choice, else the first language the browser asks for that the site has, else English. */
export function pickLocale(saved?: string | null, acceptLanguage?: string | null): Locale {
  if (isLocale(saved)) return saved;
  const asked = (acceptLanguage ?? "")
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().toLowerCase().split(";");
      const q = Number(params.find((p) => p.trim().startsWith("q="))?.split("=")[1] ?? 1);
      return { tag, q: Number.isFinite(q) ? q : 0 };
    })
    .filter((entry) => entry.tag && entry.q > 0)
    .sort((a, b) => b.q - a.q);
  for (const { tag } of asked) {
    if (tag.startsWith("ja")) return "ja";
    if (tag.startsWith("en")) return "en";
  }
  return "en";
}

/** Numbers and dates the way the reader's language writes them. */
export const INTL_TAG: Record<Locale, string> = { en: "en", ja: "ja-JP" };
