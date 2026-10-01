import type { ErrorCopy } from "@/lib/i18n/en";
import type { Messages } from "@/lib/i18n/messages";

/** What to tell someone whose sign-in stopped, by why it stopped, in their language. */
export function errorCopy(kind: string | null | undefined, m: Messages): ErrorCopy {
  return m.errors[kind ?? ""] ?? m.errors.unknown;
}
