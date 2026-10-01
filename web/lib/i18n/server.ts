import { cookies, headers } from "next/headers";
import { LANG_COOKIE, pickLocale, type Locale } from "./index";

/** The reader's language on the server, from their saved choice or their browser. */
export async function getLocale(): Promise<Locale> {
  const saved = (await cookies()).get(LANG_COOKIE)?.value;
  const accept = (await headers()).get("accept-language");
  return pickLocale(saved, accept);
}
