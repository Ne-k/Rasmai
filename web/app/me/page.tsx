import type { Metadata } from "next";
import { Dash } from "@/components/dash/Dash";
import { getTranslations } from "next-intl/server";
import "./dashboard.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("dash");
  return {
    // somebody's own scores: never a search result
    robots: { index: false, follow: false },
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default function MePage() {
  return <Dash />;
}
