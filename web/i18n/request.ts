import { getRequestConfig } from "next-intl/server";
import { getLocale } from "@/lib/i18n/server";

// the language is the reader's saved choice or their browser's, not part of the address
export default getRequestConfig(async () => {
  const locale = await getLocale();
  return { locale, messages: (await import(`../messages/${locale}.json`)).default };
});
