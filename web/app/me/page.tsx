import type { Metadata } from "next";
import { Dash } from "@/components/dash/Dash";
import { getI18n } from "@/lib/i18n/server";
import "./dashboard.css";

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return {
    // somebody's own scores: never a search result
    robots: { index: false, follow: false },
    title: m.dash.metaTitle,
    description: m.dash.metaDescription,
  };
}

export default function MePage() {
  return <Dash />;
}
