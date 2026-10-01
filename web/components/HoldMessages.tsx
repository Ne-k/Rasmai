"use client";

import { useLocale, useMessages } from "next-intl";
import { holdMessages } from "@/lib/i18n/active";

/** Keeps the page's words where plain functions (dates, API errors) can reach them, as they cannot use a hook. */
export function HoldMessages() {
  holdMessages(useLocale(), useMessages());
  return null;
}
