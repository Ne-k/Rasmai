import type { Locale } from "./index";
import { en, type Messages } from "./en";
import { ja } from "./ja";

export type { Messages };

// the central translation files: lib/i18n/en.tsx and lib/i18n/ja.tsx
export const messages: Record<Locale, Messages> = { en, ja };
