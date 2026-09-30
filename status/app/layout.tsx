import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { THEME_BOOT } from "@/components/Theme";

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

export const metadata: Metadata = {
  title: "Status · Rasmai",
  description: "Whether Rasmai, the maimai DX Discord bot, is up right now, and how it has done over the last 90 days.",
};

export const viewport: Viewport = {
  colorScheme: "light",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <meta httpEquiv="refresh" content="60" />
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
