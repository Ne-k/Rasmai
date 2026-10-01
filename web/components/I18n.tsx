"use client";

import { createContext, useContext } from "react";
import { LANG_COOKIE, type Locale } from "@/lib/i18n";
import { messages, type Messages } from "@/lib/i18n/messages";

const LocaleContext = createContext<Locale>("en");

/** Hands the reader's language, decided on the server, to every client component under it. */
export function LocaleProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

/** The words for the reader's language, in a client component. */
export function useM(): Messages {
  return messages[useContext(LocaleContext)];
}

/** The language switch in the top bar: it names the other language, saves the choice for a year and reloads. */
export function LangToggle() {
  const locale = useLocale();
  const m = useM();
  const next: Locale = locale === "ja" ? "en" : "ja";
  return (
    <button
      type="button"
      className="lang-toggle"
      lang={next}
      aria-label={m.common.switchLanguage}
      title={m.common.switchLanguage}
      onClick={() => {
        document.cookie = `${LANG_COOKIE}=${next}; Path=/; Max-Age=31536000; SameSite=Lax`;
        window.location.reload();
      }}
    >
      {next === "ja" ? "日本語" : "EN"}
    </button>
  );
}
