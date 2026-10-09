import { env } from "@/lib/env";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { RelinkNotice } from "@/components/RelinkNotice";
import { SiteNotice } from "@/components/SiteNotice";
import { Pwa } from "@/components/Pwa";
import { THEME_BOOT } from "@/components/Theme";
import { LocaleProvider, SignedInProvider } from "@/components/I18n";
import { Intl } from "@/components/Intl";
import { hasSession } from "@/lib/session";
import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";
import { getLocale } from "@/lib/i18n/server";

const display = localFont({
  src: [
    { path: "./fonts/ZenMaruGothic-700.woff2", weight: "700" },
    { path: "./fonts/ZenMaruGothic-900.woff2", weight: "900" },
  ],
  variable: "--font-display",
  display: "swap",
});
const body = localFont({
  src: [
    { path: "./fonts/ZenKakuGothicNew-400.woff2", weight: "400" },
    { path: "./fonts/ZenKakuGothicNew-500.woff2", weight: "500" },
    { path: "./fonts/ZenKakuGothicNew-700.woff2", weight: "700" },
  ],
  variable: "--font-body",
  display: "swap",
});
const mono = localFont({
  src: [
    { path: "./fonts/JetBrainsMono-500.woff2", weight: "500" },
    { path: "./fonts/JetBrainsMono-700.woff2", weight: "700" },
  ],
  variable: "--font-mono",
  display: "swap",
});

const SITE = env.publicUrl();

// The bundled fonts are Latin subsets, so Japanese text falls through to the system's own Japanese fonts:
// rounded for headings where there is one, the usual gothic for text.
const JA_DISPLAY = '"Hiragino Maru Gothic ProN", "Hiragino Sans", "Yu Gothic UI", "Yu Gothic", Meiryo, "Noto Sans JP"';
const JA_BODY = '"Hiragino Kaku Gothic ProN", "Hiragino Sans", "Yu Gothic UI", "Yu Gothic", Meiryo, "Noto Sans JP"';

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getTranslations("meta");
  const TAGLINE = t("tagline");
  return {
    // every page's canonical is resolved against this, so one address is the address
    metadataBase: new URL(SITE),
    title: { default: t("title"), template: "%s · Rasmai" },
    description: TAGLINE,
    alternates: { canonical: "/" },
    keywords: ["maimai", "maimai DX", "rating", "best 50", "Discord bot", "chart constant", "rhythm game"],
    openGraph: {
      type: "website",
      siteName: "Rasmai",
      url: SITE,
      title: t("title"),
      description: TAGLINE,
      locale: locale === "ja" ? "ja_JP" : "en",
    },
    twitter: { card: "summary_large_image", title: t("title"), description: TAGLINE },
    applicationName: "Rasmai",
    manifest: "/manifest.webmanifest",
    appleWebApp: { capable: true, title: "Rasmai", statusBarStyle: "default" },
    icons: { icon: "/favicon.ico", apple: "/app/apple-touch-icon.png" },
    formatDetection: { telephone: false },
    // Next writes the standard mobile-web-app-capable tag; older iOS only reads Apple's own
    other: { "apple-mobile-web-app-capable": "yes" },
  };
}

export const viewport: Viewport = {
  colorScheme: "light",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  // the theme-color meta is written by the theme boot script, so it follows the reader's switch rather than the device
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const signedIn = hasSession(await cookies());
  const fonts =
    locale === "ja"
      ? ({ "--font-display": `${display.style.fontFamily}, ${JA_DISPLAY}`, "--font-body": `${body.style.fontFamily}, ${JA_BODY}` } as React.CSSProperties)
      : undefined;
  return (
    <html lang={locale} className={`${display.variable} ${body.variable} ${mono.variable}`} style={fonts} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body suppressHydrationWarning>
        <Intl>
          <LocaleProvider locale={locale}>
            <SignedInProvider signedIn={signedIn}>
              <SiteNotice />
              <RelinkNotice />
              {children}
              <Pwa />
            </SignedInProvider>
          </LocaleProvider>
        </Intl>
      </body>
    </html>
  );
}
