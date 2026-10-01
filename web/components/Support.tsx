import { useTranslations } from "next-intl";

/** Where to go when something here has gone wrong: the support server, through the site's own /support link. */
export function Support({ inline = false }: { inline?: boolean }) {
  const t = useTranslations("support");
  const text = t.rich("stuck", { link: (c) => <a href="/support" target="_blank" rel="noopener noreferrer">{c}</a> });
  return inline ? <span>{text}</span> : <p className="hint">{text}</p>;
}
