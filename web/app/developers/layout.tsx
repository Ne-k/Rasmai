import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { getTranslations } from "next-intl/server";
import { LangToggle } from "@/components/I18n";
import { ThemeToggle } from "@/components/Theme";
import { env } from "@/lib/env";
import { hasSession } from "@/lib/session";
import { SignOut } from "./shared";
import "./developers.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("developers");
  return {
    // a developer's own applications: never a search result
    robots: { index: false, follow: false },
    title: t("metaTitle"),
    description: t("metaDescription"),
    // the site's layout gives every page the site's own front page as its address and its card: neither is the portal's
    alternates: {},
    openGraph: { type: "website", siteName: "Rasmai", title: t("home.title"), description: t("home.metaDescription") },
    // no picture: the site's card art is the bot's
    twitter: { card: "summary", title: t("home.title"), description: t("home.metaDescription") },
  };
}

export default async function DevelopersLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("developers");
  // on the portal's own host its pages sit at the root (next.config.ts)
  const ownHost = ((await headers()).get("host") ?? "").startsWith("developers.");
  const signedIn = hasSession(await cookies());
  return (
    <div className="dp">
      <header className="dp-bar">
        <a className="wordmark" href={`${env.publicUrl()}/`}>
          Ras<span>mai</span>
        </a>
        <a className="dp-here" href={ownHost ? "/" : "/developers/"}>{t("portal")}</a>
        <nav className="dp-nav" aria-label={t("portal")}>
          <a href={ownHost ? "/applications/" : "/developers/applications/"}>{t("navApplications")}</a>
          <a href={ownHost ? "/docs/" : "/developers/docs/"}>{t("navDocs")}</a>
        </nav>
        <div className="dp-tools">
          {signedIn && <SignOut />}
          <LangToggle />
          <ThemeToggle />
        </div>
      </header>
      {children}
    </div>
  );
}
