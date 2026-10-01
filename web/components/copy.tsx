import type { useTranslations } from "next-intl";

/** What to tell someone whose sign-in stopped, by why it stopped, in their language: `t` is the "errors" translator. */
export function errorCopy(kind: string | null | undefined, t: ReturnType<typeof useTranslations<"errors">>) {
  const key = kind && t.has(`${kind}.headline` as never) ? kind : "unknown";
  // every kind has the same three parts; the key is only known at run time, so any one kind stands for its type
  const at = (part: string) => `${key}.${part}` as "expired.headline";
  return {
    headline: t.rich(at("headline"), { em: (c) => <em>{c}</em> }),
    detail: t(at("detail")),
    hint: t(at("hint")),
  };
}
