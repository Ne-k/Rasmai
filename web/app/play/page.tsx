import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Play } from "@/components/play/Play";
import "./play.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("play");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/play/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/play/", images: ["/opengraph-image"] },
  };
}

export default function PlayPage() {
  return <Play />;
}
