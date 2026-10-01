import { INTL_TAG, isLocale, type Locale } from "./index";
import { messages, type Messages } from "./messages";

/**
 * The page's language, for plain helper functions that cannot use a hook: dates, error messages.
 * It is read from `<html lang>`, which the server sets from the same choice the hooks see. These run
 * in the browser once data has arrived; on the server they answer in English.
 */
export function activeLocale(): Locale {
  if (typeof document === "undefined") return "en";
  const lang = document.documentElement.lang;
  return isLocale(lang) ? lang : "en";
}

export function activeMessages(): Messages {
  return messages[activeLocale()];
}

export function activeTag(): string {
  return INTL_TAG[activeLocale()];
}
