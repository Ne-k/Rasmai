import { INTL_TAG, isLocale, type Locale } from "./index";
import { createTranslator, type AbstractIntlMessages, type NamespaceKeys, type NestedKeyOf } from "next-intl";
import type en from "@/messages/en.json";

/**
 * The page's language, for plain helper functions that cannot use a hook: dates, error messages.
 * It is read from `<html lang>`, which the server sets from the same choice the hooks see. These run
 * in the browser once data has arrived; on the server they answer in English.
 */
function activeLocale(): Locale {
  if (typeof document === "undefined") return "en";
  const lang = document.documentElement.lang;
  return isLocale(lang) ? lang : "en";
}

export function activeTag(): string {
  return INTL_TAG[activeLocale()];
}

let held: { locale: Locale; messages: AbstractIntlMessages } | null = null;

/** Called by HoldMessages in the browser. The server never holds any: a module-level value there would be shared between readers. */
export function holdMessages(locale: string, words: AbstractIntlMessages) {
  if (typeof window !== "undefined" && isLocale(locale)) held = { locale, messages: words };
}

type Words = typeof en;

/** A translator for plain functions that cannot use a hook, in the language the page is in; `activeT("dash.api")` is `useTranslations("dash.api")`. */
export function activeT<N extends NamespaceKeys<Words, NestedKeyOf<Words>>>(namespace: N) {
  return createTranslator({ locale: held?.locale ?? "en", messages: (held?.messages ?? {}) as unknown as Words, namespace });
}
