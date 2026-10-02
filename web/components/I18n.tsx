"use client";

import { createContext, useContext } from "react";
import { useTranslations } from "next-intl";
import { LANG_COOKIE, type Locale } from "@/lib/i18n";

const LocaleContext = createContext<Locale>("en");
const SignedInContext = createContext(false);

/** Hands the reader's language, decided on the server, to every client component under it. */
export function LocaleProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

/** Hands the server's reading of the session cookie to the top bar, so it is right on the first paint. */
export function SignedInProvider({ signedIn, children }: { signedIn: boolean; children: React.ReactNode }) {
  return <SignedInContext.Provider value={signedIn}>{children}</SignedInContext.Provider>;
}

export function useSignedIn(): boolean {
  return useContext(SignedInContext);
}

/** The language switch in the top bar: it names the other language, saves the choice for a year and reloads. */
export function LangToggle() {
  const locale = useLocale();
  const t = useTranslations("common");
  const next: Locale = locale === "ja" ? "en" : "ja";
  return (
    <button
      type="button"
      className="lang-toggle"
      lang={next}
      aria-label={t("switchLanguage")}
      title={t("switchLanguage")}
      onClick={() => {
        document.cookie = `${LANG_COOKIE}=${next}; Path=/; Max-Age=31536000; SameSite=Lax`;
        window.location.reload();
      }}
    >
      {next === "ja" ? "日本語" : "EN"}
    </button>
  );
}
