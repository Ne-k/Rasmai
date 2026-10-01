import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { HoldMessages } from "./HoldMessages";

/** next-intl's provider, handing the client everything but `docs`, which only server components render. */
export async function Intl({ children }: { children: React.ReactNode }) {
  const { docs: _docs, ...messages } = (await getMessages()) as Record<string, unknown>;
  return (
    <NextIntlClientProvider messages={messages}>
      <HoldMessages />
      {children}
    </NextIntlClientProvider>
  );
}
